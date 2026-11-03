# Architecture

```
datos/pdfs ──► ingestion ──► parsing ──► extraction ──► enrichment(join catálogo) ──► chunking
                 (UC volume /Volumes/datathon/emerson/raw/pdfs on Databricks)
                                                │                         │
                                                ▼                         ▼
                         Delta bronze/silver/gold (products, specs, commercial, chunks)
                                                │
                                                ▼
                          kg (NetworkX) ──► Delta kg_nodes/kg_edges + artifacts/graph.json
                                                │
          ┌──────────────────────┬──────────────┴──────────┬───────────────────────┐
          ▼                      ▼                         ▼                       ▼
   retrieval (BM25 +      compatibility (reglas      commercial (catálogo     recommendation
   ST/FAISS; AI Search    YAML, 4 niveles,           = verdad: status,        (nivel > cobertura
   opcional)              matriz 32×32)              precio, stock)            > score; stock desempata)
          └──────────────────────┴──────────────┬──────────┴───────────────────────┘
                                                ▼
              agent: PARSE → RESOLVE → CLARIFY | STATUS → DISCOVER → VALIDATE → RANK → COMPOSE → VERIFY
                          (llm solo NLU→JSON validado y NLG con cifras verificadas)
                                                │
                                                ▼
                         app/streamlit_app.py (local, lee artifacts/ vía repository)
```

## Capas y dirección de dependencias
De arriba abajo (solo se importa hacia abajo; verificado por import-linter y `tests/contracts/test_imports.py`):

1. `pipeline`
2. `agent`
3. `recommendation` | `llm`
4. `compatibility` | `commercial` | `retrieval`
5. `kg`
6. `chunking` | `enrichment`
7. `extraction`
8. `parsing`
9. `ingestion`
10. `repository`
11. `models` | `config`

`compatibility` y `recommendation` no pueden importar `llm`, `retrieval`, `httpx` ni `databricks` (determinismo).
`app/` solo importa `advisor.models`, `advisor.agent`, `advisor.repository`, `advisor.config`.

## Ejecución
- **Databricks (Free Edition):** notebooks 00–07 construyen Delta + artefactos; consultas acotadas e idempotentes.
- **Local:** `make pipeline-local` produce los mismos artefactos desde `datos/pdfs/`; la app solo lee artefactos.

Detalles: [MODULE_CONTRACTS.md](MODULE_CONTRACTS.md), [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).
