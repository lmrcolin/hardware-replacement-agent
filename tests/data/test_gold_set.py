"""Gold set (B-22): schema, consistency with the catalog and safety of the deterministic path."""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.data
ROOT = Path(__file__).resolve().parents[2]


def _run_eval() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "evaluation" / "run_eval.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


run_eval = _run_eval()


@pytest.fixture(scope="module")
def products() -> dict[str, object]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_eval.load_products()  # type: ignore[no-any-return]


def test_gold_set_is_valid_and_has_no_placeholders() -> None:
    gold = run_eval.load_gold_set()
    ids = [c.id for c in gold.cases]
    assert len(ids) == len(set(ids))
    assert not any(c.is_placeholder for c in gold.cases)
    assert all(c.verified_by for c in gold.cases)


def test_gold_parts_and_statuses_match_the_catalog(products: dict[str, object]) -> None:
    for case in run_eval.load_gold_set().cases:
        for part in [*case.expected_top, *case.must_not_recommend]:
            assert part in products, (case.id, part)
        if case.expected_original:
            original = products[case.expected_original]
            assert original.commercial.status == case.expected_status, case.id  # type: ignore[attr-defined]
        for part in case.expected_top:
            assert products[part].commercial.status == "ACTIVE", (case.id, part)  # type: ignore[attr-defined]


@pytest.mark.safety
def test_deterministic_path_has_no_safety_violations(products: dict[str, object]) -> None:
    cases = [c for c in run_eval.load_gold_set().cases if not c.needs_agent]
    scores = [run_eval.score_case(products, c) for c in cases]
    assert [(s.case_id, s.violations) for s in scores if s.violations] == []
