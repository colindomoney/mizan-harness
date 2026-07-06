import json
from pathlib import Path

import pytest

from mizan.bank import BankValidationError, load_bank


def write_bank(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "bank.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def row(rid: str, pair_id: str | None = None, **overrides) -> dict:
    base = {"id": rid, "domain": "History", "query": f"q-{rid}", "pair_id": pair_id}
    base.update(overrides)
    return base


def test_valid_bank_loads_typed_records(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a"), row("b", "p1"), row("c", "p1")])
    records = load_bank(path)
    assert [r.id for r in records] == ["a", "b", "c"]
    assert records[1].pair_id == "p1"


def test_missing_required_field_rejected(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [{"id": "a", "domain": "History"}])  # no query
    with pytest.raises(BankValidationError, match="query"):
        load_bank(path)


def test_invalid_domain_rejected(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a", domain="Sports")])
    with pytest.raises(BankValidationError, match="domain"):
        load_bank(path)


def test_orphaned_pair_rejected(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a", "p1"), row("b")])
    with pytest.raises(BankValidationError, match="'p1' appears 1"):
        load_bank(path)


def test_overfilled_pair_rejected(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a", "p1"), row("b", "p1"), row("c", "p1")])
    with pytest.raises(BankValidationError, match="'p1' appears 3"):
        load_bank(path)


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a"), row("a")])
    with pytest.raises(BankValidationError, match="duplicate id"):
        load_bank(path)


def test_all_errors_reported_together(tmp_path: Path) -> None:
    path = write_bank(tmp_path, [row("a", "p1", domain="Sports"), row("b", "p2")])
    with pytest.raises(BankValidationError) as excinfo:
        load_bank(path)
    assert len(excinfo.value.errors) == 2
