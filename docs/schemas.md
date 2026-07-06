# Data schemas

## Prompt record (`prompts/bank.jsonl`)

Defined in [`mizan.bank.PromptRecord`](../src/mizan/bank.py). One JSON object per line.

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable unique id. Not a Notion column — derived from the Notion page id at export time, so re-exports keep ids stable. |
| `domain` | str | One of `Casualties`, `History`, `Legal / IHL`, `Terminology`, `Framing / Symmetry`, `Counterfactual`. Mirrors the Notion **Domain** select exactly. |
| `query` | str | The prompt text (Notion **Query** title column). |
| `pair_id` | str \| null | Pairing token (Notion **Pair ID**). See below. |
| `lang` | str | Default `en`. Not yet a Notion column; defaulted at export. |
| `web_search` | bool | Default `false` (Notion **Web search?** checkbox). Recorded per prompt; the bare-API baseline run keeps it off. |
| `notes` | str | Free text (Notion **Notes**). |

Notion columns *not* exported: **Owner** (curation bookkeeping) and the **ChatGPT / Claude / Gemini**
paste columns (week-1 manual capture; the harness replaces them).

### The pairing convention

Counterfactual/symmetry prompts come in twos: the same question asked with the sides swapped
(or the frame mirrored). Both rows carry the same `pair_id` token; unpaired prompts carry `null`.

**Integrity rule:** in a valid bank every non-null `pair_id` appears **exactly twice**. The bank
loader rejects orphaned (×1) or over-filled (×3+) pairs, and the results viewer uses `pair_id`
to render the two sides adjacent.

## Provenance

The bank is curated in Notion (the editing surface). `prompts/bank.jsonl` is a frozen, committed
snapshot produced by the export script; runs record the snapshot's hash in their manifest, so a
result is always traceable to the exact bank it ran against.
