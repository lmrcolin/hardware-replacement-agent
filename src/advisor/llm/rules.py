"""Rule-based NLU (Spanish/English): the deterministic parser behind TemplateClient."""

from __future__ import annotations

import re
from typing import Literal

from advisor.extraction.values import parse_number
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
STATUS_WORDS = r"\bestado\b|disponib|\bstock\b|inventario|\bprecio\b|status|price|availab"
UNIT_TOKEN = re.compile(
    r"^\d+(?:\.\d+)?(?:gbe|gb|tb|mb|kb|mhz|ghz|khz|w|v|a|bits?|g|ms/s|ks/s|ksps|msps|x\d*)$", re.I
)

# (category or None for any, regex, key, operator, unit, fixed value or None to use group 1)
_NET, _GPU, _DAQ = Category.NETWORK, Category.GPU, Category.DAQ
_SPEED = r"(\d+(?:\.\d+)?)\s*(?:gigabit|gbe|gb/s|gbps)\b"
_CHANNELS = r"(\d+)\s*(?:canales|entradas|channels|inputs)"
_RATE = r"(\d+(?:\.\d+)?\s*(?:ms/s|ks/s|msps|ksps))"
_SRAM = r"(\d+)\s*kb\s*(?:de\s*)?(?:sram|ram)"
_PATTERNS: tuple[tuple[Category | None, str, str, Operator, str | None, str | None], ...] = (
    (_NET, _SPEED, "port_speed", Operator.GTE, "Gb/s", None),
    (_NET, r"\brdma\b", "rdma", Operator.HAS, None, "*"),
    (_NET, r"\broce\b", "rdma", Operator.HAS, None, "RoCE v2"),
    (_NET, r"\biwarp\b", "rdma", Operator.HAS, None, "iWARP"),
    (_NET, r"\bipsec\b", "offloads", Operator.HAS, None, "IPsec"),
    (_NET, r"\btls\b", "offloads", Operator.HAS, None, "TLS"),
    (_NET, r"\bvxlan\b", "offloads", Operator.HAS, None, "VXLAN"),
    (_NET, r"\bgeneve\b", "offloads", Operator.HAS, None, "GENEVE"),
    (_GPU, r"(\d+)\s*gb\b", "memory_size", Operator.GTE, "GB", None),
    (Category.STORAGE, r"(\d+(?:\.\d+)?)\s*tb\b", "capacity", Operator.GTE, "TB", None),
    (_DAQ, _CHANNELS, "analog_inputs", Operator.GTE, "count", None),
    (_DAQ, r"(\d+)\s*-?\s*bits?\b", "resolution", Operator.GTE, "bit", None),
    (_DAQ, _RATE, "sample_rate", Operator.GTE, "S/s", None),
    (Category.MICROCONTROLLER, _SRAM, "sram", Operator.GTE, "KB", None),
)


def detect_category(text: str) -> Category | None:
    lowered = text.lower()
    for pattern, category in CATEGORY_HINTS:
        if re.search(pattern, lowered):
            return category
    return None


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
    return found


def part_tokens(text: str) -> list[str]:
    """Raw part-number-like tokens (letters and digits), excluding quantities such as '100GbE'."""
    out: list[str] = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{2,}", text):
        has_both = re.search(r"[A-Za-z]", token) and re.search(r"\d", token)
        if has_both and not UNIT_TOKEN.match(token) and token not in out:
            out.append(token)
    return out


def parse_query(text: str) -> ParsedQuery:
    category = detect_category(text)
    parts = part_tokens(text)
    requirements = _requirements(text, category)
    lowered = text.lower()
    intent: Literal["replace", "find", "status", "other"]
    if re.search(REPLACE_WORDS, lowered):
        intent = "replace"
    elif re.search(STATUS_WORDS, lowered) and parts:
        intent = "status"
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
        needs_clarification=needs,
        clarification_question=(
            "¿Qué part number quieres reemplazar o qué tipo de componente necesitas?"
            if needs
            else None
        ),
    )
