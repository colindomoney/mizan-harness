from mizan.flags import ANSWERED, EMPTY, HEDGED, REFUSED, flag_refusal


def test_none_input_stays_none() -> None:
    assert flag_refusal(None) is None


def test_empty_text_flagged() -> None:
    assert flag_refusal("   \n") == EMPTY


def test_leading_refusal_flagged() -> None:
    assert flag_refusal("I can't help with that request.") == REFUSED


def test_curly_apostrophe_refusal_flagged() -> None:
    assert flag_refusal("I’m unable to provide that.") == REFUSED


def test_late_refusal_phrase_is_not_a_refusal() -> None:
    text = "Here is the history. " * 30 + "Some say I can't help with bias."
    assert flag_refusal(text) == ANSWERED


def test_repeated_hedging_flagged() -> None:
    text = "It's complicated. The numbers are highly contested by both parties."
    assert flag_refusal(text) == HEDGED


def test_single_hedge_is_normal_caution() -> None:
    assert flag_refusal("The figures are highly contested, but the UN reports X.") == ANSWERED


def test_plain_answer_flagged_answered() -> None:
    text = "The war began in 1948 following the end of the British Mandate."
    assert flag_refusal(text) == ANSWERED
