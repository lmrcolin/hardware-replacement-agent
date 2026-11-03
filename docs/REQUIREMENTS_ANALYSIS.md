# Requirements Analysis

## Funcionales
| ID | Requisito | Prioridad |
|---|---|---|
| F-01 | Entender consultas en lenguaje natural (es/en) con part number, categoría o necesidades técnicas | Must |
| F-02 | Resolver el part number aunque esté mal escrito (rapidfuzz + KG) | Must |
| F-03 | Informar el estado comercial real (catálogo = verdad) | Must |
| F-04 | Pedir aclaración si la consulta es ambigua (CLARIFY) | Must |
| F-05 | Descubrir candidatos ACTIVE (KG: misma categoría, MIGRATES_TO, SIMILAR_TO; retrieval) | Must |
| F-06 | Validar compatibilidad con reglas deterministas y 4 niveles | Must |
| F-07 | Ranking lexicográfico: nivel > cobertura > score; inventario solo desempata | Must |
| F-08 | Mostrar precio y stock solo de ACTIVE; NRND en `risky_options` | Must |
| F-09 | Justificar con evidencia (documento, página, chunk) | Must |
| F-10 | Excel de costes (desarrollo, mantenimiento 1 año, TCO anual) | Must |

## No funcionales
- Coste de APIs = 0 USD. Databricks Free Edition (serverless, cuota diaria, 1 warehouse 2X-Small, 1 endpoint AI Search, ≤3 Apps, egress restringido).
- LLM: Llama 3.3 70B (FMAPI) → Ollama qwen3:4b → plantilla. Claude/GPT con rate limit 0.
- Reproducible desde cero sin intervención manual (salvo autenticación).
- Arch Linux + Python 3.12 + uv.

## Supuestos / preguntas abiertas
- TODO: ¿qué disponibilidad real tienen ai_parse_document, ai_query y AI Search en nuestro workspace? → FEATURE_MATRIX.md
- TODO: confirmar con jueces si "NRND" puede ofrecerse como alternativa (hoy: solo en risky_options).
