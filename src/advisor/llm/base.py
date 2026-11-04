"""LLM client contracts. NLU returns validated JSON; NLG only rephrases verified data."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from advisor.llm.prompts import extract_draft, extract_query
from advisor.llm.rules import parse_query
from advisor.models import ParsedQuery


class LLMUnavailableError(RuntimeError):
    """Provider unreachable, rate-limited, timed out or unable to answer; try the next one."""


def _json_object(text: str) -> str:
    """The outermost {...} block of a model answer (models sometimes wrap JSON in prose)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMUnavailableError("model answer contains no JSON object")
    return text[start : end + 1]


class LLMClient(ABC):
    name: str

    @abstractmethod
    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        """Return ``schema``-validated output or raise (ValidationError / LLMUnavailableError)."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Free text for NLG; must be checked by the agent's VERIFY step."""


class DatabricksFMAPIClient(LLMClient):
    """Llama 3.3 70B via Databricks Foundation Model API (databricks-sdk, profile auth)."""

    name = "databricks"

    JSON_TOKENS, TEXT_TOKENS = 500, 450  # output length dominates latency (~35 tokens/s)

    def __init__(self, endpoint: str, profile: str | None, timeout_s: float = 30.0) -> None:
        self.endpoint, self.profile, self.timeout_s = endpoint, profile, timeout_s
        self._client: Any = None  # one WorkspaceClient: auth is resolved once, not per call

    def _workspace(self) -> Any:
        if self._client is None:
            from databricks.sdk import WorkspaceClient

            self._client = WorkspaceClient(profile=self.profile)
        return self._client

    def _chat(self, prompt: str, max_tokens: int = TEXT_TOKENS) -> str:
        try:
            from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

            response = self._workspace().serving_endpoints.query(
                name=self.endpoint,
                messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            message = response.choices[0].message if response.choices else None
            content = message.content if message else None
        except Exception as exc:  # SDK raises many error types; all mean "try the next provider"
            raise LLMUnavailableError(f"databricks: {exc}") from exc
        if not content:
            raise LLMUnavailableError("databricks: empty answer")
        return str(content)

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        return schema.model_validate_json(_json_object(self._chat(prompt, self.JSON_TOKENS)))

    def generate(self, prompt: str) -> str:
        return self._chat(prompt, self.TEXT_TOKENS).strip()


class OllamaClient(LLMClient):
    """Local Ollama (qwen3:4b) over HTTP."""

    name = "ollama"

    def __init__(self, model: str, host: str, timeout_s: float = 30.0) -> None:
        self.model, self.host, self.timeout_s = model, host.rstrip("/"), timeout_s

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=1.0)
            models = [m.get("name", "") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return False
        return response.status_code == 200 and any(m.startswith(self.model) for m in models)

    def _generate(self, prompt: str, fmt: dict[str, Any] | None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        if fmt is not None:
            payload["format"] = fmt
        try:
            response = httpx.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout_s)
            response.raise_for_status()
            text = response.json().get("response", "")
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMUnavailableError(f"ollama: {exc}") from exc
        # qwen3 may emit a <think>…</think> block before the answer.
        return re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).strip()

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        return schema.model_validate_json(
            _json_object(self._generate(prompt, schema.model_json_schema()))
        )

    def generate(self, prompt: str) -> str:
        return self._generate(prompt, None)


class TemplateClient(LLMClient):
    """Deterministic last resort: rule-based NLU and the verified draft as NLG. Always available."""

    name = "template"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        if schema is not ParsedQuery:
            raise LLMUnavailableError(f"template cannot produce {schema.__name__}")
        parsed = parse_query(extract_query(prompt))
        return schema.model_validate(json.loads(parsed.model_dump_json()))

    def generate(self, prompt: str) -> str:
        return extract_draft(prompt)
