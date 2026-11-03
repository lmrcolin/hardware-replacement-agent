"""Artifact repository contracts (local Parquet/JSON default; Databricks SQL optional)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

import networkx as nx

from advisor.models import Chunk, CompatibilityResult, Product


class ArtifactRepository(ABC):
    @abstractmethod
    def load_products(self) -> list[Product]: ...

    @abstractmethod
    def load_chunks(self) -> list[Chunk]: ...

    @abstractmethod
    def load_graph(self) -> nx.MultiDiGraph: ...

    @abstractmethod
    def load_compat_matrix(self) -> list[CompatibilityResult]: ...

    @abstractmethod
    def save_products(self, products: Sequence[Product]) -> None: ...

    @abstractmethod
    def save_chunks(self, chunks: Sequence[Chunk]) -> None: ...

    @abstractmethod
    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None: ...


class LocalParquetRepository(ArtifactRepository):
    """artifacts/{products,chunks,compat_matrix}.parquet + artifacts/graph.json. B-20."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_products(self) -> list[Product]:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.load_products")

    def load_chunks(self) -> list[Chunk]:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.load_chunks")

    def load_graph(self) -> nx.MultiDiGraph:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.load_graph")

    def load_compat_matrix(self) -> list[CompatibilityResult]:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.load_compat_matrix")

    def save_products(self, products: Sequence[Product]) -> None:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.save_products")

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.save_chunks")

    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None:
        raise NotImplementedError("B-20 repository.LocalParquetRepository.save_compat_matrix")


class DatabricksSQLRepository(ArtifactRepository):
    """Statement Execution API on the SQL warehouse (databricks-sdk, --profile). B-20."""

    def __init__(self, profile: str, warehouse_id: str, catalog: str, schema: str) -> None:
        self.profile, self.warehouse_id = profile, warehouse_id
        self.catalog, self.schema = catalog, schema

    def load_products(self) -> list[Product]:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.load_products")

    def load_chunks(self) -> list[Chunk]:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.load_chunks")

    def load_graph(self) -> nx.MultiDiGraph:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.load_graph")

    def load_compat_matrix(self) -> list[CompatibilityResult]:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.load_compat_matrix")

    def save_products(self, products: Sequence[Product]) -> None:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.save_products")

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.save_chunks")

    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None:
        raise NotImplementedError("B-20 repository.DatabricksSQLRepository.save_compat_matrix")
