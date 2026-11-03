# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup
# MAGIC Crea el catálogo, los esquemas `bronze`/`silver`/`gold` y el volumen `bronze.raw_files`,
# MAGIC y copia los 33 PDFs de `data/raw/` del repo al volumen. Idempotente.

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
import os
import shutil

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
VOLUME_DIR = f"/Volumes/{CATALOG}/bronze/raw_files"
EXPECTED_PDFS = 33

# COMMAND ----------

# Si tu cuenta no permite crear catálogos, cambia el widget `catalog` por uno existente.
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
for schema in ("bronze", "silver", "gold"):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.raw_files")

# COMMAND ----------

# El notebook vive en databricks/notebooks/: la raíz del repo está dos niveles arriba.
repo_root = os.path.abspath(os.path.join(os.getcwd(), "..", ".."))
src_dir = os.path.join(repo_root, "data", "raw")

src_pdfs = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".pdf"))
for name in src_pdfs:
    dst = os.path.join(VOLUME_DIR, name)
    if not os.path.exists(dst):
        shutil.copy(os.path.join(src_dir, name), dst)

in_volume = sorted(f for f in os.listdir(VOLUME_DIR) if f.lower().endswith(".pdf"))
print(f"PDFs en el repo: {len(src_pdfs)} · PDFs en el volumen: {len(in_volume)}")

# COMMAND ----------

assert len(in_volume) == EXPECTED_PDFS, (
    f"Se esperaban {EXPECTED_PDFS} PDFs en {VOLUME_DIR} y hay {len(in_volume)}."
)
assert any(f.startswith("Catalogo_Comercial") for f in in_volume), "Falta el catálogo comercial"
