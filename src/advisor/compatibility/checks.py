"""Pure value comparisons used by the compatibility engine (no I/O, no models beyond enums)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from advisor.models import Operator, SpecValue


class Check(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"  # value absent or not comparable (type/unit mismatch): never a match
    UPGRADE = "UPGRADE"  # same interface family, higher version: acceptable with conditions


@dataclass(frozen=True)
class InterfaceVersion:
    family: str
    version: float
    lanes: int | None


_INTERFACE = re.compile(
    r"\b(?P<family>pcie|usb)\s*(?:gen\s*)?(?P<version>\d+(?:\.\d+)?)(?:\s*x\s*(?P<lanes>\d+))?",
    re.IGNORECASE,
)


def parse_interface(value: str) -> InterfaceVersion | None:
    """'PCIe 4.0 x16' / 'PCIe Gen5 x16' / 'USB 2.0' / 'PCIe4x4' -> family, version, lanes."""
    match = _INTERFACE.search(value.replace("_", " "))
    if not match:
        return None
    lanes = match.group("lanes")
    return InterfaceVersion(
        family=match.group("family").lower(),
        version=float(match.group("version")),
        lanes=int(lanes) if lanes else None,
    )


def _norm(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).casefold()


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _as_set(value: SpecValue) -> set[str] | None:
    if isinstance(value, list):
        return {_norm(v) for v in value}
    if isinstance(value, str):
        return {_norm(value)}
    return None


def _interface_upgrade(required: str, candidate: str) -> bool:
    req, cand = parse_interface(required), parse_interface(candidate)
    if req is None or cand is None or req.family != cand.family or cand.version <= req.version:
        return False
    return req.lanes is None or cand.lanes is None or cand.lanes >= req.lanes


def compare(operator: Operator, required: SpecValue, candidate: SpecValue | None) -> Check:
    """Compare a candidate spec value against a requirement. Absent or incomparable => MISSING."""
    if candidate is None:
        return Check.MISSING

    if operator in (Operator.GTE, Operator.LTE):
        if not (_is_number(required) and _is_number(candidate)):
            return Check.MISSING
        req_n, cand_n = float(required), float(candidate)  # type: ignore[arg-type]
        ok = cand_n >= req_n if operator is Operator.GTE else cand_n <= req_n
        return Check.PASS if ok else Check.FAIL

    if isinstance(required, bool) or isinstance(candidate, bool):
        if not (isinstance(required, bool) and isinstance(candidate, bool)):
            return Check.MISSING
        return Check.PASS if required == candidate else Check.FAIL

    if _is_number(required) or _is_number(candidate):
        if not (_is_number(required) and _is_number(candidate)):
            return Check.MISSING
        return Check.PASS if float(required) == float(candidate) else Check.FAIL  # type: ignore[arg-type]

    req_set, cand_set = _as_set(required), _as_set(candidate)
    if req_set is None or cand_set is None:
        return Check.MISSING

    if operator is Operator.HAS:
        return Check.PASS if req_set <= cand_set else Check.FAIL
    # EQ and IN: any overlap (a list spec such as form_factor matches if it offers the value).
    if req_set & cand_set:
        return Check.PASS
    if (
        operator is Operator.EQ
        and isinstance(required, str)
        and isinstance(candidate, str)
        and _interface_upgrade(required, candidate)
    ):
        return Check.UPGRADE
    return Check.FAIL
