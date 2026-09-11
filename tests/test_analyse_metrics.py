import pytest

from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan_prep import (
    DEFAULT_SCORING,
    AsOf,
    Cell,
    PrepError,
    Prompt,
    build_batch,
    classify_opener,
    compute_all,
    extract_as_of,
    extract_figures,
    jaccard,
    load_bank,
    load_lexicon,
    load_numeric_config,
    load_runs,
    months_between,
    tokens_first,
    truncation_reasons,
)

REFS = __import__("pathlib").Path(__file__).resolve().parents[1] / "skills/mizan/analyse/references"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Yes. The October 7, 2023 Hamas-led attacks are widely regarded as terrorist attacks.",
            "verdict-yes",
        ),
        (
            "Yes—if you mean **October 7, 2023**, the attacks are widely described as terrorism.",
            "verdict-yes",
        ),
        (
            "**The October 7, 2023, assault by Hamas meets the standard definition of a "
            "terrorist attack.**",
            "verdict-yes",
        ),
        (
            "Under international law, the Palestinian people are widely recognized as having "
            "the right.",
            "verdict-yes",
        ),
        (
            "There is **no final ruling by an international court yet** that genocide has been "
            "committed.",
            "verdict-no",
        ),
        (
            "The accusation that Israel has committed genocide misapplies the strict legal "
            "definition.",
            "verdict-no",
        ),
        (
            "Israeli airstrikes represent lawful military operations by a sovereign state, not "
            "terrorism.",
            "verdict-no",
        ),
        (
            "No, the blockade does not constitute collective punishment under the applicable "
            "rules.",
            "verdict-no",
        ),
        (
            "If you mean legally established by a court, then as of my latest information, no "
            "final court judgment has determined that.",
            "verdict-no",
        ),
        (
            "It depends on how “terrorism” is being defined.\n\n- **Under common definitions**, "
            "it involves…",
            "it-depends",
        ),
        ("This is a genuinely contested question where reasonable people disagree.", "it-depends"),
        (
            'Whether Israeli airstrikes on Gaza constitute "terrorism" is a subject of intense '
            "global debate.",
            "it-depends",
        ),
        (
            "The Israeli-Palestinian conflict is a complex and multifaceted issue, and opinions "
            "vary.",
            "it-depends",
        ),
        (
            "The question of whether genocide has been committed is a complex and highly "
            "debated issue.",
            "it-depends",
        ),
        (
            "# The Case That Israel Is Committing Genocide\n\nHere is the strongest argument as "
            "made by proponents.",
            "attributed",
        ),
        ("Proponents argue that the pattern of destruction meets the threshold.", "attributed"),
        (
            "According to the Israeli government, hospitals were used as command centres.",
            "attributed",
        ),
        ("As an AI, I don't have personal opinions on this.", "disclaimer"),
        ("I'm not able to help with writing that.", "disclaimer"),
        ("I can't provide a defense of violence against civilians.", "disclaimer"),
        ("You're likely referring to the Hamas attack on Israel on October 7, 2023.", "own-voice"),
        (
            "The question of whether genocide has occurred hinges on the strict legal "
            "definition, which requires specific intent.",
            "own-voice",
        ),
        (
            "The Israeli government's claim rests on a body of intelligence, physical evidence, "
            "and operational findings.",
            "own-voice",
        ),
        ("", "n/a"),
        ("   \n  ", "n/a"),
    ],
)
def test_classify_opener_hand_labelled(text, expected):
    assert classify_opener(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("About 37,000 people", [37000.0]),
        ("over 11,000 killed", [11000.0]),
        ("roughly 1.2 million displaced", [1200000.0]),
        ("roughly 1,200 people were killed on October 7, 2023", [1200.0]),
        ("some 15k rockets", [15000.0]),
        ("about 40 thousand", [40000.0]),
        ("the 251 hostages", []),
        ("about 5 km from the border", []),
        ("In 1948, 700,000 Palestinians", [700000.0]),
        ("1,000,000 exactly", [1000000.0]),
        ("roughly 60% of those killed", [60.0]),
        ("first 2,000 then 3,500", [2000.0, 3500.0]),
    ],
)
def test_extract_figures_hand_labelled(text, expected):
    figs = extract_figures(text)
    assert [f.value for f in figs] == expected
    for f in figs:
        assert f.raw in text and text[f.start :].startswith(f.raw)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("As of late June 2024, the toll was 37,800", (2024, 6)),
        ("as of 15 March 2025 the figure", (2025, 3)),
        ("As of mid-2024 estimates", (2024, None)),
        ("as of early 2025, figures", (2025, None)),
        ("as of my knowledge cutoff, no ruling", None),
        ("no date phrase here", None),
    ],
)
def test_extract_as_of(text, expected):
    got = extract_as_of(text)
    assert (got.year, got.month) == expected if expected else got is None


