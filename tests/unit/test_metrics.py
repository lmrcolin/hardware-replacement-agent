from __future__ import annotations

import pytest

from evaluation.metrics import mean, precision_at_k, recall_at_k, reciprocal_rank

RANKING = ["a", "b", "a", "c", "d"]  # duplicate "a" counts once → effective ranking a, b, c, d


def test_precision_at_k_hand_computed() -> None:
    assert precision_at_k(RANKING, {"a", "c"}, 3) == pytest.approx(2 / 3)
    assert precision_at_k(RANKING, {"z"}, 2) == 0.0


def test_recall_at_k_hand_computed() -> None:
    assert recall_at_k(RANKING, {"a", "c", "z"}, 3) == pytest.approx(2 / 3)
    assert recall_at_k(RANKING, {"a"}, 10) == 1.0  # k larger than the ranking


def test_reciprocal_rank() -> None:
    assert reciprocal_rank(RANKING, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKING, {"z"}) == 0.0


def test_empty_relevant_set_is_not_scored() -> None:
    assert precision_at_k(RANKING, set(), 3) is None
    assert recall_at_k(RANKING, set(), 3) is None
    assert reciprocal_rank(RANKING, set()) is None
    assert precision_at_k(RANKING, {"a"}, 0) is None


def test_mean_ignores_unscored() -> None:
    assert mean([1.0, None, 0.0]) == 0.5
    assert mean([None]) is None
