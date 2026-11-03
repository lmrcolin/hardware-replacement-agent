# Demo Plan — Emerson Replacement Advisor (≈ 8 min)

**Antes de empezar (5 min antes):**
```bash
git checkout main && git pull
make pipeline-local          # artifacts/ (≈3 s); la app arranca al instante
make app                     # http://localhost:8501 — dejar abierta en "Real (catálogo + datasheets)"
```
Tener abiertos en pestañas: `evaluation/report.md`, `cost/emerson_advisor_tco.xlsx` y el run de `run_all` en Databricks.
Búsqueda: con red, arrancar con `ADVISOR_RETRIEVAL_BACKEND=hybrid ADVISOR_DATABRICKS_PROFILE=lmrcolin make app`
(BM25 + AI Search); sin red, `make app` (BM25). Si AI Search falla en vivo, la app sigue con BM25 y lo avisa.
LLM: `template` por defecto (determinista, sin red). Si Llama/FMAPI está verificado en FEATURE_MATRIX, se puede
mostrar con `ADVISOR_LLM_PROVIDERS=databricks,template` — **no** es necesario para la demo.

## Guion

| Min | Qué se muestra | Qué se dice (frases clave) |
|---|---|---|
| 0:00–0:45 | Título y una diapositiva del problema | "Cuando una pieza industrial se descontinúa, encontrar un sustituto depende de expertos. Emerson quiere mover 4 M USD/año de inventario: necesita recomendar sustitutos **vendibles** y **justificados**." |
| 0:45–1:30 | Arquitectura (diagrama de `README.md`) | "Leemos 33 PDFs: catálogo + 32 datasheets. Extraemos specs con cita literal, construimos un grafo y un motor de reglas **determinista**. El LLM solo interpreta la consulta y redacta; nunca decide compatibilidad." |
| 1:30–3:30 | App → ejemplo **Caso oficial (Intel E810)** | Señalar: ficha **E810-CQDA2 DISCONTINUED** desde 2025-08-01. "Su propio datasheet recomienda ConnectX-7 o BCM57508." Abrir la tarjeta 1: **MCX75310AAS-NEAT, 1,250.00 USD, 120 u.**, *compatible con condiciones*: 400 GbE (ópticas/switch o breakout), PCIe 5.0 retrocompatible. Abrir **Comparación de especificaciones** y **Evidencia** (archivo y página). "El precio y el stock salen del catálogo, no del datasheet." Mencionar que la E810 **no** declara IPsec: el requisito viene del cliente. |
| 3:30–4:15 | Ejemplo **DAQ descontinuada** (USB-2627) | "Única sustituta: USB-2633, la que indica el propio datasheet; las otras DAQ no llegan a 64 entradas." |
| 4:15–5:00 | Ejemplo **GPU NRND (A100)** | "El datasheet llama sucesor al H100, pero el SKU del catálogo es SXM5 frente a SXM4: no es un reemplazo directo y el sistema lo explica en lugar de recomendarlo." |
| 4:45–5:00 | Consulta libre: *"sensor para medir humedad y gases volátiles en interiores"* | "Sin part number y en español: la búsqueda híbrida con el índice vectorial de Databricks encuentra la ficha del BME680, escrita en inglés." |
| 5:00–5:30 | Ejemplos **Part number con errata** y **Consulta vaga** | "Si no está seguro, pregunta: '¿Te refieres a E810-CQDA2?'. Nunca adivina una pieza parecida." |
| 5:30–6:30 | `evaluation/report.md` | "22 casos verificados contra los PDFs; puertas de seguridad en 0: ninguna recomendación no vendible, ningún precio distinto del catálogo, ninguna cifra inventada. Es un conjunto pequeño y propio: lo decimos en el informe." |
| 6:30–7:15 | Databricks: run `run_all` + tablas `emerson_hw.*` | "Todo se recrea con `databricks bundle run run_all`: bronze con `ai_parse_document`, silver/gold, grafo y matriz. Encontramos que `ai_parse_document` leyó mal un part number del catálogo; por eso el catálogo se lee con un parser determinista (ADR-012)." |
| 7:15–8:00 | `cost/emerson_advisor_tco.xlsx` (hoja TCO_anual) | "TCO año 1 ≈ 14.4 k USD con supuestos editables (amarillo); los precios de plataforma están marcados POR CONFIRMAR. Frente a 4 M USD/año de inventario, el costo es < 0.5 %." |

## Plan B (sin red / sin Databricks)
- La app funciona sin red: LLM `template` + `artifacts/` locales (`make pipeline-local`).
- Si falla la app: `make eval` en terminal muestra los mismos casos con métricas.
- Si falla Databricks en vivo: mostrar capturas del último run y `docs/FEATURE_MATRIX.md`.
- Si falla todo lo anterior: `uv run pytest tests/data/test_agent.py -q` demuestra el caso oficial de punta a punta.

## Preguntas probables
- *¿Y si el LLM inventa?* — No decide nada; la NLU se sanea (claves del registro, cifras de la consulta) y VERIFY rechaza
  cifras o part numbers que no estén en el borrador (tests con LLM falsos que inventan).
- *¿Cómo escala a un catálogo real?* — Registro de specs por categoría en YAML, reglas en YAML, pipeline idempotente en
  Databricks; la matriz se precalcula.
- *¿Por qué no recomienda nada para MPU-6050?* — El único sensor ACTIVE (BME680) no mide giroscopio ni acelerómetro.
