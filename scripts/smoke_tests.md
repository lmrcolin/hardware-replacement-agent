# Smoke tests (antes de merge a `main` y antes de la demo)

| # | Check | Comando / acción | Esperado | OK |
|---|---|---|---|---|
| 1 | Entorno y tests | `make setup && make check` | ruff, mypy, import-linter verdes; ≥214 tests, 0 fallos | ☐ |
| 2 | Datos locales | `ls data/raw/*.pdf \| wc -l` | 33 | ☐ |
| 3 | Artefactos | `make pipeline-local` | products 32 · chunks 126 · graph_nodes 501 · migrates_to 4 · compat_matrix_rows 30 | ☐ |
| 4 | Evaluación | `make eval` | termina con 0; todas las `gate_*` en 0 | ☐ |
| 5 | Excel | `make excel` | `cost/emerson_advisor_tco.xlsx` con hojas Supuestos, Desarrollo, Mantenimiento_1_anio, TCO_anual, Inventario | ☐ |
| 6 | Caso oficial | app → ejemplo "Caso oficial (Intel E810)" | E810-CQDA2 DISCONTINUED; 1. MCX75310AAS-NEAT (1,250.00 USD, 120) 2. BCM57508 (890.00 USD, 75), ambos con condiciones | ☐ |
| 7 | Errata | app → "Part number con errata" | pregunta "¿Te refieres a E810-CQDA2?" | ☐ |
| 8 | Sucesor bloqueado | app → "GPU NRND" | ningún sustituto; explica H100-SXM5 (form_factor) | ☐ |
| 9 | Invariantes | revisar respuestas | ningún no-ACTIVE en recomendados; ningún precio en no-ACTIVE | ☐ |
| 10 | Sin red | `ADVISOR_LLM_PROVIDERS=template make app` | "Redacción: template" | ☐ |
| 11 | Secretos | `uv run pre-commit run gitleaks --all-files` | 0 hallazgos | ☐ |
| 12 | Bundle | `databricks bundle validate && databricks bundle deploy -t dev && databricks bundle run run_all -t dev` | job `run_all` verde | ☐ |
| 13 | Bronze | `SELECT count(*) FROM emerson_hw.bronze.documents_parsed` | 33 | ☐ |
| 14 | Silver | `SELECT status, count(*) FROM emerson_hw.silver.commercial GROUP BY 1` | ACTIVE 21 · DISCONTINUED 6 · EOL 2 · NRND 3 | ☐ |
