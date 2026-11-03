"""Evaluation entry point (`make eval`).

Runs the real AdvisorAgent (deterministic template LLM by default) over evaluation/gold_set.yaml and
reports retrieval, resolution and recommendation metrics. Safety gates (non-sellable or forbidden
recommendations, prices/stock that differ from the catalog, unverified figures in the text) must be
zero; otherwise the command exits with status 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from advisor.agent import AdvisorAgent
from advisor.commercial import CommercialEngine
from advisor.config import REPO_ROOT, get_settings
from advisor.llm import LLMClient, TemplateClient, build_llm_chain
from advisor.models import (
    CommercialStatus,
    CompatibilityLevel,
    CustomerQuery,
    RecommendationResponse,
)
from advisor.pipeline import BuiltArtifacts, build_in_memory
from advisor.retrieval import BM25Retriever
from evaluation.metrics import mean, precision_at_k, recall_at_k, reciprocal_rank

GOLD_SET = Path(__file__).with_name("gold_set.yaml")
REPORT_MD = Path(__file__).with_name("report.md")
RESULTS_JSON = REPO_ROOT / "artifacts" / "eval" / "results.json"
CONFIRMED = (CompatibilityLevel.COMPATIBLE, CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS)
RETRIEVAL_CHUNKS = 20
LIMITATIONS = [
    "",
    "## Cómo leer estas cifras",
    "",
    "- El golden set es pequeño (~20 casos) y lo escribió el mismo equipo a partir de",
    "  los PDFs. Dos fallos de su primera ejecución (alias de modelo 'SN860' y sugerencia",
    "  ante erratas) se corrigieron en el sistema: un 1.00 indica consistencia con casos",
    "  conocidos, no generalización. Faltan un conjunto ciego y un experto de dominio.",
    "- Precision@K de recuperación está acotada por construcción: con 1 documento",
    "  relevante, P@3 <= 0.33. Recall@5 y MRR son más informativas (33 PDFs).",
    "- Las puertas `gate_*` son bloqueantes: `make eval` falla si alguna es > 0.",
    "- LLM `template` = sin modelo (determinista); `--llm configured` usa la cadena de settings.",
]


class GoldCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str = Field(min_length=1)
    expected_original: str | None
    expected_status: CommercialStatus | None
    expected_top: list[str] | None
    expected_level: CompatibilityLevel | None
    must_not_recommend: list[str]
    expect_clarification: bool
    clarification_mentions: list[str] = []
    relevant_documents: list[str] = []
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


@dataclass
class CaseResult:
    id: str
    query: str
    resolved: str | None
    resolution_ok: bool | None
    status_ok: bool | None
    clarification_ok: bool
    hit_at_1: bool | None
    reciprocal_rank: float | None
    level_ok: bool | None
    recommendations: list[str]
    forbidden: list[str] = field(default_factory=list)
    non_active: list[str] = field(default_factory=list)
    price_mismatch: list[str] = field(default_factory=list)
    unverified_text: bool = False
    p_at_3: float | None = None
    p_at_5: float | None = None
    r_at_5: float | None = None
    retrieval_rr: float | None = None


def _document_ranking(retriever: BM25Retriever, names: dict[str, str], query: str) -> list[str]:
    hits = retriever.search(query, top_k=RETRIEVAL_CHUNKS)
    return [names[h.chunk.document_id] for h in hits]


def evaluate_case(
    case: GoldCase, resp: RecommendationResponse, built: BuiltArtifacts, docs: list[str]
) -> CaseResult:
    catalog = {c.part_number: c for c in built.catalog}
    recs = [r.product.part_number for r in resp.recommendations]
    confirmed = [r for r in resp.recommendations if r.compatibility.level in CONFIRMED]
    clarified = bool(resp.clarification_question)
    resolved = resp.original.part_number if resp.original else None

    resolution_ok: bool | None = None
    if not case.expect_clarification:
        resolution_ok = resolved == case.expected_original
    status_ok: bool | None = None
    if case.expected_status is not None:
        status = (
            resp.original.commercial.status if resp.original and resp.original.commercial else None
        )
        status_ok = status is case.expected_status

    hit: bool | None = None
    rr: float | None = None
    if case.expected_top is not None and not case.expect_clarification:
        if not case.expected_top:
            hit = not confirmed
        else:
            hit = bool(confirmed) and confirmed[0].product.part_number in case.expected_top
            rr = reciprocal_rank(recs, set(case.expected_top))
    level_ok: bool | None = None
    if case.expected_level is not None:
        level_ok = bool(confirmed) and confirmed[0].compatibility.level is case.expected_level

    relevant = set(case.relevant_documents)
    return CaseResult(
        id=case.id,
        query=case.query,
        resolved=resolved,
        resolution_ok=resolution_ok,
        status_ok=status_ok,
        clarification_ok=clarified == case.expect_clarification
        and all(p in (resp.clarification_question or "") for p in case.clarification_mentions),
        hit_at_1=hit,
        reciprocal_rank=rr,
        level_ok=level_ok,
        recommendations=recs,
        forbidden=[p for p in recs if p in case.must_not_recommend],
        non_active=[
            r.product.part_number
            for r in resp.recommendations
            if r.commercial.status is not CommercialStatus.ACTIVE
        ],
        price_mismatch=[
            r.product.part_number
            for r in resp.recommendations + resp.risky_options + resp.unverified_options
            if (r.commercial.price_usd, r.commercial.stock_units)
            != (
                catalog[r.product.part_number].price_usd,
                catalog[r.product.part_number].stock_units,
            )
        ],
        unverified_text=any("no verificados" in w for w in resp.warnings),
        p_at_3=precision_at_k(docs, relevant, 3),
        p_at_5=precision_at_k(docs, relevant, 5),
        r_at_5=recall_at_k(docs, relevant, 5),
        retrieval_rr=reciprocal_rank(docs, relevant),
    )


def _rate(values: list[bool | None]) -> float | None:
    scored = [v for v in values if v is not None]
    return sum(scored) / len(scored) if scored else None


def summarize(results: list[CaseResult]) -> dict[str, float | int | None]:
    return {
        "cases": len(results),
        "resolution_accuracy": _rate([r.resolution_ok for r in results]),
        "status_accuracy": _rate([r.status_ok for r in results]),
        "clarification_accuracy": _rate([r.clarification_ok for r in results]),
        "hit_at_1": _rate([r.hit_at_1 for r in results]),
        "mrr_recommendation": mean([r.reciprocal_rank for r in results]),
        "level_accuracy": _rate([r.level_ok for r in results]),
        "retrieval_precision_at_3": mean([r.p_at_3 for r in results]),
        "retrieval_precision_at_5": mean([r.p_at_5 for r in results]),
        "retrieval_recall_at_5": mean([r.r_at_5 for r in results]),
        "retrieval_mrr": mean([r.retrieval_rr for r in results]),
        "gate_forbidden_recommendations": sum(len(r.forbidden) for r in results),
        "gate_non_active_recommendations": sum(len(r.non_active) for r in results),
        "gate_price_stock_mismatches": sum(len(r.price_mismatch) for r in results),
        "gate_unverified_text": sum(r.unverified_text for r in results),
    }


def gates_pass(summary: dict[str, float | int | None]) -> bool:
    return all(summary[k] == 0 for k in summary if k.startswith("gate_"))


def _fmt(value: float | int | bool | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_markdown(
    summary: dict[str, float | int | None],
    results: list[CaseResult],
    provider: str,
    source: str = "gold_set.yaml",
) -> str:
    lines = [
        "# Evaluación — Emerson Replacement Advisor",
        "",
        f"Generado por `make eval` el {datetime.now(UTC).date().isoformat()} · LLM: `{provider}` · "
        f"{summary['cases']} casos de `evaluation/{source}` (verificados contra los PDFs).",
        "",
        f"**Puertas de seguridad:** {'OK (todas en 0)' if gates_pass(summary) else 'FALLAN'}",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        *[f"| {k} | {_fmt(v)} |" for k, v in summary.items()],
        "",
        "## Por caso",
        "",
        "| Caso | Resuelto | Res. | Estado | Aclar. | Hit@1 | Nivel | Recomendaciones "
        "| P@3 | R@5 | MRR ret. |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.resolved or '—'} | {_fmt(r.resolution_ok)} | {_fmt(r.status_ok)} | "
            f"{_fmt(r.clarification_ok)} | {_fmt(r.hit_at_1)} | {_fmt(r.level_ok)} | "
            f"{', '.join(r.recommendations) or '—'} | {_fmt(r.p_at_3)} | {_fmt(r.r_at_5)} | "
            f"{_fmt(r.retrieval_rr)} |"
        )
    lines += LIMITATIONS
    problems = [
        r for r in results if r.forbidden or r.non_active or r.price_mismatch or r.unverified_text
    ]
    if problems:
        lines += ["", "## Violaciones de puertas", ""]
        lines += [
            f"- {r.id}: prohibidas={r.forbidden} no_active={r.non_active} "
            f"precio/stock={r.price_mismatch} texto_no_verificado={r.unverified_text}"
            for r in problems
        ]
    return "\n".join(lines) + "\n"


Summary = dict[str, float | int | None]


def run(
    chain: list[LLMClient] | None = None, gold: GoldSet | None = None
) -> tuple[Summary, list[CaseResult], str]:
    gold = gold or load_gold_set()
    built = build_in_memory()
    retriever = BM25Retriever(built.chunks)
    chain = chain or [TemplateClient()]
    agent = AdvisorAgent(
        graph=built.graph,
        products=built.products,
        commercial=CommercialEngine(built.catalog),
        retriever=retriever,
        llm_chain=chain,
    )
    results = []
    for case in gold.cases:
        if case.is_placeholder:
            continue
        resp = agent.answer(CustomerQuery(text=case.query))
        docs = _document_ranking(retriever, built.document_names, case.query)
        results.append(evaluate_case(case, resp, built, docs))
    return summarize(results), results, "+".join(c.name for c in chain)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        choices=["template", "configured"],
        default="template",
        help="template (deterministic, default) or the chain from settings",
    )
    parser.add_argument(
        "--no-report", action="store_true", help="do not rewrite evaluation/report.md"
    )
    parser.add_argument(
        "--gold", type=Path, default=GOLD_SET, help="case file (default: evaluation/gold_set.yaml)"
    )
    args = parser.parse_args()
    gold = load_gold_set(args.gold)
    if not [c for c in gold.cases if not c.is_placeholder]:
        print(f"{args.gold.name}: sin casos reales todavía (solo PLACEHOLDER); nada que evaluar.")
        return 0
    chain = build_llm_chain(get_settings()) if args.llm == "configured" else None
    summary, results, provider = run(chain, gold)
    report = render_markdown(summary, results, provider, args.gold.name)
    print(report)
    if not args.no_report:
        report_md = (
            REPORT_MD
            if args.gold == GOLD_SET
            else REPORT_MD.with_name(f"report_{args.gold.stem}.md")
        )
        report_md.write_text(report, encoding="utf-8")
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(
            json.dumps(
                {"summary": summary, "cases": [asdict(r) for r in results]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return 0 if gates_pass(summary) else 1


if __name__ == "__main__":
    sys.exit(main())
