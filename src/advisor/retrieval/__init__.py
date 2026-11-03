"""Retriever interface: BM25, sentence-transformers/FAISS and optional Databricks AI Search."""

from advisor.retrieval.base import AISearchRetriever, BM25Retriever, FaissRetriever, Retriever

__all__ = ["AISearchRetriever", "BM25Retriever", "FaissRetriever", "Retriever"]
