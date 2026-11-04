"""Deterministic knowledge tools of the agent (ADR-014): technical Q&A over specs and datasheets,
product comparison, the most informative clarification question, and requirement relaxation.

Nothing here calls an LLM: every figure comes from the catalog, an extracted spec (with its
evidence) or a retrieved datasheet passage.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from advisor.compatibility import evaluate
from advisor.extraction import SpecDefinition, SpecRegistry
from advisor.extraction.registry import fold
from advisor.models import (
    Category,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    Evidence,
    Product,
    ProductSpecification,
    Relaxation,
    TechnicalRequirement,
)
from advisor.recommendation import rank
from advisor.retrieval import RetrievalUnavailableError, Retriever

CATEGORY_ES: dict[Category, str] = {
    Category.NETWORK: "Tarjeta de red",
    Category.GPU: "GPU",
    Category.CPU: "CPU",
    Category.DAQ: "DAQ",
    Category.FPGA: "FPGA",
    Category.MEMORY: "Memoria",
    Category.MICROCONTROLLER: "Microcontrolador",
    Category.STORAGE: "Almacenamiento (SSD)",
    Category.POWER: "Fuente de poder",
    Category.SENSOR: "Sensor",
}
MAX_CITATIONS = 3
MAX_RELAXATIONS = 3
QUOTE_CHARS = 280


def show_value(spec: ProductSpecification) -> str:
    value = ", ".join(map(str, spec.value)) if isinstance(spec.value, list) else str(spec.value)
    unit = "" if not spec.unit or spec.unit == "count" else f" {spec.unit}"
    return f"{value}{unit}"


def _specs(product: Product) -> dict[str, ProductSpecification]:
    return {s.key: s for s in product.specifications if s.value is not None}


def _mentions(text: str, phrases: Sequence[str]) -> bool:
    folded = fold(text)
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(fold(p))}(?![a-z0-9])", folded) for p in phrases
    )


def _key_phrases(key: str, definition: SpecDefinition) -> list[str]:
    phrases = [key.replace("_", " "), *definition.aliases]
    if definition.description:
        phrases += [p.strip() for p in re.split(r"[/,(]", definition.description) if len(p) > 3]
    return [p for p in phrases if p]


_COMMERCIAL = re.compile(
    r"\bprice\b|\$\s?\d|\bin stock\b|\bstock\b|\bunits\b|\bavailable from\b", re.I
)


def _without_commercial(text: str) -> str:
    """Drop datasheet sentences about price or stock: the catalog is the source of truth."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in sentences if not _COMMERCIAL.search(s))


def _stem_hit(question: str, description: str) -> bool:
    """Spanish word forms of the description ("consume" ~ "consumo de potencia")."""
    stems = {w[:6] for w in re.findall(r"[a-z]{6,}", fold(description))}
    return any(re.search(rf"(?<![a-z]){s}", fold(question)) for s in stems)


# ------------------------------------------------------------------ technical Q&A


@dataclass
class TechnicalAnswer:
    lines: list[str] = field(default_factory=list)
    citations: list[Evidence] = field(default_factory=list)


def answer_question(
    question: str,
    product: Product | None,
    registry: SpecRegistry,
    retriever: Retriever,
    warnings: list[str],
) -> TechnicalAnswer:
    """Specs of ``product`` that the question names (with their evidence) plus the datasheet
    passages that best match it. Says so when the datasheet does not declare the asked data."""
    out = TechnicalAnswer()
    if product is not None:
        specs = _specs(product)
        definitions = registry.for_category(product.category)
        for key, definition in definitions.items():
            keyword_hits = [
                kw for kw, phrases in definition.phrases().items() if _mentions(question, phrases)
            ]
            named = _mentions(question, _key_phrases(key, definition)) or _stem_hit(
                question, definition.description
            )
            if not keyword_hits and not named:
                continue
            spec = specs.get(key)
            if spec is None:
                out.lines.append(f"{key}: el datasheet de {product.part_number} no lo declara.")
                continue
            if keyword_hits:
                declared = {fold(v) for v in (spec.value if isinstance(spec.value, list) else [])}
                for kw in keyword_hits:
                    verb = "sí declara" if fold(kw) in declared else "no declara"
                    out.lines.append(f"{key}: {product.part_number} {verb} {kw}.")
            else:
                out.lines.append(f"{key}: {show_value(spec)}.")
            out.citations.extend(spec.evidence[:1])
    try:
        query = f"{question} {product.part_number}" if product else question
        hits = retriever.search(query, top_k=8)
    except RetrievalUnavailableError as exc:
        hits = []
        warnings.append(f"Búsqueda documental no disponible ({exc}).")
    if product is not None:
        hits = [h for h in hits if product.part_number in h.chunk.part_numbers] or hits[:0]
    for hit in hits[:MAX_CITATIONS]:
        chunk = hit.chunk
        quote = _without_commercial(re.sub(r"\s+", " ", chunk.text).strip())[:QUOTE_CHARS]
        if not quote:
            continue
        out.citations.append(
            Evidence(
                document_id=chunk.document_id,
                page=chunk.page_start,
                chunk_id=chunk.chunk_id,
                quote=quote,
            )
        )
        out.lines.append(f"Datasheet (p. {chunk.page_start}): «{quote}»")
    unique = {(e.document_id, e.page, e.quote): e for e in out.citations}
    out.citations = list(unique.values())
    if not out.lines:
        subject = f"de {product.part_number}" if product else "de los datasheets"
        out.lines.append(f"No encontré información {subject} que responda la pregunta.")
    return out


