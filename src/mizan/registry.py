"""Model registry.

Models live in ``config/models.toml``, never hardcoded at call sites. Each
entry is a canonical model slug (``<provider>/<model>``, Vercel-style) plus
display metadata, with an optional per-gateway wire-slug override.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_REGISTRY_PATH = Path("config/models.toml")


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `id` is the canonical identity everywhere (records, viewer, resume keys);
    # gateway-specific slugs are wire-only, resolved via `id_for`.
    id: str
    provider: str
    display_name: str
    openrouter_id: str | None = None

    def id_for(self, gateway_name: str) -> str:
        """Slug to send over the wire for this gateway; falls back to the canonical id."""
        if gateway_name == "openrouter" and self.openrouter_id:
            return self.openrouter_id
        return self.id


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[ModelEntry]:
    """Load the model registry, failing loudly on a missing or malformed file."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [ModelEntry.model_validate(entry) for entry in data["models"]]
