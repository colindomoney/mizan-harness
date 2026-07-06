"""Model registry.

Models live in ``config/models.toml``, never hardcoded at call sites. Each
entry is a Vercel AI Gateway model slug (``<provider>/<model>``) plus display
metadata.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DEFAULT_REGISTRY_PATH = Path("config/models.toml")


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    display_name: str


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[ModelEntry]:
    """Load the model registry, failing loudly on a missing or malformed file."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [ModelEntry.model_validate(entry) for entry in data["models"]]
