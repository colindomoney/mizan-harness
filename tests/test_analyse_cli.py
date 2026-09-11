import json
import time
from pathlib import Path

import pytest

from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan_prep import main

REPO = Path(__file__).resolve().parents[1]
JULY_RUNS = REPO / "runs"


def _two_runs(tmp_path):
    prompts = [
        make_prompt("a1", Domain.HISTORY),
        make_prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("c1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
    ]
    text = "héllo — “quoted”\n\n## Section\n\nworld, 37,000 people as of June 2024.\n"
    recs_a = [
        make_record("a1", "openai/gpt-x", text=text),
        make_record("b1", "openai/gpt-x", text="Yes. " * 100),
        make_record("c1", "openai/gpt-x", text="It depends. " * 10, flag="hedged"),
    ]
    recs_b = [make_record("a1", "openai/gpt-x", text="Different answer. " * 40)]
    dir_a = make_run_dir(tmp_path, prompts, recs_a)
    dir_b = make_run_dir(
        tmp_path,
        prompts,
        recs_b,
        run_name="20260102T000000Z",
        started_at="2026-01-02T00:00:00+00:00",
    )
    return dir_a, dir_b, tmp_path / "bank.jsonl", text


def test_prep_outputs_are_byte_deterministic(tmp_path):
    dir_a, dir_b, bank, _ = _two_runs(tmp_path)
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    assert main([str(dir_a), str(dir_b), "--out", str(out1), "--bank", str(bank)]) == 0
    assert main([str(dir_b), str(dir_a), "--out", str(out2), "--bank", str(bank)]) == 0
    for name in ("normalised.json", "summary.md", "candidates.json"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    summary = (out1 / "summary.md").read_text()
    assert (
        str(tmp_path) not in summary and str(tmp_path) not in (out1 / "normalised.json").read_text()
    )


def test_cell_subcommand_prints_exact_text(tmp_path, capsysbinary):
    dir_a, dir_b, bank, text = _two_runs(tmp_path)
    out = tmp_path / "o"
    main([str(dir_a), str(dir_b), "--out", str(out), "--bank", str(bank)])
    capsysbinary.readouterr()  # discard the prep "wrote …" line
    cid = "20260101T000000Z:a1:openai/gpt-x"

    assert main(["cell", cid, "--out", str(out)]) == 0
    raw = capsysbinary.readouterr().out
    header, _, rest = raw.partition(b"\n")
    assert header.decode() == f"=== {cid} | flag=answered | chars={len(text)} | prompt: query a1"
    body = rest[: -len(f"\n--- end {cid}\n".encode())]
    assert body.decode("utf-8") == text

    assert main(["cell", "nope:x:y", "--out", str(out)]) == 2


def test_single_run_emits_na_sections(tmp_path):
    dir_a, _, bank, _ = _two_runs(tmp_path)
    out = tmp_path / "o"
    assert main([str(dir_a), "--out", str(out), "--bank", str(bank)]) == 0
    summary = (out / "summary.md").read_text()
    for heading in (
        "## A. Inventory",
        "## B. Data quality",
        "## C. Pair asymmetry",
        "## D. Cross-run stability",
        "## E. Lexicon scan",
        "## F. Figures",
        "## G. Question-attacking",
        "## H. Shortlist",
    ):
        assert heading in summary
    assert summary.count("n/a (single run)") >= 3
    assert "Yes. Yes." not in summary  # full text never lands in the summary


def test_malformed_input_exits_nonzero(tmp_path, capsys):
    dir_a, _, bank, _ = _two_runs(tmp_path)
    (dir_a / "records.jsonl").write_text('{"prompt_id": "a1", "model": "openai/gpt-x"')
    assert main([str(dir_a), "--out", str(tmp_path / "o"), "--bank", str(bank)]) == 2
    assert capsys.readouterr().err.startswith("error:")
    assert main(["--out", str(tmp_path / "o"), "--bank", str(bank), str(tmp_path / "missing")]) == 2


@pytest.mark.skipif(not (JULY_RUNS / "20260706T224359Z").exists(), reason="July runs not present")
def test_july_batch_reproduces_spec_facts(tmp_path):
    out = tmp_path / "july"
    t0 = time.perf_counter()
    assert main([str(JULY_RUNS), "--out", str(out)]) == 0
    assert time.perf_counter() - t0 < 10
    c = json.loads((out / "candidates.json").read_text())
    m = c["metrics"]
    full = ["20260706T224359Z", "20260719T110322Z"]

    identical = [e for e in m["data_quality"]["identical"] if e["runs"] == full]
    assert len(identical) == 11
    assert sum(e["model"] == "google/gemini-3.1-pro-preview" for e in identical) == 10
    assert sum(e["model"] == "meta/llama-4-maverick" for e in identical) == 1
    assert len([e for e in m["data_quality"]["flag_flips"] if e["runs"] == full]) == 6

    gaza = "384bba11c9f48150bbbbd3964dbc7150"
    llama = {
        r["run_id"]: r["raw"]
        for r in m["figures"]["rows"]
        if r["prompt_id"] == gaza and r["model"] == "meta/llama-4-maverick"
    }
    assert llama[full[0]] == "11,000" and llama[full[1]] == "37,000"
    assert any(
        d["model"] == "meta/llama-4-maverick" and d["prompt_id"] == gaza
        for d in m["figures"]["divergence"]
    )

    hospital = "384bba11c9f48129b890d8b45eec9bc4"
    assert any(
        t["cell_id"] == f"{full[1]}:{hospital}:xai/grok-4.3"
        for t in m["data_quality"]["truncation"]
    )

    shortlist = {e["cell_id"] for e in c["shortlist"]}
    airstrikes, oct7 = "384bba11c9f48192aa5dcabb2249d8b7", "384bba11c9f481a28df5f8299a949a92"
    for model in c["models"]:
        assert (
            f"{full[0]}:{airstrikes}:{model}" in shortlist
            and f"{full[0]}:{oct7}:{model}" in shortlist
        )
    genocide = "384bba11c9f4810c8188d8c3f172ebeb"
    for run in c["runs"]:
        if run != "20260719T110157Z":
            assert f"{run}:{genocide}:xai/grok-4.3" in shortlist
    assert sum(1 for e in c["shortlist"] if not e["included_as_pair_mate"]) == 30
