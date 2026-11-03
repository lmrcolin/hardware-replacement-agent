# Feature Matrix — Databricks Free Edition

Rellenar al probar cada capacidad en nuestro workspace. Nada se asume disponible hasta estar en OK.

| Capacidad | Probado por | Fecha | OK/FAIL | Notas |
|---|---|---|---|---|
| `ai_parse_document` sobre `read_files(..., format => 'binaryFile')` | | | | notebook 02 |
| `ai_query` con Llama 3.3 70B (`databricks-meta-llama-3-3-70b-instruct`) | | | | rate limits / cuota |
| AI Search (Vector Search) endpoint + índice Delta Sync | | | | 1 endpoint, 1 unidad, sin Direct Vector Access |
| Databricks Connect (serverless) desde local | | | | alternativa: SQL warehouse (ADR-009) |
| Databricks Apps | | | | ≤3, se paran a las 24 h |
| Genie space sobre tablas gold | | | | opcional para la demo |
| Descarga de modelos HF desde serverless (egress) | | | | ADR-007 |
