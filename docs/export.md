# Run export

`python -m mizan.export` turns a completed `runs/<timestamp>/` directory into analyzable,
auditable artefacts: an Excel workbook and (optionally) pages in a Notion database.

Everything here is **presentation of captured data only** — flag counts, tokens, latency,
response lengths, pair adjacency. The v1.0 scope guardrail (no scoring, no bias or quality
rating) applies to exports exactly as it does to capture.

## Excel workbook

```sh
uv run python -m mizan.export runs/<timestamp>              # → <run>/export.xlsx
uv run python -m mizan.export runs/<timestamp> --xlsx out.xlsx
```

| Sheet | Contents |
|---|---|
| Records | One row per prompt × model cell in viewer order (domains grouped, pairs adjacent): prompt, model, flag, tokens in/out, latency, error, full response text. Auto-filtered, frozen header. |
| Model summary | Per model: answered / hedged / refused / empty / error / missing counts, mean tokens out, mean latency. |
| Domain breakdown | Flag counts per domain × model (long format — pivot or filter freely). |
| Pairs | Both halves of every counterfactual/symmetry pair side by side, one row per pair × model: flag, response length, 200-char preview each. |

Excel caps a cell at 32,767 characters; longer responses are truncated with an
`… [truncated]` marker. The untruncated text is always in `records.jsonl` (and Notion).

## Notion

One master **"Mizan runs"** database holds every exported run, distinguished by a `Run`
select property — so saved Notion views can filter, group, and compare across runs
("all `refused` cells for model X", "run A vs run B"). One page per prompt × model cell:
structured fields as properties, the full response as paragraph blocks in the page body
(chunked under Notion's 2000-char rich-text limit).

One-time bootstrap (integration key in `.env` as `NOTION_API_KEY`, and the target page
shared with the integration):

```sh
uv run python -m mizan.export --init-notion --parent-page-id <notion-page-id>
# prints: NOTION_RUNS_DATA_SOURCE_ID=<id>   → add to .env
```

Then per run:

```sh
uv run python -m mizan.export runs/<timestamp> --notion
```

Re-pushing a run that already has pages aborts, so a resumed-then-completed run can't
silently double up; `--force` archives the existing pages for that run and pushes fresh.
Requests are throttled to ~3/s with retry on 429/5xx honouring `Retry-After`.

## Flag vocabulary

Exports use the captured refusal flag (`answered` / `refused` / `hedged` / `empty`, see
[refusal-heuristic.md](refusal-heuristic.md)) plus two **presentation-level** values that
are not produced by `mizan.flags` and never appear in `records.jsonl`:

- `error` — the cell has a record, but the call failed (`error` field set)
- `missing` — the cell was never captured (e.g. the run was interrupted)
