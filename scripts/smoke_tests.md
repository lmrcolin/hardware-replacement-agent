# Smoke tests (antes de merge a `main` y antes de la demo)

| # | Check | Comando / acción | Esperado | OK |
|---|---|---|---|---|
| 1 | Entorno | `make setup && make check` | contratos verdes, solo xfail de stubs pendientes | ☐ |
| 2 | Datos locales | `ls data/raw/*.pdf \| wc -l` | 33 | ☐ |
| 3 | Bundle | `databricks bundle validate && databricks bundle deploy -t dev && databricks bundle run run_all -t dev` | job `run_all` OK | ☐ |
| 4 | Parse | `SELECT count(*) FROM emerson_hw.bronze.documents_parsed` | 33 | ☐ |
| 5 | Catálogo | `SELECT status, count(*) FROM emerson_hw.silver.commercial GROUP BY 1` | ACTIVE 21 · DISCONTINUED 6 · EOL 2 · NRND 3 | ☐ |
| 6 | KG | `artifacts/graph.json` existe; nodos `product:*` = 32 | ☐ |
| 7 | Caso oficial | app: consulta E810 (RDMA + IPsec) | E810-CQDA2 DISCONTINUED + sustituto ACTIVE con precio y stock del catálogo | ☐ |
| 8 | Aclaración | app: "Necesito un reemplazo" | pregunta de aclaración | ☐ |
| 9 | Invariantes | revisar respuesta | ningún no-ACTIVE recomendado; ningún precio en no-ACTIVE | ☐ |
| 10 | Sin red LLM | `ADVISOR_LLM_PROVIDERS=template make app` | respuesta por plantilla | ☐ |
| 11 | Secretos | `uv run pre-commit run gitleaks --all-files` | 0 hallazgos | ☐ |
| 12 | Excel | `make excel` | `cost/emerson_advisor_tco.xlsx` con 4 hojas | ☐ |
