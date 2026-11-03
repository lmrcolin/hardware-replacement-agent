# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · extract_enrich (K3, B-10)
# MAGIC PDFs del volumen → `parse_catalog` (catálogo, capa de texto: ADR-012) + `parse_document` /
# MAGIC `extract_product` (datasheets) → `join_catalog`. Cruce de seguridad contra
# MAGIC `bronze.documents_parsed`; si falla, el job falla.
# MAGIC Escribe `silver.commercial`, `silver.products`, `silver.product_specifications` y `gold.products`
# MAGIC con `CREATE OR REPLACE` (idempotente). Lógica en `src/advisor`; este notebook solo orquesta.
# MAGIC Requiere el entorno serverless versión 4 (Python 3.12) y el wheel en `bronze.libs`.

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (spark/dbutils los inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

from collections import Counter
from pathlib import Path

from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry
from advisor.ingestion import discover_documents
from advisor.models import DocumentType
from advisor.parsing import parse_catalog, parse_document
from advisor.repository.databricks_sql import (
    TABLES,
    assert_join_is_safe,
    commercial_rows,
    gold_product_rows,
    now_utc,
    part_numbers_misread,
    silver_product_rows,
    specification_rows,
    write_delta_with_spark,
)

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
RAW = Path(f"/Volumes/{CATALOG}/bronze/raw_files")
LIBS = Path(f"/Volumes/{CATALOG}/bronze/libs")
EXPECTED = {"ACTIVE": 21, "DISCONTINUED": 6, "EOL": 2, "NRND": 3}

# COMMAND ----------

records = discover_documents(RAW)
catalog_record = next(r for r in records if r.doc_type is DocumentType.CATALOG)
catalog = parse_catalog(catalog_record)
docs = {r.document_id: parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET}
registry = load_spec_registry(LIBS / "spec_registry.yaml")
products, report = join_catalog([extract_product(d, registry) for d in docs.values()], catalog)
print(f"catálogo {len(catalog)} filas · datasheets {len(docs)} · productos {len(products)}")

# COMMAND ----------

# Cruce de seguridad (ADR-012): un part number que está en la capa de texto del datasheet debe
# estar también en la salida de ai_parse_document; además el cruce no puede dejar huecos.
filenames = {r.document_id: r.filename for r in records}
ai_by_name = {
    row.document_name: row.parsed_json
    for row in spark.sql(
        f"SELECT document_name, to_json(parsed) AS parsed_json FROM `{CATALOG}`.bronze.documents_parsed"
    ).collect()
}
ai_by_id = {doc_id: ai_by_name.get(filenames[doc_id], "") for doc_id in docs}
misread = part_numbers_misread(report, docs, ai_by_id)
assert_join_is_safe(report, misread)
print("cruce seguro:", len(report.matched), "part numbers cruzados; notas:", report.notes)

# COMMAND ----------

at = now_utc()
synthetic = any(p.is_synthetic for p in products)
written = {
    "silver.commercial": write_delta_with_spark(
        spark, CATALOG, TABLES["silver.commercial"],
        commercial_rows(catalog, is_synthetic=synthetic, ingested_at=at),
    ),
    "silver.products": write_delta_with_spark(
        spark, CATALOG, TABLES["silver.products"], silver_product_rows(products, ingested_at=at)
    ),
    "silver.product_specifications": write_delta_with_spark(
        spark, CATALOG, TABLES["silver.product_specifications"],
        specification_rows(products, ingested_at=at),
    ),
    "gold.products": write_delta_with_spark(
        spark, CATALOG, TABLES["gold.products"], gold_product_rows(products, ingested_at=at)
    ),
}  # fmt: skip
print(written)

# COMMAND ----------

statuses = dict(
    Counter(
        r.status
        for r in spark.table(TABLES["silver.commercial"].fqn(CATALOG)).select("status").collect()
    )
)
assert statuses == EXPECTED, f"estados {statuses} ≠ {EXPECTED}"
assert written["gold.products"] == 32, written
print("OK:", statuses)
