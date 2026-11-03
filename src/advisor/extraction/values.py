"""Raw spec strings → typed values in the registry's canonical unit.

Numbers are only accepted when their unit is convertible to the canonical one; anything else
returns None (the spec is then reported as missing, never guessed).
"""

from __future__ import annotations

import re

# family -> {unit token: factor to the family's base unit}. Tokens are case-sensitive (Mb ≠ MB).
_FAMILIES: dict[str, dict[str, float]] = {
    "freq": {"Hz": 1, "kHz": 1e3, "KHz": 1e3, "MHz": 1e6, "GHz": 1e9},
    "rate": {
        "S/s": 1, "SPS": 1, "kS/s": 1e3, "KS/s": 1e3, "KSPS": 1e3, "kSPS": 1e3, "ksps": 1e3,
        "MS/s": 1e6, "MSPS": 1e6,
    },
    "size": {
        "B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4,
        "b": 1 / 8, "Kb": 1024 / 8, "Kbit": 1024 / 8, "Mb": 1024**2 / 8, "Mbit": 1024**2 / 8,
        "Gb": 1024**3 / 8,
    },
    "bandwidth": {"MB/s": 1, "MBs": 1, "GB/s": 1e3, "GBs": 1e3, "TB/s": 1e6, "TBs": 1e6},
    "link": {"Gb/s": 1, "Gbps": 1, "GbE": 1, "G": 1, "Mbps": 1e-3},
    "transfer": {"MT/s": 1, "MT": 1},
    "power": {"W": 1, "mW": 1e-3, "kW": 1e3},
    "voltage": {"V": 1, "mV": 1e-3},
    "current": {"A": 1, "mA": 1e-3, "uA": 1e-6, "µA": 1e-6},
    "flops": {"TFLOPS": 1, "TF": 1},
    "bits": {"bit": 1, "bits": 1, "-bit": 1},
    "pct": {"pct": 1, "%": 1},
    "dwpd": {"DWPD": 1},
}  # fmt: skip
_UNIT_FAMILY = {unit: fam for fam, units in _FAMILIES.items() for unit in units}
# Canonical units that are counts: a bare number, optionally with K / M / million multipliers.
_COUNT_UNITS = {"count", "IOPS"}
_COUNT_MULTIPLIERS = {"K": 1e3, "k": 1e3, "M": 1e6, "million": 1e6}
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip

_NUMBER = r"-?\d[\d,]*(?:\.\d+)?"
_TOKENS = sorted(_UNIT_FAMILY, key=len, reverse=True)
_NUM_UNIT = re.compile(rf"({_NUMBER})\s?({'|'.join(re.escape(t) for t in _TOKENS)})(?![A-Za-z])")


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def _tidy(value: float) -> int | float:
    rounded = round(value, 6)
    return int(rounded) if rounded == int(rounded) else rounded


def _convert(value: float, unit: str, target: str) -> float | None:
    fam_src, fam_dst = _UNIT_FAMILY.get(unit), _UNIT_FAMILY.get(target)
    if fam_src is None or fam_src != fam_dst:
        return None
    return value * _FAMILIES[fam_src][unit] / _FAMILIES[fam_dst][target]


def parse_count(raw: str) -> int | float | None:
    text = raw.strip()
    first_word = text.split()[0].lower() if text.split() else ""
    if first_word in _WORD_NUMBERS:
        return _WORD_NUMBERS[first_word]
    m = re.search(rf"({_NUMBER})(?:\s?(million|K|k|M)(?![A-Za-z]))?", text)
    if not m:
        return None
    multiplier = _COUNT_MULTIPLIERS.get(m.group(2) or "", 1)
    return _tidy(_to_float(m.group(1)) * multiplier)


def parse_number(raw: str, unit: str) -> int | float | None:
    """First number whose unit converts to ``unit``; a bare number is taken as ``unit``."""
    if unit in _COUNT_UNITS:
        return parse_count(raw)
    for m in _NUM_UNIT.finditer(raw):
        converted = _convert(_to_float(m.group(1)), m.group(2), unit)
        if converted is not None:
            return _tidy(converted)
    if _NUM_UNIT.search(raw):  # had units, none convertible
        return None
    bare = re.search(_NUMBER, raw)
    return _tidy(_to_float(bare.group(0))) if bare else None


def parse_range(raw: str, unit: str) -> tuple[int | float, int | float] | None:
    """'5-12V', '4.5V to 15V', '-40_85C' → (min, max) in ``unit``."""
    m = re.search(
        rf"({_NUMBER})\s?([A-Za-zµ%/]*)\s*(?:-|to|_|\u2013)\s*({_NUMBER})\s?([A-Za-zµ%/]*)", raw
    )
    if not m:
        return None
    lo_unit = m.group(2) or m.group(4) or unit
    hi_unit = m.group(4) or m.group(2) or unit
    lo = (
        _convert(_to_float(m.group(1)), lo_unit, unit) if lo_unit != unit else _to_float(m.group(1))
    )
    hi = (
        _convert(_to_float(m.group(3)), hi_unit, unit) if hi_unit != unit else _to_float(m.group(3))
    )
    if lo is None or hi is None:
        return None
    return (_tidy(min(lo, hi)), _tidy(max(lo, hi)))


def parse_bool(raw: str) -> bool | None:
    word = raw.strip().lower().split()[0] if raw.strip() else ""
    return {"yes": True, "true": True, "no": False, "false": False, "none": False}.get(word)


def parse_list(raw: str) -> list[str]:
    parts = re.split(r"[_,;]|\band\b|\bor\b", re.sub(r"\([^)]*\)", "", raw))
    return [p.strip() for p in parts if p.strip()]


def clean_string(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().rstrip(".")


def canonical_interface(raw: str) -> str:
    """'gen4x16' / 'PCIe Gen4 x16' / 'PCIe 4.0 x16' → 'PCIe 4.0 x16'; 'USB2.0' → 'USB 2.0'."""
    text = clean_string(raw)
    pcie = re.search(
        r"(?i)(?:pcie\s*)?gen\s*(\d)(?:\s*x\s*(\d+))?|pcie\s*(\d)(?:\.0)?(?:\s*x\s*(\d+))?", text
    )
    if pcie and re.search(r"(?i)pcie|gen\s*\d", text):
        gen = pcie.group(1) or pcie.group(3)
        lanes = pcie.group(2) or pcie.group(4)
        return f"PCIe {gen}.0" + (f" x{lanes}" if lanes else "")
    usb = re.fullmatch(r"(?i)usb\s*(\d\.\d)", text)
    if usb:
        return f"USB {usb.group(1)}"
    return text


def strip_parentheticals(raw: str) -> str:
    return re.sub(r"\([^)]*\)", "", raw)
