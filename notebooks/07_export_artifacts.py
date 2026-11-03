# Databricks notebook source
# MAGIC %md
# MAGIC ## 07 · export_artifacts
# MAGIC Output: `artifacts/ (products.parquet, chunks.parquet, compat_matrix.parquet, graph.json)` · Backlog: B-10
# MAGIC Thin notebook: logic lives in `src/advisor/` (import via Git folder + sys.path).

# COMMAND ----------
import sys

sys.path.append("../src")  # Git folder layout: <repo>/notebooks → <repo>/src
CATALOG, SCHEMA = "datathon", "emerson"

# COMMAND ----------
# TODO(B-10): Export gold tables for the local Streamlit app via repository.LocalParquetRepository format.
raise NotImplementedError("B-10 notebook 07_export_artifacts")
