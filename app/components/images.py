"""Product images for cards and tiles.

Real photos (freely licensed, from Wikimedia Commons) live in ``app/assets/products/`` with their
attribution in ``sources.json``; the UI shows author, license and link under each one. Parts
without a suitable photo (the source PDFs carry none) get an original vector illustration chosen
from their category and extracted form factor / package (SXM module vs PCIe card, U.2 vs M.2,
BGA vs QFP...), marked with the part number. Presentation only: nothing here feeds
compatibility or ranking.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

from advisor.models import Category, Product

PHOTOS = Path(__file__).resolve().parents[1] / "assets" / "products"
PAD = 'fill="url(#metal)"'
PHOTO_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

DEFS = """<defs>
<linearGradient id="pcb" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#2F7D52"/><stop offset="1" stop-color="#1B5C39"/></linearGradient>
<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1">
 <stop offset="0" stop-color="#F1F3F5"/><stop offset=".55" stop-color="#C6CBD1"/>
 <stop offset="1" stop-color="#9AA1A9"/></linearGradient>
<linearGradient id="black" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#454B52"/><stop offset="1" stop-color="#17191C"/></linearGradient>
<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#F5D782"/><stop offset="1" stop-color="#C4952B"/></linearGradient>
<linearGradient id="case" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#F7F8F9"/><stop offset="1" stop-color="#D9DDE1"/></linearGradient>
<filter id="sh" x="-15%" y="-15%" width="130%" height="140%">
 <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#0F1111" flood-opacity=".22"/></filter>
