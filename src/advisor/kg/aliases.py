"""Part-number aliases shared by graph construction and part resolution."""

from __future__ import annotations

import re
from collections.abc import Iterable


def normalize_part(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def part_root(part_number: str) -> str | None:
    """Distinctive first hyphen segment: 'E810' for 'E810-CQDA2', 'H100' for 'H100-SXM5'."""
    head = part_number.split("-")[0]
    has_letter = any(c.isalpha() for c in head)
    has_digit = any(c.isdigit() for c in head)
    return head if head != part_number and len(head) >= 4 and has_letter and has_digit else None


def alias_map(part_numbers: Iterable[str]) -> dict[str, str]:
    """alias → part number: the part number itself plus unique roots."""
    parts = list(part_numbers)
    roots: dict[str, list[str]] = {}
    for part in parts:
        root = part_root(part)
        if root:
            roots.setdefault(root, []).append(part)
    aliases = {part: part for part in parts}
    aliases.update({root: owners[0] for root, owners in roots.items() if len(owners) == 1})
    return aliases


def find_mentions(text: str, aliases: dict[str, str]) -> list[tuple[str, int]]:
    """(part number, position) for every alias found as a whole token, longest alias first."""
    hits: dict[str, int] = {}
    taken: list[range] = []
    for alias in sorted(aliases, key=len, reverse=True):
        for m in re.finditer(rf"(?<![A-Za-z0-9-]){re.escape(alias)}(?![A-Za-z0-9])", text):
            if any(m.start() in span for span in taken):
                continue
            taken.append(range(m.start(), m.end()))
            hits.setdefault(aliases[alias], m.start())
    return sorted(hits.items(), key=lambda item: item[1])
