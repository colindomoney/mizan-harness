import asyncio
from types import SimpleNamespace

from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, TypeSafeError

from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan.criteria.__main__ import _main
from mizan.criteria.classifier import classify_run, load_criteria, output_path, parse_response
from mizan.criteria.questions import QUESTIONS, build_state
from mizan.criteria.schema import CriteriaRecord
from mizan.criteria.validate import jev_flag, lean, mirror_residual, validate
from mizan.rundata import load_run

GPT, CLAUDE = "openai/gpt-x", "anthropic/claude-y"


def fake_response(*, refuses=0.1, hedging=0.5, opener="own-voice", pal=2.0, isr=2.0):
    answers = {
        name: NoulAnswer(type="noul", noul=0.2)
        for name in ("both_sides_caveat", "attributes_claims", "challenges_premise")
    }
    answers["addresses_asker"] = NoulAnswer(type="noul", noul=0.0)
    answers["refuses"] = NoulAnswer(type="noul", noul=refuses)
    answers["opener"] = ChoiceAnswer(
        type="choice", choice=opener, confidence=0.8, probabilities={opener: 0.8, "other": 0.2}
    )
    for name, val in (("hedging", hedging), ("stance_palestinian", pal), ("stance_israeli", isr)):
        answers[name] = ScoreAnswer(
            type="score", score=val, confidence=0.7, legend={}, probabilities={0: 0.3, 1: 0.7}
        )
    return SimpleNamespace(
        model="jev-test",
        request_id="req-1",
        usage=SimpleNamespace(input_tokens=42),
        answers=answers,
    )


class FakeJev:
    def __init__(self, *, fail_on: set[str] = frozenset(), **resp) -> None:
        self.calls: list[dict] = []
        self.fail_on = set(fail_on)
        self.resp = resp

    async def system_one(self, *, state, questions, model):
        self.calls.append({"state": state, "questions": questions, "model": model})
        if state["answer"] in self.fail_on:
            raise TypeSafeError("rate limited")
        return fake_response(**self.resp)


def _run_dir(tmp_path):
    prompts = [
        make_prompt("a1", Domain.HISTORY, pair_id="p"),
        make_prompt("a2", Domain.HISTORY, pair_id="p"),
        make_prompt("b1", Domain.CASUALTIES),
    ]
    records = [
        make_record("a1", GPT, text="Yes. It is."),
        make_record("a1", CLAUDE, text="It depends."),
        make_record("a2", GPT, text="No."),
        make_record("a2", CLAUDE, error="boom"),  # failed: skipped
        make_record("b1", GPT, text="   ", flag="empty"),  # empty: skipped
    ]
    return make_run_dir(tmp_path, prompts, records)


def test_state_omits_target_model(tmp_path):
    data = load_run(_run_dir(tmp_path))
    state = build_state(data.prompts[0], data.cells[(data.prompts[0].id, GPT)])
    assert set(state) == {"question", "domain", "answer"}
    assert "other" in QUESTIONS["opener"].criteria


def test_classify_run_skips_failed_and_empty_cells(tmp_path):
    data = load_run(_run_dir(tmp_path))
    client = FakeJev()
    path = asyncio.run(classify_run(data, client, jev_model="jev-test"))

    assert path == output_path(data.run_dir, "jev-test")
    recs = load_criteria(path)
    assert set(recs) == {("a1", GPT), ("a1", CLAUDE), ("a2", GPT)}
    assert all(c["model"] == "jev-test" for c in client.calls)
    rec = recs[("a1", GPT)]
    assert rec.request_id == "req-1" and rec.input_tokens == 42
    assert rec.answers["opener"].value == "own-voice"
    assert rec.answers["hedging"].probabilities == {"0": 0.3, "1": 0.7}
    assert rec.answers["refuses"].confidence is None


def test_errors_are_recorded_then_retried_on_resume(tmp_path):
    data = load_run(_run_dir(tmp_path))
    asyncio.run(classify_run(data, FakeJev(fail_on={"No."}), jev_model="jev-test"))
    recs = load_criteria(output_path(data.run_dir, "jev-test"))
    assert recs[("a2", GPT)].error.startswith("TypeSafeError")

    client = FakeJev()
    path = asyncio.run(classify_run(data, client, jev_model="jev-test"))
    assert len(client.calls) == 1  # only the errored cell is retried
    lines = path.read_text().splitlines()
    assert len(lines) == 3
    assert all(CriteriaRecord.from_json_line(line).error is None for line in lines)


def _parsed(**kw) -> CriteriaRecord:
    return parse_response(fake_response(**kw), prompt_id="x", model=GPT)


def test_stance_arithmetic():
    rec = _parsed(pal=3.0, isr=1.0)
    assert lean(rec) == 3.0  # (3 + (4 - 1)) / 2
    assert mirror_residual(rec) == 0.0
    assert mirror_residual(_parsed(pal=3.0, isr=3.0)) == 2.0  # both orientations lean "up"


def test_jev_flag_thresholds():
    assert jev_flag(_parsed(refuses=0.9)) == "refused"
    assert jev_flag(_parsed(hedging=2.0)) == "hedged"
    assert jev_flag(_parsed()) == "answered"


def test_validate_reports_agreement_and_pair_deltas(tmp_path):
    data = load_run(_run_dir(tmp_path))
    asyncio.run(classify_run(data, FakeJev(pal=2.5, isr=2.0), jev_model="jev-test"))
    report = validate(data, load_criteria(output_path(data.run_dir, "jev-test")))

    assert "Agreement: 3/3 (100%)" in report  # all heuristic flags are "answered"
    assert "| openai/gpt-x | 2 | 2.25 | +0.50 | 0.50 |" in report
    assert "| p | openai/gpt-x |" in report  # a1/a2 pair on the model with both halves
    assert "| p | anthropic/claude-y |" not in report  # second half failed


def test_cli_run_requires_key_and_validate_requires_output(tmp_path, monkeypatch, capsys):
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr("mizan.criteria.__main__.load_dotenv", lambda: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert _main(["run", str(run_dir)]) == 1
    assert _main(["validate", str(run_dir)]) == 1
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err
