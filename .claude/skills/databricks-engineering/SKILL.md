---
name: databricks-engineering
description: Use when writing or reviewing Databricks notebooks, PySpark transforms, Delta Lake tables, Unity Catalog DDL, SQL, MLflow tracking or data pipelines for this project. Enforces what actually works on Databricks Free Edition (serverless-only, Python/SQL, limited Vector Search and serving).
---

# Databricks Engineering (Free Edition)

## Contexto de la plataforma — compruébalo antes de diseñar

Free Edition ([límites oficiales](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)):

- **Solo cómputo serverless.** No hay clusters personalizados, init scripts, GPUs ni configuración Spark arbitraria.
- **Solo Python y SQL.** Nada de Scala/R.
- **Unity Catalog** con un único metastore y workspace. Usa nombres de tres niveles `catalog.schema.table`.
- **Vector Search / AI Search:** 1 endpoint, 1 unidad, **sin Direct Vector Access** → solo índices *Delta Sync*.
- **Model Serving:** limitado, sin GPU ni provisioned throughput; algunos modelos no disponibles.
- **Apps:** máximo 3, se paran a las 24 h.
- **Sin online tables ni clean rooms.** Uso no comercial.
- Serverless no permite `spark.sparkContext`, RDDs, `cache()`/`persist()` en DataFrames de forma fiable, ni configurar la mayoría de `spark.conf`. Evita también `dbutils.fs` sobre DBFS root: usa **Volumes** (`/Volumes/<catalog>/<schema>/<volume>/...`).

Si una funcionalidad no aparece en la página oficial como disponible, trátala como **no disponible** hasta verificarla en el workspace.

## Convenciones del proyecto

- Catálogo `emerson_hw`; esquemas `bronze`, `silver`, `gold` (configurables vía `EMERSON_UC_*`).
- Archivos fuente en un Volume: `/Volumes/emerson_hw/bronze/raw_files/`.
- Notebooks en `databricks/notebooks/NN_nombre.py` con cabecera `# Databricks notebook source` y separadores `# COMMAND ----------`. Así se versionan como texto y se importan vía Git folders.
- **Notebooks finos:** importan `emerson_agent` (Git folder + `sys.path` o `%pip install` del wheel) y solo hacen lectura/escritura Spark. La lógica (normalización de unidades, reglas) es Python puro en `src/` y se testea con pytest.
- Columnas de auditoría en Bronze: `_source_file`, `_ingested_at`, `_ingest_run_id`. Columna `is_synthetic` obligatoria en todas las capas.

## Medallion

| Capa | Contenido | Reglas |
|---|---|---|
| Bronze | dato crudo tal cual (CSV/JSON/texto PDF) | sin transformar; append-only; esquema permisivo (strings) |
| Silver | tipado, unidades normalizadas a SI, números de parte canónicos, deduplicado | `MERGE` idempotente por clave natural; registros inválidos a tabla `_quarantine` con motivo |
| Gold | `products`, `product_specifications`, `technical_documents`, `document_chunks`, `compatibility_rules` | contratos estables; `COMMENT` en tabla y columnas; constraints `CHECK` donde aplique |

## Prácticas de calidad

- Escrituras idempotentes: `MERGE INTO` o `replaceWhere`; nunca `mode("overwrite")` sin filtro en tablas compartidas.
- Esquemas explícitos (`StructType`) al leer CSV/JSON; nunca `inferSchema` en producción.
- Usa funciones nativas (`F.when`, `F.regexp_replace`) antes que UDFs Python; si una UDF es imprescindible, prefiere `pandas_udf`.
- Delta: `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)` en tablas gold que alimenten Vector Search (Delta Sync lo requiere).
- MLflow: `mlflow.set_experiment("/Users/<user>/emerson-eval")`; registra parámetros (top_k, backend), métricas (precision@k, recall@k, mrr, verdict_accuracy) y el golden set como artefacto.
- Credenciales: `databricks auth login` (OAuth) → `~/.databrickscfg`. Nunca tokens en notebooks; en Databricks usa secret scopes si alguna vez hacen falta.

## Ejemplo — notebook fino Silver

```python
# Databricks notebook source
# MAGIC %md ## 02 · Silver: normalización de especificaciones

# COMMAND ----------
from pyspark.sql import functions as F
from emerson_agent.data.units import to_si_udf  # lógica pura envuelta para Spark

CATALOG = "emerson_hw"
raw = spark.table(f"{CATALOG}.bronze.product_specifications_raw")

silver = (
    raw.withColumn("value_si", to_si_udf("value", "unit"))
    .withColumn("unit_si", F.col("value_si.unit"))
    .filter(F.col("part_number").isNotNull())
)

# COMMAND ----------
silver.createOrReplaceTempView("updates")
spark.sql(f"""
MERGE INTO {CATALOG}.silver.product_specifications t
USING updates s ON t.product_id = s.product_id AND t.attribute = s.attribute
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")
```

## Errores a evitar

- Asumir que algo que funciona con PySpark local funciona en serverless (y viceversa).
- Usar `sc`, RDDs, `spark.sparkContext.setLogLevel`, `.cache()` o rutas `dbfs:/` en serverless.
- Diseñar con Direct Vector Access, GPU serving, online tables o más de un endpoint de Vector Search.
- Poner lógica de negocio en el notebook (no es testeable).
- `inferSchema=True`, `overwrite` sin filtro, tablas sin comentarios.
- Mezclar datos sintéticos y reales sin la columna `is_synthetic`.
- Hardcodear host, token o rutas de usuario.

## Checklist antes de dar por bueno un notebook

- [ ] Corre de principio a fin en serverless de Free Edition.
- [ ] Re-ejecutarlo no duplica datos.
- [ ] La lógica no trivial está en `src/` con tests.
- [ ] Tablas con nombre de tres niveles, comentarios y `is_synthetic`.
- [ ] Sin secretos ni rutas personales.
