import importlib
import json
import logging

import pytest

from emerson_agent.config import LLMProvider, RetrievalBackend, Settings
from emerson_agent.logging_utils import JsonFormatter

SUBPACKAGES = ["domain", "data", "retrieval", "compatibility", "agent", "evaluation"]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackages_import(name: str) -> None:
    assert importlib.import_module(f"emerson_agent.{name}").__doc__


def test_settings_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("EMERSON_LLM_PROVIDER", "EMERSON_SYNTHETIC_DATA_ONLY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider is LLMProvider.NONE
    assert settings.retrieval_backend is RetrievalBackend.BM25
    assert settings.synthetic_data_only is True


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMERSON_RETRIEVAL_TOP_K", "7")
    assert Settings(_env_file=None).retrieval_top_k == 7  # type: ignore[call-arg]


def test_json_formatter_keeps_extra_fields() -> None:
    record = logging.makeLogRecord({"msg": "hello", "levelname": "INFO", "part_number": "X-1"})
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hello"
    assert out["part_number"] == "X-1"
