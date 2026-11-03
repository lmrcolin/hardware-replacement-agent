"""LLM client contracts. NLU returns validated JSON; NLG only rephrases verified data."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMUnavailableError(RuntimeError):
    """Provider unreachable, rate-limited or timed out; caller falls back to the next one."""


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

    def __init__(self, endpoint: str, profile: str, timeout_s: float = 30.0) -> None:
        self.endpoint, self.profile, self.timeout_s = endpoint, profile, timeout_s

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError("B-18 llm.DatabricksFMAPIClient.complete_json")

    def generate(self, prompt: str) -> str:
        raise NotImplementedError("B-18 llm.DatabricksFMAPIClient.generate")


class OllamaClient(LLMClient):
    """Local Ollama (qwen3:4b) over HTTP."""

    name = "ollama"

    def __init__(self, model: str, host: str, timeout_s: float = 30.0) -> None:
        self.model, self.host, self.timeout_s = model, host, timeout_s

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError("B-18 llm.OllamaClient.complete_json")

    def generate(self, prompt: str) -> str:
        raise NotImplementedError("B-18 llm.OllamaClient.generate")


class TemplateClient(LLMClient):
    """Deterministic last resort: rule-based NLU and template NLG. Always available."""

    name = "template"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError("B-18 llm.TemplateClient.complete_json")

    def generate(self, prompt: str) -> str:
        raise NotImplementedError("B-18 llm.TemplateClient.generate")
