# mizan-harness

Mizan is a discovery harness that runs a curated bank of Palestine-related prompts across
frontier LLMs (GPT, Claude, Gemini, Grok, Llama) via the [Vercel AI Gateway](https://vercel.com/docs/ai-gateway),
capturing every prompt→model call as a structured, reproducible record.

**v1.0 is capture-only.** No scoring, no LLM-as-judge, no bias rating — the goal is to run
the prompts, eyeball the outputs side by side, and publish preliminary observations that
inform the v2.0 audit design.

## Install

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Run

```sh
cp .env.example .env   # add your AI_GATEWAY_API_KEY
uv run pytest          # tests (no key needed; the gateway is mocked)
```

Harness entry points land as the runner is built out — see the Mizan project in Linear.
