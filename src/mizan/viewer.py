"""Static results viewer: prompt × model grid rendered to a single HTML file.

Reads a ``runs/<timestamp>/`` dir (records + manifest) plus the bank snapshot
and writes ``viewer.html`` next to the records — self-contained, no server,
no external assets. Rows are prompts grouped by domain with counterfactual/
symmetry pairs adjacent; columns are models; every cell shows the refusal
flag and the full captured response.
"""

import hashlib
import html
import json
from collections import Counter
from pathlib import Path

from mizan.bank import PromptRecord, load_bank
from mizan.records import RunRecord

_FLAG_LABELS = {
    "answered": "answered",
    "refused": "REFUSED",
    "hedged": "hedged",
    "empty": "empty",
}

_CSS = """
body { font-family: -apple-system, "Segoe UI", sans-serif; margin: 1.5rem; color: #1a1a1a; }
h1 { font-size: 1.3rem; margin-bottom: 0.2rem; }
.meta { color: #555; font-size: 0.85rem; margin-bottom: 1rem; }
.meta code { background: #f2f2f2; padding: 0 0.3em; }
.warn { color: #9a3412; font-weight: 600; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th, td { border: 1px solid #ddd; padding: 0.5rem; vertical-align: top; font-size: 0.82rem; }
thead th { position: sticky; top: 0; background: #fafafa; z-index: 2; }
th.prompt-col { width: 18rem; }
tr.domain td { background: #eef2f7; font-weight: 700; font-size: 0.9rem; }
td.prompt { background: #fcfcfc; }
tr.paired td.prompt { border-left: 4px solid #7c3aed; }
.pair-tag { display: inline-block; background: #ede9fe; color: #5b21b6; border-radius: 3px;
  padding: 0 0.4em; font-size: 0.72rem; margin-bottom: 0.3rem; }
.flag { display: inline-block; border-radius: 3px; padding: 0 0.45em; font-size: 0.72rem;
  font-weight: 700; margin-bottom: 0.3rem; }
.flag-answered { background: #dcfce7; color: #166534; }
.flag-hedged { background: #fef3c7; color: #92400e; }
.flag-refused { background: #fee2e2; color: #991b1b; }
.flag-empty { background: #e5e7eb; color: #374151; }
.flag-error { background: #7f1d1d; color: #fff; }
.cell-stats { color: #888; font-size: 0.7rem; margin-left: 0.4em; }
details summary { cursor: pointer; color: #444; }
details pre { white-space: pre-wrap; margin: 0.4rem 0 0; font-family: inherit;
  max-height: 24rem; overflow-y: auto; background: #f9f9f9; padding: 0.5rem; }
td.missing { color: #bbb; text-align: center; }
"""


def order_prompts(prompts: list[PromptRecord]) -> list[PromptRecord]:
    """Order for display: grouped by domain, pair members forced adjacent."""
    by_id = {p.id: p for p in prompts}
    partner: dict[str, str] = {}
    by_pair: dict[str, list[str]] = {}
    for p in prompts:
        if p.pair_id:
            by_pair.setdefault(p.pair_id, []).append(p.id)
    for ids in by_pair.values():
        if len(ids) == 2:
            partner[ids[0]], partner[ids[1]] = ids[1], ids[0]

    ordered: list[PromptRecord] = []
    emitted: set[str] = set()
    domains = {p.domain for p in prompts}
    for domain in [d for d in type(next(iter(prompts)).domain) if d in domains]:
        for p in prompts:
            if p.domain != domain or p.id in emitted:
                continue
            ordered.append(p)
            emitted.add(p.id)
            mate = partner.get(p.id)
            if mate and mate not in emitted:
                ordered.append(by_id[mate])
                emitted.add(mate)
    return ordered


