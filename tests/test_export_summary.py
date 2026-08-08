from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan.export.summary import domain_breakdown, model_summaries, pair_rows
from mizan.rundata import load_run


def _data(tmp_path):
    prompts = [
        make_prompt("a1", Domain.CASUALTIES),
        make_prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("c1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
    ]
    records = [
        make_record("a1", "openai/gpt-x", flag="answered", tokens_out=10, latency_ms=200),
        make_record("b1", "openai/gpt-x", flag="hedged", tokens_out=20, latency_ms=400),
        make_record("c1", "openai/gpt-x", error="boom 503"),
        make_record("a1", "anthropic/claude-y", flag="refused"),
        # b1/claude-y and c1/claude-y never captured: missing
    ]
    return load_run(make_run_dir(tmp_path, prompts, records))


def test_model_summaries_counts_and_means(tmp_path):
    gpt, claude = model_summaries(_data(tmp_path))

    assert gpt.display_name == "GPT-X"
    assert (gpt.answered, gpt.hedged, gpt.error, gpt.missing) == (1, 1, 1, 0)
    assert gpt.mean_tokens_out == 15.0  # error record has no tokens; excluded
    assert gpt.mean_latency_ms == 300.0

    assert (claude.refused, claude.missing) == (1, 2)
    assert claude.mean_latency_ms is not None  # one real record present


def test_model_summaries_means_none_when_no_data(tmp_path):
    prompts = [make_prompt("a1", Domain.HISTORY)]
    records = [make_record("a1", "openai/gpt-x", error="boom")]
    gpt, claude = model_summaries(load_run(make_run_dir(tmp_path, prompts, records)))

    assert gpt.mean_tokens_out is None
    assert claude.mean_tokens_out is None


def test_domain_breakdown_long_format(tmp_path):
    rows = domain_breakdown(_data(tmp_path))

    assert [(r.domain, r.model_id) for r in rows] == [
        ("Casualties", "openai/gpt-x"),
        ("Casualties", "anthropic/claude-y"),
        ("Framing / Symmetry", "openai/gpt-x"),
        ("Framing / Symmetry", "anthropic/claude-y"),
    ]
    framing_gpt = rows[2]
    assert (framing_gpt.hedged, framing_gpt.error) == (1, 1)
    framing_claude = rows[3]
    assert framing_claude.missing == 2


def test_pair_rows_side_by_side(tmp_path):
    rows = pair_rows(_data(tmp_path))

    assert len(rows) == 2  # one pair × two models
    gpt_row = rows[0]
    assert gpt_row.pair_id == "p1"
    assert (gpt_row.a_prompt_id, gpt_row.b_prompt_id) == ("b1", "c1")
    assert (gpt_row.a_flag, gpt_row.b_flag) == ("hedged", "error")
    assert gpt_row.a_chars == len("hello")
    assert gpt_row.b_chars is None

    claude_row = rows[1]
    assert (claude_row.a_flag, claude_row.b_flag) == ("missing", "missing")


def test_pair_preview_truncated(tmp_path):
    prompts = [
        make_prompt("b1", Domain.COUNTERFACTUAL, pair_id="p1"),
        make_prompt("c1", Domain.COUNTERFACTUAL, pair_id="p1"),
    ]
    records = [make_record("b1", "openai/gpt-x", text="x" * 500)]
    rows = pair_rows(load_run(make_run_dir(tmp_path, prompts, records)))

    assert rows[0].a_chars == 500
    assert len(rows[0].a_preview) == 201  # 200 chars + ellipsis
    assert rows[0].a_preview.endswith("…")
