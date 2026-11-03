# Knowledge Graph Design

## Nodos
`Product`, `Manufacturer`, `Category`, `Family`, `Interface`, `Protocol`, `Feature`, `Spec`, `Document`, `Chunk`, `Status`.

## Aristas (`EdgeType`)
| Tipo | De → A | Fuente |
|---|---|---|
| MADE_BY | Product → Manufacturer | catálogo |
| IN_CATEGORY | Product → Category | catálogo |
| IN_FAMILY | Product → Family | datasheet |
| HAS_INTERFACE | Product → Interface | datasheet |
| SUPPORTS_PROTOCOL | Product → Protocol | datasheet |
| HAS_FEATURE | Product → Feature | datasheet |
| HAS_SPEC | Product → Spec | extraction |
| DESCRIBED_IN | Product → Document | ingestion |
| HAS_CHUNK | Document → Chunk | chunking |
| HAS_STATUS | Product → Status | catálogo |
| MIGRATES_TO | Product → Product | aviso de migración en datasheet (con evidencia) |
| SIMILAR_TO | Product → Product | similitud (no implica compatibilidad) |
| SUBSTITUTE_CANDIDATE | Product → Product | resultado del motor de compatibilidad |

## Operaciones (contratos)
`build_graph`, `save`, `load`, `resolve_part`, `candidate_neighbors`. Personalized PageRank para descubrir candidatos: TODO (Dev2), no en bootstrap.

## Persistencia
Delta `kg_nodes`/`kg_edges` + `artifacts/graph.json` (node-link de NetworkX).