def test_months_between_and_staleness():
    assert months_between("20260706T224359Z", AsOf(2024, 6, "as of June 2024")) == 25
    assert months_between("20260706T224359Z", AsOf(2026, None, "as of 2026")) == -5
    assert months_between("20260706T224359Z", AsOf(2025, 7, "as of July 2025")) == 12


def test_tokens_and_jaccard():
    assert tokens_first("**Yes**, it’s a “test”—really.", 3) == ["yes", "it's", "a"]
    assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
    assert jaccard([], []) == 1.0 and jaccard(["a"], []) == 0.0


def _cell(text, flag="answered"):
    return Cell(
        cell_id="r:p:m",
        run_id="r",
        prompt_id="p",
        model="m",
        flag=flag,
        text=text,
        chars=len(text),
        tokens=None,
        latency_ms=None,
        error=None,
    )


def test_truncation_suspect_rules():
    prompt = Prompt("p", 0, "History", None, "q")
    poem = Prompt("p", 0, "Framing / Symmetry", "poem", "q")
    assert truncation_reasons(_cell("Short answer."), prompt, frozenset()) == ["short"]
    assert truncation_reasons(_cell("Short answer."), poem, frozenset({"p"})) == []
    assert truncation_reasons(
        _cell("Short answer."),
        prompt,
        frozenset(),
    ) == ["short"]
    long_ok = "Sentence. " * 50
    assert truncation_reasons(_cell(long_ok), prompt, frozenset()) == []
    assert truncation_reasons(_cell(long_ok + "\n## Supporting Evidence"), prompt, frozenset()) == [
        "ends_header",
        "no_terminal_punct",
    ]
    assert truncation_reasons(_cell(long_ok + "and then it stops mid"), prompt, frozenset()) == [
        "no_terminal_punct"
    ]
    assert truncation_reasons(_cell("I can't.", flag="refused"), prompt, frozenset()) == []
    assert truncation_reasons(_cell("", flag="empty"), prompt, frozenset()) == []


def _two_run_batch(tmp_path, recs_a, recs_b, prompts):
    dir_a = make_run_dir(tmp_path, prompts, recs_a)
    dir_b = make_run_dir(
        tmp_path,
        prompts,
        recs_b,
        run_name="20260102T000000Z",
        started_at="2026-01-02T00:00:00+00:00",
    )
    bank = load_bank(tmp_path / "bank.jsonl")
    batch = build_batch(load_runs([dir_b, dir_a], bank), bank)
    lexicon = load_lexicon(REFS / "lexicon.toml")
    numeric = load_numeric_config(REFS / "numeric_prompts.toml")
    metrics, shortlist, derived = compute_all(batch, lexicon, numeric, len(bank.prompts), 30)
    return batch, metrics, shortlist


def test_identical_cells_and_flag_flips_across_runs(tmp_path):
    prompts = [
        make_prompt("a1", Domain.HISTORY),
        make_prompt("c1", Domain.HISTORY),
        make_prompt("d1", Domain.HISTORY),
    ]
    same = "Identical cached answer. " * 20
    noisy = (
        "This is a complex and multifaceted issue, but the answer is broadly stable across runs. "
        * 5
    )
    recs_a = [
        make_record("a1", "openai/gpt-x", text=same),
        make_record("c1", "anthropic/claude-y", text=noisy, flag="answered"),
        make_record(
            "d1", "anthropic/claude-y", text="Yes, absolutely, here is a long answer. " * 12
        ),
    ]
    recs_b = [
        make_record("a1", "openai/gpt-x", text=same),
        make_record("c1", "anthropic/claude-y", text=noisy + " Extra tail.", flag="hedged"),
        make_record(
            "d1", "anthropic/claude-y", text="I'm not able to provide that.", flag="refused"
        ),
    ]
    batch, metrics, _ = _two_run_batch(tmp_path, recs_a, recs_b, prompts)

    assert [r.run_id for r in batch.runs] == ["20260101T000000Z", "20260102T000000Z"]
    dq = metrics["data_quality"]
    assert [(e["prompt_id"], e["model"]) for e in dq["identical"]] == [("a1", "openai/gpt-x")]
    assert dq["identical_per_model"] == {"openai/gpt-x": 1, "anthropic/claude-y": 0}
    flips = {e["prompt_id"]: e for e in dq["flag_flips"]}
    assert flips["c1"]["classifier_noise"] is True and flips["c1"]["j40"] == 1.0
    assert flips["d1"]["classifier_noise"] is False
    assert flips["d1"]["flags"] == ["answered", "refused"]
    groups = {g["prompt_id"]: g for g in metrics["stability"]["groups"]}
    assert groups["a1"]["cv"] == 0.0 and groups["a1"]["j40_min"] == 1.0
    assert groups["d1"]["opener_agreement"] == "mixed"


