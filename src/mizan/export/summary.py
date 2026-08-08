"""Aggregation rows for the export views: model summary, domain breakdown, pairs.

All counts are of capture-level flags (see ``mizan.rundata.effective_flag``);
means skip cells where the underlying value was never captured.
"""

from pydantic import BaseModel, ConfigDict

from mizan.bank import PromptRecord
from mizan.records import RunRecord
from mizan.rundata import RunData, effective_flag

FLAG_NAMES = ("answered", "hedged", "refused", "empty", "error", "missing")

_PREVIEW_CHARS = 200


class FlagCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answered: int = 0
    hedged: int = 0
    refused: int = 0
    empty: int = 0
    error: int = 0
    missing: int = 0


class ModelSummary(FlagCounts):
    model_id: str
    display_name: str
    mean_tokens_out: float | None = None
    mean_latency_ms: float | None = None


class DomainModelRow(FlagCounts):
    domain: str
    model_id: str
    display_name: str


class PairModelRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    domain: str
    model_id: str
    display_name: str
    a_prompt_id: str
    a_query: str
    a_flag: str
    a_chars: int | None
    a_preview: str
    b_prompt_id: str
    b_query: str
    b_flag: str
    b_chars: int | None
    b_preview: str


def _count_flags(records: list[RunRecord | None]) -> dict[str, int]:
    counts = dict.fromkeys(FLAG_NAMES, 0)
    for record in records:
        counts[effective_flag(record)] += 1
    return counts


def _mean(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def model_summaries(data: RunData) -> list[ModelSummary]:
    """Per-model flag counts and means, in manifest column order."""
    out: list[ModelSummary] = []
    for model in data.models:
        records = [data.cells.get((p.id, model["id"])) for p in data.prompts]
        present = [r for r in records if r is not None]
        out.append(
            ModelSummary(
                model_id=model["id"],
                display_name=model["display_name"],
                **_count_flags(records),
                mean_tokens_out=_mean([r.tokens_out for r in present if r.tokens_out is not None]),
                mean_latency_ms=_mean([r.latency_ms for r in present if r.latency_ms is not None]),
            )
        )
    return out


def domain_breakdown(data: RunData) -> list[DomainModelRow]:
    """Flag counts per domain × model, long format (one row per combination)."""
    domains: list[str] = []
    for p in data.prompts:  # prompts are already domain-grouped
        if p.domain not in domains:
            domains.append(p.domain)

    out: list[DomainModelRow] = []
    for domain in domains:
        in_domain = [p for p in data.prompts if p.domain == domain]
        for model in data.models:
            records = [data.cells.get((p.id, model["id"])) for p in in_domain]
            out.append(
                DomainModelRow(
                    domain=domain,
                    model_id=model["id"],
                    display_name=model["display_name"],
                    **_count_flags(records),
                )
            )
    return out


def _half(prompt: PromptRecord, record: RunRecord | None) -> dict:
    text = record.response_text if record else None
    preview = ""
    if text:
        preview = text[:_PREVIEW_CHARS] + ("…" if len(text) > _PREVIEW_CHARS else "")
    return {
        "prompt_id": prompt.id,
        "query": prompt.query,
        "flag": effective_flag(record),
        "chars": len(text) if text is not None else None,
        "preview": preview,
    }


def pair_rows(data: RunData) -> list[PairModelRow]:
    """Both halves of every pair side by side, one row per pair × model."""
    pairs: dict[str, list[PromptRecord]] = {}
    for p in data.prompts:  # ordered, so pair members arrive adjacent and in display order
        if p.pair_id:
            pairs.setdefault(p.pair_id, []).append(p)

    out: list[PairModelRow] = []
    for pair_id, members in pairs.items():
        if len(members) != 2:  # bank validation should prevent this; skip defensively
            continue
        a, b = members
        for model in data.models:
            half_a = _half(a, data.cells.get((a.id, model["id"])))
            half_b = _half(b, data.cells.get((b.id, model["id"])))
            out.append(
                PairModelRow(
                    pair_id=pair_id,
                    domain=a.domain,
                    model_id=model["id"],
                    display_name=model["display_name"],
                    **{f"a_{k}": v for k, v in half_a.items()},
                    **{f"b_{k}": v for k, v in half_b.items()},
                )
            )
    return out
