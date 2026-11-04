"""Controlled advisor agent: tools decide; the LLM only parses the query and rephrases."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

import networkx as nx

from advisor.agent.compose import draft_message, fail_reasons, money, unverified_tokens
from advisor.agent.knowledge import (
    MAX_CITATIONS,
    Question,
    answer_question,
    best_question,
    compare_products,
    relax,
)
from advisor.agent.planner import (
    MAX_STEPS,
    TOOLS_DOC,
    AgentAction,
    AgentPlan,
    PlanState,
    check,
    rule_action,
)
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
    build_planner_prompt,
    complete_json,
    generate,
    parse_query,
)
from advisor.llm.rules import explicit_intent
from advisor.models import (
    Category,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    ConversationContext,
    CustomerQuery,
    EdgeType,
    Evidence,
    Operator,
    ParsedQuery,
    PartMatch,
    Priority,
    Product,
    Recommendation,
    RecommendationResponse,
    Relaxation,
    RequirementOrigin,
    RuleOutcome,
    TechnicalRequirement,
    ToolCall,
)
from advisor.recommendation import RankedOutput, rank
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
    PLAN = "PLAN"  # the LLM proposed the tool calls (ADR-014)
    RELAX = "RELAX"
    ANSWER = "ANSWER"
    COMPARE = "COMPARE"


class Advisor(Protocol):
    """What the UI depends on. Implemented by AdvisorAgent and app.mock_agent.MockAdvisorAgent."""

    def answer(self, query: CustomerQuery) -> RecommendationResponse: ...


@dataclass
class _Search:
    reference: Product
    candidates: list[Product]
    requirements: list[TechnicalRequirement]
    results: list[CompatibilityResult]
    ranked: RankedOutput
    blocked: dict[str, CompatibilityResult]


@dataclass
class _Run:
    query: CustomerQuery
    context: ConversationContext = field(default_factory=ConversationContext)
    trace: list[AgentStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    parsed: ParsedQuery | None = None
    original: Product | None = None
    other: Product | None = None  # second product of a comparison
    search: _Search | None = None
    recommendations: list[Recommendation] = field(default_factory=list)
    rejected: list[tuple[str, str, list[str]]] = field(default_factory=list)
    relaxations: list[Relaxation] = field(default_factory=list)
    answer_lines: list[str] = field(default_factory=list)
    citations: list[Evidence] = field(default_factory=list)
    clarification: Question | None = None


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
        explicit = explicit_intent(run.query.text)
        if (
            explicit
            and explicit != parsed.intent
            and not (explicit == "question" and parsed.requirements)
        ):
            parsed = parsed.model_copy(update={"intent": explicit})
        ctx = run.context
        if parsed.category is None and ctx.category is not None:
            # Short follow-ups ("400 Gb/s", "ya no necesito IPsec") rely on the remembered category.
            hinted = parse_query(run.query.text, category_hint=ctx.category)
            parsed = parsed.model_copy(
                update={
                    "category": ctx.category,
                    "requirements": parsed.requirements or hinted.requirements,
                    "remove": parsed.remove or hinted.remove,
                    "intent": parsed.intent if parsed.intent != "other" else hinted.intent,
                }
            )
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

    def _resolve(self, parsed: ParsedQuery, run: _Run, *, trace: bool = True) -> list[PartMatch]:
        if trace:
            run.trace.append(AgentStep.RESOLVE)
        matches = {m.part_number: m for m in resolve_part(self.graph, run.query.text)}
        for token in parsed.part_numbers:
            for m in resolve_part(self.graph, token, limit=1):
                if m.part_number not in matches or m.score > matches[m.part_number].score:
                    matches[m.part_number] = m
        return sorted(matches.values(), key=lambda m: (-m.score, m.part_number))

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
        """NLU → memory → plan (LLM or rules) → deterministic tools → compose → verify."""
        run = _Run(query, context=query.context or ConversationContext())
        run.parsed = self._remember(self._parse(run), run)
        queue, planner, thought = self._plan(run)
        for _ in range(MAX_STEPS + 2):
            state = self._plan_state(run)
            proposed = queue.pop(0) if queue else None
            note = None
            if proposed is not None:
                note = check(proposed, state)
            action = proposed if proposed is not None and note is None else rule_action(state)
            decided_by = planner if proposed is not None and note is None else "rules"
            if note:
                decided_by = f"rules (corrige a {planner}: {note})"
            self._run_tool(action, run, decided_by, thought)
            thought = None
            if action.tool == "finish":
                break
        return self._finish(run)

    # ------------------------------------------------------------------ memory

    def _remember(self, parsed: ParsedQuery, run: _Run) -> ParsedQuery:
        """Merge the previous turns (ConversationContext) into this one, or start a new topic."""
        ctx = run.context
        if ctx.turn == 0:
            return parsed
        mentioned = [
            m.part_number for m in self._resolve(parsed, run, trace=False) if m.score >= CONFIDENT
        ]
        new_part = mentioned and ctx.original_part_number not in mentioned
        other_category = parsed.category is not None and parsed.category is not ctx.category
        if parsed.intent not in ("compare", "question") and (new_part or other_category):
            return parsed  # new topic: forget the previous one
        new, remove = parsed.requirements, list(parsed.remove)
        if not new:
            new, dropped = _renumber(run.query.text, ctx.requirements)
            remove += dropped
        requirements = _merge(ctx.requirements, new, remove)
        parts = parsed.part_numbers
        intent = parsed.intent
        if not parts and ctx.original_part_number and intent not in ("compare", "question"):
            parts = [ctx.original_part_number]
            intent = "replace" if intent in ("find", "other") else intent
        elif intent == "other":
            intent = "find"
        if remove:
            run.warnings.append(f"Se quitaron de los requisitos: {', '.join(remove)}.")
        if ctx.original_part_number or ctx.requirements:
            run.warnings.append("Se toma en cuenta la conversación anterior.")
        return parsed.model_copy(
            update={
                "category": parsed.category or ctx.category,
                "requirements": requirements,
                "part_numbers": parts,
                "intent": intent,
                "needs_clarification": False,
                "clarification_question": None,
            }
        )

    # ------------------------------------------------------------------ planning

    def _plan(self, run: _Run) -> tuple[list[AgentAction], str, str | None]:
        """The LLM's ordered tool calls; none (rules decide) when only templates are available."""
        if all(c.name == "template" for c in self.llm_chain):
            return [], "rules", None
        parsed = run.parsed
        assert parsed is not None
        reqs = "; ".join(f"{r.key} {r.operator.value} {r.value}" for r in parsed.requirements)
        situation = (
            f"Cliente: {run.query.text}\n"
            f"Interpretación: intención={parsed.intent}; categoría={parsed.category}; "
            f"part numbers={', '.join(parsed.part_numbers) or 'ninguno'}; "
            f"requisitos={reqs or 'ninguno'}\n"
            f"Memoria: pieza={run.context.original_part_number or 'ninguna'}; "
            f"recomendados antes={', '.join(run.context.recommended) or 'ninguno'}"
        )
        prompt = build_planner_prompt(situation, TOOLS_DOC, AgentPlan.model_json_schema())
        try:
            plan, provider = complete_json(self.llm_chain, prompt, AgentPlan)
        except LLMUnavailableError:
            return [], "rules", None
        run.trace.append(AgentStep.PLAN)
        return list(plan.steps), provider, plan.thought or None

    def _plan_state(self, run: _Run) -> PlanState:
        parsed = run.parsed
        assert parsed is not None
        original = run.original
        return PlanState(
            intent=parsed.intent,
            original=original.part_number if original else None,
            other=run.other.part_number if run.other else None,
            category=(parsed.category or (original.category if original else None)) is not None,
            requirements=bool(parsed.requirements),
            done=[c.tool for c in run.tool_calls],
            found=len(run.recommendations) if run.search is not None else None,
            blocked=run.clarification is not None,
            active_original=bool(
                original
                and original.commercial
                and original.commercial.status is CommercialStatus.ACTIVE
            ),
        )

    # ------------------------------------------------------------------ tools

    def _run_tool(
        self, action: AgentAction, run: _Run, decided_by: str, thought: str | None
    ) -> None:
        tool = action.tool
        handler = {
            "lookup_part": self._tool_lookup,
            "find_substitutes": self._tool_substitutes,
            "search_catalog": self._tool_catalog,
            "relax_requirements": self._tool_relax,
            "ask_datasheets": self._tool_datasheets,
            "compare": self._tool_compare,
            "ask_customer": self._tool_ask,
        }.get(tool)
        arguments, summary = handler(run) if handler else ({}, "Respuesta lista.")
        run.tool_calls.append(
            ToolCall(
                tool=tool,
                arguments=arguments,
                summary=summary,
                decided_by=decided_by,
                thought=thought,
            )
        )

    def _tool_lookup(self, run: _Run) -> tuple[dict[str, str], str]:
        parsed = run.parsed
        assert parsed is not None
        matches = self._resolve(parsed, run)
        if parsed.intent in ("compare", "question"):
            matches = self._with_prefixes(matches, run.query.text)
        confident = [m for m in matches if m.score >= CONFIDENT]
        args = {"texto": ", ".join(parsed.part_numbers) or run.query.text[:60]}
        if parsed.intent == "compare":
            return args, self._lookup_pair(confident, run)
        if len(confident) > 1 and confident[0].score - confident[1].score < AMBIGUITY_GAP:
            options = [m.part_number for m in confident[:4]]
            run.clarification = Question(
                f"¿A cuál de estos part numbers te refieres: {', '.join(options)}?", options
            )
            return args, f"Ambiguo entre {', '.join(options)}."
        if not confident:
            suggestions = [m.part_number for m in matches if m.score >= SUGGEST][:3]
            if suggestions and parsed.intent != "question":
                offer = " o ".join(suggestions)
                run.clarification = Question(
                    f"No encontré ese part number exacto. ¿Te refieres a {offer}?", suggestions
                )
                return args, f"Sin coincidencia exacta; sugerencias: {', '.join(suggestions)}."
            return args, "Sin part number del catálogo en la consulta."
        original = self.products[confident[0].part_number]
        self._set_original(original, run)
        c = original.commercial
        status = c.status.value if c else "sin datos comerciales"
        return {"part_number": original.part_number}, f"{original.part_number}: {status}."

    def _lookup_pair(self, confident: Sequence[PartMatch], run: _Run) -> str:
        """compare: two products named, or one plus the conversation's reference ("la")."""
        named = [self.products[m.part_number] for m in confident]
        ctx = run.context
        remembered = [*ctx.recommended, *filter(None, [ctx.original_part_number])]
        if len(named) == 1:
            reference = next((p for p in remembered if p != named[0].part_number), None)
            if reference is not None:
                named.insert(0, self.products[reference])
        if len(named) < 2:
            run.clarification = Question("¿Qué dos productos quieres comparar?", [])
            return "Falta el segundo producto a comparar."
        run.original, run.other = named[0], named[1]
        return f"Comparar {named[0].part_number} con {named[1].part_number}."

    def _with_prefixes(self, matches: list[PartMatch], text: str) -> list[PartMatch]:
        """Short names in questions ("la MCX", "la BCM") that start exactly one part number."""
        found = {m.part_number for m in matches}
        out = list(matches)
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text):
            if word.casefold() in _STOPWORDS:
                continue
            owners = [p for p in self.products if p.upper().startswith(word.upper())]
            if len(owners) == 1 and owners[0] not in found:
                found.add(owners[0])
                out.append(PartMatch(part_number=owners[0], score=CONFIDENT, method="fuzzy"))
        return out

    def _set_original(self, original: Product, run: _Run) -> None:
        parsed = run.parsed
        assert parsed is not None
        run.trace.append(AgentStep.STATUS)
        self.commercial.get(original.part_number)  # catalog is the source of truth
        if parsed.category is not None and parsed.category is not original.category:
            run.warnings.append(
                f"La consulta parece de categoría {parsed.category}, pero "
                f"{original.part_number} es {original.category} en el catálogo; se usa la del "
                "catálogo."
            )
        run.original = original
        run.parsed = parsed.model_copy(update={"category": original.category})

    def _tool_substitutes(self, run: _Run) -> tuple[dict[str, str], str]:
        original, parsed = run.original, run.parsed
        assert original is not None and parsed is not None
        parsed = self._footprint_requirement(parsed, original, run)
        run.parsed = parsed
        candidates, rejected = self._maker_filter(
            self._discover(original, run), original.category, run
        )
        run.trace.append(AgentStep.VALIDATE)
        requirements = derive_requirements(original, parsed, registry=self.registry)
        self._evaluate(run, original, candidates, requirements, rejected)
        return (
            {"part_number": original.part_number, "requisitos": str(len(requirements))},
            f"{len(candidates)} candidatos evaluados con {len(requirements)} requisitos: "
            f"{len(run.recommendations)} recomendados.",
        )

    def _tool_catalog(self, run: _Run) -> tuple[dict[str, str], str]:
        parsed = run.parsed
        assert parsed is not None and parsed.category is not None
        reference = Product(part_number="CONSULTA", manufacturer="", category=parsed.category)
        run.trace.extend([AgentStep.DISCOVER, AgentStep.VALIDATE])
        candidates, rejected = self._maker_filter(
            [p for p in self.products.values() if p.category is parsed.category],
            parsed.category,
            run,
        )
        self._evaluate(run, reference, candidates, list(parsed.requirements), rejected)
        return (
            {"categoría": parsed.category.value, "requisitos": str(len(parsed.requirements))},
            f"{len(candidates)} productos de {parsed.category.value} evaluados: "
            f"{len(run.recommendations)} cumplen.",
        )

    def _evaluate(
        self,
        run: _Run,
        reference: Product,
        candidates: Sequence[Product],
        requirements: list[TechnicalRequirement],
        rejected: list[tuple[str, str, list[str]]],
    ) -> None:
        results = [evaluate(reference, c, requirements, registry=self.registry) for c in candidates]
        run.trace.append(AgentStep.RANK)
        ranked = rank(results, self.products)
        by_candidate = {r.candidate_part_number: r for r in results}
        blocked = {
            s: by_candidate[s]
            for s in self._successors(reference.part_number)
            if s in by_candidate and by_candidate[s].level is CompatibilityLevel.INCOMPATIBLE
        }
        rejected += self._rejected(results, exclude=set(blocked))
        run.search = _Search(reference, list(candidates), requirements, results, ranked, blocked)
        run.rejected = rejected
        run.recommendations = self._by_price(ranked.recommendations, run)

    def _tool_relax(self, run: _Run) -> tuple[dict[str, str], str]:
        search = run.search
        assert search is not None
        run.trace.append(AgentStep.RELAX)
        run.relaxations = relax(
            search.reference, search.candidates, search.requirements, search.results,
            self.products, self.registry,
        )  # fmt: skip
        if not run.relaxations:
            return {}, "Quitar un solo requisito no abre ninguna opción."
        options = ", ".join(
            f"sin {_show_requirement(r.dropped)} → {r.option.product.part_number}"
            for r in run.relaxations
        )
        return {}, f"Opciones si se relaja un requisito: {options}."

    def _tool_datasheets(self, run: _Run) -> tuple[dict[str, str], str]:
        run.trace.append(AgentStep.ANSWER)
        answer = answer_question(
            run.query.text, run.original, self.registry, self.retriever, run.warnings
        )
        run.answer_lines += answer.lines
        run.citations += answer.citations
        subject = run.original.part_number if run.original else "todos los datasheets"
        return (
            {"pregunta": run.query.text[:60], "producto": subject},
            f"{len(answer.lines)} datos encontrados, {len(answer.citations)} citas.",
        )

    def _tool_compare(self, run: _Run) -> tuple[dict[str, str], str]:
        a, b, parsed = run.original, run.other, run.parsed
        assert a is not None and b is not None and parsed is not None
        run.trace.append(AgentStep.COMPARE)
        result = None
        if a.category is b.category:
            requirements = derive_requirements(a, parsed, registry=self.registry)
            result = evaluate(a, b, requirements, registry=self.registry)
            run.citations += [e for r in result.rule_results for e in r.evidence][:MAX_CITATIONS]
        run.answer_lines += compare_products(a, b, self.registry, result)
        level = result.level.value if result else "categorías distintas"
        return {"a": a.part_number, "b": b.part_number}, f"Comparación lista ({level})."

    def _tool_ask(self, run: _Run) -> tuple[dict[str, str], str]:
        parsed = run.parsed
        assert parsed is not None
        run.trace.append(AgentStep.CLARIFY)
        question = best_question(
            parsed.category, list(self.products.values()), self.registry, parsed.requirements
        )
        if parsed.clarification_question and parsed.category is None:
            question.text = parsed.clarification_question
        run.clarification = question
        return {"categoría": str(parsed.category or "—")}, question.text

    # ------------------------------------------------------------------ answer

    def _finish(self, run: _Run) -> RecommendationResponse:
        parsed = run.parsed
        assert parsed is not None
        search = run.search
        risky = list(search.ranked.risky_options) if search else []
        unverified = list(search.ranked.unverified_options) if search else []
        question = run.clarification
        if question is not None:
            run.trace.append(AgentStep.CLARIFY) if AgentStep.CLARIFY not in run.trace else None
            options = self._catalog_options(parsed, run)
            message = "Necesito un dato más para buscar un sustituto."
            message = f"{options}\n{message}" if options else message
            run.providers.append("template")
        else:
            run.trace.append(AgentStep.COMPOSE)
            lines = list(run.answer_lines)
            if search is not None or not lines:
                lines.insert(
                    0,
                    draft_message(
                        run.original, run.recommendations, risky,
                        search.blocked if search else {}, unverified, run.rejected,
                        run.relaxations,
                    ),
                )  # fmt: skip
            message = self._rephrase("\n".join(lines), run)
        self.last_trace = run.trace
        recommended = [r.product.part_number for r in run.recommendations]
        context = ConversationContext(
            original_part_number=(
                run.original.part_number
                if run.original and parsed.intent not in ("compare",)
                else run.context.original_part_number
            ),
            category=parsed.category,
            requirements=[r for r in parsed.requirements if r.origin is RequirementOrigin.QUERY],
            recommended=recommended or run.context.recommended,
            asked_key=question.key if question else None,
            turn=run.context.turn + 1,
        )
        return RecommendationResponse(
            query=run.query,
            parsed_query=parsed,
            original=run.original if parsed.intent != "compare" else None,
            recommendations=run.recommendations,
            risky_options=risky,
            unverified_options=unverified,
            clarification_question=question.text if question else None,
            clarification_options=question.options if question else [],
            relaxations=run.relaxations,
            citations=run.citations,
            tool_calls=run.tool_calls,
            context=context,
            message=message,
            llm_provider="+".join(dict.fromkeys(run.providers)),
            warnings=run.warnings,
            is_synthetic=any(p.is_synthetic for p in self.products.values()),
        )

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


