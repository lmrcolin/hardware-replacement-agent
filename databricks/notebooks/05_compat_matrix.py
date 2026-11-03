# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · compat_matrix (K5, B-10)
# MAGIC `gold.products` → para cada pieza no ACTIVE, `derive_requirements` + `evaluate` contra su
# MAGIC categoría (misma función que `make pipeline-local`) → `gold.compat_matrix` (`CREATE OR REPLACE`).
# MAGIC Las aserciones replican `tests/data/test_recommendations.py`.
# MAGIC Requiere el entorno serverless versión 4 (Python 3.12) y el wheel en `bronze.libs`.

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (spark/dbutils los inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

from pathlib import Path

from advisor.config import Settings
from advisor.models import CompatibilityLevel, Product
from advisor.pipeline import compat_matrix
from advisor.recommendation import rank
from advisor.repository.databricks_sql import TABLES, matrix_rows, now_utc, write_delta_with_spark

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
LIBS = Path(f"/Volumes/{CATALOG}/bronze/libs")
SETTINGS = Settings.model_validate(
    {"paths": {"spec_registry": str(LIBS / "spec_registry.yaml"),
               "compat_rules": str(LIBS / "compat_rules.yaml")}}
)  # fmt: skip
KNOWN = {  # tests/data/test_recommendations.py::test_known_outcomes
    "USB-2627": ["USB-2633"],
    "MPU-6050": [],
    "WUS4C6464DSP3X5": [],
    "IR3555MTRPBF": [],
    "A100-SXM4-80GB": [],
}

# COMMAND ----------

spec = TABLES["gold.products"]
products = [
    Product.model_validate_json(r.payload)
    for r in spark.sql(f"SELECT payload FROM {spec.fqn(CATALOG)} ORDER BY part_number").collect()
]
results = compat_matrix(products, SETTINGS)
count = write_delta_with_spark(
    spark,
    CATALOG,
    TABLES["gold.compat_matrix"],
    matrix_rows(results, is_synthetic=any(p.is_synthetic for p in products), ingested_at=now_utc()),
)
print(f"{count} filas en {TABLES['gold.compat_matrix'].fqn(CATALOG)}")

# COMMAND ----------

by_part = {p.part_number: p for p in products}
for part, expected in KNOWN.items():
    out = rank([r for r in results if r.original_part_number == part], by_part)
    got = [r.product.part_number for r in out.recommendations]
    assert got == expected, f"{part}: {got} ≠ {expected}"
usb = rank([r for r in results if r.original_part_number == "USB-2627"], by_part).recommendations
assert usb[0].compatibility.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS, usb[0]
print("OK:", KNOWN)
