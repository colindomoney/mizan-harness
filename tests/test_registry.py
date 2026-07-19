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


def test_id_for_falls_back_to_canonical_id() -> None:
    entry = ModelEntry(id="openai/gpt-5.5", provider="openai", display_name="GPT-5.5")
    assert entry.id_for("openrouter") == "openai/gpt-5.5"
    assert entry.id_for("vercel") == "openai/gpt-5.5"


def test_id_for_uses_openrouter_override_only_on_openrouter() -> None:
    entry = ModelEntry(
        id="xai/grok-4.3",
        provider="xai",
        display_name="Grok 4.3",
        openrouter_id="x-ai/grok-4.3",
    )
    assert entry.id_for("openrouter") == "x-ai/grok-4.3"
    assert entry.id_for("vercel") == "xai/grok-4.3"


def test_registry_loads_openrouter_id(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        '[[models]]\nid = "meta/llama-4-maverick"\nprovider = "meta"\n'
        'display_name = "Llama 4 Maverick"\nopenrouter_id = "meta-llama/llama-4-maverick"\n'
    )
    (model,) = load_registry(path)
    assert model.openrouter_id == "meta-llama/llama-4-maverick"
