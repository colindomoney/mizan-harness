"""Prompt bank schema.

The bank is curated in Notion and exported to ``prompts/bank.jsonl`` — one JSON
object per line, one prompt per object. The committed snapshot is what the
harness runs against; Notion stays the editing surface.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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