# ------------------------------------------------------------------ comparison


def compare_products(
    a: Product, b: Product, registry: SpecRegistry, result: CompatibilityResult | None
) -> list[str]:
    """Side by side: commercial data, specs both declare (or one does), and whether ``b`` can
    replace ``a`` according to the rules."""
    lines = []
    for p in (a, b):
        c = p.commercial
        if c is None:
            lines.append(f"{p.part_number}: sin información comercial.")
            continue
        price = f"{c.price_usd:,.2f} USD" if c.price_usd is not None else "sin precio"
        lines.append(
            f"{p.part_number} ({c.description}, {c.manufacturer}): {c.status.value}; {price}; "
            f"{c.stock_units} unidades."
        )
    if a.category is not b.category:
        lines.append(f"Son de categorías distintas ({a.category} vs {b.category}).")
        return lines
    sa, sb = _specs(a), _specs(b)
    for key, definition in registry.for_category(a.category).items():
        if not definition.derive or (key not in sa and key not in sb):
            continue
        va = show_value(sa[key]) if key in sa else "no declarado"
        vb = show_value(sb[key]) if key in sb else "no declarado"
        lines.append(f"- {key}: {a.part_number} {va} · {b.part_number} {vb}")
    if result is not None:
        level = {
            CompatibilityLevel.COMPATIBLE: "compatible",
            CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: "compatible con condiciones",
            CompatibilityLevel.UNKNOWN: "sin datos suficientes para confirmarlo",
            CompatibilityLevel.INCOMPATIBLE: "incompatible",
        }[result.level]
        lines.append(f"Como sustituto de {a.part_number}, {b.part_number} es {level}.")
    return lines


# ------------------------------------------------------------------ smart clarification


@dataclass
class Question:
    text: str
    options: list[str]
    key: str | None = None


def best_question(
    category: Category | None,
    products: Sequence[Product],
    registry: SpecRegistry,
    known: Sequence[TechnicalRequirement] = (),
) -> Question:
    """The question whose answer splits the ACTIVE products of the category the most."""
    if category is None:
        return Question(
            "¿Qué part number quieres reemplazar o qué tipo de componente necesitas?",
            list(CATEGORY_ES.values()),
        )
    active = [
        p
        for p in products
        if p.category is category
        and p.commercial is not None
        and p.commercial.status is CommercialStatus.ACTIVE
    ]
    asked = {r.key for r in known}
    best: tuple[float, str, list[str]] | None = None
    for key, definition in registry.for_category(category).items():
        if key in asked or not definition.derive:
            continue
        values: dict[str, str] = {}
        for p in active:
            spec = _specs(p).get(key)
            if spec is None:
                continue
            items = spec.value if isinstance(spec.value, list) else [spec.value]
            for item in items:
                shown = show_value(spec.model_copy(update={"value": item}))
                values.setdefault(fold(shown), shown)
        if len(values) < 2:
            continue
        coverage = sum(key in _specs(p) for p in active) / max(len(active), 1)
        score = min(len(values), 4) * coverage * (2.5 if definition.critical else 1.0)
        if best is None or score > best[0]:
            best = (score, key, sorted(values.values())[:5])
    if best is None:
        return Question(
            f"¿Qué requisito técnico es imprescindible para el componente de {category.value}?",
            [],
        )
    _, key, options = best
    label = registry.for_category(category)[key].description or key.replace("_", " ")
    return Question(
        f"¿Qué {label} necesitas? En el catálogo hay: {', '.join(options)}.", options, key
    )


# ------------------------------------------------------------------ requirement negotiation


def relax(
    reference: Product,
    candidates: Sequence[Product],
    requirements: Sequence[TechnicalRequirement],
    results: Sequence[CompatibilityResult],
    products: Mapping[str, Product],
    registry: SpecRegistry,
) -> list[Relaxation]:
    """Sales that open if ONE requirement is dropped: only requirements that actually made a
    candidate fail, customer requirements first. Never a recommendation (ADR-014)."""
    failing = {
        r.requirement.key + str(r.requirement.value)
        for res in results
        for r in res.rule_results
        if r.requirement is not None and r.outcome.value == "FAIL"
    }
    definitions = registry.for_category(reference.category)
    ordered = sorted(
        (
            r
            for r in requirements
            if r.key + str(r.value) in failing
            and getattr(definitions.get(r.key.split(".")[0]), "negotiable", True)
        ),
        key=lambda r: (r.origin.value != "QUERY", r.key),
    )
    already = {
        r.candidate_part_number
        for r in results
        if r.level in (CompatibilityLevel.COMPATIBLE, CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS)
    }
    out: list[Relaxation] = []
    offered: set[str] = set(already)
    for dropped in ordered:
        # Only candidates that this requirement actually blocked (FAIL), not those missing data.
        blocked = {
            res.candidate_part_number
            for res in results
            for r in res.rule_results
            if r.requirement is dropped and r.outcome.value == "FAIL"
        }
        rest = [r for r in requirements if r is not dropped]
        relaxed = [
            evaluate(reference, c, rest, registry=registry)
            for c in candidates
            if c.part_number in blocked
        ]
        for rec in rank(relaxed, products).recommendations:
            if rec.product.part_number in offered:
                continue
            offered.add(rec.product.part_number)
            out.append(Relaxation(dropped=dropped, option=rec))
            break
        if len(out) >= MAX_RELAXATIONS:
            break
    return out
