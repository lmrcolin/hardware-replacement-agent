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

## Implementación (B-09, B-11, B-12)
- Datos reales: 501 nodos, 586 aristas; 4 `MIGRATES_TO` (E810→ConnectX-7, E810→BCM57508, USB-2627→USB-2633, A100→H100).
- `MIGRATES_TO`: frases en secciones de aviso/migración/pedido o con verbos de sustitución que mencionan otro part number
  del catálogo (o su raíz única: `E810`, `H100`). "replacement for X" invierte la dirección. Evidencia = la frase literal
  + `chunk_id`; varias fuentes se acumulan en la misma arista.
- `SIMILAR_TO`: misma categoría y Jaccard ≥ 0.2 sobre nodos compartidos de familia/interfaz/protocolo/feature.
  Solo descubre candidatos; **no implica compatibilidad**.
- `resolve_part`: exacto (1.0) → normalizado (0.95) → raíz (0.9) → fuzzy sobre tokens con letras y dígitos (≤0.85).
- `candidate_neighbors`: pesos MIGRATES_TO 1.0, familia 0.5, SIMILAR_TO 0.4×peso, categoría 0.2; nunca el propio producto
  ni otra categoría.

## Operaciones (contratos)
`build_graph`, `save`, `load`, `resolve_part`, `candidate_neighbors`. Personalized PageRank: no implementado (32 productos; los pesos explícitos son suficientes y explicables).

## Persistencia
Delta `kg_nodes`/`kg_edges` + `artifacts/graph.json` (node-link de NetworkX).
