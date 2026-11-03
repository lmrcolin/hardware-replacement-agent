# Databricks notebook source
# MAGIC %md
# MAGIC # 90 · env_check
# MAGIC Verifica en serverless (K2) que `advisor` funciona: Python >= 3.12, dependencias con `%pip`,
# MAGIC el paquete como wheel desde el volumen `bronze.libs` (importar desde `/Workspace` por FUSE
# MAGIC falla con Errno 5) y el catálogo leído con `parse_catalog` (capa de texto, ADR-012).
# MAGIC **No entra al job `run_all`.** Resultado: `dbutils.notebook.exit(JSON)`
# MAGIC (léelo con `databricks jobs get-run-output`).

# COMMAND ----------

# MAGIC %pip install "pydantic>=2.9" "networkx>=3.3" pdfplumber pymupdf rapidfuzz rank-bm25 pyyaml python-dotenv httpx
# MAGIC %pip install --no-deps /Volumes/emerson_hw/bronze/libs/emerson_advisor-0.1.0-py3-none-any.whl

# COMMAND ----------

# ruff: noqa: F821, E402, E501  (dbutils lo inyecta Databricks; imports tras reiniciar Python)
dbutils.library.restartPython()

# COMMAND ----------

import importlib.metadata as md
import json
import sys
import time
import traceback
from pathlib import Path

dbutils.widgets.text("catalog", "emerson_hw")
CATALOG = dbutils.widgets.get("catalog")
RAW = Path(f"/Volumes/{CATALOG}/bronze/raw_files")
LIBS = Path(f"/Volumes/{CATALOG}/bronze/libs")
EXPECTED_ROWS = 32
TRICKY_PART = "H9HCNNNCPMML"  # ai_parse_document lo leyó como H9HCNNCPMML (ADR-012)

checks: dict[str, dict[str, object]] = {}


def check(name: str):  # type: ignore[no-untyped-def]
    """Run fn, record OK/FAIL with detail and duration; never stop the notebook."""

    def wrap(fn):  # type: ignore[no-untyped-def]
        start = time.time()
        try:
            checks[name] = {"ok": True, "detail": fn()}
        except Exception as exc:  # every failure goes to the report
            checks[name] = {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-1500:],
            }
        checks[name]["seconds"] = round(time.time() - start, 1)
        print(name, checks[name])
        return fn

    return wrap


# COMMAND ----------


@check("python_312")
def _python() -> str:
    assert sys.version_info >= (3, 12), f"Python {sys.version.split()[0]} < 3.12"
    return sys.version.split()[0]


@check("versions")
def _versions() -> dict[str, str]:
    pkgs = ["emerson-advisor", "pydantic", "networkx", "pdfplumber", "pymupdf", "rapidfuzz"]
    return {p: md.version(p) for p in pkgs}


@check("import_advisor")
def _imports() -> str:
    import advisor
    from advisor.pipeline import build_in_memory  # noqa: F401  (arrastra agent/llm/retrieval)

    return str(Path(advisor.__file__).parent)


@check("spec_registry_from_volume")
def _registry() -> int:
    from advisor.extraction import load_spec_registry

    return len(load_spec_registry(LIBS / "spec_registry.yaml").categories)


@check("parse_catalog_from_volume")
def _catalog() -> dict[str, object]:
    from collections import Counter

    from advisor.ingestion import discover_documents
    from advisor.models import DocumentType
    from advisor.parsing import parse_catalog

    record = next(r for r in discover_documents(RAW) if r.doc_type is DocumentType.CATALOG)
    rows = parse_catalog(record)
    parts = {r.part_number for r in rows}
    assert len(rows) == EXPECTED_ROWS, f"{len(rows)} filas, se esperaban {EXPECTED_ROWS}"
    assert TRICKY_PART in parts, f"falta {TRICKY_PART}"
    return {"rows": len(rows), "statuses": dict(Counter(str(r.status) for r in rows))}


@check("build_in_memory_from_volume")
def _build() -> dict[str, int]:
    from advisor.config import Settings
    from advisor.pipeline import build_in_memory

    settings = Settings.model_validate(
        {
            "paths": {
                "pdf_dir": str(RAW),
                "spec_registry": str(LIBS / "spec_registry.yaml"),
                "compat_rules": str(LIBS / "compat_rules.yaml"),
            }
        }
    )
    built = build_in_memory(settings)
    return {
        "products": len(built.products),
        "chunks": len(built.chunks),
        "graph_nodes": built.graph.number_of_nodes(),
        "graph_edges": built.graph.number_of_edges(),
    }


# COMMAND ----------

summary = {"all_ok": all(c["ok"] for c in checks.values()), "checks": checks}
print(json.dumps(summary, indent=1, default=str))
dbutils.notebook.exit(json.dumps(summary, default=str))
