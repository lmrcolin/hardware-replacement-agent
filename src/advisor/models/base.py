"""Base model and shared warning category."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Immutable, strict base for every cross-module contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DataConsistencyWarning(UserWarning):
    """Emitted when source data is internally inconsistent but still loadable."""
