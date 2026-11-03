"""Dependency-direction contract (mirrors [tool.importlinter] in pyproject.toml).

Higher layers may import lower ones; same-layer siblings and upward imports are violations.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "advisor"
APP = ROOT / "app"

# Top → bottom. Modules on the same line are independent siblings.
LAYERS: list[set[str]] = [
    {"pipeline"},
    {"agent"},
    {"recommendation", "llm"},
    {"compatibility", "commercial", "retrieval"},
    {"kg"},
    {"chunking", "enrichment"},
    {"extraction"},
    {"parsing"},
    {"ingestion"},
    {"repository"},
    {"models", "config"},
]
LEVEL = {module: i for i, layer in enumerate(LAYERS) for module in layer}

FORBIDDEN: dict[str, set[str]] = {
    "compatibility": {"advisor.llm", "advisor.retrieval", "httpx", "databricks"},
    "recommendation": {"advisor.llm", "advisor.retrieval", "httpx", "databricks"},
    "models": {"advisor"},  # models depend on nothing internal except themselves
}
# advisor.pipeline is the composition root (builds the real agent).
APP_ALLOWED = {
    "advisor.models", "advisor.agent", "advisor.repository", "advisor.config", "advisor.pipeline",
    "advisor",
}  # fmt: skip


def imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def top_module(dotted: str) -> str | None:
    parts = dotted.split(".")
    return parts[1] if parts[0] == "advisor" and len(parts) > 1 else None


def violations_for(owner: str, source: str) -> list[str]:
    found: list[str] = []
    for name in imported_modules(source):
        target = top_module(name)
        layered = target and target != owner and target in LEVEL and owner in LEVEL
        if layered and LEVEL[target] <= LEVEL[owner]:
            found.append(f"advisor.{owner} -> {name} (layer direction)")
        for banned in FORBIDDEN.get(owner, set()):
            is_self = top_module(name) == owner
            if (name == banned or name.startswith(banned + ".")) and not is_self:
                found.append(f"advisor.{owner} -> {name} (forbidden)")
    return found


def owner_of(path: Path) -> str:
    rel = path.relative_to(SRC)
    return rel.parts[0].removesuffix(".py")


def test_every_module_is_assigned_a_layer() -> None:
    owners = {owner_of(p) for p in SRC.rglob("*.py")} - {"__init__"}
    assert owners <= set(LEVEL), f"unassigned modules: {owners - set(LEVEL)}"


def test_src_respects_layers() -> None:
    problems = [
        f"{path.relative_to(ROOT)}: {v}"
        for path in SRC.rglob("*.py")
        if owner_of(path) != "__init__"
        for v in violations_for(owner_of(path), path.read_text(encoding="utf-8"))
    ]
    assert not problems, "\n".join(problems)


def test_app_only_uses_public_layers() -> None:
    problems = [
        f"{path.relative_to(ROOT)} -> {name}"
        for path in APP.rglob("*.py")
        for name in imported_modules(path.read_text(encoding="utf-8"))
        if name.startswith("advisor") and name not in APP_ALLOWED
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("owner", "source"),
    [
        ("models", "from advisor.kg import build_graph"),
        ("kg", "from advisor.agent import AdvisorAgent"),
        ("compatibility", "from advisor.llm import LLMClient"),
        ("compatibility", "import httpx"),
        ("retrieval", "from advisor.commercial import CommercialEngine"),  # sibling
    ],
)
def test_checker_detects_violations(owner: str, source: str) -> None:
    assert violations_for(owner, source)


def test_checker_allows_downward_imports() -> None:
    assert not violations_for("agent", "from advisor.compatibility import evaluate")
    assert not violations_for("compatibility", "from advisor.models import Product")
