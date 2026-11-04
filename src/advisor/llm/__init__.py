"""LLM clients for NLU (validated JSON) and NLG: Databricks FMAPI, Ollama, Template."""

from advisor.llm.base import (
    DatabricksFMAPIClient,
    LLMClient,
    LLMUnavailableError,
    OllamaClient,
    TemplateClient,
)
from advisor.llm.chain import build_llm_chain, complete_json, generate
from advisor.llm.prompts import build_nlg_prompt, build_nlu_prompt, build_planner_prompt
from advisor.llm.rules import parse_query

__all__ = [
    "DatabricksFMAPIClient",
    "LLMClient",
    "LLMUnavailableError",
    "OllamaClient",
    "TemplateClient",
    "build_llm_chain",
    "build_nlg_prompt",
    "build_nlu_prompt",
    "build_planner_prompt",
    "complete_json",
    "generate",
    "parse_query",
]
