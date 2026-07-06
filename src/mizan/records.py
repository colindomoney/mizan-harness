"""Run-record schema: one record per prompt→model call.

This is the reproducibility backbone — everything about a call is captured,
including failures, so a run directory is a complete account of what happened.
Records serialise one-per-line into ``runs/<timestamp>/records.jsonl``.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from mizan.gateway import Response, RunParams


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    query: str
    model: str
    provider: str
    params: RunParams
    timestamp: datetime
    # Response fields are None when the call failed; `error` says why.
    response_text: str | None = None
    raw: dict | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    # Heuristic capture-only flag (answered / refused / hedged); no quality
    # or bias judgement belongs here — that line holds until v2.0.
    refusal_flag: str | None = None

    @classmethod
    def from_response(
        cls,
        *,
        prompt_id: str,
        query: str,
        model: str,
        provider: str,
        params: RunParams,
        response: Response,
    ) -> "RunRecord":
        return cls(
            prompt_id=prompt_id,
            query=query,
            model=model,
            provider=provider,
            params=params,
            timestamp=datetime.now(UTC),
            response_text=response.text,
            raw=response.raw,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
        )

    def to_json_line(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json_line(cls, line: str) -> "RunRecord":
        return cls.model_validate_json(line)
