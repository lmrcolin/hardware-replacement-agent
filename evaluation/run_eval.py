"""Evaluation entry point (`make eval`). Validates the gold set; scoring is B-22."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from advisor.models import CommercialStatus, CompatibilityLevel

GOLD_SET = Path(__file__).with_name("gold_set.yaml")


class GoldCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str = Field(min_length=1)
    expected_original: str | None
    expected_status: CommercialStatus | None
    expected_top: list[str]
    expected_level: CompatibilityLevel | None
    must_not_recommend: list[str]
    expect_clarification: bool
    verified_by: str | None
    notes: str = ""

    @property
    def is_placeholder(self) -> bool:
        return self.id.startswith("PLACEHOLDER")


class GoldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[GoldCase] = Field(min_length=1)


def load_gold_set(path: Path = GOLD_SET) -> GoldSet:
    return GoldSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def main() -> Literal[0, 1]:
    gold = load_gold_set()
    real = [c for c in gold.cases if not c.is_placeholder]
    print(f"gold set v{gold.version}: {len(gold.cases)} cases, {len(real)} verified")
    if not real:
        print("No verified cases yet; replace the PLACEHOLDER entries (B-22).")
        return 0
    print("Scoring not implemented yet (B-22).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
