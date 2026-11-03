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

## Implementación (B-18, B-19)

- **Cadena LLM** (`llm.build_llm_chain`): `databricks` solo si hay `ADVISOR_DATABRICKS_PROFILE`; `ollama` solo si
  responde y tiene el modelo; `template` siempre al final. Cualquier error/JSON inválido pasa al siguiente.
- **NLU** (`PARSE`): prompt con claves permitidas por categoría; la salida se valida como `ParsedQuery` y se
  **sanea**: se descartan requisitos con claves fuera del registro o cifras que no aparecen en la consulta (con aviso).
  `TemplateClient` usa `llm/rules.py` (regex es/en).
- **RESOLVE**: `kg.resolve_part` sobre el texto y sobre cada token; umbral 0.85; dos coincidencias a < 0.05 ⇒ CLARIFY.
  Sin part number: con categoría + requisitos ⇒ búsqueda por requisitos; si no ⇒ CLARIFY.
- **DISCOVER**: toda la categoría (32 productos: exhaustivo) + vecinos del grafo + hits BM25.
- **VALIDATE/RANK**: `derive_requirements` + `evaluate` + `rank`. Sucesores `MIGRATES_TO` incompatibles se explican.
- **COMPOSE/VERIFY**: borrador determinista desde los datos; el LLM solo lo reescribe. Si el texto contiene cifras o
  part numbers que no están en el borrador/catálogo ⇒ se usa el borrador y se avisa.
- `AdvisorAgent.last_trace` registra los pasos ejecutados.
