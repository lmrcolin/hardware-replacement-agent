#!/usr/bin/env bash
# Rebuild everything from a clean clone. Only manual step: `databricks auth login` (Databricks part).
# Usage: scripts/reproduce_from_scratch.sh [--profile NAME] [--local-only]
set -euo pipefail

PROFILE_ARGS=() LOCAL_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE_ARGS=(--profile "$2"); shift 2 ;;
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
  databricks bundle run run_all -t dev "${PROFILE_ARGS[@]}"
  # TODO(K10): verificar conteos (bronze.documents_parsed = 33, gold.products = 32) y copiar artefactos del volumen.
fi

step "Listo"
echo "Demo: make app  (http://localhost:8501)"
