# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · ai_search (K4) — última tarea de `run_all`
# MAGIC Deja AI Search reproducible e idempotente sobre `gold.document_chunks`:
# MAGIC 1. Endpoint `emerson-vs` (STANDARD; Free Edition permite uno): lo crea si falta y
# MAGIC    espera ONLINE.
# MAGIC 2. Índice `<catalog>.gold.document_chunks_index` (Delta Sync, TRIGGERED, embeddings
# MAGIC    `databricks-gte-large-en` sobre `text`): lo crea si falta; si existe, comprueba que su
# MAGIC    especificación coincide y lo re-sincroniza.
# MAGIC 3. Espera a que el índice tenga tantas filas como la tabla y hace una consulta de humo.
# MAGIC
# MAGIC No va en `resources:` del bundle porque el índice necesita la tabla (que crea `run_all`
# MAGIC después del deploy) y el modo development prefijaría un segundo endpoint.
# MAGIC Cualquier fallo hace fallar la tarea; `ai_search=false` la desactiva.

# COMMAND ----------

# ruff: noqa: F821  (spark y dbutils los inyecta Databricks)
import time
from datetime import datetime

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import AlreadyExists, DatabricksError, NotFound
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

dbutils.widgets.text("catalog", "emerson_hw")
dbutils.widgets.dropdown("ai_search", "true", ["true", "false"])
CATALOG = dbutils.widgets.get("catalog")
if dbutils.widgets.get("ai_search") != "true":
    dbutils.notebook.exit("SKIP: ai_search=false")

ENDPOINT = "emerson-vs"
EMBEDDING_MODEL = "databricks-gte-large-en"
SOURCE_TABLE = f"{CATALOG}.gold.document_chunks"
INDEX = f"{CATALOG}.gold.document_chunks_index"
COLUMNS = ["chunk_id", "document_id", "page_start", "page_end", "section", "text", "part_numbers"]
ENDPOINT_TIMEOUT_S, INDEX_TIMEOUT_S, POLL_S = 1800, 2700, 30  # la 1.ª provisión tardó ~21 min

ws = WorkspaceClient()
expected = spark.table(SOURCE_TABLE).count()


