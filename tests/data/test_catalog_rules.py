"""Commercial catalog rules (Catalogo_Comercial_Precios_Inventario_2026.pdf, header note):

ACTIVE = for sale with price and stock; DISCONTINUED = no longer sold; EOL = end of life, no
support nor stock; NRND = not recommended for new designs, limited stock possible. Price only for
ACTIVE. The catalog is the source of truth (CLAUDE.md rule 1) and only ACTIVE is recommended
(rule 4). These tests pin the loaded catalog to the PDF and the agent's answers to those rules.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from advisor.agent import AdvisorAgent
from advisor.models import CommercialInformation, CommercialStatus, CustomerQuery
from advisor.pipeline import BuiltArtifacts, build_agent, load_or_build

pytestmark = pytest.mark.data

# Transcribed from the catalog PDF: part number | status | discontinued | last buy | price | stock
CATALOG_PDF = """\
Cortex-A78|NRND|-|-|-|-
EPYC-9654|ACTIVE|-|-|2150.00|25
w9-3595X|ACTIVE|-|-|1890.00|30
AD7606|ACTIVE|-|-|245.00|3200
USB-1608GX|DISCONTINUED|2024-12-01|2025-03-31|-|0
USB-1808X|ACTIVE|-|-|1125.00|85
USB-2627|DISCONTINUED|2025-06-01|2025-09-30|-|0
USB-2633|ACTIVE|-|-|879.00|150
USB-6001|EOL|2023-09-01|2024-01-31|-|0
AGFB014R24A|ACTIVE|-|-|1450.00|40
ICE40UP5K|ACTIVE|-|-|58.00|8000
XC7A200T|NRND|2025-03-01|-|-|500
A100-SXM4-80GB|NRND|2025-01-15|-|-|12
H100-SXM5|ACTIVE|-|-|2850.00|45
MI300X|ACTIVE|-|-|2490.00|60
RTX-4090|ACTIVE|-|-|1599.00|200
H3A8G32AMR|ACTIVE|-|-|1200.00|2000
H9HCNNNCPMML|ACTIVE|-|-|450.00|5000
MT60B4G8HB-48B|ACTIVE|-|-|185.00|15000
ATSAMD21G18A|DISCONTINUED|2025-04-01|2025-10-31|-|0
ESP32-S3|ACTIVE|-|-|28.00|25000
RP2040|ACTIVE|-|-|8.00|50000
STM32H743ZIT6|ACTIVE|-|-|142.00|4500
BCM57508|ACTIVE|-|-|890.00|75
E810-CQDA2|DISCONTINUED|2025-08-01|2026-02-28|-|0
MCX75310AAS-NEAT|ACTIVE|-|-|1250.00|120
IR3555MTRPBF|EOL|2024-06-01|2024-12-31|-|0
TPS65982AB|ACTIVE|-|-|65.00|3000
BME680|ACTIVE|-|-|98.00|7000
MPU-6050|DISCONTINUED|2023-01-01|2023-06-30|-|0
MZ-V9P2T0|ACTIVE|-|-|389.00|800
WUS4C6464DSP3X5|DISCONTINUED|2025-05-01|2025-11-30|-|0
"""
NOT_ACTIVE = [line.split("|")[0] for line in CATALOG_PDF.splitlines() if "|ACTIVE|" not in line]
REQUIREMENT_SEARCHES = [
    "Busco una GPU de 80GB",
    "Busco una tarjeta de red de 100 Gigabit Ethernet con RDMA",
    "Busco un SSD NVMe de 2TB",
]


@pytest.fixture(scope="module")
def artifacts() -> BuiltArtifacts:
    return load_or_build()


@pytest.fixture(scope="module")
def catalog(artifacts: BuiltArtifacts) -> dict[str, CommercialInformation]:
    return {c.part_number: c for c in artifacts.catalog}


@pytest.fixture(scope="module")
def agent(artifacts: BuiltArtifacts) -> AdvisorAgent:
    return build_agent(artifacts=artifacts)


def _row(c: CommercialInformation) -> tuple[str, ...]:
    return (
        c.status.value,
        c.discontinued_on.isoformat() if c.discontinued_on else "-",
        c.last_buy_on.isoformat() if c.last_buy_on else "-",
        f"{c.price_usd:.2f}" if c.price_usd is not None else "-",
        str(c.stock_units) if c.stock_units is not None else "-",
    )


def test_loaded_catalog_matches_the_pdf_row_by_row(
    catalog: dict[str, CommercialInformation],
) -> None:
    expected = {line.split("|")[0]: tuple(line.split("|")[1:]) for line in CATALOG_PDF.splitlines()}
    assert set(catalog) == set(expected)
    assert {pn: _row(c) for pn, c in catalog.items()} == expected


def test_price_and_stock_follow_the_status_definitions(
    catalog: dict[str, CommercialInformation],
) -> None:
    for c in catalog.values():
        if c.status is CommercialStatus.ACTIVE:
            assert c.price_usd is not None and c.price_usd > 0, c.part_number
            assert c.stock_units, c.part_number  # ACTIVE = available, with stock
        else:
            assert c.price_usd is None, c.part_number  # price only for ACTIVE
        if c.status in (CommercialStatus.DISCONTINUED, CommercialStatus.EOL):
            assert c.stock_units == 0 and c.discontinued_on and c.last_buy_on, c.part_number


@pytest.mark.parametrize("part_number", NOT_ACTIVE)
def test_agent_answers_respect_catalog_rules(
    part_number: str, agent: AdvisorAgent, catalog: dict[str, CommercialInformation]
) -> None:
    response = agent.answer(CustomerQuery(text=f"Necesito reemplazar la {part_number}"))
    assert response.original is not None and response.original.part_number == part_number
    assert response.original.commercial == catalog[part_number]  # status straight from catalog
    statuses = {
        "recommendations": {r.commercial.status for r in response.recommendations},
        "risky": {r.commercial.status for r in response.risky_options},
        "unverified": {r.commercial.status for r in response.unverified_options},
    }
    assert statuses["recommendations"] <= {CommercialStatus.ACTIVE}
    assert statuses["risky"] <= {CommercialStatus.NRND}
    assert statuses["unverified"] <= {CommercialStatus.ACTIVE}
    options = response.recommendations + response.risky_options + response.unverified_options
    for rec in options:  # price, stock and status come from the catalog, never the datasheet
        assert rec.commercial == catalog[rec.product.part_number]
    _no_price_quoted_for_non_active(response.message, options)


@pytest.mark.parametrize("text", REQUIREMENT_SEARCHES)
def test_requirement_searches_never_recommend_non_active(
    text: str, agent: AdvisorAgent, catalog: dict[str, CommercialInformation]
) -> None:
    response = agent.answer(CustomerQuery(text=text))
    assert all(r.commercial.status is CommercialStatus.ACTIVE for r in response.recommendations)
    assert all(r.commercial.status is CommercialStatus.NRND for r in response.risky_options)
    gone = {CommercialStatus.DISCONTINUED, CommercialStatus.EOL}
    options = response.recommendations + response.risky_options + response.unverified_options
    assert not [r.product.part_number for r in options if r.commercial.status in gone]
    for rec in options:
        assert rec.commercial == catalog[rec.product.part_number]
    _no_price_quoted_for_non_active(response.message, options)


def _no_price_quoted_for_non_active(message: str, options: list) -> None:  # type: ignore[type-arg]
    for rec in options:
        if rec.commercial.status is CommercialStatus.ACTIVE:
            continue
        line = next((ln for ln in message.splitlines() if rec.product.part_number in ln), "")
        assert not re.search(r"\d[\d,]*\.\d{2} USD", line), (rec.product.part_number, line)


def test_ui_shows_price_only_for_active(catalog: dict[str, CommercialInformation]) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
    from components.render import price_text

    for c in catalog.values():
        text = price_text(c)
        if c.status is CommercialStatus.ACTIVE:
            assert text == f"US$ {Decimal(c.price_usd or 0):,.2f}"
        else:
            assert text == "Sin precio de venta vigente"
