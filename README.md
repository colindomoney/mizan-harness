# mizan-harness

[![CI](https://github.com/colindomoney/mizan-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/colindomoney/mizan-harness/actions/workflows/ci.yml)

Mizan is a discovery harness that runs a curated bank of Palestine-related prompts across
frontier LLMs (GPT, Claude, Gemini, Grok, Llama) through an OpenAI-compatible gateway —
[OpenRouter](https://openrouter.ai) by default, the
[Vercel AI Gateway](https://vercel.com/docs/ai-gateway) as an alternative — capturing every
prompt→model call as a structured, reproducible record.

**v1.0 is capture-only.** No scoring, no LLM-as-judge, no bias rating — the goal is to run
the prompts, eyeball the outputs side by side, and publish preliminary observations that
inform the v2.0 audit design.

New to the project? Start with the [newbie guide](docs/NEWBIE.md).

## Install

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Setup

One secret is needed: an OpenRouter API key (one key covers all models; create one at
[openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)).

```sh
cp .env.example .env    # then paste your OPENROUTER_API_KEY into .env
./hello-gateway.sh      # smoke-test the key: one cheap call, one premium call
```

To use the Vercel AI Gateway instead, set `VERCEL_AI_GATEWAY_API_KEY` in `.env` and pass
`--gateway vercel` (smoke test: `./hello-gateway.sh vercel`). On Vercel, if the Llama call
passes but GPT fails with a 403, the key works but the account is still being treated as
free tier — premium models unlock once paid credit is visible.

> **Migration note:** the Vercel key env var was renamed `AI_GATEWAY_API_KEY` →
> `VERCEL_AI_GATEWAY_API_KEY`. Rename it in your existing `.env`.

## Usage

### Run a sweep

```sh
uv run python -m mizan.runner              # full sweep: every prompt × every model
uv run python -m mizan.runner --limit 2    # cheap smoke run: first 2 prompts only
```

Each run writes to `runs/<timestamp>/` (gitignored):

- `records.jsonl` — one line per prompt × model cell, failures included with `error` set
- `manifest.json` — pins what ran: model list, params, bank snapshot SHA-256, counts

Progress prints to stderr, one line per cell (suppress with `--quiet`):

```
[ 12/285] anthropic/claude-sonnet-5            26b3a1f0  answered (3.2s)
[ 13/285] xai/grok-4.3                         26b3a1f0  refused (1.8s)
```

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--bank PATH` | `prompts/bank.jsonl` | prompt bank snapshot to run |
| `--registry PATH` | `config/models.toml` | model registry |
| `--gateway {openrouter,vercel}` | `openrouter` | HTTP gateway to route calls through |
| `--temperature F` | `0.0` | sampling temperature for every call |
| `--system-prompt S` | none | optional system prompt for every call |
| `--limit N` | all | only run the first N prompts |
| `--resume DIR` | — | continue an interrupted run (see below) |
| `--quiet` | off | suppress per-cell progress lines |

Records are flushed per cell, so an interrupted run loses nothing — resume it and
already-captured cells are skipped:

```sh
uv run python -m mizan.runner --resume runs/20260706T224359Z
```

A run directory sticks to one gateway: resuming with a different `--gateway` than the
original run fails loudly. Runs captured before the gateway field existed count as
`vercel` — resume them with `--gateway vercel`.

Transient gateway failures (429/5xx) retry with backoff; auth failures (401/403) stop
the run immediately rather than recording a wall of errors.

### View the results

```sh
uv run python -m mizan.viewer runs/<timestamp>
open runs/<timestamp>/viewer.html
```

Renders a single self-contained HTML file — no server, no external assets, safe to
email or drop in a shared folder. Rows are prompts grouped by domain (counterfactual/
symmetry pairs adjacent), columns are models, and every cell shows the refusal flag,
token/latency stats, and the full captured response. `--out PATH` overrides the output
location.

### Validate the bank

```sh
uv run python -m mizan.bank    # checks prompts/bank.jsonl: schema + pairing integrity
```

## Prompt bank

The prompt bank is committed at `prompts/bank.jsonl` — the harness reads only this file.
Cloning the repo gives you everything needed to run a sweep; Notion access is **not**
required and no Notion credentials are used at runtime.

Notion is the curation surface, not a runtime dependency. Re-exporting the snapshot
(`scripts/export_bank.py`, needs `NOTION_API_KEY`) is a deliberate, reviewable step done
by the bank maintainer; run manifests pin the snapshot's SHA-256, so a changed bank shows
up as a changed hash.

## Models

The registry lives in [`config/models.toml`](config/models.toml) — one entry per model
with its canonical slug (`<provider>/<model>`, Vercel-style). Never hardcode model ids
elsewhere. Where OpenRouter uses a different slug (e.g. `x-ai/…`, `meta-llama/…`), the
entry carries an `openrouter_id` override — the canonical `id` is still what records and
the viewer use, regardless of gateway. Vendors rotate slugs frequently; verify against
the gateway catalogue before a run (`GET https://openrouter.ai/api/v1/models`, no key
needed, or Vercel's `GET /v1/models`).

## Docs

- [Newbie guide](docs/NEWBIE.md) — orientation for new team members
- [Data schemas](docs/schemas.md) — field-level detail for `PromptRecord` and `RunRecord`
- [Refusal heuristic](docs/refusal-heuristic.md) — how the answered/refused/hedged flag works

## Development

```sh
uv run pytest          # tests need no API key — the gateway is always mocked
uv run ruff check      # lint (CI enforces)
uv run ruff format     # format (CI enforces)
```

Work is tracked in the **Mizan** team in Linear (`MIZ-*` issues).
