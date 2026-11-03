"""`make pipeline-local`: artifacts round-trip and an agent built from them answers like the in-memory one."""

from __future__ import annotations

from pathlib import Path

import pytest

from advisor.llm import TemplateClient
from advisor.models import CompatibilityLevel, CustomerQuery
from advisor.pipeline import build_agent, build_in_memory, export_artifacts, load_artifacts
from advisor.repository import LocalParquetRepository

pytestmark = [pytest.mark.integration, pytest.mark.data]
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


@pytest.fixture(scope="module")
def artifacts_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("artifacts")
    summary = export_artifacts(artifacts_dir=root)
    assert summary["products"] == 32 and summary["chunks"] == 126 and summary["migrates_to"] == 4
    return root


def test_files_written(artifacts_dir: Path) -> None:
    names = {p.name for p in artifacts_dir.iterdir()}
    assert {
        "products.parquet",
        "chunks.parquet",
        "compat_matrix.parquet",
        "graph.json",
        "documents.json",
    } <= names


def test_roundtrip_matches_in_memory(artifacts_dir: Path) -> None:
    loaded = load_artifacts(artifacts_dir=artifacts_dir)
    built = build_in_memory()
    assert loaded is not None
    assert {p.part_number: p for p in loaded.products} == {p.part_number: p for p in built.products}
    assert [c.chunk_id for c in loaded.chunks] == sorted(c.chunk_id for c in built.chunks)
    assert set(loaded.graph.nodes) == set(built.graph.nodes)
    assert loaded.document_names == built.document_names


def test_compat_matrix_contents(artifacts_dir: Path) -> None:
    matrix = LocalParquetRepository(artifacts_dir).load_compat_matrix()
    by_pair = {(r.original_part_number, r.candidate_part_number): r.level for r in matrix}
    assert by_pair[("USB-2627", "USB-2633")] is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    assert by_pair[("MPU-6050", "BME680")] is CompatibilityLevel.INCOMPATIBLE
    assert all(orig != cand for orig, cand in by_pair)


def test_missing_artifacts_returns_none(tmp_path: Path) -> None:
    assert load_artifacts(artifacts_dir=tmp_path) is None


def test_agent_from_artifacts_answers_official_case(artifacts_dir: Path) -> None:
    loaded = load_artifacts(artifacts_dir=artifacts_dir)
    agent = build_agent(artifacts=loaded)
    agent.llm_chain = [TemplateClient()]  # deterministic regardless of local settings
    resp = agent.answer(CustomerQuery(text=OFFICIAL))
    assert [r.product.part_number for r in resp.recommendations] == ["MCX75310AAS-NEAT", "BCM57508"]
