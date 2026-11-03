"""Typed loader for config/spec_registry.yaml (infrastructure, not extraction logic)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from advisor.models import Category

SpecType = Literal["number", "string", "boolean", "list", "range"]
Compare = Literal["gte", "lte", "eq", "interface", "has_all", "intersects", "contains"]
_DEFAULT_COMPARE: dict[str, Compare] = {
    "number": "gte", "range": "contains", "list": "has_all", "string": "eq", "boolean": "eq",
}  # fmt: skip


def fold(text: str) -> str:
    """Lowercase without accents or extra spaces ('Gases Volátiles' -> 'gases volatiles')."""
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


class SpecDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str | None = None
    type: SpecType
    critical: bool = False
    description: str = ""
    aliases: list[str] = []
    patterns: list[str] = []
    keywords: list[str] = []
    # canonical keyword -> es/en phrases meaning it in a query, e.g. humidity: [humedad]
    synonyms: dict[str, list[str]] = {}
    compare: Compare | None = None
    derive: bool = True
    upgrade_condition: str | None = None

    @property
    def comparison(self) -> Compare:
        return self.compare or _DEFAULT_COMPARE[self.type]

    def phrases(self) -> dict[str, list[str]]:
        """Canonical keyword -> normalized phrases denoting it (keyword itself + synonyms)."""
        return {
            kw: [fold(kw), *(fold(s) for s in self.synonyms.get(kw, []))] for kw in self.keywords
        }

    def canonical(self, value: str) -> str | None:
        """Registry keyword for a free-text value ('humedad' -> 'humidity'); None if unknown."""
        wanted = fold(value)
        for keyword, phrases in self.phrases().items():
            if wanted in phrases:
                return keyword
        return None

    @field_validator("aliases")
    @classmethod
    def _lowercase_aliases(cls, v: list[str]) -> list[str]:
        return [a.lower() for a in v]

    @field_validator("patterns")
    @classmethod
    def _valid_regex(cls, v: list[str]) -> list[str]:
        for pattern in v:
            if re.compile(pattern).groups < 1:
                raise ValueError(f"pattern needs a capture group: {pattern}")
        return v

    @model_validator(mode="after")
    def _keywords_only_for_lists(self) -> SpecDefinition:
        if set(self.synonyms) - set(self.keywords):
            raise ValueError(
                f"synonyms for unknown keywords: {set(self.synonyms) - set(self.keywords)}"
            )
        if self.keywords and self.type != "list":
            raise ValueError("keywords are only valid for type 'list'")
        if self.type in ("number", "range") and not self.unit:
            raise ValueError("numeric specs need a unit ('count' for plain counts)")
        return self


class SpecRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    common: dict[str, SpecDefinition] = {}
    categories: dict[Category, dict[str, SpecDefinition]] = Field(min_length=1)

    def for_category(self, category: Category) -> dict[str, SpecDefinition]:
        return self.categories.get(category, {})


def load_spec_registry(path: Path) -> SpecRegistry:
    return SpecRegistry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
