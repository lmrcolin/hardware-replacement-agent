"""Artifact repository contracts (local Parquet/JSON default; Databricks SQL optional)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

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
