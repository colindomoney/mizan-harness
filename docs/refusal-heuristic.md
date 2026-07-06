# Refusal / hedge flagging heuristic

Implemented in [`mizan.flags.flag_refusal`](../src/mizan/flags.py); the flag lands in
`RunRecord.refusal_flag`. **This is a flag, not a score** — it marks "the model declined
or heavily hedged", never whether an answer is correct, biased, or good. There is
deliberately no correctness or bias logic anywhere in this code path (that's v2.0).

## Categories

| Flag | Trips when |
|---|---|
| `empty` | Response text is empty or whitespace. |
| `refused` | A refusal phrase (e.g. "I can't help with", "I'm unable to", "I must decline") appears in the **first 400 characters**. Refusals lead a response; the same phrase mid-answer is usually quotation or nuance, so the scan window is deliberately short. |
| `hedged` | No refusal, but **two or more** hedge phrases (e.g. "it's complicated", "highly contested", "there is no consensus", "both sides") appear anywhere. One hedge is normal caution; repetition is a pattern worth eyeballing. |
| `answered` | Everything else. |
| *(null)* | The call failed — there is no response to flag. |

Matching is case-insensitive with curly apostrophes normalised. The phrase lists live in
`_REFUSAL_MARKERS` / `_HEDGE_MARKERS` in `flags.py` — update this doc when they change.

## Known limitations (accepted for v1.0)

- Phrase lists are English-only (`lang: en` bank) and will miss novel refusal wordings.
- A model that answers *after* an initial refusal-ish disclaimer may be over-flagged.
- The flag exists to make refusals visible at a glance in the viewer, not to be a
  statistic — treat counts as indicative, and always read the underlying text.
