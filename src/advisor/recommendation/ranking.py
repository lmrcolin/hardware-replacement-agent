"""Ranking contract: level > coverage > score; inventory only breaks ties."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from advisor.models import CompatibilityResult, Product, Recommendation


class RankedOutput(NamedTuple):
    recommendations: list[Recommendation]  # ACTIVE only
    risky_options: list[Recommendation]  # NRND only


def rank(results: Sequence[CompatibilityResult], products: Mapping[str, Product]) -> RankedOutput:
    """Lexicographic ranking; excludes INCOMPATIBLE, DISCONTINUED and EOL. B-17."""
    raise NotImplementedError("B-17 recommendation.rank")
