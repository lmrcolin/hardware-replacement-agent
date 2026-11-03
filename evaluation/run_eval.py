"""Evaluation entry point (`make eval`): validates the gold set and scores it.

Until the agent exists (B-18/B-19) scoring follows the deterministic path over the real catalog and
datasheets: derive_requirements -> evaluate -> rank, for every case that names its original part.
Cases that need NLU (no part number, clarification) are counted and reported as pending.
Exit code 1 only on safety violations (a must_not_recommend or non-ACTIVE part recommended).
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from advisor.compatibility import derive_requirements, evaluate
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry
from advisor.ingestion import discover_documents
from advisor.models import (
    CommercialStatus,
    CompatibilityLevel,
    DocumentType,
    ParsedQuery,
    Product,
)
from advisor.parsing import parse_catalog, parse_document
from advisor.recommendation import RankedOutput, rank

ROOT = Path(__file__).resolve().parents[1]
GOLD_SET = Path(__file__).with_name("gold_set.yaml")
CONFIRMED = (CompatibilityLevel.COMPATIBLE, CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS)


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

    @property
    def needs_agent(self) -> bool:
        return self.expect_clarification or self.expected_original is None


class GoldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[GoldCase] = Field(min_length=1)


def load_gold_set(path: Path = GOLD_SET) -> GoldSet:
    return GoldSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_products(root: Path = ROOT) -> dict[str, Product]:
    """Catalog + datasheets joined, exactly as the deterministic pipeline builds them."""
    registry = load_spec_registry(root / "config" / "spec_registry.yaml")
    records = discover_documents(root / "data" / "raw")
    catalog = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    docs = [parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET]
    joined, _ = join_catalog([extract_product(d, registry) for d in docs], catalog)
    return {p.part_number: p for p in joined}


def recommend(products: Mapping[str, Product], case: GoldCase) -> RankedOutput:
    assert case.expected_original is not None
    original = products[case.expected_original]
    query = ParsedQuery(original_text=case.query, part_numbers=[original.part_number])
    requirements = derive_requirements(original, query)
    results = [
        evaluate(original, candidate, requirements)
        for candidate in products.values()
        if candidate.part_number != original.part_number
    ]
    return rank(results, products)


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    status_ok: bool
    hit_at_1: bool
    level_ok: bool | None  # None when the case does not fix a level
    top: str | None
    top_level: CompatibilityLevel
    violations: tuple[str, ...]


def score_case(products: Mapping[str, Product], case: GoldCase) -> CaseScore:
    assert case.expected_original is not None
    original = products[case.expected_original]
    out = recommend(products, case)
    recs = out.recommendations
    top = recs[0] if recs else None
    top_level = top.compatibility.level if top else CompatibilityLevel.INCOMPATIBLE

    if case.expected_top:
        hit = top is not None and top.product.part_number in case.expected_top
    else:  # no substitute expected: nothing may be offered as confirmed
        hit = not any(r.compatibility.level in CONFIRMED for r in recs)

    violations = [
        f"recomienda {r.product.part_number} (must_not_recommend)"
        for r in recs
        if r.product.part_number in case.must_not_recommend
    ]
    violations += [
        f"recomienda {r.product.part_number} con estado {r.commercial.status}"
        for r in recs
        if r.commercial.status is not CommercialStatus.ACTIVE
    ]
    status = original.commercial.status if original.commercial else None
    return CaseScore(
        case_id=case.id,
        status_ok=status == case.expected_status,
        hit_at_1=hit,
        level_ok=None if case.expected_level is None else top_level == case.expected_level,
        top=top.product.part_number if top else None,
        top_level=top_level,
        violations=tuple(violations),
    )


def _pct(part: int, total: int) -> str:
    return f"{part}/{total} ({100 * part / total:.0f}%)" if total else "0/0"


def main() -> Literal[0, 1]:
    gold = load_gold_set()
    real = [c for c in gold.cases if not c.is_placeholder]
    print(f"gold set v{gold.version}: {len(gold.cases)} cases, {len(real)} verified")
    if not real:
        print("No verified cases yet; replace the PLACEHOLDER entries (B-22).")
        return 0

    scorable = [c for c in real if not c.needs_agent]
    pending = [c for c in real if c.needs_agent]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # DataConsistencyWarning from the catalog is expected
        products = load_products()
    scores = [score_case(products, c) for c in scorable]

    print(f"\nCamino determinista (sin agente): {len(scores)} casos")
    for s in scores:
        mark = "OK " if s.hit_at_1 and s.level_ok is not False and not s.violations else "XX "
        level = "" if s.level_ok is None else f" nivel={'ok' if s.level_ok else 'DIFF'}"
        print(f"  {mark}{s.case_id:<22} top={s.top or '-':<18} {s.top_level}{level}")
        for v in s.violations:
            print(f"       SEGURIDAD: {v}")

    leveled = [s for s in scores if s.level_ok is not None]
    violations = sum(len(s.violations) for s in scores)
    print("\nMétricas")
    print(f"  hit@1                    {_pct(sum(s.hit_at_1 for s in scores), len(scores))}")
    print(
        f"  nivel del top            {_pct(sum(bool(s.level_ok) for s in leveled), len(leveled))}"
    )
    print(f"  estado vs catálogo       {_pct(sum(s.status_ok for s in scores), len(scores))}")
    print(f"  violaciones de seguridad {violations} (meta 0)")
    print(f"  pendientes de agente     {len(pending)}: {', '.join(c.id for c in pending)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
