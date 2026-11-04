"""Design system loader: one stylesheet (``app/static/design.css``) with the tokens, the unified
avatar, and the Spanish status/compatibility badges used across the UI.

Only presentation. Colors and spacing live as CSS tokens in the stylesheet, never here.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from advisor.models import CommercialStatus, CompatibilityLevel

STATIC = Path(__file__).resolve().parents[1] / "static"


def css() -> str:
    """The stylesheet, read on every run (edits to design.css show up without a restart)."""
    return f"<style>{(STATIC / 'design.css').read_text(encoding='utf-8')}</style>"


CSS = css()
AVATAR_PATH = STATIC / "avatar.svg"
AVATAR_URI = "data:image/svg+xml;base64," + base64.b64encode(AVATAR_PATH.read_bytes()).decode()

# (label, color, explanation) — Spanish, sentence case; the tooltip says what it means.
STATUS_BADGE: dict[CommercialStatus, tuple[str, str, str]] = {
    CommercialStatus.ACTIVE: ("Disponible", "green", "Activa: se vende con precio y stock."),
    CommercialStatus.DISCONTINUED: (
        "Descontinuada", "red", "El fabricante dejó de producirla; ya no se vende.",
    ),
    CommercialStatus.EOL: (
        "Fin de vida (EOL)", "orange", "End of life: sin soporte ni stock nuevo.",
    ),
    CommercialStatus.NRND: (
        "No recomendada (NRND)", "amber",
        "Not recommended for new designs: puede quedar stock, pero no conviene para diseños "
        "nuevos.",
    ),
}  # fmt: skip
LEVEL_BADGE: dict[CompatibilityLevel, tuple[str, str, str]] = {
    CompatibilityLevel.COMPATIBLE: (
        "Compatible", "green", "Cumple todos los requisitos críticos con evidencia.",
    ),
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: (
        "Compatible con condiciones", "orange",
        "Cumple lo crítico, pero requiere una acción (adaptador, firmware, ópticas…).",
    ),
    CompatibilityLevel.UNKNOWN: (
        "Sin datos suficientes", "gray",
        "Su datasheet no declara algún dato crítico: requiere validación de un experto.",
    ),
    CompatibilityLevel.INCOMPATIBLE: (
        "No compatible", "red", "Falla al menos un requisito crítico.",
    ),
}  # fmt: skip


def badge(spec: tuple[str, str, str], *, large: bool = False) -> str:
    label, color, tip = spec
    size = " lg" if large else ""
    return f'<span class="badge {color}{size}" title="{escape(tip)}">{escape(label)}</span>'


def status_badge(status: CommercialStatus, *, large: bool = False) -> str:
    return badge(STATUS_BADGE[status], large=large)


def level_badge(level: CompatibilityLevel, *, large: bool = False) -> str:
    return badge(LEVEL_BADGE[level], large=large)
