"""Controlled advisor agent: tools decide; the LLM only parses the query and rephrases."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

import networkx as nx

from advisor.agent.compose import draft_message, fail_reasons, money, unverified_tokens
from advisor.commercial import CommercialEngine
from advisor.compatibility import derive_requirements, evaluate
from advisor.compatibility.engine import ANY, base_key, default_registry
from advisor.extraction import SpecDefinition, SpecRegistry
from advisor.extraction.registry import fold
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
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    CustomerQuery,
    EdgeType,
    Operator,
    ParsedQuery,
    PartMatch,
    Priority,
    Product,
    Recommendation,
    RecommendationResponse,
    RequirementOrigin,
    RuleOutcome,
    TechnicalRequirement,
)
from advisor.recommendation import rank
from advisor.retrieval import RetrievalUnavailableError, Retriever

log = logging.getLogger(__name__)

CONFIDENT = 0.85  # minimum PartMatch score to act without asking
SUGGEST = 0.6  # fuzzy matches above this are offered back, never assumed
AMBIGUITY_GAP = 0.05  # two matches closer than this → ask which one
MAX_REJECTED = 3  # discarded candidates explained when nothing is recommended

# Explicit customer constraints, read deterministically from the query (never by the LLM).
CHEAP = re.compile(r"barat|econ[oó]mic|cheap|low[- ]cost|menor precio|bajo costo|presupuesto", re.I)
SAME_FOOTPRINT = re.compile(
    r"pin[- ]?(?:to[- ]?pin[- ]?)?compatible|drop[- ]?in|mismo encapsulado|same package|footprint",
    re.I,
)
MAKER_CONSTRAINT = re.compile(
    r"(?:debe ser|tiene que ser|que sea|s[oó]lo|[uú]nicamente|marca|fabricante|must be|only)"
    r"\s+(?:de\s+|del\s+|from\s+)?(.{1,60})",
    re.I,
)
LEVEL_ORDER = list(CompatibilityLevel)


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
            cat.value: [_describe(k, d) for k, d in self.registry.for_category(cat).items()]
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
            definition = keys[base_key(req.key)]
            if definition.keywords and req.operator in (Operator.HAS, Operator.IN):
                kept.extend(self._canonical_values(req, definition, run))
                continue
            kept.append(self._registry_operator(req, definition.comparison, run))
        unique = list({(r.key, r.operator, str(r.value)): r for r in kept}.values())
        return parsed.model_copy(update={"original_text": run.query.text, "requirements": unique})

    @staticmethod
    def _canonical_values(
        req: TechnicalRequirement, definition: SpecDefinition, run: _Run
    ) -> list[TechnicalRequirement]:
        """Map free-text values ('humedad', ['gases volátiles']) to registry keywords.

        HAS with a list becomes one HAS per item; IN keeps the (canonical) list. Values outside the
        vocabulary are dropped with a warning instead of failing every candidate.
        """
        values = req.value if isinstance(req.value, list) else [req.value]
        canonical: list[str] = []
        for value in values:
            if value == ANY:
                canonical.append(ANY)
                continue
            keyword = definition.canonical(str(value))
            if keyword is None:
                run.warnings.append(
                    f"Requisito ignorado (valor no reconocido para {req.key}): {value}"
                )
            elif keyword not in canonical:
                canonical.append(keyword)
        if req.operator is Operator.IN:
            items = [v for v in canonical if v != ANY]
            return [req.model_copy(update={"value": items})] if items else []
        return [
            TechnicalRequirement.model_validate({**req.model_dump(), "value": v}) for v in canonical
        ]

    @staticmethod
    def _registry_operator(
        req: TechnicalRequirement, comparison: str, run: _Run
    ) -> TechnicalRequirement:
        """Numeric capability keys compare as the registry says (gte/lte), never as EQ.

        "100 Gigabit" means *at least* 100 Gb/s; an LLM returning EQ would silently turn faster,
        compatible parts into failures.
        """
        if req.operator is not Operator.EQ or comparison not in ("gte", "lte"):
            return req
        operator = Operator.GTE if comparison == "gte" else Operator.LTE
        symbol = "≥" if operator is Operator.GTE else "≤"
        run.warnings.append(f"Se interpretó {req.key} = {req.value} como {symbol} {req.value}.")
        return TechnicalRequirement.model_validate({**req.model_dump(), "operator": operator})

    def _resolve(self, parsed: ParsedQuery, run: _Run) -> list[PartMatch]:
        run.trace.append(AgentStep.RESOLVE)
        matches = {m.part_number: m for m in resolve_part(self.graph, run.query.text)}
        for token in parsed.part_numbers:
            for m in resolve_part(self.graph, token, limit=1):
                if m.part_number not in matches or m.score > matches[m.part_number].score:
                    matches[m.part_number] = m
        return sorted(matches.values(), key=lambda m: (-m.score, m.part_number))

    def _clarify(
        self, run: _Run, parsed: ParsedQuery, question: str, *, options: str = ""
    ) -> RecommendationResponse:
        run.trace.append(AgentStep.CLARIFY)
        message = "Necesito un dato más para buscar un sustituto."
        if options:
            message = f"{options}\n{message}"
        return self._response(run, parsed, None, [], [], question, message=message)

    def _catalog_options(self, parsed: ParsedQuery, run: _Run) -> str:
        """Vague query with a known category: show what is for sale while asking for the need."""
        if parsed.category is None:
            return ""
        active = [
            (p.part_number, p.commercial)
            for p in self.products.values()
            if p.category is parsed.category
            and p.commercial is not None
            and p.commercial.status is CommercialStatus.ACTIVE
        ]
        if not active:
            return ""
        cheap = CHEAP.search(run.query.text) is not None
        if cheap:
            active.sort(key=lambda pc: (pc[1].price_usd or Decimal("Infinity"), pc[0]))
        else:
            active.sort(key=lambda pc: (-(pc[1].stock_units or 0), pc[0]))
        order = "de menor a mayor precio" if cheap else "por inventario"
        lines = [
            f"Opciones ACTIVE de {parsed.category.value} en el catálogo ({order}; "
            "compatibilidad aún sin validar):"
        ]
        lines += [
            f"- {pn} — {c.description}: {money(c.price_usd)}; {c.stock_units} unidades."
            for pn, c in active
        ]
        return "\n".join(lines)

    def _discover(self, original: Product, run: _Run) -> list[Product]:
        run.trace.append(AgentStep.DISCOVER)
        pool = {p.part_number for p in self.products.values() if p.category is original.category}
        for c in candidate_neighbors(self.graph, original.part_number, max_candidates=50):
            pool.add(c.part_number)
        try:
            hits = self.retriever.search(run.query.text, top_k=8)
        except RetrievalUnavailableError as exc:
            hits = []
            run.warnings.append(
                f"Búsqueda documental no disponible ({exc}); se usa catálogo y grafo."
            )
        for error in getattr(self.retriever, "last_errors", []):
            run.warnings.append(
                f"Búsqueda semántica no disponible; se usó solo BM25 ({error[:120]})."
            )
        for hit in hits:
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
                return self._clarify(
                    run, parsed, question, options=self._catalog_options(parsed, run)
                )
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
        parsed = self._footprint_requirement(parsed, original, run)
        candidates, rejected = self._maker_filter(
            self._discover(original, run), original.category, run
        )

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
        rejected += self._rejected(results, exclude=set(blocked))
        return self._response(
            run, parsed, original, self._by_price(ranked.recommendations, run),
            ranked.risky_options, None, blocked=blocked, unverified=ranked.unverified_options,
            rejected=rejected,
        )  # fmt: skip

    def _find_by_requirements(self, run: _Run, parsed: ParsedQuery) -> RecommendationResponse:
        """No part number: evaluate every product of the category against the query alone."""
        assert parsed.category is not None
        reference = Product(part_number="CONSULTA", manufacturer="", category=parsed.category)
        run.trace.extend([AgentStep.DISCOVER, AgentStep.VALIDATE])
        candidates, rejected = self._maker_filter(
            [p for p in self.products.values() if p.category is parsed.category],
            parsed.category,
            run,
        )
        results = [
            evaluate(reference, c, parsed.requirements, registry=self.registry) for c in candidates
        ]
        run.trace.append(AgentStep.RANK)
        ranked = rank(results, self.products)
        rejected += self._rejected(results, exclude=set())
        return self._response(
            run, parsed, None, self._by_price(ranked.recommendations, run),
            ranked.risky_options, None, unverified=ranked.unverified_options, rejected=rejected,
        )  # fmt: skip

    # ------------------------------------------------------------ constraints

    def _footprint_requirement(
        self, parsed: ParsedQuery, original: Product, run: _Run
    ) -> ParsedQuery:
        """ "Pin compatible" / "drop-in" makes the original's package a MUST requirement."""
        if not SAME_FOOTPRINT.search(run.query.text):
            return parsed
        package = next((s for s in original.specifications if s.key == "package"), None)
        if package is None or package.value is None:
            run.warnings.append(
                f"Se pidió compatibilidad pin a pin, pero el datasheet de {original.part_number} "
                "no declara el encapsulado: no se puede verificar."
            )
            return parsed
        requirement = TechnicalRequirement(
            key="package", operator=Operator.EQ, value=package.value,
            priority=Priority.MUST, origin=RequirementOrigin.QUERY,
        )  # fmt: skip
        return parsed.model_copy(update={"requirements": [*parsed.requirements, requirement]})

    def _maker_filter(
        self, candidates: Sequence[Product], category: Category, run: _Run
    ) -> tuple[list[Product], list[tuple[str, str, list[str]]]]:
        """Honor "debe ser de <fabricante>": other makers are discarded with the reason."""
        match = MAKER_CONSTRAINT.search(run.query.text)
        if match is None:
            return list(candidates), []
        wanted_text = fold(match.group(1))
        makers = {
            word
            for p in self.products.values()
            if p.commercial is not None
            for word in re.findall(r"[a-z0-9]{3,}", fold(p.commercial.manufacturer))
            if re.search(rf"(?<![a-z0-9]){word}(?![a-z0-9])", wanted_text)
        }
        if not makers:
            return list(candidates), []
        kept, rejected = [], []
        asked = re.split(r"\s+(?:y|e|and|con|with)\s+|[,.;]", match.group(1).strip())[0]
        for c in candidates:
            maker = c.commercial.manufacturer if c.commercial else c.manufacturer
            if set(re.findall(r"[a-z0-9]{3,}", fold(maker))) & makers:
                kept.append(c)
            elif c.category is category:
                description = c.commercial.description if c.commercial else c.part_number
                rejected.append(
                    (c.part_number, description, [f"fabricante {maker}; se pidió {asked}"])
                )
        run.warnings.append(f"Solo se consideran fabricantes que coinciden con: {asked}.")
        return kept, rejected

    def _rejected(
        self, results: Sequence[CompatibilityResult], *, exclude: set[str]
    ) -> list[tuple[str, str, list[str]]]:
        """Best same-category candidates that failed a critical rule, with the reason."""
        failed = [
            r
            for r in results
            if r.level is CompatibilityLevel.INCOMPATIBLE
            and r.candidate_part_number not in exclude
            and all(
                x.outcome is not RuleOutcome.FAIL for x in r.rule_results if x.rule_id == "R-CAT"
            )
        ]
        failed.sort(key=lambda r: (-r.score, r.candidate_part_number))
        out = []
        for r in failed[:MAX_REJECTED]:
            product = self.products[r.candidate_part_number]
            description = (
                product.commercial.description if product.commercial else product.part_number
            )
            out.append((r.candidate_part_number, description, fail_reasons(r)))
        return out

    @staticmethod
    def _by_price(recommendations: Sequence[Recommendation], run: _Run) -> list[Recommendation]:
        """ "Lo más barato": within the same compatibility level, cheaper first."""
        recs = list(recommendations)
        if not CHEAP.search(run.query.text) or len(recs) < 2:
            return recs
        recs.sort(
            key=lambda r: (
                LEVEL_ORDER.index(r.compatibility.level),
                r.commercial.price_usd
                if r.commercial.price_usd is not None
                else Decimal("Infinity"),
            )
        )
        run.warnings.append(
            "Se pidió la opción más económica: mismo nivel de compatibilidad, menor precio primero."
        )
        return [r.model_copy(update={"rank": i}) for i, r in enumerate(recs, start=1)]

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
        rejected: Sequence[tuple[str, str, Sequence[str]]] = (),
    ) -> RecommendationResponse:
        recs = list(recommendations)
        risk = list(risky)
        if message is None:
            run.trace.append(AgentStep.COMPOSE)
            draft = draft_message(original, recs, risk, blocked or {}, unverified, rejected)
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


def _describe(key: str, definition: SpecDefinition) -> str:
    """Key as shown to the NLU: unit, description and aliases, so the LLM picks the right one."""
    hints = ", ".join(h for h in [definition.description, *definition.aliases][:4] if h)
    unit = definition.unit or definition.type
    return f"{key} ({unit}; {hints})" if hints else f"{key} ({unit})"
