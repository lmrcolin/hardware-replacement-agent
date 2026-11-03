-- Databricks notebook source
-- MAGIC %md
-- MAGIC ## 02 · Parse with `ai_parse_document` → `datathon.emerson.silver_parsed_documents`
-- MAGIC Owner: Dev1 · Backlog: B-02 · Record the result in docs/FEATURE_MATRIX.md.

-- COMMAND ----------
-- Smoke test on ONE document (bounded: LIMIT 1) before running on all 33.
SELECT path, ai_parse_document(content)
FROM read_files('/Volumes/datathon/emerson/raw/pdfs/', format => 'binaryFile')
LIMIT 1;

-- COMMAND ----------
-- TODO(B-02): CREATE OR REPLACE TABLE datathon.emerson.silver_parsed_documents AS
--   SELECT document_id, path, ai_parse_document(content) AS parsed FROM datathon.emerson.bronze_documents;
