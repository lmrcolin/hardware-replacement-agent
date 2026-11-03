"""LLM layer without network: fallback chain, template client, error handling."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from advisor.config import Settings
from advisor.llm import (
    DatabricksFMAPIClient,
    LLMClient,
    LLMUnavailableError,
    OllamaClient,
    TemplateClient,
    build_llm_chain,
    build_nlg_prompt,
    build_nlu_prompt,
    complete_json,
    generate,
    parse_query,
)
from advisor.models import Category, Operator, ParsedQuery


class Broken(LLMClient):
    name = "broken"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise LLMUnavailableError("down")

    def generate(self, prompt: str) -> str:
        raise LLMUnavailableError("down")


class Garbage(LLMClient):
    name = "garbage"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        return schema.model_validate_json('{"not": "valid"}')

    def generate(self, prompt: str) -> str:
        return "   "


OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


def test_rule_parser_official_query() -> None:
    parsed = parse_query(OFFICIAL)
    assert parsed.intent == "replace" and parsed.category is Category.NETWORK
    assert "E810" in parsed.part_numbers
    reqs = {(r.key, r.operator, r.value) for r in parsed.requirements}
    assert reqs == {
        ("port_speed", Operator.GTE, 100),
        ("rdma", Operator.HAS, "*"),
        ("offloads", Operator.HAS, "IPsec"),
    }


def test_rule_parser_asks_when_nothing_is_known() -> None:
    parsed = parse_query("hola, necesito ayuda")
    assert parsed.needs_clarification and parsed.clarification_question


def test_quantities_are_not_part_numbers() -> None:
    assert parse_query("tarjeta 100GbE de 2x 25GbE").part_numbers == []


def test_chain_falls_back_to_template() -> None:
    prompt = build_nlu_prompt(OFFICIAL, {})
    parsed, provider = complete_json([Broken(), Garbage(), TemplateClient()], prompt, ParsedQuery)
    assert provider == "template" and parsed.category is Category.NETWORK
    text, provider = generate(
        [Broken(), Garbage(), TemplateClient()], build_nlg_prompt("borrador 1")
    )
    assert (text, provider) == ("borrador 1", "template")


def test_chain_without_working_provider_raises() -> None:
    with pytest.raises(LLMUnavailableError):
        complete_json([Broken()], "x", ParsedQuery)


def test_template_cannot_invent_other_schemas() -> None:
    class Other(BaseModel):
        x: int

    with pytest.raises(LLMUnavailableError):
        TemplateClient().complete_json("x", Other)


def test_unreachable_providers_raise_typed_errors() -> None:
    ollama = OllamaClient("qwen3:4b", "http://127.0.0.1:9", timeout_s=0.5)
    assert not ollama.is_available()
    with pytest.raises(LLMUnavailableError):
        ollama.generate("hola")
    with pytest.raises(LLMUnavailableError):
        DatabricksFMAPIClient("endpoint", profile="__no_such_profile__").generate("hola")


def test_chain_always_ends_with_template() -> None:
    settings = Settings.model_validate({"llm": {"providers": ["databricks", "ollama"],
                                                 "ollama_host": "http://127.0.0.1:9"}})  # fmt: skip
    chain = build_llm_chain(settings)
    assert [c.name for c in chain] == ["template"]  # no profile, no ollama → template only
