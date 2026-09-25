# Mizan — agent context

## What this is

Mizan (Arabic for *scale/balance*) is a discovery harness auditing how frontier LLMs handle
Palestine-related queries. It runs a curated prompt bank across models (GPT, Claude, Gemini,
Grok, Muse Spark, DeepSeek) through an **OpenAI-compatible gateway** (OpenRouter by default, Vercel AI
Gateway as an alternative) and captures every prompt→model call as a
structured, reproducible record on disk. The v1.0 deliverable is a completed bare-API run, a
prompt × model viewer, and a short published note (*Mizan: Preliminary Observations*).

## Scope guardrail — read before writing code

**Capture stays judgement-free.** `gateway`, `runner`, `records` and `flags` capture model
outputs only; the one per-record annotation there is the heuristic *refusal/hedge flag*.
Classification of answers (including stance) lives **only** in `mizan.criteria`, runs over
a finished capture, and writes to its own files — never back into `records.jsonl`. It
reports distributions and differences, not verdicts on who is right.

## Code conventions

- Python ≥ 3.12, `uv` for deps/venv (`uv sync`), `src/`-layout with the `mizan` package.
- `ruff check` + `ruff format` (both must pass; CI enforces), `pytest` for tests.
- Type hints everywhere; pydantic models with `extra="forbid"` for data schemas.
- Tests never need a real API key — the gateway and Jev are always mocked (inject a fake `client`).
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
- `mizan.criteria` — Jev (TypeSafe) criteria classifier over a finished run. Versioned
  question set in `questions.py` (bump `QUESTION_SET_VERSION` on any wording change);
  `classifier.classify_run` is an async, resumable batch writing
  `runs/<ts>/criteria/<jev-model>/qs<N>.jsonl` with full distributions; `validate` compares
  against the refusal flag and the analyse opener class. See [docs/criteria.md](docs/criteria.md).
- `skills/mizan/analyse` — Hermes Agent skill (not part of the `mizan` package). Stdlib-only
  `scripts/mizan_prep.py` normalises `runs/*/records.jsonl` and computes every metric
  (`summary.md`/`candidates.json`/`normalised.json`, byte-deterministic); `SKILL.md` tells the
  judge LLM how to write `report.md`. Findings are *relative only* (differences between
  outputs), never correctness or bias — the same guardrail. Config is TOML in `references/`;
  tests in `tests/test_analyse_*.py`. Analysis outputs go to `runs/analysis/<judge>/`.

Field-level detail for both schemas: [docs/schemas.md](docs/schemas.md).
What each call actually sends (no tools, no web search, no reasoning control):
[docs/call-path.md](docs/call-path.md). Deferred work goes in
[docs/future-enhancements.md](docs/future-enhancements.md) rather than being started.
Work is tracked in the **Mizan** team in Linear (`MIZ-*` issues; schema → MIZ-6/MIZ-9,
gateway contract → MIZ-3).
