"""CLI: classify a run's answers with Jev, then compare against existing labels.

Usage:
    uv run python -m mizan.criteria run runs/<timestamp> [--model jev-1.13.0]
    uv run python -m mizan.criteria validate runs/<timestamp> [--model jev-1.13.0]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from mizan.rundata import load_run

from .classifier import (
    DEFAULT_CONCURRENCY,
    DEFAULT_JEV_MODEL,
    classify_run,
    load_criteria,
    output_path,
)
from .validate import validate


def _progress(done: int, total: int, rec) -> None:
    status = "error" if rec.error else "ok"
    print(f"\r  jev: {done}/{total} ({status})", end="", file=sys.stderr, flush=True)


async def _run(run_dir: Path, model: str, concurrency: int) -> Path:
    from typesafe_sdk import AsyncTypeSafeClient

    data = load_run(run_dir)
    async with AsyncTypeSafeClient(model=model) as client:
        return await classify_run(
            data, client, jev_model=model, concurrency=concurrency, on_progress=_progress
        )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jev criteria classification of a run.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "validate"):
        p = sub.add_parser(name)
        p.add_argument("run_dir", type=Path)
        p.add_argument("--model", default=DEFAULT_JEV_MODEL, help="pinned Jev model version")
    sub.choices["run"].add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args(argv)

    if args.cmd == "run":
        load_dotenv()
        if not os.environ.get("TYPESAFE_API_KEY"):
            print("error: TYPESAFE_API_KEY is not set — add it to .env", file=sys.stderr)
            return 1
        path = asyncio.run(_run(args.run_dir, args.model, args.concurrency))
        recs = load_criteria(path)
        errors = sum(1 for r in recs.values() if r.error)
        print(f"\n{path}: {len(recs)} cells classified, {errors} errors")
        return 0

    path = output_path(args.run_dir, args.model)
    if not path.exists():
        print(f"error: no criteria output at {path} — run `run` first", file=sys.stderr)
        return 1
    report = validate(load_run(args.run_dir), load_criteria(path))
    out = path.with_name(path.stem + "-validation.md")
    out.write_text(report)
    print(report.split("## Disagreements")[0].rstrip())
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
