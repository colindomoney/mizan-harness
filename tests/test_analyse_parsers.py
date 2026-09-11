from pathlib import Path

import pytest

from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan.bank import load_bank as mizan_load_bank
from mizan.rundata import order_prompts
from mizan_prep import (
    DOMAIN_ORDER,
    PrepError,
    load_bank,
    load_runs,
    order_bank,
    parse_native,
    resolve_inputs,
    resolve_run_id,
    run_id_from_started,
)

REPO_BANK = Path(__file__).resolve().parents[1] / "prompts" / "bank.jsonl"


def test_parse_native_joins_bank_and_builds_cell_ids(tmp_path):
    prompts = [
        make_prompt("a1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("c1", Domain.HISTORY),
    ]
    records = [
        make_record("a1", "openai/gpt-x", text="Yes. Clearly."),
        make_record("b1", "openai/gpt-x", error="boom 503"),
        make_record("c1", "openai/gpt-x", text="   ", flag=None),
        # no record for claude-y at all: missing cells
    ]
    run_dir = make_run_dir(tmp_path, prompts, records)
    bank = load_bank(tmp_path / "bank.jsonl")

    run = parse_native(run_dir, bank)

    assert run.run_id == "20260101T000000Z"
    assert run.gateway == "openrouter"
    assert run.bank_hash_matches
    assert run.models == ["openai/gpt-x", "anthropic/claude-y"]
    assert run.display_names["anthropic/claude-y"] == "Claude Y"
    # History precedes Framing / Symmetry in display order; pair halves adjacent
    assert run.prompt_ids == ["c1", "a1", "b1"]
    assert bank.pairs == {"p1": ("a1", "b1")}
    cell = run.cells[("a1", "openai/gpt-x")]
    assert cell.cell_id == "20260101T000000Z:a1:openai/gpt-x"
    assert cell.flag == "answered" and cell.chars == 13
    assert run.cells[("b1", "openai/gpt-x")].flag == "error"
    assert run.cells[("b1", "openai/gpt-x")].text == ""
    assert run.cells[("c1", "openai/gpt-x")].flag == "empty"
    assert ("a1", "anthropic/claude-y") not in run.cells


def test_run_id_derived_from_started_at():
    assert run_id_from_started("2026-07-19T11:03:22.941121+00:00") == "20260719T110322Z"
    assert run_id_from_started("2026-07-19T12:03:22+01:00") == "20260719T110322Z"
    assert run_id_from_started("t0") is None
    assert resolve_run_id("t0", "20260101T000000Z") == "20260101T000000Z"
    with pytest.raises(PrepError, match="cannot derive a run id"):
        resolve_run_id("t0", "run")


def test_order_bank_matches_mizan_order_prompts():
    rows = [
        {"id": p.id, "domain": p.domain.value, "query": p.query, "pair_id": p.pair_id}
        for p in mizan_load_bank(REPO_BANK)
    ]
    assert [r["id"] for r in order_bank(rows)] == [
        p.id for p in order_prompts(mizan_load_bank(REPO_BANK))
    ]
    assert tuple(d.value for d in Domain) == DOMAIN_ORDER


def test_load_bank_reads_committed_bank():
    bank = load_bank(REPO_BANK)
    assert len(bank.prompts) == 57
    assert len(bank.pairs) == 14
    assert [p.index for p in bank.prompts] == list(range(57))


def test_rejects_raw_stream_bad_json_and_missing_manifest(tmp_path):
    prompts = [make_prompt("a1", Domain.HISTORY)]
    run_dir = make_run_dir(tmp_path, prompts, [make_record("a1", "openai/gpt-x")])
    bank = load_bank(tmp_path / "bank.jsonl")

    (run_dir / "records-raw.jsonl").write_text("{}\n")
    with pytest.raises(PrepError, match="records-raw"):
        resolve_inputs([run_dir / "records-raw.jsonl"])

    (run_dir / "records.jsonl").write_text('{"prompt_id": "a1", "model": "m"\n')
    with pytest.raises(PrepError, match="invalid JSON"):
        parse_native(run_dir, bank)

    (run_dir / "manifest.json").unlink()
    with pytest.raises(PrepError, match="manifest.json missing"):
        parse_native(run_dir, bank)
    with pytest.raises(PrepError, match="no run directories"):
        resolve_inputs([tmp_path])


def test_duplicate_run_id_is_rejected(tmp_path):
    prompts = [make_prompt("a1", Domain.HISTORY)]
    run_dir = make_run_dir(tmp_path, prompts, [make_record("a1", "openai/gpt-x")])
    bank = load_bank(tmp_path / "bank.jsonl")
    with pytest.raises(PrepError, match="duplicate run id"):
        load_runs([run_dir, run_dir], bank)


def test_batch_dir_expansion_skips_analysis_dir(tmp_path):
    prompts = [make_prompt("a1", Domain.HISTORY)]
    run_dir = make_run_dir(tmp_path, prompts, [make_record("a1", "openai/gpt-x")])
    (tmp_path / "analysis" / "judge").mkdir(parents=True)
    (tmp_path / "analysis" / "judge" / "manifest.json").write_text("{}")
    (tmp_path / "analysis" / "judge" / "records.jsonl").write_text("")

    assert resolve_inputs([tmp_path]) == [run_dir]
    assert resolve_inputs([run_dir / "records.jsonl"]) == [run_dir]
