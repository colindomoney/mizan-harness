import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from mizan.bank import Domain, PromptRecord
from mizan.gateway import RunParams
from mizan.records import RunRecord

RUN_MODELS = [
    {"id": "openai/gpt-x", "provider": "openai", "display_name": "GPT-X"},
    {"id": "anthropic/claude-y", "provider": "anthropic", "display_name": "Claude Y"},
]


def make_prompt(pid: str, domain: Domain, pair_id: str | None = None) -> PromptRecord:
    return PromptRecord(id=pid, domain=domain, query=f"query {pid}", pair_id=pair_id)


def make_record(
    pid: str,
    model: str,
    *,
    text: str | None = "hello",
    error: str | None = None,
    flag: str | None = "answered",
    tokens_out: int | None = 5,
    latency_ms: int | None = 100,
) -> RunRecord:
    return RunRecord(
        prompt_id=pid,
        query=f"query {pid}",
        model=model,
        provider=model.split("/")[0],
        params=RunParams(),
        timestamp=datetime.now(UTC),
        response_text=text if error is None else None,
        tokens_in=None if error else 12,
        tokens_out=None if error else tokens_out,
        latency_ms=None if error else latency_ms,
        error=error,
        refusal_flag=None if error else flag,
    )


def make_run_dir(
    tmp_path: Path,
    prompts: list[PromptRecord],
    records: list[RunRecord],
    *,
    models: list[dict] = RUN_MODELS,
    corrupt_hash: bool = False,
    run_name: str = "20260101T000000Z",
    started_at: str = "2026-01-01T00:00:00+00:00",
) -> Path:
    """Write a synthetic bank + run dir (manifest.json, records.jsonl) under tmp_path."""
    bank_path = tmp_path / "bank.jsonl"
    bank_path.write_text("".join(p.model_dump_json() + "\n" for p in prompts))

    run_dir = tmp_path / run_name
    run_dir.mkdir()
    manifest = {
        "bank_path": str(bank_path),
        "bank_sha256": "0" * 64
        if corrupt_hash
        else hashlib.sha256(bank_path.read_bytes()).hexdigest(),
        "gateway": "openrouter",
        "models": models,
        "params": RunParams().model_dump(),
        "total_cells": len(prompts) * len(models),
        "started_at": started_at,
        "finished_at": None,
        "completed": len(records),
        "errors": sum(1 for r in records if r.error),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    (run_dir / "records.jsonl").write_text("".join(r.to_json_line() + "\n" for r in records))
    return run_dir


class FakeCompletions:
    """Stands in for client.chat.completions; records requests, can fail on cue."""

    def __init__(
        self,
        *,
        reply: str = "hello",
        error: Exception | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self.reply = reply
        self.error = error
        self.errors = errors or []  # raised one by one, then calls succeed
        self.calls = 0
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.errors:
            raise self.errors.pop(0)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
            model_dump=lambda: {"id": "cmpl-fake", "model": kwargs["model"]},
        )


def fake_client(completions: FakeCompletions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))
