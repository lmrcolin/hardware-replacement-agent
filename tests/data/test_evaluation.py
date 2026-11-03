"""Gold-set integrity (checked against the catalog, not the agent) and the evaluation gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from advisor.ingestion import discover_documents
from advisor.models import CommercialStatus, DocumentType
from advisor.parsing import parse_catalog
from evaluation.run_eval import gates_pass, load_gold_set, run

pytestmark = pytest.mark.data
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def catalog():  # type: ignore[no-untyped-def]
    records = discover_documents(ROOT / "data" / "raw")
    rows = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    return {r.part_number: r for r in rows}, {r.filename for r in records}


def test_gold_set_is_consistent_with_the_pdfs(catalog) -> None:  # type: ignore[no-untyped-def]
    rows, filenames = catalog
    gold = load_gold_set()
    assert len({c.id for c in gold.cases}) == len(gold.cases)
    for case in gold.cases:
        mentioned = (
            (case.expected_top or []) + case.must_not_recommend + case.clarification_mentions
        )
        if case.expected_original:
            mentioned.append(case.expected_original)
            assert rows[case.expected_original].status is case.expected_status, case.id
        assert set(mentioned) <= set(rows), (case.id, set(mentioned) - set(rows))
        for part in case.expected_top or []:
            assert rows[part].status is CommercialStatus.ACTIVE, (case.id, part)
        assert set(case.relevant_documents) <= filenames, case.id
        assert case.notes and case.verified_by, case.id


def test_evaluation_gates_pass() -> None:
    summary, results, provider = run()
    assert provider == "template" and summary["cases"] == len(results) >= 20
    assert gates_pass(summary), summary
    assert summary["hit_at_1"] is not None and summary["hit_at_1"] >= 0.9
