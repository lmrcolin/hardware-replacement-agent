"""Pure retrieval metrics. An empty relevant set yields None (not scored), never 0 or 1."""

from __future__ import annotations

from collections.abc import Sequence


def _dedupe(ranking: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in ranking if not (x in seen or seen.add(x))]


def precision_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float | None:
    """|top-k ∩ relevant| / k; duplicates in the ranking count once."""
    if not relevant or k <= 0:
        return None
    top = _dedupe(ranking)[:k]
    return sum(x in relevant for x in top) / k


def recall_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float | None:
    if not relevant or k <= 0:
        return None
    top = _dedupe(ranking)[:k]
    return sum(x in relevant for x in top) / len(relevant)


def reciprocal_rank(ranking: Sequence[str], relevant: set[str]) -> float | None:
    """1 / rank of the first relevant item; 0.0 if none appears; None if nothing is relevant."""
    if not relevant:
        return None
    for i, x in enumerate(_dedupe(ranking), start=1):
        if x in relevant:
            return 1.0 / i
    return 0.0


def mean(values: Sequence[float | None]) -> float | None:
    scored = [v for v in values if v is not None]
    return sum(scored) / len(scored) if scored else None
