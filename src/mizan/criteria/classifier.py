"""Async batch runner: classify every captured answer in a run with Jev.

One ``system_one`` call per answer carrying the whole question set, behind a
semaphore (Jev's rate limit is per minute, not per connection). Failed and
empty cells are skipped — there is no answer to judge. Output is resumable:
cells already classified without error are kept and skipped on re-run, cells
that errored are retried.

All access to the SDK response goes through ``parse_response`` so a change in
response shape is a one-place fix.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from typesafe_sdk import TypeSafeError

from mizan.rundata import RunData

from .questions import QUESTION_SET_VERSION, QUESTIONS, build_state
from .schema import Answer, CriteriaRecord

DEFAULT_JEV_MODEL = "jev-1.13.0"  # pinned: a model change moves the probabilities
DEFAULT_CONCURRENCY = 16


def output_path(run_dir: Path, jev_model: str) -> Path:
    return run_dir / "criteria" / jev_model / f"qs{QUESTION_SET_VERSION}.jsonl"


def load_criteria(path: Path) -> dict[tuple[str, str], CriteriaRecord]:
    """Index a criteria file by (prompt_id, model); later lines win."""
    out: dict[tuple[str, str], CriteriaRecord] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = CriteriaRecord.from_json_line(line)
                out[(rec.prompt_id, rec.model)] = rec
    return out


def parse_response(response, *, prompt_id: str, model: str) -> CriteriaRecord:
    answers: dict[str, Answer] = {}
    for name, a in response.answers.items():
        if a.type == "noul":
            answers[name] = Answer(kind="noul", value=a.noul)
        elif a.type == "choice":
            answers[name] = Answer(
                kind="choice",
                value=a.choice,
                probabilities=dict(a.probabilities),
                confidence=a.confidence,
            )
        else:
            answers[name] = Answer(
                kind="score",
                value=a.score,
                probabilities={str(k): v for k, v in a.probabilities.items()},
                confidence=a.confidence,
            )
    usage = getattr(response, "usage", None)
    return CriteriaRecord(
        prompt_id=prompt_id,
        model=model,
        question_set_version=QUESTION_SET_VERSION,
        jev_model=response.model,
        request_id=getattr(response, "request_id", None),
        timestamp=datetime.now(UTC),
        answers=answers,
        input_tokens=getattr(usage, "input_tokens", None),
    )


def pending_cells(data: RunData, done: dict[tuple[str, str], CriteriaRecord]) -> list:
    """(prompt, record) for every answered cell not yet classified cleanly, in view order."""
    out = []
    for prompt in data.prompts:
        for m in data.models:
            rec = data.cells.get((prompt.id, m["id"]))
            if rec is None or rec.error is not None or not (rec.response_text or "").strip():
                continue
            prior = done.get((prompt.id, rec.model))
            if prior is not None and prior.error is None:
                continue
            out.append((prompt, rec))
    return out


async def classify_run(
    data: RunData,
    client,
    *,
    jev_model: str = DEFAULT_JEV_MODEL,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_progress: Callable[[int, int, CriteriaRecord], None] | None = None,
) -> Path:
    """Classify a run's answers into its criteria file; returns the file path."""
    path = output_path(data.run_dir, jev_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = load_criteria(path)
    todo = pending_cells(data, done)

    # Rewrite with clean records only, so retried cells don't leave stale error lines.
    kept = [r for r in done.values() if r.error is None]
    path.write_text("".join(r.to_json_line() + "\n" for r in kept))

    sem = asyncio.Semaphore(concurrency)
    finished = 0

    async def one(prompt, rec) -> None:
        nonlocal finished
        async with sem:
            try:
                resp = await client.system_one(
                    state=build_state(prompt, rec), questions=QUESTIONS, model=jev_model
                )
                out = parse_response(resp, prompt_id=prompt.id, model=rec.model)
            except TypeSafeError as e:
                out = CriteriaRecord(
                    prompt_id=prompt.id,
                    model=rec.model,
                    question_set_version=QUESTION_SET_VERSION,
                    jev_model=jev_model,
                    timestamp=datetime.now(UTC),
                    error=f"{type(e).__name__}: {e}",
                )
        # Single event loop: appends between awaits never interleave.
        with path.open("a") as f:
            f.write(out.to_json_line() + "\n")
        finished += 1
        if on_progress:
            on_progress(finished, len(todo), out)

    await asyncio.gather(*(one(p, r) for p, r in todo))
    return path
