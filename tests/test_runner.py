import hashlib
import json
from pathlib import Path

import httpx
import openai
import pytest

from conftest import FakeCompletions, fake_client
from mizan.bank import PromptRecord
from mizan.gateway import GatewayError, RunParams
from mizan.records import RunRecord
from mizan.registry import ModelEntry
from mizan.runner import MAX_ATTEMPTS, capture_one, run_matrix

PROMPT = PromptRecord(id="p1", domain="History", query="what happened?")
MODEL = ModelEntry(id="fake/model-a", provider="fake", display_name="Model A")


def make_status_error(status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://gw/v1"))
    return openai.APIStatusError(f"http {status}", response=response, body=None)


def write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    bank = tmp_path / "bank.jsonl"
    rows = [
        {"id": "p1", "domain": "History", "query": "q1", "pair_id": None},
        {"id": "p2", "domain": "Counterfactual", "query": "q2", "pair_id": "pairA"},
        {"id": "p3", "domain": "Counterfactual", "query": "q3", "pair_id": "pairA"},
    ]
    bank.write_text("".join(json.dumps(r) + "\n" for r in rows))

    registry = tmp_path / "models.toml"
    registry.write_text(
        '[[models]]\nid = "fake/model-a"\nprovider = "fake"\ndisplay_name = "A"\n\n'
        '[[models]]\nid = "fake/model-b"\nprovider = "fake"\ndisplay_name = "B"\n'
    )
    return bank, registry


def read_records(run_dir: Path) -> list[RunRecord]:
    with (run_dir / "records.jsonl").open() as f:
        return [RunRecord.from_json_line(line) for line in f if line.strip()]


def test_capture_one_success_is_flagged() -> None:
    record = capture_one(PROMPT, MODEL, RunParams(), client=fake_client(FakeCompletions()))
    assert record.response_text == "hello"
    assert record.refusal_flag == "answered"
    assert record.error is None


def test_capture_one_retries_transient_then_succeeds() -> None:
    completions = FakeCompletions(errors=[make_status_error(429), make_status_error(503)])
    sleeps: list[float] = []
    record = capture_one(
        PROMPT, MODEL, RunParams(), client=fake_client(completions), sleep=sleeps.append
    )
    assert record.error is None
    assert completions.calls == 3
    assert len(sleeps) == 2


def test_capture_one_permanent_error_becomes_error_record() -> None:
    completions = FakeCompletions(error=make_status_error(404))
    client = fake_client(completions)
    record = capture_one(PROMPT, MODEL, RunParams(), client=client, sleep=lambda _: None)
    assert completions.calls == 1  # no retry on permanent errors
    assert record.error and "404" in record.error
    assert record.response_text is None and record.refusal_flag is None


def test_capture_one_exhausts_retries_then_records_error() -> None:
    completions = FakeCompletions(error=make_status_error(429))
    client = fake_client(completions)
    record = capture_one(PROMPT, MODEL, RunParams(), client=client, sleep=lambda _: None)
    assert completions.calls == MAX_ATTEMPTS
    assert record.error is not None


def test_capture_one_auth_error_raises() -> None:
    completions = FakeCompletions(error=make_status_error(401))
    with pytest.raises(GatewayError):
        capture_one(PROMPT, MODEL, RunParams(), client=fake_client(completions))


def test_run_matrix_full_run_with_manifest(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    run_dir = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(FakeCompletions()),
    )

    records = read_records(run_dir)
    assert len(records) == 6  # 3 prompts × 2 models
    assert {(r.prompt_id, r.model) for r in records} == {
        (p, m) for p in ("p1", "p2", "p3") for m in ("fake/model-a", "fake/model-b")
    }

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["bank_sha256"] == hashlib.sha256(bank.read_bytes()).hexdigest()
    assert [m["id"] for m in manifest["models"]] == ["fake/model-a", "fake/model-b"]
    assert manifest["total_cells"] == manifest["completed"] == 6
    assert manifest["errors"] == 0
    assert manifest["finished_at"] is not None


def test_run_matrix_resume_skips_captured_cells(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    first = FakeCompletions()
    run_dir = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(first),
        limit=2,  # capture only p1, p2
    )
    assert first.calls == 4

    second = FakeCompletions()
    resumed = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        resume_dir=run_dir,
        client=fake_client(second),
    )
    assert resumed == run_dir
    assert second.calls == 2  # only p3's two cells
    assert len(read_records(run_dir)) == 6
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["completed"] == 6
