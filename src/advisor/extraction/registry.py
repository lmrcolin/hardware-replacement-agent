"""Typed loader for config/spec_registry.yaml (infrastructure, not extraction logic)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from advisor.models import Category

SpecType = Literal["number", "string", "boolean", "list", "enum"]


class SpecDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str | None = None
    type: SpecType
    critical: bool = False
    description: str = ""
    aliases: list[str] = []


class SpecRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    categories: dict[Category, dict[str, SpecDefinition]] = Field(min_length=1)


def load_spec_registry(path: Path) -> SpecRegistry:
    return SpecRegistry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
