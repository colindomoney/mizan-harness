import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from mizan.bank import Domain, PromptRecord
from mizan.gateway import RunParams
from mizan.records import RunRecord
from mizan.viewer import build_viewer, order_prompts, render_html

MODELS = [
    {"id": "openai/gpt-x", "provider": "openai", "display_name": "GPT-X"},
    {"id": "anthropic/claude-y", "provider": "anthropic", "display_name": "Claude Y"},
]


def _prompt(pid: str, domain: Domain, pair_id: str | None = None) -> PromptRecord:
    return PromptRecord(id=pid, domain=domain, query=f"query {pid}", pair_id=pair_id)


def _record(pid: str, model: str, *, text: str | None = "hello", error: str | None = None):
    return RunRecord(
        prompt_id=pid,
        query=f"query {pid}",
        model=model,
        provider=model.split("/")[0],
        params=RunParams(),
        timestamp=datetime.now(UTC),
        response_text=text if error is None else None,
        tokens_out=None if error else 5,
        latency_ms=None if error else 100,
        error=error,
        refusal_flag=None if error else "answered",
    )


def test_order_prompts_groups_domains_and_adjoins_pairs():
    prompts = [
        _prompt("a1", Domain.CASUALTIES),
        _prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        _prompt("c1", Domain.CASUALTIES),
        _prompt("d1", Domain.FRAMING_SYMMETRY),
        _prompt("e1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
    ]
    ordered = [p.id for p in order_prompts(prompts)]

    b, e = ordered.index("b1"), ordered.index("e1")
    assert abs(b - e) == 1  # pair members adjacent
    # domains contiguous
    domains = [p.domain for p in order_prompts(prompts)]
    assert domains == sorted(domains, key=domains.index)


def test_render_shows_flags_missing_cells_and_errors():
    prompts = [_prompt("a1", Domain.HISTORY)]
    cells = {
        ("a1", "openai/gpt-x"): _record("a1", "openai/gpt-x"),
        # no record for claude-y: missing cell
    }
    manifest = {"started_at": "t0", "bank_sha256": "f" * 64, "total_cells": 2}
    out = render_html(prompts, MODELS, cells, manifest)

    assert "GPT-X" in out and "Claude Y" in out
    assert "flag-answered" in out
    assert 'class="missing"' in out


def test_render_error_cell_and_hash_warning():
    prompts = [_prompt("a1", Domain.HISTORY)]
    cells = {("a1", "openai/gpt-x"): _record("a1", "openai/gpt-x", error="boom 503")}
    manifest = {"started_at": "t0", "bank_sha256": "f" * 64, "total_cells": 2}
    out = render_html(prompts, MODELS, cells, manifest, bank_hash_matches=False)

    assert "flag-error" in out and "boom 503" in out
    assert "bank snapshot ≠ manifest hash" in out


def test_build_viewer_end_to_end(tmp_path: Path):
    bank_path = tmp_path / "bank.jsonl"
    prompts = [_prompt("a1", Domain.HISTORY), _prompt("b1", Domain.TERMINOLOGY)]
    bank_path.write_text("".join(p.model_dump_json() + "\n" for p in prompts))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = {
        "bank_path": str(bank_path),
        "bank_sha256": hashlib.sha256(bank_path.read_bytes()).hexdigest(),
        "models": MODELS,
        "params": RunParams().model_dump(),
        "total_cells": 4,
        "started_at": "t0",
        "finished_at": None,
        "completed": 1,
        "errors": 0,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    rec = _record("a1", "openai/gpt-x")
    (run_dir / "records.jsonl").write_text(rec.to_json_line() + "\n")

    out = build_viewer(run_dir)

    assert out == run_dir / "viewer.html"
    html = out.read_text()
    assert "query a1" in html and "query b1" in html
    assert "bank snapshot ≠ manifest hash" not in html
