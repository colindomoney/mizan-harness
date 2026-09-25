"""Criteria-record schema: one Jev classification per captured answer.

Records serialise one-per-line into
``runs/<timestamp>/criteria/<jev-model>/qs<version>.jsonl``, so every file is
pinned to both the Jev model and the question-set version that produced it.
Full distributions are stored, never only the argmax.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["noul", "choice", "score"]
    # noul: P(true); choice: winning key; score: probability-weighted level.
    value: float | str
    # choice: key -> p; score: level index (as str, for JSON) -> p; noul: None.
    probabilities: dict[str, float] | None = None
    # Present for choice and score only; Jev returns none for noul.
    confidence: float | None = None


class CriteriaRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    model: str  # the target model whose answer was classified
    question_set_version: str
    jev_model: str
    request_id: str | None = None
    timestamp: datetime
    answers: dict[str, Answer] = {}
    input_tokens: int | None = None
    error: str | None = None

    def to_json_line(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json_line(cls, line: str) -> "CriteriaRecord":
        return cls.model_validate_json(line)
