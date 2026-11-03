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

## Tablas Delta (`datathon.emerson.*`)
TODO: `bronze_documents`, `silver_parsed_pages`, `silver_products`, `silver_specs`, `silver_commercial`,
`gold_products`, `gold_chunks`, `kg_nodes`, `kg_edges`, `compat_matrix`. Columnas = campos de los modelos.

## Convenciones
- Unidades canónicas por clave en `config/spec_registry.yaml`.
- Valor ausente = `None` + regla R-MISSING; nunca se imputa.
- Precio solo si `status == ACTIVE` (validador emite warning si no cuadra).