</defs>"""


def _svg(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180" '
        f'font-family="Arial, Helvetica, sans-serif">{DEFS}'
        f'<rect width="240" height="180" fill="#fff"/>{body}</svg>'
    )


def _mark(
    x: float,
    y: float,
    lines: list[str],
    size: float,
    color: str = "#D5D9DD",
    max_width: float = 150,
) -> str:
    """Laser-etched style marking, centred at x; long lines are squeezed to ``max_width``."""
    out = []
    for i, line in enumerate(lines):
        weight = 700 if i == 0 else 400
        fs = size if i == 0 else size * 0.78
        fit = ""
        if len(line) * fs * 0.62 > max_width:
            fit = f' textLength="{max_width:.0f}" lengthAdjust="spacingAndGlyphs"'
        out.append(
            f'<text x="{x}" y="{y + i * size * 1.25}" font-size="{fs:.1f}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="middle"{fit}>{escape(line)}</text>'
        )
    return "".join(out)


def _gold_fingers(x: float, y: float, width: float, n: int, h: float = 10) -> str:
    step = width / n
    return "".join(
        f'<rect x="{x + i * step + 0.8:.1f}" y="{y}" width="{step - 1.6:.1f}" height="{h}" '
        'fill="url(#gold)"/>'
        for i in range(n)
    )


# ---------------------------------------------------------------- packages (chips)


def _chip(pkg: str, lines: list[str], *, w: float = 96, h: float = 96, lid: bool = False) -> str:
    x, y = 120 - w / 2, 90 - h / 2
    parts = []
    if pkg == "qfp":  # gull-wing leads on four sides
        n = 12
        for i in range(n):
            px = x + 8 + i * (w - 16) / (n - 1)
            py = y + 8 + i * (h - 16) / (n - 1)
            parts.append(
                f'<rect x="{px - 2:.1f}" y="{y - 12}" width="4" height="13" fill="url(#metal)"/>'
            )
            parts.append(
                f'<rect x="{px - 2:.1f}" y="{y + h - 1}" width="4" height="13" fill="url(#metal)"/>'
            )
            parts.append(
                f'<rect x="{x - 12}" y="{py - 2:.1f}" width="13" height="4" fill="url(#metal)"/>'
            )
            parts.append(
                f'<rect x="{x + w - 1}" y="{py - 2:.1f}" width="13" height="4" fill="url(#metal)"/>'
            )
        body = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="url(#black)"/>'
    elif pkg == "qfn":  # flat pads flush with the body edge
        n = 9
        for i in range(n):
            px = x + 10 + i * (w - 20) / (n - 1)
            py = y + 10 + i * (h - 20) / (n - 1)
            parts.append(f'<rect x="{px - 2.5:.1f}" y="{y + h - 4}" width="5" height="5" {PAD}/>')
            parts.append(
                f'<rect x="{x - 1}" y="{py - 2.5:.1f}" width="5" height="5" fill="url(#metal)"/>'
            )
            parts.append(f'<rect x="{x + w - 4}" y="{py - 2.5:.1f}" width="5" height="5" {PAD}/>')
        body = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="url(#black)"/>'
    else:  # bga / lga: substrate, optional metal lid
        body = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="url(#pcb)"/>'
        if lid:
            m = min(w, h) * 0.16
            body += (
                f'<rect x="{x + m}" y="{y + m}" width="{w - 2 * m}" height="{h - 2 * m}" rx="4" '
                'fill="url(#metal)" stroke="#8E959C" stroke-width=".8"/>'
            )
        else:
            m = min(w, h) * 0.08
            body += (
                f'<rect x="{x + m}" y="{y + m}" width="{w - 2 * m}" height="{h - 2 * m}" rx="3" '
                'fill="url(#black)"/>'
            )
    dot = f'<circle cx="{x + 11}" cy="{y + 11}" r="3.2" fill="#6B7178"/>'
    color = "#3A3F45" if lid else "#D5D9DD"
    size = 11 if w >= 90 else 9
    return f'<g filter="url(#sh)">{"".join(parts)}{body}</g>{dot}' + _mark(
        120,
        90 - (len(lines) - 1) * size * 0.6 + size * 0.35,
        lines,
        size,
        color,
        max_width=(w * 0.68 if lid else w * 0.84),
    )


# ---------------------------------------------------------------- boards and devices


def _nic(lines: list[str]) -> str:
    return (
        '<g filter="url(#sh)">'
        '<rect x="34" y="42" width="190" height="88" rx="4" fill="url(#pcb)"/>'
        + _gold_fingers(92, 130, 108, 22)
        + '<rect x="14" y="26" width="22" height="128" rx="2" fill="url(#metal)"/>'
        '<rect x="18" y="48" width="14" height="30" rx="2" fill="#24282C"/>'
        '<rect x="18" y="98" width="14" height="30" rx="2" fill="#24282C"/>'
        '<rect x="104" y="54" width="86" height="60" rx="4" fill="url(#black)"/>'
        + "".join(
            f'<rect x="{108 + i * 8}" y="58" width="3" height="52" fill="#5A6067"/>'
            for i in range(10)
        )
        + '<rect x="56" y="58" width="30" height="22" rx="2" fill="url(#black)"/>'
        '<rect x="56" y="88" width="30" height="22" rx="2" fill="url(#black)"/>'
        "</g>" + _mark(147, 152, lines[:1], 11, "#565959")
    )


def _gpu_card(lines: list[str]) -> str:
    fan = "".join(
        f'<circle cx="{cx}" cy="82" r="30" fill="#24282C"/>'
        f'<circle cx="{cx}" cy="82" r="27" fill="none" stroke="#3E444A" stroke-width="2"/>'
        + "".join(
            f'<path d="M{cx} 82 L{cx + 24} {82 - 7 + k}" stroke="#565C63" stroke-width="5" '
            f'transform="rotate({k * 40} {cx} 82)"/>'
            for k in range(9)
        )
        + f'<circle cx="{cx}" cy="82" r="8" fill="url(#metal)"/>'
        for cx in (82, 162)
    )
    return (
        '<g filter="url(#sh)">'
        '<rect x="34" y="118" width="190" height="16" fill="url(#pcb)"/>'
        + _gold_fingers(70, 134, 100, 20)
        + '<rect x="14" y="30" width="22" height="122" rx="2" fill="url(#metal)"/>'
        '<rect x="34" y="40" width="190" height="84" rx="10" fill="url(#black)"/>'
        + fan
        + "</g>"
        + _mark(122, 160, lines[:1], 11, "#565959")
    )


def _gpu_module(lines: list[str]) -> str:
    hbm = "".join(
        f'<rect x="{x}" y="{y}" width="18" height="24" rx="2" fill="url(#black)"/>'
        for x in (64, 158)
        for y in (48, 78, 108)
    )
    holes = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="5" fill="#fff" stroke="url(#metal)" stroke-width="3"/>'
        for cx in (40, 200)
        for cy in (28, 152)
    )
    return (
        '<g filter="url(#sh)">'
        '<rect x="26" y="14" width="188" height="152" rx="6" fill="url(#pcb)"/>'
        '<rect x="88" y="44" width="64" height="92" rx="4" fill="url(#metal)" stroke="#8E959C"/>'
        + hbm
        + holes
        + '<rect x="56" y="146" width="56" height="10" rx="2" fill="#24282C"/>'
        '<rect x="128" y="146" width="56" height="10" rx="2" fill="#24282C"/></g>'
        + _mark(120, 86, lines, 9.5, "#3A3F45", max_width=56)
    )


def _daq(lines: list[str]) -> str:
    screws = "".join(
        f'<rect x="{36 + i * 11}" y="36" width="10" height="16" rx="1.5" fill="#2F8A57"/>'
        f'<circle cx="{41 + i * 11}" cy="44" r="3" fill="url(#metal)"/>'
        for i in range(16)
    )
    return (
        '<g filter="url(#sh)">'
        '<rect x="28" y="46" width="188" height="100" rx="10" fill="url(#case)" stroke="#B9BFC5"/>'
        + screws
        + '<rect x="44" y="70" width="156" height="50" rx="4" fill="#232F3E"/>'
        '<rect x="214" y="84" width="10" height="20" rx="2" fill="url(#metal)"/>'
        '<circle cx="190" cy="132" r="3.5" fill="#33C26B"/><circle cx="178" cy="132" r="3.5" '
        'fill="#FFB020"/></g>' + _mark(122, 92, lines, 12, "#FFFFFF", max_width=140)
    )


def _ssd_m2(lines: list[str]) -> str:
    return (
        '<g filter="url(#sh)">'
        '<path d="M22 66 h196 a8 8 0 0 1 0 16 v4 a8 8 0 0 1 0 16 h-196 z" fill="url(#pcb)"/>'
        + _gold_fingers(10, 68, 12, 1, 32)
        + '<rect x="40" y="70" width="40" height="28" rx="2" fill="url(#black)"/>'
        '<rect x="92" y="68" width="52" height="32" rx="2" fill="url(#black)"/>'
        '<rect x="152" y="68" width="52" height="32" rx="2" fill="url(#black)"/>'
        '<circle cx="218" cy="84" r="5" fill="#fff"/></g>' + _mark(120, 128, lines, 11, "#565959")
    )


def _ssd_u2(lines: list[str]) -> str:
    screws = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="4" fill="url(#metal)" stroke="#8E959C"/>'
        for cx in (54, 186)
        for cy in (30, 142)
    )
    return (
        '<g filter="url(#sh)">'
        '<rect x="40" y="16" width="160" height="148" rx="8" fill="url(#metal)" stroke="#8E959C"/>'
        '<rect x="62" y="42" width="116" height="86" rx="4" fill="#FFFFFF" stroke="#C6CBD1"/>'
        '<rect x="62" y="42" width="116" height="16" rx="4" fill="#232F3E"/>'
        + screws
        + '<rect x="78" y="160" width="84" height="8" rx="2" fill="#24282C"/></g>'
        + _mark(120, 84, lines, 11, "#0F1111", max_width=104)
    )


def _hbm(lines: list[str]) -> str:
    layers = "".join(
        f'<path d="M60 {112 - i * 10} L120 {82 - i * 10} L180 {112 - i * 10} '
        f'L120 {142 - i * 10} Z" '
        f'fill="{"url(#metal)" if i == 7 else "#2B3036"}" stroke="#596068" stroke-width=".8"/>'
        for i in range(8)
    )
    return f'<g filter="url(#sh)">{layers}</g>' + _mark(120, 168, lines[:1], 11, "#565959")


def _ip_die(lines: list[str]) -> str:
    blocks = "".join(
        f'<rect x="{62 + c * 30}" y="{34 + r * 30}" width="26" height="26" rx="2" '
        f'fill="{["#5B4E8C", "#6E62A3", "#4A6FA5", "#7A6BB0"][(r + c) % 4]}"/>'
        for r in range(2)
        for c in range(4)
    )
    return (
        '<g filter="url(#sh)"><rect x="52" y="24" width="136" height="132" rx="4" fill="#3B3456"/>'
        + blocks
        + '<rect x="62" y="96" width="116" height="50" rx="2" fill="#2A4E7A"/></g>'
        + _mark(120, 118, lines, 10.5, "#FFFFFF", max_width=104)
    )


def _cpu(lines: list[str]) -> str:
    return _chip("bga", lines, w=168, h=140, lid=True)


# ---------------------------------------------------------------- selection


def _spec_text(product: Product, *keys: str) -> str:
    values = [s.value for s in product.specifications if s.key in keys]
    flat = [v for value in values for v in (value if isinstance(value, list) else [value])]
    return " ".join(str(v) for v in flat).upper()


def kind(product: Product) -> str:
    """Illustration family from category plus form factor / package / host interface."""
    package = _spec_text(product, "package")
    form = _spec_text(product, "form_factor")
    host = _spec_text(product, "host_interface", "interface")
    memory = _spec_text(product, "memory_type")
    pn = product.part_number.upper()
    match product.category:
        case Category.NETWORK:
            return "nic"
        case Category.GPU:
            sxm = "SXM" in form or "OAM" in form or "SXM" in pn
            return "gpu_module" if sxm else "gpu_card"
        case Category.DAQ:
            return "daq" if "USB" in host or pn.startswith("USB") else "qfp"
        case Category.FPGA:
            return "qfn" if package.startswith("48-PIN QFN") else "fpga"
        case Category.CPU:
            description = (product.description or "").upper()
            return "ip_die" if " IP " in f" {description} " or pn.startswith("CORTEX") else "cpu"
        case Category.MEMORY:
            return "hbm" if "HBM" in memory else "bga"
        case Category.STORAGE:
            return "ssd_u2" if "U.2" in form else "ssd_m2"
        case Category.POWER:
            return "bga" if "BGA" in package else "qfn"
        case Category.SENSOR:
            return "lga" if "LGA" in package else "qfn"
        case _:  # microcontrollers and anything new
            return "qfp"


def _marking(product: Product) -> list[str]:
    pn = product.part_number
    lines = [pn if len(pn) <= 14 else pn[:13] + "…"]
    maker = product.manufacturer.split("(")[0].strip()
    return [*lines, maker[:16]]


def illustration_svg(product: Product) -> str:
    lines = _marking(product)
    drawers: dict[str, Callable[[list[str]], str]] = {
        "nic": _nic,
        "gpu_card": _gpu_card,
        "gpu_module": _gpu_module,
        "daq": _daq,
        "ssd_m2": _ssd_m2,
        "ssd_u2": _ssd_u2,
        "hbm": _hbm,
        "ip_die": _ip_die,
        "cpu": _cpu,
        "qfp": lambda m: _chip("qfp", m),
        "qfn": lambda m: _chip("qfn", m),
        "bga": lambda m: _chip("bga", m, w=110, h=110),
        "fpga": lambda m: _chip("bga", m, w=130, h=130, lid=True),
        "lga": lambda m: _chip("bga", m, w=84, h=84, lid=True),
    }
    return _svg(drawers[kind(product)](lines))


_CACHE: dict[str, tuple[str, bool]] = {}


def image_source(product: Product) -> tuple[str, bool]:
    """(data URI, is_photo). Real photo in app/assets/products/ wins over the illustration."""
    if product.part_number not in _CACHE:
        for suffix, mime in PHOTO_TYPES.items():
            photo = PHOTOS / f"{product.part_number}{suffix}"
            if photo.is_file():
                data = base64.b64encode(photo.read_bytes()).decode()
                _CACHE[product.part_number] = (f"data:{mime};base64,{data}", True)
                break
        else:
            data = base64.b64encode(illustration_svg(product).encode()).decode()
            _CACHE[product.part_number] = (f"data:image/svg+xml;base64,{data}", False)
    return _CACHE[product.part_number]


def photo_credit(part_number: str) -> dict[str, Any] | None:
    """Attribution entry from ``assets/products/sources.json`` (required by CC BY / BY-SA)."""
    manifest = PHOTOS / "sources.json"
    if not manifest.is_file():
        return None
    entry: dict[str, Any] | None = json.loads(manifest.read_text(encoding="utf-8")).get(part_number)
    return entry


def _caption(product: Product, is_photo: bool) -> str:
    if not is_photo:
        return '<div class="pimg-note">Ilustración</div>'
    credit = photo_credit(product.part_number)
    if credit is None:
        return '<div class="pimg-note">Foto</div>'
    text = (
        f'Foto: <a href="{escape(credit["source_url"])}" target="_blank">'
        f"{escape(credit['author'])}</a> · "
        f'<a href="{escape(credit["license_url"])}" target="_blank">{escape(credit["license"])}</a>'
    )
    if credit.get("note"):
        prefix = "" if credit.get("exact") else "Referencia: "
        text += f"<br>{prefix}{escape(credit['note'])}"
    return f'<div class="pimg-note">{text}</div>'


def image_html(product: Product, *, css_class: str = "pimg") -> str:
    src, is_photo = image_source(product)
    alt = escape(f"{product.part_number} · {product.manufacturer}")
    caption = _caption(product, is_photo)
    return f'<div class="{css_class}"><img src="{src}" alt="{alt}" loading="lazy"/>{caption}</div>'
