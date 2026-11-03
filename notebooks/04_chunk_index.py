# Databricks notebook source
# MAGIC %md
# MAGIC ## 04 · chunk_index
# MAGIC Output: `gold_chunks (+ optional AI Search Delta Sync index)` · Backlog: B-08, B-13
# MAGIC Thin notebook: logic lives in `src/advisor/` (import via Git folder + sys.path).

# COMMAND ----------
import sys

sys.path.append("../src")  # Git folder layout: <repo>/notebooks → <repo>/src
CATALOG, SCHEMA = "datathon", "emerson"

# COMMAND ----------
# TODO(B-08, B-13): chunk_document per parsed doc; enable Change Data Feed; AI Search only if FEATURE_MATRIX says OK (1 endpoint).
raise NotImplementedError("B-08, B-13 notebook 04_chunk_index")
