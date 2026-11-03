# Databricks notebook source
# MAGIC %md
# MAGIC ## 06 · compat_matrix
# MAGIC Output: `compat_matrix` · Backlog: B-15
# MAGIC Thin notebook: logic lives in `src/advisor/` (import via Git folder + sys.path).

# COMMAND ----------
import sys

sys.path.append("../src")  # Git folder layout: <repo>/notebooks → <repo>/src
CATALOG, SCHEMA = "datathon", "emerson"

# COMMAND ----------
# TODO(B-15): evaluate(original, candidate, derive_requirements(...)) for every ordered pair (32×32 minus diagonal).
raise NotImplementedError("B-15 notebook 06_compat_matrix")
