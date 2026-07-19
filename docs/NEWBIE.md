# Mizan newbie guide

You've been given access to this repo and want to know what it is, what's already been
done, and how to poke at it yourself. This page is the tour. (Command reference lives in
the [README](../README.md); this is the *why* and *what*.)

## What Mizan is

Mizan (Arabic for *scale/balance*) audits how frontier LLMs handle Palestine-related
queries. The idea: ask the same curated set of questions to GPT, Claude, Gemini, Grok,
and Llama under identical conditions, capture every answer verbatim, and put them side
by side.

**v1.0 deliberately does not judge the answers.** No scoring, no bias rating, no
LLM-as-judge. It captures what each model said, flags whether it answered at all, and
renders the grid for human eyeballs. Judging output quality is v2.0 — if you catch
yourself wanting to add a "correctness" column, stop; that's out of scope by design.

## The moving parts

**The prompt bank** — `prompts/bank.jsonl`, 57 prompts across six domains (Casualties,
History, Legal/IHL, Terminology, Framing/Symmetry, Counterfactual). Curated in a private
Notion database, exported to this frozen snapshot, and committed. You don't need Notion
access — the committed file is the input, treat it as read-only.

The interesting design bit: 14 prompts are *counterfactual/symmetry pairs* — the same
question asked with the sides swapped or the frame mirrored. Both members carry the same
`pair_id`, and the tooling keeps them adjacent so you can compare how a model treats each
side of the same question.

**The model registry** — `config/models.toml`, the five models under test, addressed by
a canonical `<provider>/<model>` slug (with an `openrouter_id` override where OpenRouter
names a model differently).

**The gateway** — all model calls go through one OpenAI-compatible gateway (one API key,
all vendors): OpenRouter by default, the Vercel AI Gateway via `--gateway vercel`.
`src/mizan/gateway.py` is the only file that talks to either; nothing else in the
codebase touches a vendor API.

**The runner** — `src/mizan/runner.py` runs the full prompt × model matrix. Every call
becomes one JSON line in `runs/<timestamp>/records.jsonl`: the exact query, model,
params, response text, token counts, latency, and (if the call failed) the error. A
`manifest.json` alongside pins the model list, params, and the SHA-256 of the bank
snapshot — so every run states precisely what produced it. Runs are resumable;
interrupting one loses nothing.

**The refusal flag** — the one annotation the harness adds. A phrase-matching heuristic
tags each response `answered`, `refused`, `hedged`, or `empty`. It marks *whether* the
model engaged, never whether the answer was good. Details and known limitations:
[refusal-heuristic.md](refusal-heuristic.md).

**The viewer** — renders a run into one self-contained HTML file: prompts as rows
(pairs adjacent, purple-marked), models as columns, refusal flags colour-coded, full
response text expandable in each cell.

## What's been done so far

The first full discovery run is complete: the whole bank against all five models with
bare-API settings (temperature 0, no system prompt, no web search) — 285/285 cells
captured. That baseline plus its viewer HTML is what the *Mizan: Preliminary
Observations* note draws from.

## Try it yourself in five minutes

```sh
git clone <this repo> && cd mizan-harness
uv sync
cp .env.example .env      # paste in an OPENROUTER_API_KEY (ask Colin, or mint your own)
./hello-gateway.sh        # verify the key works

uv run python -m mizan.runner --limit 2     # tiny sweep: 2 prompts × 5 models
uv run python -m mizan.viewer runs/<the-new-timestamp>
open runs/<the-new-timestamp>/viewer.html
```

That's the whole loop. Drop `--limit` for the real thing (285 calls — some spend, and
premium models need the gateway account to have paid credit).

`uv run pytest` needs no key at all — the gateway is mocked in tests.

## FAQ

**Do I need Notion access?** No. The bank snapshot is committed; Notion is only the
curation surface, and only the bank maintainer re-exports it.

**Can two runs be compared?** Yes, if their manifests show the same `bank_sha256` and
params — that's exactly what the manifest is for.

**Why did a cell error?** Failures are captured, not hidden: the record's `error` field
has the gateway message. Transient errors (429/5xx) were already retried before being
recorded.

**A model's slug stopped working?** Vendors rotate model names. Check the gateway
catalogue (`GET https://openrouter.ai/api/v1/models`, or Vercel's `GET /v1/models`) and
update `config/models.toml` — never a hardcoded id.

**Where do I file issues?** The Mizan team in Linear (`MIZ-*`).

## Reading list

- [Data schemas](schemas.md) — every field of `PromptRecord` and `RunRecord`
- [Refusal heuristic](refusal-heuristic.md) — flag categories and limitations
- [AGENTS.md](../AGENTS.md) — code conventions and the v1.0 scope guardrail