_STOPWORDS = {"la", "el", "los", "las", "con", "que", "del", "una", "uno", "por", "para", "and"}


def _show_requirement(req: TechnicalRequirement) -> str:
    unit = "" if not req.unit or req.unit == "count" else f" {req.unit}"
    value = "soporte" if req.value == ANY else req.value
    symbol = {"GTE": "≥", "LTE": "≤"}.get(req.operator.value, "")
    return " ".join(f"{req.key} {symbol} {value}{unit}".split())


def _merge(
    previous: Sequence[TechnicalRequirement],
    new: Sequence[TechnicalRequirement],
    remove: Sequence[str],
) -> list[TechnicalRequirement]:
    """Previous requirements + new ones (a new figure for the same key replaces the old one),
    minus the keys or values the customer dropped."""
    dropped = {fold(x) for x in remove}
    merged: dict[tuple[str, str], TechnicalRequirement] = {}
    for req in [*previous, *new]:
        numeric = req.operator in (Operator.GTE, Operator.LTE, Operator.EQ)
        merged[(req.key, "" if numeric else fold(str(req.value)))] = req
    return [
        r
        for r in merged.values()
        if fold(r.key) not in dropped and fold(str(r.value)) not in dropped
    ]


def _renumber(
    text: str, previous: Sequence[TechnicalRequirement]
) -> tuple[list[TechnicalRequirement], list[str]]:
    """Bare figures in a follow-up ("ya no necesito 800, con 200 me basta") refer to the one
    remembered numeric requirement: a figure equal to it drops it, a new one replaces it."""
    numeric = [r for r in previous if r.operator in (Operator.GTE, Operator.LTE)]
    if len(numeric) != 1:
        return [], []
    old = numeric[0]
    figures = [float(n) for n in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", text)]
    fresh = [f for f in figures if f != float(old.value)]  # type: ignore[arg-type]
    if not fresh:
        return [], []
    value = int(fresh[-1]) if fresh[-1].is_integer() else fresh[-1]
    return [old.model_copy(update={"value": value})], []
