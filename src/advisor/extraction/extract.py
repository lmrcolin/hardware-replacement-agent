"""Spec extraction: ParsedDocument → Product with ProductSpecification + Evidence.

Every extracted value carries a literal quote (whitespace-normalized) from the page it came from.
Nothing is inferred from similar products; keys not found in the text are simply absent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from advisor.extraction.registry import SpecDefinition, SpecRegistry
from advisor.extraction.values import (
    canonical_interface,
    clean_string,
    parse_bool,
    parse_list,
    parse_number,
    parse_range,
)
from advisor.models import (
    Category,
    Evidence,
    ParsedDocument,
    Product,
    ProductSpecification,
    SpecValue,
)

log = logging.getLogger(__name__)

SUMMARY_HEADING = "Key Specifications Summary"
META_LABELS = (
    "Product Status",
    "Manufacturer",
    "Part Number",
    "Category",
    "Document Revision",
    "Language",
)
INTERFACE_KEYS = {"host_interface", "interface"}
# Sections that describe *other* products (successors, alternatives, ordering); never a spec source.
FOREIGN_SECTIONS = re.compile(r"Notice|Migration|Ordering Information|Replacement")

_HEADER = re.compile(r"^(Part Number|Manufacturer|Category):\s*(.+?)(?:\.\s|\.?$)", re.M)
_SUMMARY_PAIR = re.compile(r"([A-Za-z]\w*):\s*(.*?)\.(?=\s+[A-Za-z]\w*:|\s*$)")
_LABELED = re.compile(r"(?:^|(?<=\.\s))([A-Z][A-Za-z0-9 /+()-]{0,40}?):\s*(.+?)(?=\.\s|\.?$)")
_PART_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\b")
_NEGATION = r"\b(?:no|not|without|none)\b\W+(?:\w+\W+){0,2}"
# Deterministic fallback for datasheets without a "Category:" header; join_catalog overrides it.
_CATEGORY_HINTS: tuple[tuple[str, Category], ...] = (
    (r"\bGPU\b", Category.GPU),
    (r"Ethernet|SmartNIC|\bNIC\b|Network", Category.NETWORK),
    (r"\bDAQ\b|Data Acquisition", Category.DAQ),
    (r"\bFPGA", Category.FPGA),
    (r"\bMCU\b|Microcontroller", Category.MICROCONTROLLER),
    (r"\bSSD\b|NVMe", Category.STORAGE),
    (r"DRAM|SDRAM|\bHBM", Category.MEMORY),
    (r"Processor|\bCPU\b", Category.CPU),
    (r"Sensor", Category.SENSOR),
    (r"Regulator|Power Delivery|\bPD Controller", Category.POWER),
)


class ExtractionError(ValueError):
    """The document cannot be turned into a Product (no part number / category)."""


@dataclass(frozen=True)
class Segment:
    page: int
    heading: str
    text: str  # whitespace-normalized


@dataclass(frozen=True)
class _Found:
    raw: str
    page: int
    quote: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_heading(line: str) -> bool:
    return (
        ":" not in line
        and not line.endswith(".")
        and len(line) <= 60
        and len(line.split()) <= 7
        and line[0].isupper()
    )


def segments(doc: ParsedDocument) -> list[Segment]:
    """Split each page at section headings and metadata lines ('Manufacturer: ...')."""
    out: list[Segment] = []
    for page in doc.pages:
        heading: str = ""
        buf: list[str] = []
        for raw in page.text.splitlines():
            line = raw.strip()
            if not line:
                continue
            is_meta = line.startswith(tuple(f"{m}:" for m in META_LABELS))
            if _is_heading(line) or is_meta:
                if buf:
                    out.append(Segment(page.page_number, heading, normalize(" ".join(buf))))
                heading, buf = (line, []) if not is_meta else ("", [line])
            else:
                buf.append(line)
        if buf:
            out.append(Segment(page.page_number, heading, normalize(" ".join(buf))))
    return out


def header_fields(doc: ParsedDocument) -> dict[str, str]:
    """'Part Number', 'Manufacturer', 'Category' lines (first occurrence wins)."""
    fields: dict[str, str] = {}
    for page in doc.pages:
        for key, value in _HEADER.findall(page.text):
            fields.setdefault(key, value.strip())
    return fields


def own_segments(segs: list[Segment]) -> list[Segment]:
    return [s for s in segs if not FOREIGN_SECTIONS.search(s.heading)]


def _find_raw(segs: list[Segment], definition: SpecDefinition) -> _Found | None:
    """Precedence: summary alias > prose label alias > regex pattern."""
    for seg in segs:
        if seg.heading == SUMMARY_HEADING:
            for key, value in _SUMMARY_PAIR.findall(seg.text):
                if key.lower() in definition.aliases:
                    return _Found(value.strip(), seg.page, f"{key}: {value.strip()}")
    for seg in segs:
        if seg.heading != SUMMARY_HEADING:
            for label, value in _LABELED.findall(seg.text):
                if label.strip().lower() in definition.aliases:
                    return _Found(value.strip(), seg.page, f"{label.strip()}: {value.strip()}")
    for pattern in definition.patterns:
        for seg in segs:
            m = re.search(pattern, seg.text)
            if m:
                return _Found(m.group(1), seg.page, m.group(0))
    return None


def _sentence(text: str, start: int, end: int) -> str:
    left = text.rfind(". ", 0, start)
    right = text.find(". ", end)
    return text[left + 2 if left >= 0 else 0 : right if right >= 0 else len(text)]


def _keyword_hits(segs: list[Segment], keywords: list[str]) -> list[tuple[str, _Found]]:
    hits: list[tuple[str, _Found]] = []
    for keyword in keywords:
        # Short acronyms (CAN, TLS, GRE) are case-sensitive: prose like "can shift" must not match.
        flags = 0 if len(keyword) <= 4 else re.I
        rx = re.compile(rf"(?<![A-Za-z]){re.escape(keyword)}(?![A-Za-z])", flags)
        found = None
        for seg in segs:
            for m in rx.finditer(seg.text):
                sentence = _sentence(seg.text, m.start(), m.end())
                if re.search(_NEGATION + re.escape(m.group(0)), sentence, re.I):
                    continue  # "No NVLink support" is not evidence of NVLink
                found = _Found(m.group(0), seg.page, sentence)
                break
            if found:
                break
        if found:
            hits.append((keyword, found))
    return hits


def _evidence(doc: ParsedDocument, found: _Found) -> Evidence:
    return Evidence(document_id=doc.document_id, page=found.page, quote=found.quote)


def _spec(
    key: str, value: SpecValue, unit: str | None, raw: str, ev: list[Evidence]
) -> ProductSpecification:
    return ProductSpecification(key=key, value=value, unit=unit, raw_value=raw, evidence=ev)


def _typed_specs(
    doc: ParsedDocument, segs: list[Segment], key: str, definition: SpecDefinition
) -> list[ProductSpecification]:
    if definition.type == "list" and definition.keywords:
        hits = _keyword_hits(segs, definition.keywords)
        if not hits:
            return []
        evidence = [_evidence(doc, f) for _, f in hits]
        return [
            _spec(key, [kw for kw, _ in hits], None, ", ".join(f.raw for _, f in hits), evidence)
        ]

    found = _find_raw(segs, definition)
    if found is None:
        return []
    evidence = [_evidence(doc, found)]
    unit = definition.unit
    value: SpecValue | None
    if definition.type == "range":
        assert unit is not None
        single = parse_number(found.raw, unit)
        bounds = parse_range(found.raw, unit) or ((single, single) if single is not None else None)
        if bounds is None:
            return []
        return [
            _spec(f"{key}_min", bounds[0], unit, found.raw, evidence),
            _spec(f"{key}_max", bounds[1], unit, found.raw, evidence),
        ]
    if definition.type == "number":
        assert unit is not None
        value = parse_number(found.raw, unit)
    elif definition.type == "boolean":
        value = parse_bool(found.raw)
    elif definition.type == "list":
        value = parse_list(found.raw)
    elif key in INTERFACE_KEYS:
        value = canonical_interface(found.raw)
    else:
        value = clean_string(found.raw)
    if value is None or value == [] or value == "":
        log.debug("unparseable spec", extra={"key": key, "raw": found.raw})
        return []
    return [_spec(key, value, unit if definition.type == "number" else None, found.raw, evidence)]


def _category(doc: ParsedDocument, header: dict[str, str]) -> tuple[Category, str | None]:
    raw = header.get("Category")
    if raw:
        main, _, sub = raw.partition("/")
        try:
            return Category(main.strip()), sub.strip() or None
        except ValueError as exc:
            raise ExtractionError(f"unknown category {main!r}") from exc
    for text in (doc.title or "", doc.pages[0].text if doc.pages else ""):
        for pattern, category in _CATEGORY_HINTS:
            if re.search(pattern, text):
                return category, None
    raise ExtractionError(f"no category for document {doc.document_id[:12]}")


def document_part_number(doc: ParsedDocument) -> str | None:
    """Header 'Part Number:' or, failing that, the first title token containing a digit."""
    header = header_fields(doc)
    if header.get("Part Number"):
        return header["Part Number"]
    return next(
        (t for t in _PART_TOKEN.findall(doc.title or "") if any(c.isdigit() for c in t)), None
    )


def _part_number(doc: ParsedDocument) -> str:
    part = document_part_number(doc)
    if part is None:
        raise ExtractionError(f"no part number for document {doc.document_id[:12]}")
    return part


def extract_product(doc: ParsedDocument, registry: SpecRegistry) -> Product:
    """Datasheet → Product with ProductSpecification + Evidence (no commercial data)."""
    header = header_fields(doc)
    category, subcategory = _category(doc, header)
    segs = own_segments(segments(doc))
    definitions = {**registry.common, **registry.for_category(category)}
    specs: list[ProductSpecification] = []
    for key, definition in definitions.items():
        if key != "subcategory":
            specs.extend(_typed_specs(doc, segs, key, definition))
    if subcategory:
        found = _Found(subcategory, 1, f"Category: {header['Category']}")
        specs.append(_spec("subcategory", subcategory, None, subcategory, [_evidence(doc, found)]))
    return Product(
        part_number=_part_number(doc),
        manufacturer=header.get("Manufacturer", ""),
        category=category,
        description=doc.title,
        specifications=specs,
        document_ids=[doc.document_id],
    )
