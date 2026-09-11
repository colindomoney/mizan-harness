# How calls reach the models

Written up 2026-09-11 after auditing the gateway code and the raw responses captured in
the two full-bank runs (`20260706T224359Z` via Vercel, `20260719T110322Z` via OpenRouter).
Read this before comparing runs or drawing conclusions about vendor behaviour.

## One request shape, every model

Every prompt → model call goes through a single function, `mizan.gateway.run`. It uses
the OpenAI Python SDK's chat-completions endpoint with the `base_url` pointed at a
gateway; the gateway translates to each vendor's native API server-side. So GPT, Claude,
Gemini, Grok and Llama all receive an **identical** request:

| Field | Value |
|---|---|
| `messages` | optional `system` message, then one `user` message with the prompt |
| `temperature` | `RunParams.temperature` (default `0.0`) |
| `max_tokens` | `RunParams.max_output_tokens` (default `4096`) |

Nothing vendor-specific is sent. The only per-model difference is the wire slug: OpenRouter
names Grok and Llama differently from Vercel, and the registry's `openrouter_id` override
handles that (see [`config/models.toml`](../config/models.toml)).

## Two gateways

`--gateway openrouter` (default) or `--gateway vercel`. Both expose an OpenAI-compatible
endpoint, so the harness code is the same either way; only the base URL and API-key env
var change (`GATEWAYS` table in `gateway.py`). Each record stores which gateway carried it,
and a run directory sticks to one gateway.

## What is deliberately *not* sent

- **No tools.** No `tools` array, no function definitions. Models cannot call anything.
- **No web search.** `RunParams.web_search` exists and is written into every record and
  manifest for reproducibility, but `gateway.run` never reads it and the runner has no flag
  for it. It is always `false`. The per-prompt `web_search` field in the bank (the Notion
  checkbox) is likewise recorded but not acted on.
- **No reasoning control.** No reasoning-effort or thinking-budget parameter is sent, so
  each model applies its own default.

## Empirical check of the captured raw responses

The `raw` field on every record is the gateway's full response object. Across all 285
records in each full run:

| | Vercel run (06 Jul) | OpenRouter run (19 Jul) |
|---|---|---|
| `tool_calls` present | 0 | 0 |
| citation `annotations` present | 0 | 0 |
| non-empty message fields | content, reasoning_details, provider_metadata, phase | content, reasoning, reasoning_details |

No model went to the web in either run. The answers are from training data alone.

Reasoning fields **are** present for some models, which confirms the "no reasoning
control" point above — these models thought before answering, on their own defaults:

| Model | Vercel run | OpenRouter run |
|---|---|---|
| GPT-5.5 | `reasoning_details` on 57/57 | `reasoning_details` 57/57, `reasoning` 37/57 |
| Gemini 3.1 Pro | `reasoning_details` 57/57 | both 57/57 |
| Grok 4.3 | both 57/57 | both 57/57 |
| Claude Sonnet 5 | none | none |
| Llama 4 Maverick | none | none |

The two gateways surface reasoning differently (Vercel omits the plain `reasoning` text
where OpenRouter includes it), so treat the presence/absence of those fields as a gateway
artefact, not a model difference.

## Implications for reading results

- **Cross-run diffs are fair on inputs.** Same prompt, same params, same request shape.
  Differences between the two full runs are down to the model, the gateway's translation,
  and the vendor's own defaults on that day — not to anything the harness varied.
- **Reasoning is uncontrolled.** Latency and `tokens_out` differences between runs can be
  partly explained by how much a model chose to think. `tokens_out` as reported by the
  gateway may or may not include reasoning tokens depending on vendor.
- **"No search" is enforced by omission, not assertion.** The harness sends no search
  parameter; it does not send a parameter that *disables* search. A vendor that switches
  search on by default for a model tier would pass through silently. The raw responses show
  no sign of that in either run, but it is worth re-checking after any model or gateway
  change (the check is a one-liner over `raw.choices[0].message` — see the counts above).

Wiring `web_search` through to the gateways, and controlling reasoning, are both tracked
in [future-enhancements.md](future-enhancements.md).
