# Databricks notebook source
# MAGIC %md
# MAGIC ## 03 · extract_enrich
# MAGIC Output: `silver_products, silver_specs, silver_commercial, gold_products` · Backlog: B-06, B-07
# MAGIC Thin notebook: logic lives in `src/advisor/` (import via Git folder + sys.path).

# COMMAND ----------
import sys

sys.path.append("../src")  # Git folder layout: <repo>/notebooks → <repo>/src
CATALOG, SCHEMA = "datathon", "emerson"

# COMMAND ----------
# TODO(B-06, B-07): parse_catalog on the catalog, extract_product per datasheet (config/spec_registry.yaml), join_catalog → JoinReport. Catalog = truth.
raise NotImplementedError("B-06, B-07 notebook 03_extract_enrich")
