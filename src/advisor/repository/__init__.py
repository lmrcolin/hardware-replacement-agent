"""Artifact repositories: local Parquet/JSON and Databricks SQL."""

from advisor.repository.base import ArtifactRepository, DatabricksSQLRepository
from advisor.repository.local import LocalParquetRepository

__all__ = ["ArtifactRepository", "DatabricksSQLRepository", "LocalParquetRepository"]
