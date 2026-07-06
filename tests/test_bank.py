import pytest
from pydantic import ValidationError

from mizan.bank import Domain, PromptRecord


def test_minimal_record_defaults() -> None:
    rec = PromptRecord(id="p001", domain=Domain.HISTORY, query="What happened in 1948?")
    assert rec.pair_id is None
    assert rec.lang == "en"
    assert rec.web_search is False
    assert rec.notes == ""


def test_domain_parses_from_string() -> None:
    rec = PromptRecord(id="p002", domain="Legal / IHL", query="q")
    assert rec.domain is Domain.LEGAL_IHL


def test_invalid_domain_rejected() -> None:
    with pytest.raises(ValidationError):
        PromptRecord(id="p003", domain="Sports", query="q")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        PromptRecord(id="p004", domain="History", query="q", score=1)


def test_json_round_trip() -> None:
    rec = PromptRecord(
        id="p005",
        domain=Domain.COUNTERFACTUAL,
        query="q",
        pair_id="pair-03",
        notes="one side of a pair",
    )
    assert PromptRecord.model_validate_json(rec.model_dump_json()) == rec
