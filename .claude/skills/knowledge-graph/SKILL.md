---
name: knowledge-graph
description: Builds, persists and queries the NetworkX knowledge graph (nodes, typed edges, part resolution, candidate discovery). Use when touching src/advisor/kg/, kg_nodes/kg_edges tables or artifacts/graph.json.
---

# Knowledge graph

## Alcance
`src/advisor/kg/` (`build.py` y `query.py`), notebook `05_build_kg`, `tests/fixtures/mock_graph.json`.

## Convenciones
- `nx.MultiDiGraph`; `node_id` con prefijo de tipo: `product:E810-CQDA2`, `category:Network`, `protocol:RoCEv2`, `doc:<sha12>`, `chunk:<id>`.
- Aristas solo de `EdgeType` (MADE_BY, IN_CATEGORY, IN_FAMILY, HAS_INTERFACE, SUPPORTS_PROTOCOL, HAS_FEATURE, HAS_SPEC, DESCRIBED_IN, HAS_CHUNK, HAS_STATUS, MIGRATES_TO, SIMILAR_TO, SUBSTITUTE_CANDIDATE).
- Cada arista derivada de documento lleva `evidence`. `MIGRATES_TO` solo con aviso explícito en el datasheet.
- `SIMILAR_TO` sirve para descubrir candidatos; **nunca implica compatibilidad**.
- Persistencia: `nx.node_link_data` → `artifacts/graph.json`; Delta `kg_nodes`/`kg_edges` con las mismas columnas.

## Contratos
`build_graph`, `save`, `load`, `resolve_part` (rapidfuzz, devuelve `PartMatch` ordenados con score), `candidate_neighbors` (devuelve `CandidateProduct` con `DiscoveryPath`).

## Pruebas
`save`→`load` es identidad; `resolve_part("e810")` resuelve `E810-CQDA2`; `candidate_neighbors` no devuelve el propio producto; funciona sobre `mock_graph.json`.

## Prohibido
Lógica de compatibilidad o comercial dentro de `kg/`; aristas sin tipo; PPR u otras heurísticas sin test.
