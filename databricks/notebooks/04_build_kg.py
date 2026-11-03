# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · build_kg (K4, B-09/B-10)
# MAGIC `gold.products` + `gold.document_chunks` → `build_graph` → `gold.kg_nodes` y `gold.kg_edges`
# MAGIC (`CREATE OR REPLACE`). Las aserciones replican `tests/data/test_knowledge_graph.py`.
# MAGIC Requiere el entorno serverless versión 4 (Python 3.12) y el wheel en `bronze.libs`.

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (spark/dbutils los inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

from advisor.kg import build_graph, resolve_part
from advisor.models import Chunk, Product
from advisor.repository.databricks_sql import (
    TABLES,
    kg_edge_rows,
    kg_node_rows,
    now_utc,
    write_delta_with_spark,
)

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
EXPECTED_MIGRATIONS = {
    ("product:E810-CQDA2", "product:MCX75310AAS-NEAT"),
    ("product:E810-CQDA2", "product:BCM57508"),
    ("product:USB-2627", "product:USB-2633"),
    ("product:A100-SXM4-80GB", "product:H100-SXM5"),
}


def payloads(key: str, model):  # type: ignore[no-untyped-def]
    spec = TABLES[key]
    rows = spark.sql(f"SELECT payload FROM {spec.fqn(CATALOG)} ORDER BY {spec.order_by}").collect()
    return [model.model_validate_json(r.payload) for r in rows]


# COMMAND ----------

products = payloads("gold.products", Product)
chunks = payloads("gold.document_chunks", Chunk)
graph = build_graph(products, chunks)
synthetic, at = any(p.is_synthetic for p in products), now_utc()
nodes = write_delta_with_spark(
    spark, CATALOG, TABLES["gold.kg_nodes"], kg_node_rows(graph, is_synthetic=synthetic, ingested_at=at)
)
edges = write_delta_with_spark(
    spark, CATALOG, TABLES["gold.kg_edges"], kg_edge_rows(graph, is_synthetic=synthetic, ingested_at=at)
)
print(f"{nodes} nodos · {edges} aristas")

# COMMAND ----------

migrations = {
    (r.source, r.target)
    for r in spark.sql(
        f"SELECT source, target, evidence FROM {TABLES['gold.kg_edges'].fqn(CATALOG)} "
        "WHERE edge_type = 'MIGRATES_TO'"
    ).collect()
}
no_evidence = spark.sql(
    f"SELECT count(*) AS n FROM {TABLES['gold.kg_edges'].fqn(CATALOG)} "
    "WHERE edge_type = 'MIGRATES_TO' AND evidence = '[]'"
).first().n
product_nodes = spark.sql(
    f"SELECT count(*) AS n FROM {TABLES['gold.kg_nodes'].fqn(CATALOG)} WHERE node_id LIKE 'product:%'"
).first().n

assert migrations == EXPECTED_MIGRATIONS, migrations
assert no_evidence == 0, f"{no_evidence} aristas MIGRATES_TO sin evidencia"
assert product_nodes == len(products) == 32, (product_nodes, len(products))
assert [m.part_number for m in resolve_part(graph, "Intel E810-CQDA2")][:1] == ["E810-CQDA2"]
print(f"OK: {len(migrations)} MIGRATES_TO con evidencia, {product_nodes} nodos de producto")
