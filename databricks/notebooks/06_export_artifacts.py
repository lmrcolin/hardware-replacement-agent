# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · export_artifacts (K6, B-10)
# MAGIC Tablas `gold` → `/Volumes/<catalog>/gold/artifacts/` en el formato de `LocalParquetRepository`
# MAGIC (`products.parquet`, `chunks.parquet`, `compat_matrix.parquet`, `graph.json`, `documents.json`),
# MAGIC el mismo que produce `make pipeline-local` y consume la app.
# MAGIC
# MAGIC Para bajarlos a local:
# MAGIC `databricks fs cp -r dbfs:/Volumes/emerson_hw/gold/artifacts ./artifacts --profile <perfil>`
# MAGIC (la carpeta `_delta/` es staging interno de las tablas; se puede ignorar).
# MAGIC Requiere el entorno serverless versión 4 (Python 3.12) y el wheel en `bronze.libs`.

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (spark/dbutils los inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

import json
from pathlib import Path

from advisor.ingestion import discover_documents
from advisor.kg import save as save_graph
from advisor.models import Chunk, CompatibilityResult, Product
from advisor.pipeline import write_manifest
from advisor.repository import LocalParquetRepository
from advisor.repository.databricks_sql import TABLES, graph_from_rows

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
RAW = Path(f"/Volumes/{CATALOG}/bronze/raw_files")
OUT = Path(f"/Volumes/{CATALOG}/gold/artifacts")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{CATALOG}`.gold.artifacts")


def select(key: str, columns: str) -> list:  # type: ignore[type-arg]
    spec = TABLES[key]
    return spark.sql(f"SELECT {columns} FROM {spec.fqn(CATALOG)} ORDER BY {spec.order_by}").collect()


# COMMAND ----------

products = [Product.model_validate_json(r.payload) for r in select("gold.products", "payload")]
chunks = [Chunk.model_validate_json(r.payload) for r in select("gold.document_chunks", "payload")]
matrix = [
    CompatibilityResult.model_validate_json(r.payload) for r in select("gold.compat_matrix", "payload")
]
graph = graph_from_rows(
    [tuple(r) for r in select("gold.kg_nodes", "node_id, node_type, label, properties")],
    [tuple(r) for r in select("gold.kg_edges", "source, target, edge_type, weight, evidence")],
)

repo = LocalParquetRepository(OUT)
repo.save_products(products)
repo.save_chunks(chunks)
repo.save_compat_matrix(matrix)
save_graph(graph, OUT / LocalParquetRepository.GRAPH)
names = {r.document_id: r.filename for r in discover_documents(RAW)}  # citas en la app
(OUT / "documents.json").write_text(
    json.dumps(names, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
)
# Procedencia visible en la app ("Fuentes en uso"): estos artefactos salen de Databricks.
write_manifest(OUT, "databricks", products=len(products), chunks=len(chunks))

# COMMAND ----------

assert len(repo.load_products()) == 32
assert len(repo.load_chunks()) == len(chunks)
assert repo.load_graph().number_of_edges() == graph.number_of_edges()
print("OK:", sorted(p.name for p in OUT.iterdir()))
