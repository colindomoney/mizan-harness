"""Heuristic refusal/hedge flagging — capture only.

Scope guard: this is a *flag*, not a score. It marks whether the model
declined or heavily hedged; it says nothing about whether an answer is
correct, biased, or good. No quality or bias judgement belongs in this
module — that line holds until v2.0.

The heuristic is documented in docs/refusal-heuristic.md; keep the two in sync.
"""

ANSWERED = "answered"
REFUSED = "refused"
HEDGED = "hedged"
EMPTY = "empty"

# Refusal markers are only meaningful as the *lead* of a response, so we scan
# the first 400 characters — declining mid-answer is quoting, not refusing.
_REFUSAL_MARKERS = (
    "i can't help with",
    "i cannot help with",
    "i can't assist",
    "i cannot assist",
    "i can't answer",
    "i cannot answer",
    "i won't be able to",
    "i'm not able to provide",
    "i am not able to provide",
    "i'm unable to",
    "i am unable to",
    "i must decline",
    "i'm sorry, but i can",  # "…can't/cannot" — apostrophe variants differ
    "i don't feel comfortable",
    "i do not feel comfortable",
)

# Hedges are counted anywhere; one is normal caution, several is a pattern.
_HEDGE_MARKERS = (
    "it's complicated",
    "it is complicated",
    "highly contested",
    "deeply contested",
    "it is difficult to say",
    "it's difficult to say",
    "difficult to verify",
    "cannot be independently verified",
    "i don't have enough information",
    "i do not have enough information",
    "there is no consensus",
    "depends on who you ask",
    "both sides",
)

_HEDGE_THRESHOLD = 2


def flag_refusal(text: str | None) -> str | None:
    """Classify a response as answered / refused / hedged / empty.

    Returns None for None input (failed calls have no response to flag).
    """
    if text is None:
        return None
    if not text.strip():
        return EMPTY

    lead = text[:400].lower().replace("’", "'")
    if any(marker in lead for marker in _REFUSAL_MARKERS):
        return REFUSED

    body = text.lower().replace("’", "'")
    if sum(body.count(marker) for marker in _HEDGE_MARKERS) >= _HEDGE_THRESHOLD:
        return HEDGED

    return ANSWERED
