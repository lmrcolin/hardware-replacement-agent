"""Rule-based NLU (Spanish/English): the deterministic parser behind TemplateClient."""

from __future__ import annotations

import re
from typing import Literal

from advisor.compatibility.engine import default_registry
from advisor.extraction.registry import fold
from advisor.extraction.values import parse_number
from advisor.kg.aliases import is_technical_term
from advisor.models import (
    Category,
    Operator,
    ParsedQuery,
    Priority,
    RequirementOrigin,
    TechnicalRequirement,
)

CATEGORY_HINTS: tuple[tuple[str, Category], ...] = (
    (r"tarjeta de red|\bnic\b|ethernet|\bred\b|network|smartnic", Category.NETWORK),
    (r"\bgpu\b|gr[aá]fica|acelerador|accelerator", Category.GPU),
    (r"\bdaq\b|adquisici[oó]n de datos|data acquisition", Category.DAQ),
    (r"microcontrolador|microcontroller|\bmcu\b", Category.MICROCONTROLLER),
    (r"\bfpga\b", Category.FPGA),
    (r"\bssd\b|almacenamiento|\bdisco\b|nvme|storage", Category.STORAGE),
    (r"memoria|memory|\bdram\b|\bddr\d|\bhbm", Category.MEMORY),
    (r"sensor|\bimu\b|aceler[oó]metro|giroscopio", Category.SENSOR),
    (
        r"regulador|fuente de (?:poder|alimentaci[oó]n)|power stage|\bvrm\b|usb[- ]?pd",
        Category.POWER,
    ),
    (r"\bcpu\b|procesador|processor", Category.CPU),
)
REPLACE_WORDS = (
    r"reemplaz|sustitu|ya no (?:la|lo|las|los)? ?encuentr|descontinu|alternativ"
    r"|replace|substitut|discontinu|equivalente"
)
STATUS_WORDS = (
    r"\bestado\b|disponib|\bstock\b|inventario|\bprecio\b|cu[aá]nto cuesta|status|price|availab"
)
CHEAP_WORDS = r"barat|econ[oó]mic|cheap|low[- ]cost|menor precio|bajo costo|presupuesto"
COMPARE_WORDS = r"comp[aá]r|\bvs\.?\b|versus|diferencias? entre|\bdifference"
QUESTION_WORDS = (
    r"^\s*¿|\?\s*$|^\s*(?:qu[eé]|cu[aá]l|cu[aá]nt[oa]s?|soporta|tiene|admite|es compatible|"
    r"does|what|which|how much|is it|can it)\b"
)
# "ya no necesito IPsec", "sin RDMA", "quita el requisito de TLS": requirements to drop (follow-ups)
REMOVE_SPAN = re.compile(
    r"(?:ya no (?:necesito|requiero|hace falta|importa)|no (?:necesito|requiero|hace falta)"
    r"|\bsin\b|quita(?:r|le)?(?: el requisito de)?|olvida|no importa|without|drop)\s+([^.;,]+)",
    re.I,
)
UNIT_TOKEN = re.compile(
    r"^\d+(?:\.\d+)?(?:gbe|gb|tb|mb|kb|mhz|ghz|khz|w|v|a|bits?|g|ms/s|ks/s|ksps|msps|x\d*)$", re.I
)

# (category or None for any, regex, key, operator, unit, fixed value or None to use group 1)
_NET, _GPU, _DAQ = Category.NETWORK, Category.GPU, Category.DAQ
_SPEED = r"(\d+(?:\.\d+)?)\s*(?:gigabit|gbe|gb/s|gbps|gb|g)\b"  # "25 Gb", "25G" in a NIC query
_CHANNELS = r"(\d+)\s*(?:canales|entradas|channels|inputs)"
_RATE = r"(\d+(?:\.\d+)?\s*(?:ms/s|ks/s|msps|ksps))"
_SRAM = r"(\d+)\s*kb\s*(?:de\s*)?(?:sram|ram)"
_MCU, _MEM = Category.MICROCONTROLLER, Category.MEMORY
_PATTERNS: tuple[tuple[Category | None, str, str, Operator, str | None, str | None], ...] = (
    (_NET, _SPEED, "port_speed", Operator.GTE, "Gb/s", None),
    (_NET, r"\brdma\b", "rdma", Operator.HAS, None, "*"),
    (_NET, r"\broce\b", "rdma", Operator.HAS, None, "RoCE v2"),
    (_NET, r"\biwarp\b", "rdma", Operator.HAS, None, "iWARP"),
    (_NET, r"\bipsec\b", "offloads", Operator.HAS, None, "IPsec"),
    (_NET, r"\btls\b", "offloads", Operator.HAS, None, "TLS"),
    (_NET, r"\bvxlan\b", "offloads", Operator.HAS, None, "VXLAN"),
    (_NET, r"\bgeneve\b", "offloads", Operator.HAS, None, "GENEVE"),
    (_NET, r"\bsr-?iov\b", "sriov_vfs", Operator.HAS, None, "*"),
    (_GPU, r"(\d+)\s*gb\b", "memory_size", Operator.GTE, "GB", None),
    (Category.STORAGE, r"(\d+(?:\.\d+)?)\s*tb\b", "capacity", Operator.GTE, "TB", None),
    (_DAQ, _CHANNELS, "analog_inputs", Operator.GTE, "count", None),
    (_DAQ, r"(\d+)\s*-?\s*bits?\b", "resolution", Operator.GTE, "bit", None),
    (_DAQ, _RATE, "sample_rate", Operator.GTE, "S/s", None),
    (_MCU, _SRAM, "sram", Operator.GTE, "KB", None),
    (_MCU, r"\busb\b", "usb", Operator.HAS, None, "*"),
    (_MEM, r"\b(lpddr5x|ddr5|hbm3)\b", "memory_type", Operator.EQ, None, None),
)
# Memory density keeps the customer's unit: "16 Gb" (gigabits, DRAM density) ≠ "16 GB".
_MEM_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(Gb|GB|Gbit)\b")


