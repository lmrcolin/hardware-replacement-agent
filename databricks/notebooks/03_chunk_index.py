# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · chunk_index (K4, B-10)
# MAGIC Datasheets del volumen → `chunk_document` → `gold.document_chunks` con Change Data Feed
# MAGIC (requisito de un índice Delta Sync de AI Search). Idempotente (`CREATE OR REPLACE`).
# MAGIC Requiere el entorno serverless versión 4 (Python 3.12) y el wheel en `bronze.libs`.

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (spark/dbutils los inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

from pathlib import Path

from advisor.chunking import chunk_document
from advisor.ingestion import discover_documents
from advisor.models import DocumentType
from advisor.parsing import parse_document
from advisor.repository.databricks_sql import TABLES, chunk_rows, now_utc, write_delta_with_spark

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
RAW = Path(f"/Volumes/{CATALOG}/bronze/raw_files")
EXPECTED_CHUNKS = 126  # valor local actual (make pipeline-local)
SPEC = TABLES["gold.document_chunks"]

# COMMAND ----------

datasheets = [r for r in discover_documents(RAW) if r.doc_type is DocumentType.DATASHEET]
chunks = [c for r in datasheets for c in chunk_document(parse_document(r))]
synthetic = bool(
    spark.sql(f"SELECT max(is_synthetic) AS s FROM {TABLES['gold.products'].fqn(CATALOG)}").first().s
)
count = write_delta_with_spark(
    spark, CATALOG, SPEC, chunk_rows(chunks, is_synthetic=synthetic, ingested_at=now_utc())
)
spark.sql(f"ALTER TABLE {SPEC.fqn(CATALOG)} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

# COMMAND ----------

distinct = spark.table(SPEC.fqn(CATALOG)).select("chunk_id").distinct().count()
assert count == EXPECTED_CHUNKS, f"{count} chunks, se esperaban {EXPECTED_CHUNKS}"
assert distinct == count, f"chunk_ids repetidos: {count - distinct}"
print(f"OK: {count} chunks únicos en {SPEC.fqn(CATALOG)} (CDF activado)")
