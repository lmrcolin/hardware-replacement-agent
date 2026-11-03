# Databricks notebook source
# MAGIC %md
# MAGIC ## 05 · build_kg
# MAGIC Output: `kg_nodes, kg_edges` · Backlog: B-09
# MAGIC Thin notebook: logic lives in `src/advisor/` (import via Git folder + sys.path).

# COMMAND ----------
import sys

sys.path.append("../src")  # Git folder layout: <repo>/notebooks → <repo>/src
CATALOG, SCHEMA = "datathon", "emerson"

# COMMAND ----------
# TODO(B-09): build_graph(products, chunks) → write nodes/edges with the GraphNode/GraphEdge columns.
raise NotImplementedError("B-09 notebook 05_build_kg")
