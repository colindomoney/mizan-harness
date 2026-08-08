"""Excel workbook writer: four sheets per run.

Records (one row per prompt × model cell, full response text), Model summary,
Domain breakdown, and Pairs. Response text is truncated at Excel's hard
32,767-chars-per-cell limit; the full text always remains in records.jsonl.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from mizan.rundata import RunData, effective_flag

from .summary import domain_breakdown, model_summaries, pair_rows

_CELL_CHAR_LIMIT = 32_000  # under Excel's 32,767 hard cap, leaves room for the marker
_TRUNCATION_MARKER = "… [truncated]"

_RECORDS_HEADER = [
    "prompt_id",
    "domain",
    "pair_id",
    "query",
    "model",
    "flag",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "error",
    "response_text",
]

_WRAP = Alignment(wrap_text=True, vertical="top")
_BOLD = Font(bold=True)


def _truncate(text: str) -> str:
    if len(text) <= _CELL_CHAR_LIMIT:
        return text
    return text[:_CELL_CHAR_LIMIT] + _TRUNCATION_MARKER


def _write_sheet(
    ws: Worksheet,
    header: list[str],
    rows: list[list],
    *,
    widths: dict[str, int] | None = None,
    wrap_columns: set[str] = frozenset(),
) -> None:
    ws.append(header)
    for cell in ws[1]:
        cell.font = _BOLD
    wrap_idx = {header.index(c) for c in wrap_columns}
    for row in rows:
        ws.append(row)
        for idx in wrap_idx:
            ws.cell(row=ws.max_row, column=idx + 1).alignment = _WRAP
    for name, width in (widths or {}).items():
        ws.column_dimensions[get_column_letter(header.index(name) + 1)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write_workbook(data: RunData, out: Path) -> Path:
    wb = Workbook()

    records_rows = []
    for prompt in data.prompts:
        for model in data.models:
            record = data.cells.get((prompt.id, model["id"]))
            records_rows.append(
                [
                    prompt.id,
                    str(prompt.domain),
                    prompt.pair_id,
                    prompt.query,
                    model["display_name"],
                    effective_flag(record),
                    record.tokens_in if record else None,
                    record.tokens_out if record else None,
                    record.latency_ms if record else None,
                    record.error if record else None,
                    _truncate(record.response_text) if record and record.response_text else None,
                ]
            )
    _write_sheet(
        wb.active,
        _RECORDS_HEADER,
        records_rows,
        widths={"query": 50, "response_text": 90, "model": 22, "domain": 18},
        wrap_columns={"query", "response_text"},
    )
    wb.active.title = "Records"

    summaries = model_summaries(data)
    _write_sheet(
        wb.create_sheet("Model summary"),
        [
            "model",
            "answered",
            "hedged",
            "refused",
            "empty",
            "error",
            "missing",
            "mean_tokens_out",
            "mean_latency_ms",
        ],
        [
            [
                s.display_name,
                s.answered,
                s.hedged,
                s.refused,
                s.empty,
                s.error,
                s.missing,
                s.mean_tokens_out,
                s.mean_latency_ms,
            ]
            for s in summaries
        ],
        widths={"model": 24},
    )

    _write_sheet(
        wb.create_sheet("Domain breakdown"),
        ["domain", "model", "answered", "hedged", "refused", "empty", "error", "missing"],
        [
            [r.domain, r.display_name, r.answered, r.hedged, r.refused, r.empty, r.error, r.missing]
            for r in domain_breakdown(data)
        ],
        widths={"domain": 20, "model": 24},
    )

    _write_sheet(
        wb.create_sheet("Pairs"),
        [
            "pair_id",
            "domain",
            "model",
            "a_query",
            "a_flag",
            "a_chars",
            "a_preview",
            "b_query",
            "b_flag",
            "b_chars",
            "b_preview",
        ],
        [
            [
                r.pair_id,
                r.domain,
                r.display_name,
                r.a_query,
                r.a_flag,
                r.a_chars,
                r.a_preview,
                r.b_query,
                r.b_flag,
                r.b_chars,
                r.b_preview,
            ]
            for r in pair_rows(data)
        ],
        widths={"a_query": 40, "b_query": 40, "a_preview": 50, "b_preview": 50, "model": 24},
        wrap_columns={"a_query", "b_query", "a_preview", "b_preview"},
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
