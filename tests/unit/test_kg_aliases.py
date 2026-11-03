from __future__ import annotations

from advisor.kg.aliases import alias_map, find_mentions, part_root


def test_part_root() -> None:
    assert part_root("E810-CQDA2") == "E810"
    assert part_root("H100-SXM5") == "H100"
    assert part_root("USB-2633") is None  # 'USB' is not distinctive
    assert part_root("BCM57508") is None  # no hyphen: the part number itself is the alias


def test_roots_shared_by_several_parts_are_dropped() -> None:
    aliases = alias_map(["AB12-X", "AB12-Y", "CD34-Z"])
    assert "AB12" not in aliases and aliases["CD34"] == "CD34-Z"


def test_find_mentions_prefers_longest_alias() -> None:
    aliases = alias_map(["E810-CQDA2", "MCX75310AAS-NEAT"])
    text = "consider ConnectX-7 (MCX75310AAS-NEAT) instead of E810-CQDA2 or any E810"
    assert [p for p, _ in find_mentions(text, aliases)] == ["MCX75310AAS-NEAT", "E810-CQDA2"]


def test_no_partial_token_matches() -> None:
    assert find_mentions("XE8100 board", alias_map(["E810-CQDA2"])) == []
