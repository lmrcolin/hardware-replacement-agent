"""Settings loader: ``config/settings.yaml`` with ``ADVISOR_*`` environment overrides.

Only infrastructure lives here; no business logic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"

LLMProviderName = Literal["databricks", "ollama", "template"]
RepositoryBackend = Literal["local", "databricks_sql"]
RetrieverBackend = Literal["bm25", "faiss", "hybrid", "ai_search"]


class DatabricksSettings(BaseModel):
    profile: str | None = None  # None = CLI default profile (same as databricks.yml bundle)
    catalog: str = "emerson_hw"  # bundle variable `catalog`
    schema_bronze: str = "bronze"
    schema_silver: str = "silver"
    schema_gold: str = "gold"
    volume_pdf_dir: str = "/Volumes/emerson_hw/bronze/raw_files"
    warehouse_id: str | None = None


class PathSettings(BaseModel):
    pdf_dir: Path = Path("data/raw")
    artifacts_dir: Path = Path("artifacts")
    spec_registry: Path = Path("config/spec_registry.yaml")
    compat_rules: Path = Path("config/compat_rules.yaml")


class LLMSettings(BaseModel):
    providers: list[LLMProviderName] = ["databricks", "ollama", "template"]
    databricks_endpoint: str = "databricks-meta-llama-3-3-70b-instruct"
    ollama_model: str = "qwen3:4b"
    ollama_host: str = "http://localhost:11434"
    timeout_s: float = 30.0


class RetrievalSettings(BaseModel):
    backend: RetrieverBackend = "bm25"
    top_k: int = Field(default=8, ge=1, le=100)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ai_search_endpoint: str = "emerson-vs"
    ai_search_index: str = "emerson_hw.gold.document_chunks_index"


class Settings(BaseModel):
    databricks: DatabricksSettings = DatabricksSettings()
    paths: PathSettings = PathSettings()
    llm: LLMSettings = LLMSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    repository_backend: RepositoryBackend = "local"


_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "ADVISOR_DATABRICKS_PROFILE": ("databricks", "profile"),
    "ADVISOR_DATABRICKS_WAREHOUSE_ID": ("databricks", "warehouse_id"),
    "ADVISOR_REPOSITORY_BACKEND": ("repository_backend",),
    "ADVISOR_RETRIEVAL_BACKEND": ("retrieval", "backend"),
    "ADVISOR_OLLAMA_HOST": ("llm", "ollama_host"),
}


def _apply_env(raw: dict[str, Any]) -> dict[str, Any]:
    for var, path in _ENV_OVERRIDES.items():
        value = os.environ.get(var)
        if not value:
            continue
        node = raw
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    providers = os.environ.get("ADVISOR_LLM_PROVIDERS")
    if providers:
        raw.setdefault("llm", {})["providers"] = [p.strip() for p in providers.split(",")]
    return raw


def load_settings(path: Path | None = None) -> Settings:
    load_dotenv(REPO_ROOT / ".env", override=False)
    settings_path = path or DEFAULT_SETTINGS_PATH
    raw: dict[str, Any] = {}
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(_apply_env(raw))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
