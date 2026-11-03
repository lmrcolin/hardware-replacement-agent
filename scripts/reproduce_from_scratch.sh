#!/usr/bin/env bash
# Rebuild everything from a clean clone. Only manual step: `databricks auth login`.
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

command -v uv >/dev/null || { echo "install uv first: pipx install uv" >&2; exit 1; }
[[ "$(ls data/raw/*.pdf | wc -l)" -eq 33 ]] || { echo "expected 33 PDFs in data/raw" >&2; exit 1; }

make setup
make check

if [[ $LOCAL_ONLY -eq 0 ]]; then
  command -v databricks >/dev/null || { echo "databricks CLI not found" >&2; exit 1; }
  databricks bundle validate "${PROFILE_ARGS[@]}"
  databricks bundle deploy -t dev "${PROFILE_ARGS[@]}"
  databricks bundle run run_all -t dev "${PROFILE_ARGS[@]}"   # 00_setup + 01_parse (+ later steps)
fi

make pipeline-local   # TODO(B-10): builds artifacts/ once the pipeline steps are implemented
make eval
echo "Reproduction finished. Launch the demo with: make app"
