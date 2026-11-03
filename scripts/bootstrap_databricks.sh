#!/usr/bin/env bash
# Create UC objects, upload PDFs and import notebooks into Databricks Free Edition.
# Requires: databricks CLI authenticated via `databricks auth login --profile <name>`.
# Usage: scripts/bootstrap_databricks.sh --profile emerson [--warehouse-id ID] [--dry-run]
set -euo pipefail

PROFILE="" WAREHOUSE_ID="${ADVISOR_DATABRICKS_WAREHOUSE_ID:-}" DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --warehouse-id) WAREHOUSE_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$PROFILE" ]] || { echo "--profile is required" >&2; exit 2; }
command -v databricks >/dev/null || { echo "databricks CLI not found" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VOLUME="dbfs:/Volumes/datathon/emerson/raw/pdfs"
run() { echo "+ $*"; [[ $DRY_RUN -eq 1 ]] || "$@"; }

run databricks current-user me --profile "$PROFILE" >/dev/null

# 1. DDL (idempotent) through the SQL warehouse.
if [[ -n "$WAREHOUSE_ID" ]]; then
  grep -v '^--' "$ROOT/scripts/sql/00_bootstrap.sql" | tr '\n' ' ' | tr ';' '\n' | while read -r stmt; do
    [[ -z "${stmt// }" || "$stmt" == LIST* ]] && continue
    run databricks api post /api/2.0/sql/statements --profile "$PROFILE" \
      --json "{\"warehouse_id\":\"$WAREHOUSE_ID\",\"statement\":\"$stmt\",\"wait_timeout\":\"30s\"}"
  done
else
  echo "No --warehouse-id: run notebooks/00_bootstrap.sql in the workspace instead."
fi

# 2. Upload source PDFs (never modified).
run databricks fs mkdir "$VOLUME" --profile "$PROFILE"
run databricks fs cp -r --overwrite "$ROOT/datos/pdfs" "$VOLUME" --profile "$PROFILE"

# 3. Import notebooks.
USER_NAME="$(databricks current-user me --profile "$PROFILE" --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)["userName"])')"
run databricks workspace import-dir "$ROOT/notebooks" "/Workspace/Users/$USER_NAME/emerson-advisor/notebooks" --overwrite --profile "$PROFILE"

echo "Done. Next: run notebooks 01–07 in order (see scripts/smoke_tests.md)."
