"""AdvisorAgent end to end over the real data (template LLM; fakes for hallucination checks)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from advisor.agent import AdvisorAgent, AgentStep
from advisor.commercial import CommercialEngine
from advisor.llm import LLMClient, TemplateClient
from advisor.models import (
    Category,
    CommercialStatus,
    CustomerQuery,
    Operator,
    ParsedQuery,
    RequirementOrigin,
    TechnicalRequirement,
)
from advisor.pipeline import BuiltArtifacts, build_in_memory
from advisor.retrieval import BM25Retriever

pytestmark = pytest.mark.data
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


@pytest.fixture(scope="module")
def built() -> BuiltArtifacts:
    return build_in_memory()


def make_agent(built: BuiltArtifacts, *chain: LLMClient) -> AdvisorAgent:
    return AdvisorAgent(
        graph=built.graph,
        products=built.products,
        commercial=CommercialEngine(built.catalog),
        retriever=BM25Retriever(built.chunks),
        llm_chain=list(chain) or [TemplateClient()],
    )


def test_official_case_end_to_end(built: BuiltArtifacts) -> None:
    agent = make_agent(built)
    resp = agent.answer(CustomerQuery(text=OFFICIAL))
    assert resp.original is not None and resp.original.part_number == "E810-CQDA2"
    assert [
        (r.product.part_number, r.commercial.price_usd, r.commercial.stock_units)
        for r in resp.recommendations
    ] == [
        ("MCX75310AAS-NEAT", Decimal("1250.00"), 120),
        ("BCM57508", Decimal("890.00"), 75),
    ]
    assert "DISCONTINUED" in resp.message and "1,250.00 USD" in resp.message
    assert agent.last_trace == [
        AgentStep.PARSE, AgentStep.RESOLVE, AgentStep.STATUS, AgentStep.DISCOVER,
        AgentStep.VALIDATE, AgentStep.RANK, AgentStep.COMPOSE, AgentStep.VERIFY,
    ]  # fmt: skip
    assert resp.llm_provider == "template" and not resp.is_synthetic


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("reemplazo para el usb 2627", ["USB-2633"]),
        ("necesito reemplazar la A100", []),
        ("MPU-6050", []),
    ],
)
def test_known_cases(built: BuiltArtifacts, text: str, expected: list[str]) -> None:
    resp = make_agent(built).answer(CustomerQuery(text=text))
    assert [r.product.part_number for r in resp.recommendations] == expected


def test_a100_explains_why_its_successor_is_not_a_drop_in(built: BuiltArtifacts) -> None:
    resp = make_agent(built).answer(CustomerQuery(text="necesito reemplazar la A100"))
    assert "H100-SXM5 como sucesor" in resp.message and "form_factor" in resp.message


def test_vague_query_asks_for_clarification(built: BuiltArtifacts) -> None:
    agent = make_agent(built)
    resp = agent.answer(CustomerQuery(text="busco un microcontrolador barato"))
    assert resp.clarification_question and not resp.recommendations
    assert agent.last_trace[-1] is AgentStep.CLARIFY


def test_find_by_requirements_without_part_number(built: BuiltArtifacts) -> None:
    resp = make_agent(built).answer(CustomerQuery(text="busco una GPU de 80GB"))
    parts = [r.product.part_number for r in resp.recommendations]
    assert set(parts) == {"MI300X", "H100-SXM5"} and resp.original is None
    assert [r.product.part_number for r in resp.risky_options] == ["A100-SXM4-80GB"]


@pytest.mark.safety
def test_recommendations_are_always_active_with_catalog_prices(built: BuiltArtifacts) -> None:
    agent = make_agent(built)
    catalog = {c.part_number: c for c in built.catalog}
    for product in built.products:
        resp = agent.answer(CustomerQuery(text=f"necesito reemplazar {product.part_number}"))
        for rec in resp.recommendations:
            row = catalog[rec.product.part_number]
            assert row.status is CommercialStatus.ACTIVE
            assert (rec.commercial.price_usd, rec.commercial.stock_units) == (
                row.price_usd,
                row.stock_units,
            )


# ------------------------------------------------------------------ hallucination control


class LyingNLU(TemplateClient):
    """Returns the right part number plus requirements the customer never stated."""

    name = "liar"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        parsed = ParsedQuery(
            original_text="x",
            part_numbers=["E810"],
            category=Category.NETWORK,
            requirements=[
                TechnicalRequirement(
                    key="port_speed",
                    operator=Operator.GTE,
                    value=800,
                    unit="Gb/s",
                    origin=RequirementOrigin.QUERY,
                ),
                TechnicalRequirement(
                    key="warp_drive",
                    operator=Operator.HAS,
                    value="yes",
                    origin=RequirementOrigin.QUERY,
                ),
            ],
        )
        return schema.model_validate(parsed.model_dump())


class InventingNLG(TemplateClient):
    name = "inventor"

    def generate(self, prompt: str) -> str:
        return super().generate(prompt) + "\nOferta especial: MCX99999-FAKE por 99.99 USD."


@pytest.mark.safety
def test_invented_requirements_are_dropped(built: BuiltArtifacts) -> None:
    resp = make_agent(built, LyingNLU()).answer(CustomerQuery(text="Usábamos la Intel E810"))
    assert resp.parsed_query is not None and resp.parsed_query.requirements == []
    assert any("warp_drive" in w for w in resp.warnings) and any(
        "port_speed" in w for w in resp.warnings
    )
    assert [r.product.part_number for r in resp.recommendations] == ["MCX75310AAS-NEAT", "BCM57508"]


@pytest.mark.safety
def test_invented_figures_in_text_fall_back_to_verified_draft(built: BuiltArtifacts) -> None:
    resp = make_agent(built, InventingNLG()).answer(CustomerQuery(text=OFFICIAL))
    assert "MCX99999-FAKE" not in resp.message and "99.99" not in resp.message
    assert any("no verificados" in w for w in resp.warnings)
    assert resp.llm_provider.endswith("template")


@pytest.mark.safety
def test_typo_is_suggested_never_assumed(built: BuiltArtifacts) -> None:
    resp = make_agent(built).answer(CustomerQuery(text="Reemplazo para la E81O-CQDA2"))
    assert resp.original is None and not resp.recommendations
    assert resp.clarification_question and "E810-CQDA2" in resp.clarification_question


@pytest.mark.safety
def test_unknown_candidates_are_shown_as_unverified(built: BuiltArtifacts) -> None:
    resp = make_agent(built).answer(CustomerQuery(text="Necesito reemplazar el Arm Cortex-A78"))
    assert resp.recommendations == []
    assert [r.product.part_number for r in resp.unverified_options] == ["w9-3595X"]
    assert "sin datos suficientes" in resp.message and "w9-3595X" in resp.message


@pytest.mark.safety
def test_agent_degrades_when_semantic_search_is_down(built: BuiltArtifacts) -> None:
    from advisor.retrieval import HybridRetriever, RetrievalUnavailableError, Retriever

    class Down(Retriever):
        name = "ai_search"

        def search(self, query, *, top_k=8, filters=None):  # type: ignore[no-untyped-def]
            raise RetrievalUnavailableError("index not ready")

    agent = make_agent(built)
    agent.retriever = HybridRetriever([BM25Retriever(built.chunks), Down()])
    resp = agent.answer(CustomerQuery(text=OFFICIAL))
    assert [r.product.part_number for r in resp.recommendations] == ["MCX75310AAS-NEAT", "BCM57508"]
    assert any("solo BM25" in w for w in resp.warnings)


class EqualityNLU(TemplateClient):
    """An LLM that reads '100 Gigabit' as *exactly* 100 Gb/s (seen with Llama 3.3 on FMAPI)."""

    name = "eq-llm"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        parsed = super().complete_json(prompt, schema)
        reqs = [
            r.model_copy(update={"operator": Operator.EQ}) if r.key == "port_speed" else r
            for r in parsed.requirements  # type: ignore[attr-defined]
        ]
        return parsed.model_copy(update={"requirements": reqs})


@pytest.mark.safety
def test_numeric_capability_eq_from_llm_is_read_as_minimum(built: BuiltArtifacts) -> None:
    resp = make_agent(built, EqualityNLU()).answer(CustomerQuery(text=OFFICIAL))
    assert [r.product.part_number for r in resp.recommendations] == ["MCX75310AAS-NEAT", "BCM57508"]
    port = next(r for r in resp.parsed_query.requirements if r.key == "port_speed")  # type: ignore[union-attr]
    assert port.operator is Operator.GTE
    assert any("port_speed = 100 como ≥ 100" in w for w in resp.warnings)


SENSOR_QUERY = "sensor para medir humedad y gases volátiles en interiores"


def test_template_understands_spanish_measurands(built: BuiltArtifacts) -> None:
    resp = make_agent(built).answer(CustomerQuery(text=SENSOR_QUERY))
    assert [r.product.part_number for r in resp.recommendations] == ["BME680"]


class SpanishValuesNLU(TemplateClient):
    """Returns measurands as Spanish free text in one list (seen with Llama 3.3 on FMAPI)."""

    name = "es-llm"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        parsed = ParsedQuery(
            original_text="x",
            intent="find",
            category=Category.SENSOR,
            requirements=[
                TechnicalRequirement(
                    key="measurands",
                    operator=Operator.HAS,
                    value=["humedad", "gases volátiles", "sabor"],
                    origin=RequirementOrigin.QUERY,
                ),
            ],
        )
        return schema.model_validate(parsed.model_dump())


@pytest.mark.safety
def test_llm_values_are_mapped_to_the_registry_vocabulary(built: BuiltArtifacts) -> None:
    resp = make_agent(built, SpanishValuesNLU()).answer(CustomerQuery(text=SENSOR_QUERY))
    assert [r.product.part_number for r in resp.recommendations] == ["BME680"]
    values = sorted(r.value for r in resp.parsed_query.requirements)  # type: ignore[union-attr, type-var]
    assert values == ["gas", "humidity"]
    assert any("sabor" in w for w in resp.warnings)  # unknown value dropped, never guessed
