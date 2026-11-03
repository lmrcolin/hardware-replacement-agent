# Feature Matrix — Databricks Free Edition

Rellenar al probar cada capacidad en nuestro workspace. Nada se asume disponible hasta estar en OK.

| Capacidad | Probado por | Fecha | OK/FAIL | Notas |
|---|---|---|---|---|
| `ai_parse_document` sobre `read_files(..., format => 'binaryFile')` | lmrcolin (CLI, solo lectura) | 2026-11-03 | OK con reservas | 33/33 filas en `bronze.documents_parsed`, 0 nulos, 0 `error_status`. **Catálogo: leyó `H9HCNNCPMML` en vez de `H9HCNNNCPMML`** (31/32 part numbers literales). Ver ADR-012 |
| `ai_query` con Llama 3.3 70B (`databricks-meta-llama-3-3-70b-instruct`) | | | | rate limits / cuota; `DatabricksFMAPIClient` implementado vía `serving_endpoints.query`, **sin probar contra el endpoint real** |
| Ollama local (`qwen3:4b`) | | | | `OllamaClient` implementado (`/api/generate` con `format` JSON schema), **sin probar**; el modelo no está descargado |
| AI Search (Vector Search) endpoint + índice Delta Sync | | | | 1 endpoint, 1 unidad, sin Direct Vector Access |
| Databricks Connect (serverless) desde local | | | | alternativa: SQL warehouse (ADR-009) |
| Statement Execution API en `Serverless Starter Warehouse` (2X-Small) desde el CLI | lmrcolin | 2026-11-03 | OK | lecturas de verificación; arranque en frío ~segundos |
| Lectura de binarios del repo vía FUSE `/Workspace` en serverless | Kevinvlz | 2026-11-03 | FAIL | 403 (SSE-C); `00_setup` usa la API de Workspace (PR #3) |
| Permisos UC entre miembros del equipo | equipo | 2026-11-03 | OK tras GRANT | el owner del catálogo es quien ejecutó el bundle; admin de workspace no basta (falta `MANAGE`) |
| Databricks Apps | | | | ≤3, se paran a las 24 h |
| Genie space sobre tablas gold | | | | opcional para la demo |
| Descarga de modelos HF desde serverless (egress) | | | | ADR-007 |
