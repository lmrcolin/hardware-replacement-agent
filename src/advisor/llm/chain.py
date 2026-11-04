"""Provider chain with fallback: databricks → ollama → template (always last)."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from advisor.config import LLMChoice, Settings
from advisor.llm.base import (
    DatabricksFMAPIClient,
    LLMClient,
    LLMUnavailableError,
    OllamaClient,
    TemplateClient,
)

log = logging.getLogger(__name__)


def _databricks_configured(profile: str | None) -> bool:
    """A named profile, or the CLI's default one / DATABRICKS_* variables, resolves to a host.
    Without it the FMAPI client would fail on every call, so it is left out of the chain."""
    try:
        from databricks.sdk.core import Config

        return bool(Config(profile=profile).host)
    except Exception:  # SDK raises several error types for "not configured"
        return False


def _wants_databricks(settings: Settings) -> bool:
    """Llama is used with an explicit profile, or with the CLI's default one when the run is
    already on Databricks (Delta tables or AI Search). A plain local run stays on templates."""
    if settings.databricks.profile:
        return True
    on_databricks = settings.repository_backend == "databricks_sql" or (
        settings.retrieval.backend in ("ai_search", "hybrid")
    )
    return on_databricks and _databricks_configured(None)


CLAUDE_KEY_ENV = "ANTHROPIC_API_KEY"  # read from the environment / .env, never from code


def claude_status() -> str:
    """ "ready", or why the Claude option cannot be used yet."""
    if not os.environ.get(CLAUDE_KEY_ENV):
        return f"falta {CLAUDE_KEY_ENV} en .env"
    try:
        from advisor.llm import claude  # noqa: F401  (client implemented by the team: llm/claude.py)
    except ImportError:
        return "falta el cliente advisor.llm.claude.ClaudeClient"
    return "ready"


def _claude_client(settings: Settings) -> LLMClient | None:
    """``ClaudeClient(model, timeout_s)`` from ``advisor/llm/claude.py`` (an ``LLMClient`` named
    "claude" that reads ``ANTHROPIC_API_KEY``), when it exists and a key is configured."""
    if claude_status() != "ready":
        return None
    from advisor.llm.claude import ClaudeClient  # type: ignore[import-not-found,unused-ignore]

    client: LLMClient = ClaudeClient(settings.llm.claude_model, settings.llm.timeout_s)
    return client


def build_llm_chain(settings: Settings, choice: LLMChoice = "ours") -> list[LLMClient]:
    """Configured providers that can actually answer; TemplateClient is always appended.

    ``choice="claude"`` (chat selector) uses only the Claude API client, with templates as the
    fallback; ``"ours"`` is the configured chain (Llama on Databricks → Ollama → templates)."""
    if choice == "claude":
        claude = _claude_client(settings)
        return [claude, TemplateClient()] if claude else [TemplateClient()]
    chain: list[LLMClient] = []
    for name in settings.llm.providers:
        if name == "databricks" and _wants_databricks(settings):
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
        elif name == "claude":
            claude = _claude_client(settings)
            if claude is not None:
                chain.append(claude)
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
