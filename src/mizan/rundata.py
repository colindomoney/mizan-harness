"""Shared run loading: the manifest → bank → records join.

Every consumer of a ``runs/<timestamp>/`` dir (viewer, exporters) needs the
same assembly: read the manifest, load the bank snapshot it pins, verify the
snapshot hash, and index records by (prompt_id, model). Models come from the
manifest — not the live registry — so old runs load against the model set
that actually ran.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from mizan.bank import PromptRecord, load_bank
from mizan.records import RunRecord


@dataclass(frozen=True)
class RunData:
    run_dir: Path
    manifest: dict
    prompts: list[PromptRecord]  # ordered: grouped by domain, pair members adjacent
    models: list[dict]  # manifest["models"], in column order
    cells: dict[tuple[str, str], RunRecord]
    bank_hash_matches: bool

    @property
    def run_id(self) -> str:
        return self.run_dir.name


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


def effective_flag(record: RunRecord | None) -> str:
    """Presentation flag for a cell: the captured refusal flag, or why there isn't one.

    ``missing`` (cell never captured — e.g. interrupted run) and ``error`` are
    export-level presentation values, not new flags in ``mizan.flags``.
    """
    if record is None:
        return "missing"
    if record.error is not None:
        return "error"
    return record.refusal_flag or "empty"


def load_run(run_dir: Path, bank_path: Path | None = None) -> RunData:
    """Assemble a RunData from a run dir; ``bank_path`` overrides the manifest's."""
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

    return RunData(
        run_dir=run_dir,
        manifest=manifest,
        prompts=prompts,
        models=manifest["models"],
        cells=cells,
        bank_hash_matches=bank_hash_matches,
    )
