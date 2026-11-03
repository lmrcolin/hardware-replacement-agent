# Architecture Decisions (ADR)

Formato: contexto → decisión → consecuencias. Estado: Propuesto | Aceptado | Reemplazado.

## ADR-001 Catálogo comercial = fuente de verdad (Aceptado)
Estado, precio y stock salen solo del catálogo. Los datasheets aportan specs y avisos de migración; si contradicen al catálogo, gana el catálogo y se registra en `JoinReport`.

## ADR-002 Motor de compatibilidad determinista con reglas YAML (Aceptado)
Niveles COMPATIBLE, COMPATIBLE_WITH_CONDITIONS, UNKNOWN, INCOMPATIBLE. Una regla crítica fallida ⇒ INCOMPATIBLE. El LLM nunca decide compatibilidad.

## ADR-003 LLM solo para NLU y NLG con fallback (Aceptado)
Cadena `databricks` (Llama 3.3 70B) → `ollama` (qwen3:4b) → `template`. NLU devuelve JSON validado por Pydantic; NLG solo puede usar cifras presentes en `RecommendationResponse` (VERIFY lo comprueba).

## ADR-004 Grafo de conocimiento en NetworkX persistido en Delta + JSON (Aceptado)
32 productos caben en memoria. Delta `kg_nodes`/`kg_edges` para trazabilidad en Databricks y `artifacts/graph.json` para la app local.

## ADR-005 Matriz de compatibilidad 32×32 precalculada (Aceptado)
Coste trivial (1 024 pares) y elimina latencia en la demo. Se recalcula al cambiar reglas o specs.

## ADR-006 Retrieval detrás de interfaz `Retriever` (Aceptado)
BM25 por defecto; sentence-transformers + FAISS local; AI Search opcional (1 endpoint, 1 unidad, sin Direct Vector Access → índice Delta Sync).

## ADR-007 Embeddings y modelos fuera de Databricks (Propuesto)
**Riesgo:** egress restringido en Free Edition puede impedir descargar modelos de Hugging Face desde serverless.
**Decisión:** calcular embeddings localmente y subir el índice como artefacto; en Databricks usar AI Search con embeddings gestionados si está disponible. Verificar en FEATURE_MATRIX.

## ADR-008 App Streamlit local sobre artefactos (Aceptado)
Las Apps de Free Edition se detienen a las 24 h y consumen cuota; la demo corre local. Databricks Apps queda como opción.

## ADR-009 Acceso a datos desde local vía SQL warehouse (Propuesto)
Databricks Connect con serverless en Free Edition no está verificado. `repository.DatabricksSQL` usa la Statement Execution API (databricks-sdk) contra el warehouse 2X-Small; `LocalParquet` es el default.

## ADR-010 gitleaks como hook de pre-commit (Aceptado)
gitleaks no se distribuye por PyPI; se instala vía pre-commit (binario Go), no como dependencia Python.

## ADR-011 Torch CPU-only (Aceptado)
`sentence-transformers` arrastra torch; se fija el índice `pytorch-cpu` en `pyproject.toml` para evitar ~GB de CUDA.
