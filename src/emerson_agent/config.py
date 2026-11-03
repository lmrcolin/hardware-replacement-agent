"""Runtime configuration loaded from environment variables (prefix ``EMERSON_``)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnv(StrEnum):
    LOCAL = "local"
    DATABRICKS = "databricks"


class RetrievalBackend(StrEnum):
    BM25 = "bm25"
    DATABRICKS_VECTOR_SEARCH = "databricks_vector_search"


class LLMProvider(StrEnum):
    NONE = "none"
    DATABRICKS = "databricks"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMERSON_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: RuntimeEnv = RuntimeEnv.LOCAL
    log_level: str = "INFO"
    log_json: bool = True

    data_dir: Path = Path("data")
    synthetic_data_only: bool = True

    retrieval_backend: RetrievalBackend = RetrievalBackend.BM25
    retrieval_top_k: int = Field(default=5, ge=1, le=50)

    llm_provider: LLMProvider = LLMProvider.NONE
    llm_endpoint: str | None = None

    uc_catalog: str = "emerson_hw"
    uc_schema_bronze: str = "bronze"
    uc_schema_silver: str = "silver"
    uc_schema_gold: str = "gold"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
