# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · export_artifacts
# MAGIC Backlog: B-10
# MAGIC Output: `artifacts/ (products.parquet, chunks.parquet, compat_matrix.parquet, graph.json)`
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

# TODO(B-10): Export gold tables for the local Streamlit app in repository.LocalParquetRepository
#   format.
raise NotImplementedError("B-10 notebook 06_export_artifacts")
