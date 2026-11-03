# Agent Design

```
PARSE → RESOLVE → (CLARIFY | STATUS) → DISCOVER → VALIDATE → RANK → COMPOSE → VERIFY
```
| Paso | Herramienta | LLM |
|---|---|---|
| PARSE | `llm.complete_json` → `ParsedQuery` validado | NLU |
| RESOLVE | `kg.resolve_part` (rapidfuzz) | — |
| CLARIFY | pregunta si `PartMatch` ambiguo o sin categoría | — |
| STATUS | `commercial.get` (catálogo) | — |
| DISCOVER | `kg.candidate_neighbors` + `retrieval.search` | — |
| VALIDATE | `compatibility.derive_requirements` + `evaluate` | — |
| RANK | `recommendation.rank` | — |
| COMPOSE | `llm.generate` con datos de `RecommendationResponse` | NLG |
| VERIFY | toda cifra/part number del texto debe existir en la respuesta estructurada; si no → plantilla | — |

Solo ACTIVE en `recommendations`; NRND en `risky_options`. Fallback LLM: databricks → ollama → template.
