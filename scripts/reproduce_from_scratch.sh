#!/usr/bin/env bash
# Rebuild everything from a clean clone. Only manual step: `databricks auth login` (Databricks part).
# Usage: scripts/reproduce_from_scratch.sh [--profile NAME] [--local-only] [--pull-artifacts]
#   --pull-artifacts  al final, reemplaza ./artifacts con los que exportó el job en Databricks.
set -euo pipefail

PROFILE_ARGS=() PROFILE="" LOCAL_ONLY=0 PULL_ARTIFACTS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; PROFILE_ARGS=(--profile "$2"); shift 2 ;;
    --pull-artifacts) PULL_ARTIFACTS=1; shift ;;
    --local-only) LOCAL_ONLY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$0")/.."
step() { printf '\n==> %s\n' "$*"; }

# ---------------------------------------------------------------- LOCAL (L6)
command -v uv >/dev/null || { echo "install uv first: pipx install uv" >&2; exit 1; }
[[ "$(ls data/raw/*.pdf | wc -l)" -eq 33 ]] || { echo "expected 33 PDFs in data/raw" >&2; exit 1; }

step "Entorno y verificación (ruff, mypy, import-linter, tests)"
make setup
make check

step "Artefactos locales (productos, chunks, grafo, matriz de compatibilidad)"
make pipeline-local
for f in products.parquet chunks.parquet compat_matrix.parquet graph.json documents.json; do
  [[ -s "artifacts/$f" ]] || { echo "missing artifacts/$f" >&2; exit 1; }
done

step "Evaluación (falla si alguna puerta de seguridad > 0)"
make eval >/dev/null
grep -q "Puertas de seguridad:\*\* OK" evaluation/report.md || { echo "safety gates failed" >&2; exit 1; }

step "Excel de costos"
make excel

# ---------------------------------------------------------------- DATABRICKS (K10 — Kevin)
if [[ $LOCAL_ONLY -eq 0 ]]; then
  step "Databricks: bundle"
  command -v databricks >/dev/null || { echo "databricks CLI not found" >&2; exit 1; }
  databricks bundle validate "${PROFILE_ARGS[@]}"
  databricks bundle deploy -t dev "${PROFILE_ARGS[@]}"
  databricks bundle run run_all -t dev "${PROFILE_ARGS[@]}"   # 00 setup -> 06 export (~5 min)

  step "Databricks: verificar tablas (Statement Execution en el SQL warehouse)"
  WAREHOUSE="${ADVISOR_DATABRICKS_WAREHOUSE_ID:-$(databricks warehouses list "${PROFILE_ARGS[@]}"     | awk 'NR > 1 && $1 ~ /^[0-9a-f]+$/ {print $1; exit}')}"
  [[ -n "$WAREHOUSE" ]] || { echo "no SQL warehouse found (set ADVISOR_DATABRICKS_WAREHOUSE_ID)" >&2; exit 1; }
  CATALOG="${ADVISOR_DATABRICKS_CATALOG:-emerson_hw}" PROFILE="$PROFILE" WAREHOUSE="$WAREHOUSE"     uv run python - <<'PY'
import os
from advisor.repository import DatabricksSQLRepository

repo = DatabricksSQLRepository(os.environ["PROFILE"], os.environ["WAREHOUSE"], os.environ["CATALOG"])
expected = {
    "bronze.documents_parsed": 33, "silver.commercial": 32, "silver.product_specifications": 272,
    "gold.products": 32, "gold.document_chunks": 126, "gold.compat_matrix": 30,
    "gold.kg_nodes": 501, "gold.kg_edges": 586,
}
got = {t: int(repo.execute(f"SELECT count(*) FROM `{repo.catalog}`.{t}")[0][0]) for t in expected}
statuses = dict(repo.execute(f"SELECT status, count(*) FROM `{repo.catalog}`.silver.commercial GROUP BY 1"))
bad = {t: (got[t], n) for t, n in expected.items() if got[t] != n}
if statuses != {"ACTIVE": "21", "DISCONTINUED": "6", "EOL": "2", "NRND": "3"}:
    bad["silver.commercial.status"] = statuses
for table, count in got.items():
    print(f"  {table:<32} {count}")
if bad:
    raise SystemExit(f"conteos inesperados (obtenido, esperado): {bad}")
PY

  if [[ $PULL_ARTIFACTS -eq 1 ]]; then
    step "Databricks: copiar artefactos del volumen a ./artifacts"
    tmp="$(mktemp -d)"
    databricks fs cp -r "dbfs:/Volumes/${ADVISOR_DATABRICKS_CATALOG:-emerson_hw}/gold/artifacts" "$tmp"       "${PROFILE_ARGS[@]}" >/dev/null
    for f in products.parquet chunks.parquet compat_matrix.parquet graph.json documents.json; do
      cp "$tmp/$f" "artifacts/$f"
    done
    rm -rf "$tmp"
  fi
fi

step "Listo"
echo "Demo: make app  (http://localhost:8501)"
