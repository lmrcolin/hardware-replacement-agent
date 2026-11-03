# Databricks notebook source
# MAGIC %md
# MAGIC ## 01 · Ingest → `datathon.emerson.bronze_documents`
# MAGIC Binary PDFs from the UC volume into Delta (path, sha256, size, modificationTime, content).
# MAGIC Owner: Dev1 · Backlog: B-02 · Skill: databricks-data-pipeline

# COMMAND ----------
CATALOG, SCHEMA = "datathon", "emerson"
VOLUME_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/raw/pdfs/"

# COMMAND ----------
# TODO(B-02): read_files(VOLUME_DIR, format => 'binaryFile') → add sha256(content) as document_id,
# doc_type (CATALOG if name starts with 'Catalogo_' else DATASHEET) → CREATE OR REPLACE TABLE bronze_documents.
# Expect 33 rows. Bounded + idempotent.
raise NotImplementedError("B-02 notebook 01_ingest")
