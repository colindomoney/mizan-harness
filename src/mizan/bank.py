"""Prompt bank schema.

The bank is curated in Notion and exported to ``prompts/bank.jsonl`` — one JSON
object per line, one prompt per object. The committed snapshot is what the
harness runs against; Notion stays the editing surface.
"""

from collections import Counter
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError


class Domain(StrEnum):
    """The six prompt domains, mirroring the Notion select column."""

    CASUALTIES = "Casualties"
    HISTORY = "History"
    LEGAL_IHL = "Legal / IHL"
    TERMINOLOGY = "Terminology"
    FRAMING_SYMMETRY = "Framing / Symmetry"
    COUNTERFACTUAL = "Counterfactual"


class PromptRecord(BaseModel):
    """One prompt in the bank, mirroring the Notion columns.

    ``pair_id`` links the two rows of a counterfactual/symmetry pair: both rows
    carry the same token, and a valid bank contains each token exactly twice.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    domain: Domain
    query: str
    pair_id: str | None = None
    lang: str = "en"
    web_search: bool = False
    notes: str = ""


class BankValidationError(Exception):
    """The bank file is structurally invalid; `errors` lists every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def load_bank(path: Path) -> list[PromptRecord]:
    """Load and validate bank.jsonl, raising BankValidationError on any defect.

    Beyond per-record field validation, enforces the pairing integrity rule:
    every non-null pair_id must appear exactly twice, and ids must be unique.
    """
    errors: list[str] = []
    records: list[PromptRecord] = []

    with path.open() as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                records.append(PromptRecord.model_validate_json(line))
            except ValidationError as exc:
                errors.append(f"line {lineno}: {exc}")

    id_counts = Counter(r.id for r in records)
    errors.extend(f"duplicate id {rid!r} (×{n})" for rid, n in id_counts.items() if n > 1)

    pair_counts = Counter(r.pair_id for r in records if r.pair_id)
    errors.extend(
        f"pair_id {pid!r} appears {n}× (must be exactly 2)"
        for pid, n in sorted(pair_counts.items())
        if n != 2
    )

    if errors:
        raise BankValidationError(errors)
    return records


def _main(argv: list[str]) -> int:
    """CLI entry point: validate a bank file, non-zero exit on failure."""
    path = Path(argv[0]) if argv else Path("prompts/bank.jsonl")
    try:
        records = load_bank(path)
    except BankValidationError as exc:
        print(f"{path}: INVALID\n{exc}")
        return 1
    paired = sum(1 for r in records if r.pair_id)
    print(f"{path}: OK — {len(records)} prompts, {paired // 2} pairs")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
