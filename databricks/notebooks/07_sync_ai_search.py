# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · sync_ai_search (K4, opcional)
# MAGIC Sincroniza el índice Delta Sync de AI Search sobre `gold.document_chunks` tras reescribir la
# MAGIC tabla (el índice es `TRIGGERED`). AI Search es opcional (el agente usa BM25): si el
# MAGIC índice no existe o la sincronización tarda, se informa y el job **no** falla.
# MAGIC Índice: endpoint `emerson-vs`, `<catalog>.gold.document_chunks_index`, embeddings
# MAGIC `databricks-gte-large-en` (ver FEATURE_MATRIX).

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
import time
from datetime import datetime

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
INDEX = f"{CATALOG}.gold.document_chunks_index"
TIMEOUT_S, POLL_S = 900, 20

# COMMAND ----------

ws = WorkspaceClient()
try:
    index = ws.vector_search_indexes.get_index(INDEX)
except NotFound:
    dbutils.notebook.exit(f"SKIP: {INDEX} no existe (AI Search es opcional)")

# El estado de la sincronización está en el pipeline del índice (get_index no expone
# detailed_state): se espera la primera actualización creada después de lanzar el sync.
pipeline_id = index.delta_sync_index_spec.pipeline_id
expected = spark.table(f"`{CATALOG}`.gold.document_chunks").count()
started_ms = int(time.time() * 1000) - 60_000  # margen por desfase de reloj
ws.vector_search_indexes.sync_index(INDEX)
print(f"sync lanzado para {INDEX} (pipeline {pipeline_id}); filas en la tabla: {expected}")

# COMMAND ----------


def latest_update_state() -> str | None:
    """State of the newest pipeline update created after the sync request, if any."""
    updates = ws.pipelines.get(pipeline_id).latest_updates or []
    for update in updates:
        if not update.creation_time:
            continue
        created = datetime.fromisoformat(update.creation_time.replace("Z", "+00:00"))
        if created.timestamp() * 1000 >= started_ms:
            return str(getattr(update.state, "value", update.state))
    return None


deadline, state = time.time() + TIMEOUT_S, None
while time.time() < deadline:
    state = latest_update_state()
    print(f"{time.strftime('%X')} actualización: {state}")
    if state in ("COMPLETED", "FAILED", "CANCELED"):
        break
    time.sleep(POLL_S)

rows = ws.vector_search_indexes.get_index(INDEX).status.indexed_row_count
if state == "COMPLETED" and rows == expected:
    dbutils.notebook.exit(f"OK: {INDEX} sincronizado con {rows} filas")
dbutils.notebook.exit(f"AVISO: {INDEX} actualización={state}, filas={rows}/{expected}")
