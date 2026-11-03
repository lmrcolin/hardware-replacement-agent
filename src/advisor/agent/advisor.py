"""Controlled advisor agent: tools decide; the LLM only parses the query and rephrases."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import networkx as nx

from advisor.agent.compose import draft_message, unverified_tokens
from advisor.commercial import CommercialEngine
from advisor.compatibility import derive_requirements, evaluate
from advisor.compatibility.engine import base_key, default_registry
from advisor.extraction import SpecRegistry
from advisor.kg import candidate_neighbors, resolve_part
from advisor.llm import (
    LLMClient,
    LLMUnavailableError,
    build_nlg_prompt,
    build_nlu_prompt,
    complete_json,
    generate,
    parse_query,
)
from advisor.models import (
    Category,
    CompatibilityLevel,
    CompatibilityResult,
    CustomerQuery,
    EdgeType,
    Operator,
    ParsedQuery,
    PartMatch,
    Product,
    Recommendation,
    RecommendationResponse,
    TechnicalRequirement,
)
from advisor.recommendation import rank
from advisor.retrieval import Retriever

log = logging.getLogger(__name__)

CONFIDENT = 0.85  # minimum PartMatch score to act without asking
SUGGEST = 0.6  # fuzzy matches above this are offered back, never assumed
AMBIGUITY_GAP = 0.05  # two matches closer than this → ask which one


class AgentStep(StrEnum):
    PARSE = "PARSE"
    RESOLVE = "RESOLVE"
    CLARIFY = "CLARIFY"
    STATUS = "STATUS"
    DISCOVER = "DISCOVER"
    VALIDATE = "VALIDATE"
    RANK = "RANK"
    COMPOSE = "COMPOSE"
    VERIFY = "VERIFY"


class Advisor(Protocol):
    """What the UI depends on. Implemented by AdvisorAgent and app.mock_agent.MockAdvisorAgent."""

    def answer(self, query: CustomerQuery) -> RecommendationResponse: ...


@dataclass
class _Run:
    query: CustomerQuery
    trace: list[AgentStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)


class AdvisorAgent:
    def __init__(
        self,
        *,
        graph: nx.MultiDiGraph,
        products: Sequence[Product],
        commercial: CommercialEngine,
        retriever: Retriever,
        llm_chain: Sequence[LLMClient],
        registry: SpecRegistry | None = None,
    ) -> None:
        self.graph = graph
        self.products = {p.part_number: p for p in products}
        self.commercial = commercial
        self.retriever = retriever
        self.llm_chain = list(llm_chain)
        self.registry = registry or default_registry()
        self.last_trace: list[AgentStep] = []

    # ------------------------------------------------------------------ steps

    def _parse(self, run: _Run) -> ParsedQuery:
        run.trace.append(AgentStep.PARSE)
        allowed = {
            cat.value: [
                f"{k} ({d.unit or d.type})" for k, d in self.registry.for_category(cat).items()
            ]
            for cat in Category
        }
        prompt = build_nlu_prompt(run.query.text, allowed)
        try:
            parsed, provider = complete_json(self.llm_chain, prompt, ParsedQuery)
        except LLMUnavailableError:
            parsed, provider = parse_query(run.query.text), "rules"
        run.providers.append(provider)
        return self._sanitize(parsed, run)

    def _sanitize(self, parsed: ParsedQuery, run: _Run) -> ParsedQuery:
        """Drop requirements with unknown keys or numbers absent from the customer's text."""
        text = run.query.text.replace(",", "")
        kept: list[TechnicalRequirement] = []
        for req in parsed.requirements:
            keys = self.registry.for_category(parsed.category) if parsed.category else {}
            if base_key(req.key) not in keys:
                run.warnings.append(f"Requisito ignorado (clave desconocida): {req.key}")
                continue
            if isinstance(req.value, int | float) and not isinstance(req.value, bool):
                number = f"{req.value:g}"
                present = re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", text)
                if not present and req.operator in (Operator.GTE, Operator.LTE, Operator.EQ):
                    run.warnings.append(
                        f"Requisito ignorado (cifra no presente en la consulta): {req.key}"
                    )
                    continue
            kept.append(req.model_copy(update={"origin": req.origin}))
        return parsed.model_copy(update={"original_text": run.query.text, "requirements": kept})

    def _resolve(self, parsed: ParsedQuery, run: _Run) -> list[PartMatch]:
        run.trace.append(AgentStep.RESOLVE)
        matches = {m.part_number: m for m in resolve_part(self.graph, run.query.text)}
        for token in parsed.part_numbers:
            for m in resolve_part(self.graph, token, limit=1):
                if m.part_number not in matches or m.score > matches[m.part_number].score:
                    matches[m.part_number] = m
        return sorted(matches.values(), key=lambda m: (-m.score, m.part_number))

    def _clarify(self, run: _Run, parsed: ParsedQuery, question: str) -> RecommendationResponse:
        run.trace.append(AgentStep.CLARIFY)
        return self._response(
            run,
            parsed,
            None,
            [],
            [],
            question,
            message="Necesito un dato más para buscar un sustituto.",
        )

    def _discover(self, original: Product, run: _Run) -> list[Product]:
        run.trace.append(AgentStep.DISCOVER)
        pool = {p.part_number for p in self.products.values() if p.category is original.category}
        for c in candidate_neighbors(self.graph, original.part_number, max_candidates=50):
            pool.add(c.part_number)
        for hit in self.retriever.search(run.query.text, top_k=8):
            pool.update(pn for pn in hit.chunk.part_numbers if pn in self.products)
        pool.discard(original.part_number)
        return [self.products[p] for p in sorted(pool) if p in self.products]

    def _successors(self, part_number: str) -> list[str]:
        node = f"product:{part_number}"
        if node not in self.graph:
            return []
        return [
            self.graph.nodes[t]["label"]
            for _, t, k in self.graph.out_edges(node, keys=True)
            if k == EdgeType.MIGRATES_TO.value
        ]

    # ------------------------------------------------------------------ answer

    def answer(self, query: CustomerQuery) -> RecommendationResponse:
        """PARSE→RESOLVE→CLARIFY|STATUS→DISCOVER→VALIDATE→RANK→COMPOSE→VERIFY."""
        run = _Run(query)
        parsed = self._parse(run)
        matches = self._resolve(parsed, run)
        confident = [m for m in matches if m.score >= CONFIDENT]

        if len(confident) > 1 and confident[0].score - confident[1].score < AMBIGUITY_GAP:
            options = ", ".join(m.part_number for m in confident[:4])
            return self._clarify(
                run, parsed, f"¿A cuál de estos part numbers te refieres: {options}?"
            )
        if not confident:
            suggestions = [m.part_number for m in matches if m.score >= SUGGEST][:3]
            if suggestions:
                options = " o ".join(suggestions)
                question = f"No encontré ese part number exacto. ¿Te refieres a {options}?"
                return self._clarify(run, parsed, question)
            if parsed.category is None or not parsed.requirements:
                question = parsed.clarification_question or (
                    "¿Qué part number quieres reemplazar o qué requisitos técnicos debe cumplir "
                    f"el componente{' de ' + parsed.category.value if parsed.category else ''}?"
                )
                return self._clarify(run, parsed, question)
            return self._find_by_requirements(run, parsed)

        original = self.products[confident[0].part_number]
        run.trace.append(AgentStep.STATUS)
        self.commercial.get(
            original.part_number
        )  # catalog is the source of truth; KeyError if absent
        if parsed.category is not None and parsed.category is not original.category:
            run.warnings.append(
                f"La consulta parece de categoría {parsed.category}, pero "
                f"{original.part_number} es {original.category} en el catálogo; se usa la del "
                "catálogo."
            )
        parsed = parsed.model_copy(update={"category": original.category})
        candidates = self._discover(original, run)

        run.trace.append(AgentStep.VALIDATE)
        requirements = derive_requirements(original, parsed, registry=self.registry)
        results = [evaluate(original, c, requirements, registry=self.registry) for c in candidates]

        run.trace.append(AgentStep.RANK)
        ranked = rank(results, self.products)
        by_candidate = {r.candidate_part_number: r for r in results}
        blocked = {
            s: by_candidate[s]
            for s in self._successors(original.part_number)
            if s in by_candidate and by_candidate[s].level is CompatibilityLevel.INCOMPATIBLE
        }
        return self._response(
            run, parsed, original, ranked.recommendations, ranked.risky_options, None,
            blocked=blocked, unverified=ranked.unverified_options,
        )  # fmt: skip

    def _find_by_requirements(self, run: _Run, parsed: ParsedQuery) -> RecommendationResponse:
        """No part number: evaluate every product of the category against the query alone."""
        assert parsed.category is not None
        reference = Product(part_number="CONSULTA", manufacturer="", category=parsed.category)
        run.trace.extend([AgentStep.DISCOVER, AgentStep.VALIDATE])
        candidates = [p for p in self.products.values() if p.category is parsed.category]
        results = [
            evaluate(reference, c, parsed.requirements, registry=self.registry) for c in candidates
        ]
        run.trace.append(AgentStep.RANK)
        ranked = rank(results, self.products)
        return self._response(
            run, parsed, None, ranked.recommendations, ranked.risky_options, None,
            unverified=ranked.unverified_options,
        )  # fmt: skip

    def _response(
        self,
        run: _Run,
        parsed: ParsedQuery,
        original: Product | None,
        recommendations: Sequence[Recommendation],
        risky: Sequence[Recommendation],
        clarification: str | None,
        *,
        message: str | None = None,
        blocked: Mapping[str, CompatibilityResult] | None = None,
        unverified: Sequence[Recommendation] = (),
    ) -> RecommendationResponse:
        recs = list(recommendations)
        risk = list(risky)
        if message is None:
            run.trace.append(AgentStep.COMPOSE)
            draft = draft_message(original, recs, risk, blocked or {}, unverified)
            message = self._rephrase(draft, run)
        else:
            run.providers.append("template")
        self.last_trace = run.trace
        return RecommendationResponse(
            query=run.query,
            parsed_query=parsed,
            original=original,
            recommendations=recs,
            risky_options=risk,
            unverified_options=list(unverified),
            clarification_question=clarification,
            message=message,
            llm_provider="+".join(dict.fromkeys(run.providers)),
            warnings=run.warnings,
            is_synthetic=any(p.is_synthetic for p in self.products.values()),
        )

    def _rephrase(self, draft: str, run: _Run) -> str:
        try:
            text, provider = generate(self.llm_chain, build_nlg_prompt(draft))
        except LLMUnavailableError:
            text, provider = draft, "template"
        run.trace.append(AgentStep.VERIFY)
        bad = unverified_tokens(text, draft, self.products)
        if bad:
            run.warnings.append(
                f"El texto generado por {provider} contenía datos no verificados "
                f"({', '.join(bad[:5])}); se muestra la versión verificada."
            )
            text, provider = draft, "template"
        run.providers.append(provider)
        return text
