# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · compat_matrix
# MAGIC Backlog: B-15
# MAGIC Output: `gold.compat_matrix`
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

# TODO(B-15): evaluate(original, candidate, derive_requirements(...)) for every ordered pair
#   (32x32 minus diagonal).
raise NotImplementedError("B-15 notebook 05_compat_matrix")
