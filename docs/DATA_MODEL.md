# Data Model

Contratos Pydantic v2 en `src/advisor/models/` (`CONTRACT_VERSION = "1.0.0"`). Cambios solo vía PR `contract-change`.

## Entidades
| Modelo | Propósito | Clave |
|---|---|---|
| `DocumentRecord` | PDF descubierto (path, sha256, tipo) | `document_id` |
| `ParsedDocument` | texto/tablas por página | `document_id` |
| `Chunk` / `ChunkHit` | fragmento indexable / resultado de búsqueda | `chunk_id` |
| `Evidence` | cita: documento, página, chunk, cita textual | — |
| `ProductSpecification` | atributo normalizado (`key`, `value`, `unit`, `evidence`) | (`part_number`, `key`) |
| `CommercialInformation` | estado, fechas, precio, stock (catálogo) | `part_number` |
| `Product` | producto con specs + comercial | `part_number` |
| `JoinReport` | resultado del cruce catálogo ↔ datasheets | — |
| `CustomerQuery` / `ParsedQuery` | consulta cruda / interpretada | — |
| `TechnicalRequirement` | requisito (`EQ|GTE|LTE|IN|HAS`) con prioridad y origen | — |
| `PartMatch` | resolución de part number con score | — |
| `GraphNode` / `GraphEdge` | KG | `node_id` |
| `CandidateProduct` | candidato + ruta de descubrimiento | `part_number` |
| `RuleResult` / `CompatibilityResult` | evaluación por regla / global | (`original`, `candidate`) |
| `Recommendation` / `RecommendationResponse` | salida al usuario | — |

## Tablas Delta (`emerson_hw.<capa>.*`)

Las escribe el job `run_all` (`databricks.yml`) en serverless, entorno versión 4. Esquemas y orden en
`advisor.repository.databricks_sql.TABLES` (una sola definición para notebooks y `DatabricksSQLRepository`).
Toda tabla silver/gold tiene `is_synthetic` y `_ingested_at` y `COMMENT`; se reescribe con
`CREATE OR REPLACE TABLE ... AS SELECT * FROM read_files(<parquet en gold.artifacts/_delta/>)`, así que
re-ejecutar no duplica filas. Columnas JSON = texto JSON del contrato correspondiente.

| Tabla | Notebook | Filas | Clave | Columnas |
|---|---|---|---|---|
| `bronze.documents_parsed` | 01_parse | 33 | `document_name` | `document_name`, `doc_type`, `parsed` (VARIANT de `ai_parse_document`), `_source_file`, `_ingested_at`, `_ingest_run_id`, `is_synthetic` |
| `silver.commercial` | 02_extract_enrich | 32 (21/6/2/3) | `part_number` | `part_number`, `description`, `manufacturer`, `category`, `status`, `discontinued_on`, `last_buy_on`, `price_usd` decimal(14,2) (solo ACTIVE), `stock_units`, `inventory_value_usd` |
| `silver.products` | 02_extract_enrich | 32 | `part_number` | `part_number`, `manufacturer`, `category`, `description`, `document_ids` array |
| `silver.product_specifications` | 02_extract_enrich | 272 | `part_number, key` | `part_number`, `key`, `value` JSON, `unit`, `raw_value`, `evidence` JSON (documento, página, cita) |
| `gold.products` | 02_extract_enrich | 32 | `part_number` | `part_number`, `manufacturer`, `category`, `description`, `status`, `price_usd`, `stock_units`, `payload` (Product JSON) |
| `gold.document_chunks` | 03_chunk_index | 126 | `chunk_id` | `chunk_id`, `document_id`, `page_start`, `page_end`, `section`, `text`, `part_numbers` array, `payload` (Chunk JSON). Change Data Feed activado |
| `gold.kg_nodes` | 04_build_kg | 501 | `node_id` | `node_id`, `node_type`, `label`, `properties` JSON |
| `gold.kg_edges` | 04_build_kg | 586 | `source, target, edge_type` | `source`, `target`, `edge_type` (= clave de la arista), `weight`, `evidence` JSON; 4 `MIGRATES_TO` |
| `gold.compat_matrix` | 05_compat_matrix | 30 | `original_part_number, candidate_part_number` | `level`, `coverage`, `score`, `conditions` JSON, `missing` JSON, `rule_results` JSON, `payload` (CompatibilityResult JSON) |

Volúmenes: `bronze.raw_files` (33 PDFs), `bronze.libs` (wheel de `advisor` + `config/*.yaml`, lo llena 00_setup),
`gold.artifacts` (export de 06_export_artifacts en formato `LocalParquetRepository`; `_delta/` es staging interno).

## Convenciones
- Unidades canónicas por clave en `config/spec_registry.yaml`.
- Valor ausente = `None` + regla R-MISSING; nunca se imputa.
- Precio solo si `status == ACTIVE` (validador emite warning si no cuadra).
