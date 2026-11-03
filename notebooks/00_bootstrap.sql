-- Databricks notebook source
-- MAGIC %md
-- MAGIC ## 00 · Bootstrap (idempotent)
-- MAGIC Creates catalog, schema and volume. Keep in sync with `scripts/sql/00_bootstrap.sql`.
-- MAGIC Then upload PDFs: `scripts/bootstrap_databricks.sh --profile emerson`.

-- COMMAND ----------
CREATE CATALOG IF NOT EXISTS datathon;

-- COMMAND ----------
CREATE SCHEMA IF NOT EXISTS datathon.emerson;

-- COMMAND ----------
CREATE VOLUME IF NOT EXISTS datathon.emerson.raw;

-- COMMAND ----------
-- Expect 33 files once uploaded.
LIST '/Volumes/datathon/emerson/raw/pdfs/';
