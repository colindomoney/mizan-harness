from conftest import RUN_MODELS, make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan.rundata import effective_flag, load_run


def test_load_run_orders_prompts_and_indexes_cells(tmp_path):
    prompts = [
        make_prompt("a1", Domain.HISTORY),
        make_prompt("b1", Domain.CASUALTIES),
        make_prompt("c1", Domain.HISTORY),
    ]
    records = [make_record("a1", "openai/gpt-x"), make_record("b1", "anthropic/claude-y")]
    run_dir = make_run_dir(tmp_path, prompts, records)

    data = load_run(run_dir)

    assert data.run_id == "20260101T000000Z"
    assert data.models == RUN_MODELS
    assert data.bank_hash_matches
    # Casualties precedes History in Domain enum order; domains contiguous
    assert [p.id for p in data.prompts] == ["b1", "a1", "c1"]
    assert set(data.cells) == {("a1", "openai/gpt-x"), ("b1", "anthropic/claude-y")}


def test_load_run_detects_hash_mismatch(tmp_path):
    prompts = [make_prompt("a1", Domain.HISTORY)]
    run_dir = make_run_dir(tmp_path, prompts, [], corrupt_hash=True)

    assert not load_run(run_dir).bank_hash_matches


def test_effective_flag():
    assert effective_flag(None) == "missing"
    assert effective_flag(make_record("a1", "m", error="boom")) == "error"
    assert effective_flag(make_record("a1", "m", flag="hedged")) == "hedged"
    assert effective_flag(make_record("a1", "m", flag=None)) == "empty"
