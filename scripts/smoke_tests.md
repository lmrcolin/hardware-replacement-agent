# Smoke tests (antes de merge a `main` y antes de la demo)

| # | Check | Comando / acción | Esperado | OK |
|---|---|---|---|---|
| 1 | Entorno | `make setup && make check` | contratos verdes, solo xfail de stubs pendientes | ☐ |
| 2 | Datos locales | `ls datos/pdfs/*.pdf \| wc -l` | 33 | ☐ |
| 3 | Bootstrap Databricks | `scripts/bootstrap_databricks.sh --profile emerson --dry-run` y luego sin `--dry-run` | volumen con 33 PDFs | ☐ |
| 4 | Parse | notebook 02 (LIMIT 1) | salida de `ai_parse_document` no nula | ☐ |
| 5 | Catálogo | `SELECT status, count(*) FROM datathon.emerson.silver_commercial GROUP BY 1` | ACTIVE 21 · DISCONTINUED 6 · EOL 2 · NRND 3 | ☐ |
| 6 | KG | `artifacts/graph.json` existe; nodos `product:*` = 32 | ☐ |
| 7 | Caso oficial | app: consulta E810 (RDMA + IPsec) | E810-CQDA2 DISCONTINUED + sustituto ACTIVE con precio y stock del catálogo | ☐ |
| 8 | Aclaración | app: "Necesito un reemplazo" | pregunta de aclaración | ☐ |
| 9 | Invariantes | revisar respuesta | ningún no-ACTIVE recomendado; ningún precio en no-ACTIVE | ☐ |
| 10 | Sin red LLM | `ADVISOR_LLM_PROVIDERS=template make app` | respuesta por plantilla | ☐ |
| 11 | Secretos | `uv run pre-commit run gitleaks --all-files` | 0 hallazgos | ☐ |
| 12 | Excel | `make excel` | `cost/emerson_advisor_tco.xlsx` con 4 hojas | ☐ |
