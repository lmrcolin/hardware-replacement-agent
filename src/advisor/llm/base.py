"""LLM client contracts. NLU returns validated JSON; NLG only rephrases verified data."""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
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

    def __init__(self, endpoint: str, profile: str | None, timeout_s: float = 30.0) -> None:
        self.endpoint, self.profile, self.timeout_s = endpoint, profile, timeout_s

    def _chat(self, prompt: str) -> str:
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

            client = WorkspaceClient(profile=self.profile)
            response = client.serving_endpoints.query(
                name=self.endpoint,
                messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
                temperature=0.0,
                max_tokens=1200,
            )
            message = response.choices[0].message if response.choices else None
            content = message.content if message else None
        except Exception as exc:  # SDK raises many error types; all mean "try the next provider"
            raise LLMUnavailableError(f"databricks: {exc}") from exc
        if not content:
            raise LLMUnavailableError("databricks: empty answer")
        return str(content)

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        return schema.model_validate_json(_json_object(self._chat(prompt)))

    def generate(self, prompt: str) -> str:
        return self._chat(prompt).strip()


# NLG instruction: the agent's draft is already complete and verified; Claude only makes it read
# well. Brevity is asked for explicitly (no greetings/headings), and nothing may be added.
NLG_SYSTEM = (
    "Eres el redactor de un asesor de reemplazo de componentes electrónicos. Reescribe el "
    "borrador que recibes para el cliente, en español, claro y breve. Reglas: conserva todos "
    "los part numbers, cifras, fechas, estados y condiciones del borrador, escritos "
    "exactamente igual; no agregues datos, opiniones ni recomendaciones que no estén en el "
    "borrador; sin saludos, despedidas, encabezados ni frases de relleno; usa viñetas cortas "
    "cuando haya varias opciones; no seas más largo que el borrador."
)


@dataclass
class LLMCall:
    kind: str  # "json" (NLU/plan) or "text" (NLG)
    seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    ok: bool = True


class AnthropicClient(LLMClient):
    """Claude via the official Anthropic SDK (optional extra ``claude``; key in ANTHROPIC_API_KEY).

    NLU uses structured outputs (``messages.parse`` with the Pydantic schema), so the answer is
    validated JSON by construction; NLG returns plain text that the agent's VERIFY step checks.
    Any API error, refusal or truncation raises LLMUnavailableError: the chain moves on to the
    next provider (ending in the template), exactly as with the other clients. Every call is
    recorded in ``calls`` (tokens, latency) so cost per query can be measured.
    """

    name = "anthropic"

    def __init__(self, model: str, effort: str = "low", timeout_s: float = 30.0) -> None:
        self.model, self.effort, self.timeout_s = model, effort, timeout_s
        self._client: Any = None
        self.calls: list[LLMCall] = []

    def _api(self) -> Any:
        if self._client is None:
            import anthropic  # optional dependency: uv sync --extra claude

            # Transient API errors (429, 5xx, timeouts, dropped connections) are retried with
            # backoff before the chain gives up on Claude and falls back to the template.
            self._client = anthropic.Anthropic(timeout=self.timeout_s, max_retries=2)
        return self._client

    def _request(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4000,  # adaptive thinking shares this budget; answers are short
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system
        return request

    def _call(self, kind: str, method: Callable[..., Any], **request: Any) -> Any:
        import anthropic

        started = time.perf_counter()
        call = LLMCall(kind, 0.0)
        try:
            response = method(**request)
            usage = getattr(response, "usage", None)
            call.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            call.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            if response.stop_reason == "refusal":
                raise LLMUnavailableError("anthropic: refusal")
            if response.stop_reason == "max_tokens":
                raise LLMUnavailableError("anthropic: answer truncated (max_tokens)")
            return response
        except anthropic.APIError as exc:
            call.ok = False
            raise LLMUnavailableError(f"anthropic: {exc}") from exc
        except LLMUnavailableError:
            call.ok = False
            raise
        finally:
            call.seconds = time.perf_counter() - started
            self.calls.append(call)

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        response = self._call(
            "json", self._api().messages.parse, **self._request(prompt), output_format=schema
        )
        parsed = response.parsed_output
        if parsed is None:
            self.calls[-1].ok = False
            raise LLMUnavailableError("anthropic: no structured output")
        return schema.model_validate(parsed)

    def generate(self, prompt: str) -> str:
        response = self._call(
            "text", self._api().messages.create, **self._request(prompt, system=NLG_SYSTEM)
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()


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
