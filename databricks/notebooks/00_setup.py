# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup
# MAGIC Crea el catálogo, los esquemas `bronze`/`silver`/`gold` y el volumen `bronze.raw_files`,
# MAGIC y copia los 33 PDFs de `data/raw/` del repo al volumen. Idempotente.

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ExportFormat

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

# Se descarga con la API de Workspace (SDK) en vez de leer el archivo por el FUSE de /Workspace:
# en serverless, leer ciertos binarios por FUSE falla con 403 (SSE-C) aunque el archivo esté bien.
ws = WorkspaceClient()
src_pdfs = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".pdf"))
for name in src_pdfs:
    dst = os.path.join(VOLUME_DIR, name)
    if not os.path.exists(dst):
        with ws.workspace.download(os.path.join(src_dir, name), format=ExportFormat.AUTO) as src:
            data = src.read()
        with open(dst, "wb") as out:
            out.write(data)

in_volume = sorted(f for f in os.listdir(VOLUME_DIR) if f.lower().endswith(".pdf"))
print(f"PDFs en el repo: {len(src_pdfs)} · PDFs en el volumen: {len(in_volume)}")

# COMMAND ----------

assert len(in_volume) == EXPECTED_PDFS, (
    f"Se esperaban {EXPECTED_PDFS} PDFs en {VOLUME_DIR} y hay {len(in_volume)}."
)
assert any(f.startswith("Catalogo_Comercial") for f in in_volume), "Falta el catálogo comercial"

# COMMAND ----------

# Librería y configuración para los notebooks 02-06 (K2): el bundle construye `dist/*.whl` en cada
# deploy (artifacts de databricks.yml) y lo sincroniza; aquí se copia al volumen `bronze.libs`,
# desde donde se instala con %pip (importar `advisor` desde /Workspace por FUSE falla).
# Se sobrescribe siempre: el wheel conserva el nombre aunque cambie el código.
LIBS_DIR = f"/Volumes/{CATALOG}/bronze/libs"
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.libs")
wheels = [f for f in os.listdir(os.path.join(repo_root, "dist")) if f.endswith(".whl")]
libs = [os.path.join("dist", f) for f in wheels]
configs = ("spec_registry.yaml", "compat_rules.yaml", "settings.yaml")
libs += [os.path.join("config", f) for f in configs]
for rel in libs:
    with ws.workspace.download(os.path.join(repo_root, rel), format=ExportFormat.AUTO) as src:
        data = src.read()
    with open(os.path.join(LIBS_DIR, os.path.basename(rel)), "wb") as out:
        out.write(data)
print("libs:", sorted(os.listdir(LIBS_DIR)))
assert any(f.endswith(".whl") for f in os.listdir(LIBS_DIR)), "Falta el wheel en bronze.libs"
