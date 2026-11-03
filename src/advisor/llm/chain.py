"""Provider chain with fallback: databricks → ollama → template (always last)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from advisor.config import Settings
from advisor.llm.base import (
    DatabricksFMAPIClient,
    LLMClient,
    LLMUnavailableError,
    OllamaClient,
    TemplateClient,
)

log = logging.getLogger(__name__)


def build_llm_chain(settings: Settings) -> list[LLMClient]:
    """Configured providers that can actually answer; TemplateClient is always appended."""
    chain: list[LLMClient] = []
    for name in settings.llm.providers:
        if name == "databricks" and settings.databricks.profile:
            chain.append(
                DatabricksFMAPIClient(
                    settings.llm.databricks_endpoint,
                    settings.databricks.profile,
                    settings.llm.timeout_s,
                )
            )
        elif name == "ollama":
            ollama = OllamaClient(
                settings.llm.ollama_model, settings.llm.ollama_host, settings.llm.timeout_s
            )
            if ollama.is_available():
                chain.append(ollama)
        elif name == "template":
            chain.append(TemplateClient())
    if not chain or not isinstance(chain[-1], TemplateClient):
        chain.append(TemplateClient())
    return chain


def complete_json[T: BaseModel](
    chain: Sequence[LLMClient], prompt: str, schema: type[T]
) -> tuple[T, str]:
    """First provider whose answer validates against ``schema``; returns (answer, provider)."""
    errors: list[str] = []
    for client in chain:
        try:
            return client.complete_json(prompt, schema), client.name
        except (LLMUnavailableError, ValidationError, ValueError) as exc:
            log.warning(
                "llm provider failed", extra={"provider": client.name, "error": str(exc)[:200]}
            )
            errors.append(f"{client.name}: {exc}")
    raise LLMUnavailableError("; ".join(errors) or "empty provider chain")


def generate(chain: Sequence[LLMClient], prompt: str) -> tuple[str, str]:
    errors: list[str] = []
    for client in chain:
        try:
            text = client.generate(prompt)
            if text.strip():
                return text, client.name
        except (LLMUnavailableError, ValueError) as exc:
            log.warning(
                "llm provider failed", extra={"provider": client.name, "error": str(exc)[:200]}
            )
            errors.append(f"{client.name}: {exc}")
    raise LLMUnavailableError("; ".join(errors) or "empty provider chain")