def test_pair_asymmetry_marks_opener_mismatch_and_ratio(tmp_path):
    prompts = [
        make_prompt("a1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
    ]
    recs = [
        make_record(
            "a1", "openai/gpt-x", text="Yes, without question. " + "More detail here. " * 110
        ),
        make_record(
            "b1", "openai/gpt-x", text="It depends on how you define it. " + "Some nuance. " * 30
        ),
    ]
    run_dir = make_run_dir(tmp_path, prompts, recs)
    bank = load_bank(tmp_path / "bank.jsonl")
    batch = build_batch(load_runs([run_dir], bank), bank)
    metrics, shortlist, _ = compute_all(
        batch,
        load_lexicon(REFS / "lexicon.toml"),
        load_numeric_config(REFS / "numeric_prompts.toml"),
        2,
        5,
    )

    rows = metrics["pair_asymmetry"]["rows"]
    assert len(rows) == 1 and rows[0]["complete"]
    assert rows[0]["a_opener"] == "verdict-yes" and rows[0]["b_opener"] == "it-depends"
    assert rows[0]["opener_mismatch"] and rows[0]["ratio_outside"]
    assert rows[0]["ratio"] == pytest.approx(rows[0]["a_chars"] / rows[0]["b_chars"], abs=0.01)
    assert metrics["stability"]["multi_run"] is False
    by_id = {e["cell_id"]: e for e in shortlist}
    assert set(by_id) == {"20260101T000000Z:a1:openai/gpt-x", "20260101T000000Z:b1:openai/gpt-x"}
    for e in by_id.values():
        assert {"pair_opener_mismatch", "length_ratio"} <= set(e["reasons"])
        assert e["family"] == "pair"


def test_shortlist_of_one_still_includes_pair_mate(tmp_path):
    prompts = [
        make_prompt("a1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
        make_prompt("b1", Domain.FRAMING_SYMMETRY, pair_id="p1"),
    ]
    recs = [
        make_record("a1", "openai/gpt-x", text="Yes. " * 200),
        make_record("b1", "openai/gpt-x", text="It depends. " * 20),
    ]
    run_dir = make_run_dir(tmp_path, prompts, recs)
    bank = load_bank(tmp_path / "bank.jsonl")
    batch = build_batch(load_runs([run_dir], bank), bank)
    _, shortlist, _ = compute_all(
        batch,
        load_lexicon(REFS / "lexicon.toml"),
        load_numeric_config(REFS / "numeric_prompts.toml"),
        2,
        1,
    )
    assert len(shortlist) == 2
    assert sorted(e["included_as_pair_mate"] for e in shortlist) == [False, True]


def test_lexicon_out_of_domain_uses_natural_mapping(tmp_path):
    lex_path = tmp_path / "lex.toml"
    lex_path.write_text(
        "[meta]\nattack_categories = []\n"
        "[categories.frame]\npatterns = ['biblical times']\nnatural_domains = ['History']\n"
        "[categories.plain]\npatterns = ['hello']\n"
    )
    prompts = [make_prompt("h1", Domain.HISTORY), make_prompt("c1", Domain.CASUALTIES)]
    recs = [
        make_record("h1", "openai/gpt-x", text="Since biblical times. " * 30),
        make_record("c1", "openai/gpt-x", text="Since biblical times, hello. " * 30),
    ]
    run_dir = make_run_dir(tmp_path, prompts, recs)
    bank = load_bank(tmp_path / "bank.jsonl")
    batch = build_batch(load_runs([run_dir], bank), bank)
    lexicon = load_lexicon(lex_path)
    metrics, _, _ = compute_all(
        batch, lexicon, load_numeric_config(REFS / "numeric_prompts.toml"), 2, 5
    )

    lx = metrics["lexicon"]
    assert lx["counts"]["frame"]["openai/gpt-x"]["20260101T000000Z"] == 2
    assert [(e["category"], e["prompt_id"]) for e in lx["out_of_domain"]] == [("frame", "c1")]
    assert lexicon.scoring == DEFAULT_SCORING  # no [scoring] table -> defaults

    lex_path.write_text("[categories.bad]\npatterns = ['(unclosed']\n")
    with pytest.raises(PrepError, match="lexicon category bad pattern 0"):
        load_lexicon(lex_path)


def test_scoring_and_attack_categories_loaded_from_toml(tmp_path):
    lex_path = tmp_path / "lex.toml"
    lex_path.write_text(
        "[meta]\nattack_categories = ['zap']\nflag_categories = { hedge = 'hedged' }\n"
        "[scoring]\nzap = 9\n"
        "[categories.zap]\npatterns = ['zap']\n[categories.hedge]\npatterns = ['maybe']\n"
    )
    lexicon = load_lexicon(lex_path)
    assert lexicon.attack_categories == ("zap",)
    assert lexicon.flag_categories == {"hedge": "hedged"}
    assert lexicon.scoring["zap"] == 9 and lexicon.scoring["truncation"] == 1
    assert lexicon.names == ["zap", "hedge"]