def wait(what: str, check, timeout_s: int):  # type: ignore[no-untyped-def]
    """Poll ``check()`` until it returns a truthy value; raise on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(POLL_S)
    raise TimeoutError(f"{what}: sin terminar tras {timeout_s} s")


def deletion_in_progress(exc: DatabricksError) -> bool:
    """Borrar endpoints/índices es asíncrono: mientras termina, el nombre sigue reservado y la
    API responde AlreadyExists o InvalidParameterValue ("pending deletion"): se reintenta."""
    return isinstance(exc, AlreadyExists) or "delet" in str(exc).lower()


# COMMAND ----------


# 1. Endpoint. Borrar un endpoint es asíncrono: un rato después de que get_endpoint deja de
# encontrarlo, el nombre sigue reservado y create_endpoint responde AlreadyExists. Se reintenta.
def endpoint_exists_or_created() -> bool:
    try:
        ws.vector_search_endpoints.get_endpoint(ENDPOINT)
        print(f"endpoint {ENDPOINT} existe")
        return True
    except NotFound:
        pass
    except DatabricksError as exc:  # "is being deleted"
        print(f"{time.strftime('%X')} endpoint {ENDPOINT}: {exc}")
        return False
    try:
        ws.vector_search_endpoints.create_endpoint(ENDPOINT, EndpointType.STANDARD)
        print(f"endpoint {ENDPOINT} creado")
        return True
    except DatabricksError as exc:
        if not deletion_in_progress(exc):
            raise
        print(f"{time.strftime('%X')} {ENDPOINT} aún reservado (borrado en curso); reintento")
        return False


wait(f"crear endpoint {ENDPOINT}", endpoint_exists_or_created, ENDPOINT_TIMEOUT_S)


def endpoint_online() -> bool:
    status = ws.vector_search_endpoints.get_endpoint(ENDPOINT).endpoint_status
    state = str(getattr(status.state, "value", status.state)) if status else None
    print(f"{time.strftime('%X')} endpoint {state}")
    if state in ("OFFLINE", "RED_STATE", "DELETED"):
        raise RuntimeError(f"endpoint {ENDPOINT} en estado {state}: {status.message}")
    return state == "ONLINE"


wait(f"endpoint {ENDPOINT}", endpoint_online, ENDPOINT_TIMEOUT_S)

# COMMAND ----------

# 2. Índice: crear (la creación hace la primera sincronización) o verificar y re-sincronizar
created = False


def index_exists_or_created() -> bool:
    """Same as the endpoint: a just-deleted index keeps its name reserved for a while."""
    global created
    try:
        ws.vector_search_indexes.get_index(INDEX)
        print(f"índice {INDEX} existe")
        return True
    except NotFound:
        pass
    except DatabricksError as exc:
        if not deletion_in_progress(exc):
            raise
        print(f"{time.strftime('%X')} {INDEX}: {exc}")
        return False
    try:
        ws.vector_search_indexes.create_index(
            name=INDEX,
            endpoint_name=ENDPOINT,
            primary_key="chunk_id",
            index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=SOURCE_TABLE,
                pipeline_type=PipelineType.TRIGGERED,
                columns_to_sync=COLUMNS,
                embedding_source_columns=[
                    EmbeddingSourceColumn(
                        name="text", embedding_model_endpoint_name=EMBEDDING_MODEL
                    )
                ],
            ),
        )
        print(f"índice {INDEX} creado")
        created = True
        return True
    except DatabricksError as exc:
        if not deletion_in_progress(exc):
            raise
        print(f"{time.strftime('%X')} {INDEX} aún reservado (borrado en curso); reintento")
        return False


wait(f"crear índice {INDEX}", index_exists_or_created, INDEX_TIMEOUT_S)

# create_index devuelve CreateVectorIndexResponse (sin endpoint_name/spec): se relee siempre.
index = ws.vector_search_indexes.get_index(INDEX)
spec = index.delta_sync_index_spec
mismatch = {
    "endpoint": (index.endpoint_name, ENDPOINT),
    "source_table": (spec.source_table, SOURCE_TABLE),
    "embedding": (
        [c.embedding_model_endpoint_name for c in spec.embedding_source_columns or []],
        [EMBEDDING_MODEL],
    ),
}
mismatch = {k: v for k, v in mismatch.items() if v[0] != v[1]}
if mismatch:
    raise RuntimeError(f"{INDEX} existe con otra especificación (actual, esperado): {mismatch}")

started_ms = int(time.time() * 1000) - 60_000  # margen por desfase de reloj


def sync_started() -> bool:
    """Si otra ejecución (otro miembro del equipo) está sincronizando, la API responde
    "not ready to sync" (pipeline INITIALIZING/RUNNING): se espera y se reintenta."""
    try:
        ws.vector_search_indexes.sync_index(INDEX)
    except DatabricksError as exc:
        if "not ready to sync" not in str(exc).lower():
            raise
        print(f"{time.strftime('%X')} sincronización en curso de otra ejecución; reintento")
        return False
    print(f"sync lanzado para {INDEX}")
    return True


if not created:
    wait(f"lanzar sync de {INDEX}", sync_started, INDEX_TIMEOUT_S)


def update_done() -> bool:
    """Newest pipeline update created after this run reached a final state (raise if failed)."""
    if created:  # la creación no deja una actualización "posterior": basta con ready + filas
        return True
    for update in ws.pipelines.get(spec.pipeline_id).latest_updates or []:
        if not update.creation_time:
            continue
        created_at = datetime.fromisoformat(update.creation_time.replace("Z", "+00:00"))
        if created_at.timestamp() * 1000 < started_ms:
            continue
        state = str(getattr(update.state, "value", update.state))
        print(f"{time.strftime('%X')} actualización {state}")
        if state in ("FAILED", "CANCELED"):
            raise RuntimeError(f"sincronización de {INDEX}: {state}")
        return state == "COMPLETED"
    return False


def index_ready() -> bool:
    status = ws.vector_search_indexes.get_index(INDEX).status
    print(f"{time.strftime('%X')} índice ready={status.ready} filas={status.indexed_row_count}")
    return bool(status.ready and status.indexed_row_count == expected)


wait(f"sincronización de {INDEX}", update_done, INDEX_TIMEOUT_S)
wait(f"índice {INDEX} con {expected} filas", index_ready, INDEX_TIMEOUT_S)

# COMMAND ----------

# 3. Consulta de humo (recuperación de evidencia; la compatibilidad la decide el motor de reglas)
hits = ws.vector_search_indexes.query_index(
    INDEX,
    columns=["chunk_id", "part_numbers"],
    query_text="NIC 100GbE con RDMA RoCE v2",
    num_results=3,
).result.data_array
assert hits, "la consulta de humo no devolvió resultados"
print("humo:", [row[1] for row in hits])
dbutils.notebook.exit(
    f"OK: {INDEX} {'creado' if created else 'sincronizado'} con {expected} filas en {ENDPOINT}"
)
