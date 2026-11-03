# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · extract_enrich
# MAGIC Backlog: B-06, B-07
# MAGIC Output: `silver.products, silver.product_specifications, silver.commercial, gold.products`
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

# TODO(B-06, B-07): read bronze.documents_parsed; parse_catalog on the catalog row,
#   extract_product per datasheet (config/spec_registry.yaml), join_catalog → JoinReport. Catalog
#   = truth.
raise NotImplementedError("B-06, B-07 notebook 02_extract_enrich")
