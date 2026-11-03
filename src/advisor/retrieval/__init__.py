"""Retriever interface: BM25 (local), Databricks AI Search and hybrid RRF; FAISS pending."""

from advisor.retrieval.base import (
    AISearchRetriever,
    BM25Retriever,
    FaissRetriever,
    HybridRetriever,
    RetrievalUnavailableError,
    Retriever,
    tokenize,
)

__all__ = [
    "AISearchRetriever",
    "BM25Retriever",
    "FaissRetriever",
    "HybridRetriever",
    "RetrievalUnavailableError",
    "Retriever",
    "tokenize",
]