def detect_category(text: str) -> Category | None:
    lowered = text.lower()
    for pattern, category in CATEGORY_HINTS:
        if re.search(pattern, lowered):
            return category
    return None


def _keyword_requirements(text: str, category: Category) -> list[TechnicalRequirement]:
    """HAS requirements for registry keywords (and their es/en synonyms) mentioned in the query."""
    folded = fold(text)
    found: list[TechnicalRequirement] = []
    for key, definition in default_registry().for_category(category).items():
        for keyword, phrases in definition.phrases().items():
            if keyword.isupper() and len(keyword) <= 4:  # CAN/TLS/GRE: acronym as written ("can")
                pattern = rf"(?<![A-Za-z]){re.escape(keyword)}(?![A-Za-z])"
                hit = re.search(pattern, text) is not None
            else:
                hit = any(
                    re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", folded) for p in phrases
                )
            if hit:
                found.append(
                    TechnicalRequirement(key=key, operator=Operator.HAS, value=keyword,
                                         priority=Priority.MUST, origin=RequirementOrigin.QUERY)
                )  # fmt: skip
    return found


def _requirements(text: str, category: Category | None) -> list[TechnicalRequirement]:
    lowered = text.lower()
    found: list[TechnicalRequirement] = []
    seen: set[tuple[str, str]] = set()
    for cat, pattern, key, op, unit, fixed in _PATTERNS:
        if cat is not None and cat is not category:
            continue
        m = re.search(pattern, lowered)
        if not m:
            continue
        value: str | float | int
        if fixed is not None:
            value = fixed
        elif unit is None:
            value = m.group(1).upper()
        else:
            parsed = parse_number(m.group(1), unit) if unit else None
            if parsed is None:
                continue
            value = parsed
        if (key, str(value)) in seen:
            continue
        seen.add((key, str(value)))
        found.append(
            TechnicalRequirement(
                key=key,
                operator=op,
                value=value,
                unit=unit,
                priority=Priority.MUST,
                origin=RequirementOrigin.QUERY,
            )
        )
    size = _MEM_SIZE.search(text) if category is Category.MEMORY else None
    if size:
        unit = "Gb" if size.group(2) in ("Gb", "Gbit") else "GB"
        found.append(
            TechnicalRequirement(key="capacity", operator=Operator.GTE, value=float(size.group(1)),
                                 unit=unit, priority=Priority.MUST, origin=RequirementOrigin.QUERY)
        )  # fmt: skip
    if category is not None:
        for req in _keyword_requirements(text, category):
            if (req.key, str(req.value)) not in seen:
                seen.add((req.key, str(req.value)))
                found.append(req)
    return found


def part_tokens(text: str) -> list[str]:
    """Raw part-number-like tokens (letters and digits), excluding quantities such as '100GbE'."""
    out: list[str] = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{2,}", text):
        has_both = re.search(r"[A-Za-z]", token) and re.search(r"\d", token)
        technical = UNIT_TOKEN.match(token) or is_technical_term(token)
        if has_both and not technical and token not in out:
            out.append(token)
    return out


def _removals(text: str, category: Category | None) -> tuple[str, list[str]]:
    """(text without the "ya no necesito X" spans, keys/values to drop)."""
    removed: list[str] = []
    kept = text
    for match in REMOVE_SPAN.finditer(text):
        span = match.group(1)
        found = _requirements(span, category)
        if not found:
            continue
        kept = kept.replace(match.group(0), " ")
        removed += [r.key if r.value == "*" else str(r.value) for r in found]
    return kept, removed


def explicit_intent(text: str) -> str | None:
    """Intent stated by unambiguous words (replace / compare / question), else None."""
    lowered = text.lower()
    if re.search(REPLACE_WORDS, lowered):
        return "replace"
    if re.search(COMPARE_WORDS, lowered):
        return "compare"
    question = re.search(QUESTION_WORDS, lowered) and not re.search(CHEAP_WORDS, lowered)
    if question and not re.search(STATUS_WORDS, lowered) and not REMOVE_SPAN.search(text):
        return "question"
    return None


def parse_query(text: str, category_hint: Category | None = None) -> ParsedQuery:
    """``category_hint``: the category remembered from the conversation (short follow-ups such as
    "400 Gb/s" or "ya no necesito IPsec" do not name it)."""
    category = detect_category(text) or category_hint
    parts = part_tokens(text)
    kept, remove = _removals(text, category)
    requirements = _requirements(kept, category)
    lowered = text.lower()
    intent: Literal["replace", "find", "status", "question", "compare", "other"]
    if re.search(REPLACE_WORDS, lowered):
        intent = "replace"
    elif re.search(COMPARE_WORDS, lowered):
        intent = "compare"
    elif re.search(STATUS_WORDS, lowered) and parts:
        intent = "status"
    elif re.search(QUESTION_WORDS, lowered) and not (
        remove or requirements or re.search(CHEAP_WORDS, lowered)
    ):
        intent = "question"
    elif category or requirements:
        intent = "find"
    else:
        intent = "replace" if parts else "other"
    needs = not parts and category is None
    return ParsedQuery(
        original_text=text,
        intent=intent,
        part_numbers=parts,
        category=category,
        requirements=requirements,
        remove=remove,
        needs_clarification=needs,
        clarification_question=(
            "¿Qué part number quieres reemplazar o qué tipo de componente necesitas?"
            if needs
            else None
        ),
    )
