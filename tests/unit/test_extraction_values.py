from __future__ import annotations

import re

import pytest

from advisor.extraction.values import (
    canonical_interface,
    parse_bool,
    parse_count,
    parse_list,
    parse_number,
    parse_range,
)


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("200KSPS", "S/s", 200_000),
        ("1 MS/s aggregate", "S/s", 1_000_000),
        ("2.4GHz", "GHz", 2.4),
        ("2x 100GbE (QSFP28) or 8x 25GbE breakout", "Gb/s", 100),
        ("192GB_HBM3", "GB", 192),
        ("32Gb", "GB", 4),  # bits → bytes
        ("200Mb", "Kb", 204_800),
        ("2MB", "KB", 2048),
        ("2,039 GB/s", "GB/s", 2039),
        ("5300GBs", "GB/s", 5300),
        ("400W (SXM4), 300W (PCIe)", "W", 400),
        ("16 bits", "bit", 16),
        ("81.7TF", "TFLOPS", 81.7),
        ("96", "W", 96),  # bare number taken in the canonical unit
    ],
)
def test_parse_number(raw: str, unit: str, expected: float) -> None:
    assert parse_number(raw, unit) == expected


def test_incompatible_unit_is_rejected() -> None:
    assert parse_number("5V", "W") is None
    assert parse_number("80 GB", "MHz") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("128lanes", 128),
        ("8SE/4DIFF", 8),
        ("1400K", 1_400_000),
        ("1200K_IOPS", 1_200_000),
        ("up to 1,024 virtual functions", 1024),
        ("Two 16-bit analog outputs", 2),
        ("1.4 million", 1_400_000),
    ],
)
def test_parse_count(raw: str, expected: int) -> None:
    assert parse_count(raw) == expected


def test_parse_range() -> None:
    assert parse_range("5-12V", "V") == (5, 12)
    assert parse_range("4.5V to 15V", "V") == (4.5, 15)
    assert parse_range("300-1500kHz", "kHz") == (300, 1500)
    assert parse_range("1.62V to 3.63V", "V") == (1.62, 3.63)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("gen4x16", "PCIe 4.0 x16"),
        ("PCIe Gen4 x16", "PCIe 4.0 x16"),
        ("PCIe 5.0 x16", "PCIe 5.0 x16"),
        ("gen5", "PCIe 5.0"),
        ("PCIe4x4", "PCIe 4.0 x4"),
        ("USB2.0", "USB 2.0"),
        ("USB 3.0", "USB 3.0"),
        ("SPI/PAR", "SPI/PAR"),
    ],
)
def test_canonical_interface(raw: str, expected: str) -> None:
    assert canonical_interface(raw) == expected


def test_bool_and_list() -> None:
    assert parse_bool("yes") is True and parse_bool("none (via chipset)") is False
    assert parse_list("SXM4 (for DGX/HGX systems), PCIe dual-slot") == ["SXM4", "PCIe dual-slot"]


def test_unit_tokens_belong_to_one_family() -> None:
    from advisor.extraction.values import _FAMILIES

    tokens = [t for units in _FAMILIES.values() for t in units]
    assert len(tokens) == len(set(tokens))


def test_registry_synonyms_map_to_canonical_keywords() -> None:
    from pathlib import Path

    from advisor.extraction import load_spec_registry

    registry = load_spec_registry(
        Path(__file__).resolve().parents[2] / "config" / "spec_registry.yaml"
    )
    measurands = registry.categories["Sensor"]["measurands"]  # type: ignore[index]
    assert measurands.canonical("Humedad") == "humidity"
    assert measurands.canonical("gases volátiles") == "gas"
    assert measurands.canonical("sabor") is None


def test_agilex_user_io_is_read_from_the_gpio_line() -> None:
    from advisor.compatibility.engine import default_registry
    from advisor.models import Category

    pattern = default_registry().for_category(Category.FPGA)["user_io"].patterns[0]
    assert re.search(pattern, "GPIO: up to 624 user I/O. Package:").group(1) == "624"  # type: ignore[union-attr]
