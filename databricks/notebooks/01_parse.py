# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze: parsing de PDFs
# MAGIC Parsea los 33 PDFs con `ai_parse_document` a `bronze.documents_parsed`.
# MAGIC Si ya están parseados no vuelve a gastar cómputo (usa `force=true` para rehacerlo).

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
dbutils.widgets.text("catalog", "emerson_hw")
dbutils.widgets.dropdown("force", "false", ["false", "true"])
CATALOG = dbutils.widgets.get("catalog")
FORCE = dbutils.widgets.get("force") == "true"
TABLE = f"{CATALOG}.bronze.documents_parsed"
VOLUME_DIR = f"/Volumes/{CATALOG}/bronze/raw_files/"
EXPECTED_PDFS = 33

# COMMAND ----------

already = spark.table(TABLE).count() if spark.catalog.tableExists(TABLE) else 0

if already == EXPECTED_PDFS and not FORCE:
    print(f"{TABLE} ya tiene {already} documentos; se omite el parsing.")
else:
    spark.sql(f"""
        CREATE OR REPLACE TABLE {TABLE}
        COMMENT 'Salida cruda de ai_parse_document por PDF (catálogo y datasheets)'
        AS
        SELECT
          regexp_extract(path, '[^/]+$', 0)                         AS document_name,
          CASE WHEN path LIKE '%Catalogo_Comercial%' THEN 'catalog'
               ELSE 'datasheet' END                                 AS doc_type,
          ai_parse_document(content)                                AS parsed,
          path                                                      AS _source_file,
          current_timestamp()                                       AS _ingested_at,
          uuid()                                                    AS _ingest_run_id,
          true                                                      AS is_synthetic
        FROM read_files('{VOLUME_DIR}', format => 'binaryFile')
    """)

# COMMAND ----------

display(spark.sql(f"SELECT doc_type, count(*) AS docs FROM {TABLE} GROUP BY doc_type"))

# COMMAND ----------

n = spark.table(TABLE).count()
assert n == EXPECTED_PDFS, f"Se esperaban {EXPECTED_PDFS} documentos parseados y hay {n}"
