# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · chunk_index
# MAGIC Backlog: B-08, B-13
# MAGIC Output: `gold.document_chunks (+ optional AI Search Delta Sync index)`
# MAGIC Thin notebook: logic lives in `src/advisor/`.
# MAGIC Not yet in the `run_all` job: add it to databricks.yml when implemented.

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
import os
import sys

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
# Notebook lives in databricks/notebooks/: repo root is two levels up.
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..", "..", "src")))

# COMMAND ----------

# TODO(B-08, B-13): chunk_document per parsed doc; enable Change Data Feed; AI Search only if
#   FEATURE_MATRIX says OK (1 endpoint).
raise NotImplementedError("B-08, B-13 notebook 03_chunk_index")
