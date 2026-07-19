import json
from datetime import UTC, datetime

from mizan.gateway import Response, RunParams
from mizan.records import RunRecord


def make_record(**overrides) -> RunRecord:
    fields = {
        "prompt_id": "p001",
        "query": "What happened in 1948?",
        "model": "anthropic/claude-sonnet-5",
        "provider": "anthropic",
        "params": RunParams(temperature=0.0, web_search=False),
        "timestamp": datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC),
        "response_text": "…",
        "raw": {"id": "cmpl-1"},
        "tokens_in": 10,
        "tokens_out": 200,
        "latency_ms": 1234,
    }
    fields.update(overrides)
    return RunRecord(**fields)


def test_jsonl_round_trip() -> None:
    rec = make_record()
    line = rec.to_json_line()
    assert "\n" not in line
    assert RunRecord.from_json_line(line) == rec


def test_error_record_round_trip() -> None:
    rec = make_record(
        response_text=None,
        raw=None,
        tokens_in=None,
        tokens_out=None,
        latency_ms=None,
        error="gateway call failed for bad/model: 404",
    )
    back = RunRecord.from_json_line(rec.to_json_line())
    assert back.error and back.response_text is None


def test_from_response_captures_everything() -> None:
    resp = Response(
        text="answer",
        model="openai/gpt-5.1",
        tokens_in=5,
        tokens_out=50,
        latency_ms=900,
        raw={"id": "cmpl-2"},
    )
    rec = RunRecord.from_response(
        prompt_id="p002",
        query="q",
        model="openai/gpt-5.1",
        provider="openai",
        gateway="openrouter",
        params=RunParams(),
        response=resp,
    )
    assert rec.response_text == "answer"
    assert rec.gateway == "openrouter"
    assert (rec.tokens_in, rec.tokens_out, rec.latency_ms) == (5, 50, 900)
    assert rec.refusal_flag is None and rec.error is None


def test_pre_gateway_field_lines_parse_as_vercel() -> None:
    # Records written before the `gateway` field existed (all captured via
    # Vercel) must still parse, defaulting to "vercel".
    line = make_record().to_json_line()
    old = json.loads(line)
    del old["gateway"]
    back = RunRecord.from_json_line(json.dumps(old))
    assert back.gateway == "vercel"


def test_gateway_serialises_on_every_line() -> None:
    rec = make_record(gateway="openrouter")
    data = json.loads(rec.to_json_line())
    assert data["gateway"] == "openrouter"
    assert RunRecord.from_json_line(rec.to_json_line()) == rec
