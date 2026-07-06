from pathlib import Path

import pytest
from pydantic import ValidationError

from mizan.registry import ModelEntry, load_registry

REPO_REGISTRY = Path(__file__).parent.parent / "config" / "models.toml"


def test_repo_registry_loads_v1_target_set() -> None:
    models = load_registry(REPO_REGISTRY)
    providers = {m.provider for m in models}
    assert {"openai", "anthropic", "google", "xai", "meta"} <= providers
    assert all(isinstance(m, ModelEntry) for m in models)
    assert all("/" in m.id for m in models)  # gateway slugs are provider/model


def test_malformed_registry_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "models.toml"
    bad.write_text('[[models]]\nid = "x/y"\n')  # missing provider + display_name
    with pytest.raises(ValidationError):
        load_registry(bad)
