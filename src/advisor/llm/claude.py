"""Claude client for the chat's "Claude (API key)" option (docs/AGENT_DESIGN.md).

``ClaudeClient(model, timeout_s)`` is an ``LLMClient`` named "claude" on the official Anthropic SDK
(optional extra ``claude``: ``uv sync --extra claude``). The key is read by the SDK from
``ANTHROPIC_API_KEY`` (``.env``, ignored by git), never from code. Default model: Claude Haiku 5.5
at low effort, which matched Sonnet 5.5 and Opus 5.5 on the gold set at a fraction of the cost.

NLU/plan use structured outputs (``messages.parse`` with the Pydantic schema): validated JSON by
construction. NLG returns plain text under brevity rules and is still checked by the agent's
VERIFY step. API errors (after the SDK's retries), refusals and truncations raise
``LLMUnavailableError`` so the chain falls back to the templates. Every call is recorded in
``calls`` (tokens, latency) to measure cost per query.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel

from advisor.llm.base import LLMClient, LLMUnavailableError

DEFAULT_MODEL = "claude-haiku-5-5"
EFFORT = "low"  # NLU, plan and rephrasing are short, well-specified tasks

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


class ClaudeClient(LLMClient):
    name = "claude"

    def __init__(self, model: str = DEFAULT_MODEL, timeout_s: float = 30.0) -> None:
        self.model, self.timeout_s, self.effort = model, timeout_s, EFFORT
        self._client: Any = None
        self.calls: list[LLMCall] = []

    def _api(self) -> Any:
        if self._client is None:
            # Transient API errors (429, 5xx, timeouts, dropped connections) are retried with
            # backoff before the chain gives up on Claude and falls back to the templates.
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
        started = time.perf_counter()
        call = LLMCall(kind, 0.0)
        try:
            response = method(**request)
            usage = getattr(response, "usage", None)
            call.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            call.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            if response.stop_reason == "refusal":
                raise LLMUnavailableError("claude: refusal")
            if response.stop_reason == "max_tokens":
                raise LLMUnavailableError("claude: answer truncated (max_tokens)")
            return response
        except anthropic.APIError as exc:
            call.ok = False
            raise LLMUnavailableError(f"claude: {exc}") from exc
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
            raise LLMUnavailableError("claude: no structured output")
        return schema.model_validate(parsed)

    def generate(self, prompt: str) -> str:
        response = self._call(
            "text", self._api().messages.create, **self._request(prompt, system=NLG_SYSTEM)
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
