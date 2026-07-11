"""Runner: bank × registry through the gateway, captured to runs/<timestamp>/.

Layout per run:
    runs/<timestamp>/records.jsonl   one RunRecord per prompt × model cell
    runs/<timestamp>/manifest.json   pins exactly what ran (models, params,
                                     bank snapshot hash, counts, timestamps)

Records are appended and flushed per cell, and already-captured cells are
skipped on resume — an interrupted run never loses progress.
"""

import hashlib
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import openai

from mizan import gateway
from mizan.bank import PromptRecord, load_bank
from mizan.flags import flag_refusal
from mizan.gateway import GatewayError, RunParams
from mizan.records import RunRecord
from mizan.registry import DEFAULT_REGISTRY_PATH, ModelEntry, load_registry

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0


def bank_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_run_dir(base: Path = Path("runs")) -> Path:
    run_dir = base / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    return run_dir


def capture_one(
    prompt: PromptRecord,
    model: ModelEntry,
    params: RunParams,
    *,
    client: openai.OpenAI,
    sleep=time.sleep,
) -> RunRecord:
    """Run one cell, retrying transient failures; failures become error records.

    Auth failures (401/403) re-raise instead — they would fail every remaining
    cell, so the run should stop rather than record a wall of errors.
    """
    last_error = "unreachable"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = gateway.run(prompt.query, model.id, params, client=client)
            record = RunRecord.from_response(
                prompt_id=prompt.id,
                query=prompt.query,
                model=model.id,
                provider=model.provider,
                params=params,
                response=response,
            )
            record.refusal_flag = flag_refusal(record.response_text)
            return record
        except GatewayError as exc:
            if exc.status_code in (401, 403):
                raise
            last_error = str(exc)
            transient = exc.status_code is None or exc.status_code in RETRYABLE_STATUSES
            if not transient or attempt == MAX_ATTEMPTS:
                break
            sleep(exc.retry_after or BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))

    return RunRecord(
        prompt_id=prompt.id,
        query=prompt.query,
        model=model.id,
        provider=model.provider,
        params=params,
        timestamp=datetime.now(UTC),
        error=last_error,
    )


def _captured_cells(records_path: Path) -> set[tuple[str, str]]:
    if not records_path.exists():
        return set()
    with records_path.open() as f:
        return {
            (rec.prompt_id, rec.model)
            for rec in (RunRecord.from_json_line(line) for line in f if line.strip())
        }


def run_matrix(
    bank_path: Path,
    params: RunParams,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    out_base: Path = Path("runs"),
    resume_dir: Path | None = None,
    client: openai.OpenAI | None = None,
    sleep=time.sleep,
    limit: int | None = None,
    on_progress: Callable[[RunRecord, int, int], None] | None = None,
) -> Path:
    """Run every bank prompt against every registry model; return the run dir.

    ``on_progress`` is called after each captured cell with
    ``(record, completed_cells, total_cells)``; skipped (already-captured) cells
    don't trigger it.
    """
    prompts = load_bank(bank_path)[:limit]
    models = load_registry(registry_path)
    client = client or gateway.make_client()

    run_dir = resume_dir or new_run_dir(out_base)
    records_path = run_dir / "records.jsonl"
    done = _captured_cells(records_path)

    manifest_path = run_dir / "manifest.json"
    started_at = (
        json.loads(manifest_path.read_text())["started_at"]
        if manifest_path.exists()
        else datetime.now(UTC).isoformat()
    )
    manifest = {
        "bank_path": str(bank_path),
        "bank_sha256": bank_sha256(bank_path),
        "models": [m.model_dump() for m in models],
        "params": params.model_dump(),
        "total_cells": len(prompts) * len(models),
        "started_at": started_at,
        "finished_at": None,
        "completed": len(done),
        "errors": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    errors = 0
    with records_path.open("a") as out:
        for prompt in prompts:
            for model in models:
                if (prompt.id, model.id) in done:
                    continue
                record = capture_one(prompt, model, params, client=client, sleep=sleep)
                out.write(record.to_json_line() + "\n")
                out.flush()
                errors += record.error is not None
                done.add((prompt.id, model.id))
                if on_progress:
                    on_progress(record, len(done), manifest["total_cells"])

    manifest["finished_at"] = datetime.now(UTC).isoformat()
    manifest["completed"] = len(done)
    manifest["errors"] = errors
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return run_dir


def _print_progress(record: RunRecord, completed: int, total: int) -> None:
    """One stderr line per captured cell: count, model, prompt, outcome."""
    if record.error:
        outcome = f"ERROR: {record.error.splitlines()[0][:80]}"
    else:
        outcome = record.refusal_flag or "ok"
        if record.latency_ms is not None:
            outcome += f" ({record.latency_ms / 1000:.1f}s)"
    width = len(str(total))
    print(
        f"[{completed:>{width}}/{total}] {record.model:<36} {record.prompt_id[:8]}  {outcome}",
        file=sys.stderr,
    )


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the prompt bank across the model registry.")
    parser.add_argument("--bank", type=Path, default=Path("prompts/bank.jsonl"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--system-prompt", default=None)
    parser.add_argument("--resume", type=Path, default=None, help="existing run dir to resume")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N prompts")
    parser.add_argument("--quiet", action="store_true", help="suppress per-cell progress output")
    args = parser.parse_args()

    params = RunParams(temperature=args.temperature, system_prompt=args.system_prompt)
    run_dir = run_matrix(
        args.bank,
        params,
        registry_path=args.registry,
        resume_dir=args.resume,
        limit=args.limit,
        on_progress=None if args.quiet else _print_progress,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    print(
        f"{run_dir}: {manifest['completed']}/{manifest['total_cells']} cells captured, "
        f"{manifest['errors']} errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
