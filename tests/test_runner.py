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


def test_capture_one_sends_openrouter_slug_but_records_canonical_id() -> None:
    model = ModelEntry(
        id="fake/model-a", provider="fake", display_name="A", openrouter_id="or-fake/model-a"
    )
    completions = FakeCompletions()
    record = capture_one(
        PROMPT, model, RunParams(), client=fake_client(completions), gateway_name="openrouter"
    )
    assert completions.last_kwargs is not None
    assert completions.last_kwargs["model"] == "or-fake/model-a"  # wire slug
    assert record.model == "fake/model-a"  # canonical id
    assert record.gateway == "openrouter"


def test_capture_one_error_record_carries_gateway() -> None:
    completions = FakeCompletions(error=make_status_error(404))
    record = capture_one(
        PROMPT,
        MODEL,
        RunParams(),
        client=fake_client(completions),
        gateway_name="openrouter",
        sleep=lambda _: None,
    )
    assert record.error is not None
    assert record.gateway == "openrouter"


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
    assert manifest["gateway"] == "openrouter"  # default gateway
    assert all(r.gateway == "openrouter" for r in records)
    assert [m["id"] for m in manifest["models"]] == ["fake/model-a", "fake/model-b"]
    assert manifest["total_cells"] == manifest["completed"] == 6
    assert manifest["errors"] == 0
    assert manifest["finished_at"] is not None


def test_run_matrix_reports_progress_per_captured_cell(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    calls: list[tuple[str, str, int, int]] = []
    run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(FakeCompletions()),
        on_progress=lambda rec, done, total: calls.append((rec.prompt_id, rec.model, done, total)),
    )
    assert len(calls) == 6
    assert [c[2] for c in calls] == [1, 2, 3, 4, 5, 6]
    assert all(c[3] == 6 for c in calls)


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


def test_run_matrix_records_explicit_vercel_gateway(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    run_dir = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(FakeCompletions()),
        gateway_name="vercel",
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["gateway"] == "vercel"
    assert all(r.gateway == "vercel" for r in read_records(run_dir))


def test_run_matrix_resume_gateway_mismatch_raises(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    run_dir = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(FakeCompletions()),
        limit=1,
    )
    with pytest.raises(ValueError, match="gateway mismatch"):
        run_matrix(
            bank,
            RunParams(),
            registry_path=registry,
            resume_dir=run_dir,
            client=fake_client(FakeCompletions()),
            gateway_name="vercel",
        )


def test_run_matrix_resume_pre_gateway_manifest_treated_as_vercel(tmp_path: Path) -> None:
    bank, registry = write_fixtures(tmp_path)
    run_dir = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        out_base=tmp_path / "runs",
        client=fake_client(FakeCompletions()),
        gateway_name="vercel",
        limit=1,
    )
    # Simulate a run captured before the gateway field existed.
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["gateway"]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="gateway mismatch"):
        run_matrix(
            bank,
            RunParams(),
            registry_path=registry,
            resume_dir=run_dir,
            client=fake_client(FakeCompletions()),
        )  # default openrouter must not silently mix into a vercel run
    resumed = run_matrix(
        bank,
        RunParams(),
        registry_path=registry,
        resume_dir=run_dir,
        client=fake_client(FakeCompletions()),
        gateway_name="vercel",
    )
    assert resumed == run_dir