def _render_cell(record: RunRecord | None) -> str:
    if record is None:
        return '<td class="missing">—</td>'
    if record.error is not None:
        body = html.escape(record.error)
        return f'<td><span class="flag flag-error">error</span><pre>{body}</pre></td>'

    flag = record.refusal_flag or "empty"
    label = _FLAG_LABELS.get(flag, flag)
    text = record.response_text or ""
    preview = html.escape(text[:120]) + ("…" if len(text) > 120 else "")
    stats = f"{record.tokens_out} tok · {record.latency_ms} ms"
    return (
        f'<td><span class="flag flag-{flag}">{label}</span>'
        f'<span class="cell-stats">{stats}</span>'
        f"<details><summary>{preview}</summary><pre>{html.escape(text)}</pre></details></td>"
    )


def render_html(
    prompts: list[PromptRecord],
    models: list[dict],
    cells: dict[tuple[str, str], RunRecord],
    manifest: dict,
    *,
    bank_hash_matches: bool = True,
) -> str:
    flag_counts = Counter(r.refusal_flag if r.error is None else "error" for r in cells.values())
    flag_summary = " · ".join(f"{flag_counts[f]} {f}" for f in sorted(flag_counts, key=str))
    hash_warn = ""
    if not bank_hash_matches:
        hash_warn = ' · <span class="warn">bank snapshot ≠ manifest hash</span>'

    head = [
        f"<style>{_CSS}</style>",
        "<h1>Mizan run viewer</h1>",
        '<p class="meta">'
        f"started <code>{html.escape(str(manifest.get('started_at')))}</code> · "
        f"bank <code>{html.escape(str(manifest.get('bank_sha256'))[:12])}</code> · "
        f"{len(cells)}/{manifest.get('total_cells')} cells · {flag_summary}" + hash_warn + "</p>",
    ]

    cols = "".join(f"<th>{html.escape(m['display_name'])}</th>" for m in models)
    rows: list[str] = [f'<tr><th class="prompt-col">Prompt</th>{cols}</tr>']

    current_domain: str | None = None
    for p in prompts:
        if p.domain != current_domain:
            current_domain = p.domain
            rows.append(f'<tr class="domain"><td colspan="{len(models) + 1}">{p.domain}</td></tr>')
        pair_tag = ""
        if p.pair_id:
            pair_tag = f'<span class="pair-tag">⇄ {html.escape(p.pair_id)}</span><br>'
        cls = ' class="paired"' if p.pair_id else ""
        cell_html = "".join(_render_cell(cells.get((p.id, m["id"]))) for m in models)
        rows.append(
            f'<tr{cls}><td class="prompt">{pair_tag}{html.escape(p.query)}</td>{cell_html}</tr>'
        )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Mizan run viewer</title></head><body>"
        + "".join(head)
        + f"<table><thead>{rows[0]}</thead><tbody>{''.join(rows[1:])}</tbody></table>"
        + "</body></html>"
    )


def build_viewer(run_dir: Path, bank_path: Path | None = None, out: Path | None = None) -> Path:
    """Render viewer.html for a run dir; returns the output path."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    bank_path = bank_path or Path(manifest["bank_path"])
    prompts = order_prompts(load_bank(bank_path))

    bank_hash_matches = (
        hashlib.sha256(bank_path.read_bytes()).hexdigest() == manifest["bank_sha256"]
    )

    cells: dict[tuple[str, str], RunRecord] = {}
    with (run_dir / "records.jsonl").open() as f:
        for line in f:
            if line.strip():
                rec = RunRecord.from_json_line(line)
                cells[(rec.prompt_id, rec.model)] = rec

    html_text = render_html(
        prompts, manifest["models"], cells, manifest, bank_hash_matches=bank_hash_matches
    )
    out = out or run_dir / "viewer.html"
    out.write_text(html_text)
    return out


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Render a static viewer for a run dir.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--bank", type=Path, default=None, help="override bank snapshot path")
    parser.add_argument(
        "--out", type=Path, default=None, help="output path (default: <run>/viewer.html)"
    )
    args = parser.parse_args(argv)

    out = build_viewer(args.run_dir, bank_path=args.bank, out=args.out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
