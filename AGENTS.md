# Mizan — agent context

## What this is

Mizan (Arabic for *scale/balance*) is a discovery harness auditing how frontier LLMs handle
Palestine-related queries. It runs a curated prompt bank across models (GPT, Claude, Gemini,
Grok, Llama) through an **OpenAI-compatible gateway** (OpenRouter by default, Vercel AI
Gateway as an alternative) and captures every prompt→model call as a
structured, reproducible record on disk. The v1.0 deliverable is a completed bare-API run, a
prompt × model viewer, and a short published note (*Mizan: Preliminary Observations*).

## Scope guardrail — read before writing code

**v1.0 captures model outputs only.** No scoring, no LLM-as-judge, no bias or quality rating.
The only per-record annotation allowed is a heuristic *refusal/hedge flag* (did the model
answer, refuse, or hedge) — never whether an answer is correct or biased. If a change starts
to judge output quality, it belongs in v2.0; stop and flag it instead.

## Code conventions

- Python ≥ 3.12, `uv` for deps/venv (`uv sync`), `src/`-layout with the `mizan` package.
- `ruff check` + `ruff format` (both must pass; CI enforces), `pytest` for tests.
- Type hints everywhere; pydantic models with `extra="forbid"` for data schemas.
- Tests never need a real API key — the gateway is always mocked (inject a fake `client`).
- Secrets live in `.env` (gitignored, documented in `.env.example`); never commit keys.

## Module map & contracts

- `mizan.gateway` — the **only** place that talks to a vendor endpoint.
  `run(prompt: str, model: str, params: RunParams) -> Response` via an OpenAI-compatible
  gateway endpoint (`GATEWAYS` table: OpenRouter default, Vercel alternative); failures
  raise `GatewayError`. Never import vendor SDKs elsewhere.
- `mizan.registry` — model list from `config/models.toml`; never hardcode model ids at call sites.
- `mizan.bank` — `PromptRecord` schema for `prompts/bank.jsonl`. The bank is curated in Notion
  and exported; treat the committed snapshot as read-only input.
- `mizan.records` — `RunRecord`, one JSONL line per call (failures included, with `error` set).
- `mizan.rundata` — shared run loading: manifest → bank → records join (`load_run` →
  `RunData`), prompt ordering, and the presentation-level `effective_flag` (adds `missing` /
  `error` on top of the captured refusal flag). Viewer and exporters both build on this.
- `mizan.export` — run exporters: `export.xlsx` (four-sheet Excel workbook) and
  `export.notion` (push to the master "Mizan runs" Notion database). Presentation only —
  same capture-only guardrail as everywhere else. See [docs/export.md](docs/export.md).
- Runs write to `runs/<timestamp>/` (gitignored): `records.jsonl` + `manifest.json` pinning
  the bank snapshot hash.

Field-level detail for both schemas: [docs/schemas.md](docs/schemas.md).
What each call actually sends (no tools, no web search, no reasoning control):
[docs/call-path.md](docs/call-path.md). Deferred work goes in
[docs/future-enhancements.md](docs/future-enhancements.md) rather than being started.
Work is tracked in the **Mizan** team in Linear (`MIZ-*` issues; schema → MIZ-6/MIZ-9,
gateway contract → MIZ-3).
