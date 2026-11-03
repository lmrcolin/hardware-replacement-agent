# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · build_kg
# MAGIC Backlog: B-09
# MAGIC Output: `gold.kg_nodes, gold.kg_edges`
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

# TODO(B-09): build_graph(products, chunks) → write nodes/edges with the GraphNode/GraphEdge
#   columns.
raise NotImplementedError("B-09 notebook 04_build_kg")
