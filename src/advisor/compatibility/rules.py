"""Typed loader for config/compat_rules.yaml (declarations only; logic lives in engine.py)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from advisor.models import Severity


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^R-[A-Z0-9-]+$")
    name: str
    description: str
    severity: Severity
    applies_to: list[str] = ["*"]  # categories or "*"


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    rules: list[RuleDefinition] = Field(min_length=1)


def load_rules(path: Path) -> RuleSet:
    return RuleSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
