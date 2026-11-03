#!/usr/bin/env bash
# Rebuild everything from a clean clone. Only manual step: `databricks auth login --profile <name>`.
# Usage: scripts/reproduce_from_scratch.sh [--profile emerson] [--local-only]
set -euo pipefail

PROFILE="emerson" LOCAL_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --local-only) LOCAL_ONLY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "install uv first: pipx install uv" >&2; exit 1; }
[[ "$(ls datos/pdfs/*.pdf | wc -l)" -eq 33 ]] || { echo "expected 33 PDFs in datos/pdfs" >&2; exit 1; }

make setup
make check

if [[ $LOCAL_ONLY -eq 0 ]]; then
  scripts/bootstrap_databricks.sh --profile "$PROFILE"
  # TODO(B-24): trigger notebooks 01–07 as a job (databricks jobs submit) and wait.
fi

make pipeline-local   # TODO(B-10): builds artifacts/ once the pipeline steps are implemented
make eval
echo "Reproduction finished. Launch the demo with: make app"
