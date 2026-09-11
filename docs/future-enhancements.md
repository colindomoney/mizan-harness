# Future enhancements

A parking lot for work that is deliberately **not** in v1.0. Each item says what it is,
why it matters, and whether it fits the v1.0 capture-only guardrail (see
[AGENTS.md](../AGENTS.md)) or belongs to v2.0. Add to this file rather than starting on
something out of scope.

Items are roughly ordered by how much they would change what a run captures.

## 1. Wire `web_search` through to the gateways

**What.** `RunParams.web_search` is recorded but never sent
([call-path.md](call-path.md)). Make it real: when true, ask the gateway to enable the
vendor's web search for the call, and expose it as `--web-search` on the runner.

**Why.** The bare-API baseline is answered from training data only. A second axis with
search on would show how much retrieval changes framing, refusals and hedging on the same
prompt bank — arguably the more interesting comparison for the published note.

**Scope.** Fits v1.0: it changes what is captured, not how it is judged.

**Sketch.** Both gateways accept search through the same OpenAI-compatible request, so it
stays inside `gateway.run` and the `openai` SDK's `extra_body` hook:

- OpenRouter: the `web` plugin (`plugins: [{"id": "web"}]`) or the `:online` model suffix.
- Vercel AI Gateway: vendor-native search tools via provider options.

Verify the exact request shape against each gateway's current docs before wiring — both
change often. Record the search results/citations the gateway returns (they arrive in the
message, e.g. as `annotations`) so the capture stays complete. The manifest already pins
`web_search`, so a search-on run is distinguishable from the baseline. Mock the client in
tests as usual; assert the extra body is present when the flag is on and absent when off.
Also honour the per-prompt bank field, or decide explicitly that the run-level flag wins.

**Size.** Small: tens of lines plus tests, plus a doc update in `call-path.md`.

## 2. Control (or at least record) reasoning effort

**What.** Models currently apply their own reasoning defaults; GPT, Gemini and Grok all
return reasoning fields, Claude and Llama do not. Add a `reasoning` param to `RunParams`
(off / low / medium / high, mapped per gateway) and record what came back.

**Why.** Uncontrolled thinking is a hidden variable in latency and token counts, and
possibly in how a model frames a contested answer. Pinning it makes cross-run diffs cleaner.

**Scope.** Fits v1.0 (capture parameter, not a judgement). Vendor support is uneven, so
the mapping may have to be "best effort, recorded in the manifest".

## 3. Cross-run diff view

**What.** A viewer or export mode that takes two or more run dirs and lays out the same
prompt × model cell side by side across runs, with the flag and response for each.

**Why.** The first question anyone asks with two full runs in hand is "what changed for
this prompt on this model?" Today that means opening two viewers and scrolling in sync.

**Scope.** Fits v1.0: presentation only. Builds on `mizan.rundata.load_run`, which already
joins manifest → bank → records, so most of the work is rendering.

## 4. Tighten the hedge heuristic

**What.** The hedge flag counts phrases anywhere in the text; two hits trips it. In the
11 July run Gemini was flagged on "deeply contested" plus "the arguments presented by
both sides" — the second is a description of the answer's structure, not a hedge.

**Options.** Weight phrases, exclude structural uses ("presented by both sides", "hear
from both sides"), or require hits in distinct sentences. Any change must stay a
phrase-level flag with no quality or bias judgement, and
[refusal-heuristic.md](refusal-heuristic.md) must be updated in step.

**Scope.** Fits v1.0 as long as it remains "did the model hedge", never "was the hedge
warranted".

## 5. Assert the bare-API baseline, don't just assume it

**What.** The harness enforces "no search, no tools" by sending nothing, not by sending an
explicit off switch. Add a post-run check (or a runner assertion) that scans `raw` for
`tool_calls`, `annotations`, or other retrieval evidence and warns if any appear in a run
where `web_search` is false.

**Why.** A vendor enabling search by default for a model tier would currently pass through
silently. The two full runs are clean, but that was checked by hand.

**Scope.** Fits v1.0: it validates the capture.

## 6. Analyse skill follow-ups

The Hermes skill in `skills/mizan/analyse` (spec: `spec/mizan-analyse-skill-spec.md`)
shipped as phase 1. Deferred from the spec, in rough priority:

- **`viewer.html` as an input.** The pre-processor reads native `records.jsonl` only.
  Collaborators who only have the zipped viewer exports would need a stdlib `html.parser`
  path that re-keys prompts by exact query text against the bank (all 57 unique) and maps
  display names to canonical model ids via the registry. Adding `data-prompt-id` /
  `data-model-id` attributes to the viewer would make future exports self-describing.
- **`judge_diff.py`.** With reports from several judge profiles for the same batch, list
  findings by claim similarity across judges (three-judge consensus).
- **Plugin wrap.** Expose `mizan_prep` / `mizan_report` as typed Hermes tools and add a
  hook or cron that watches `runs/` for new captures.
- **Arabic prompts.** Lexicon and opener classifier are English-only.
- **Search-on/off variants** as a first-class dimension in the stability section, once
  item 1 above (wiring `web_search`) lands.
- **Summary length.** `summary.md` runs ≈6k words for the five July runs against the
  spec's 4k target; the pair and lexicon tables are the bulk. Per-run columns will grow
  with the batch, so consider a `--runs-since`/`--last N` selector or collapsing older
  runs into an aggregate column.

## Out of scope until v2.0

Anything that scores output: correctness, bias, quality ratings, LLM-as-judge. The
guardrail in AGENTS.md applies; do not start on it under the banner of an "enhancement".
