# Tech Stack and Setup

| Capa | Tecnología |
|---|---|
| Lenguaje / entorno | Python 3.12, uv (Arch Linux) |
| Datos | Databricks Free Edition, Unity Catalog, Delta, `ai_parse_document`, `read_files` |
| PDF local | pdfplumber, PyMuPDF |
| Grafo | NetworkX |
| Búsqueda | rank-bm25, sentence-transformers (torch CPU), FAISS; AI Search opcional |
| Matching | rapidfuzz |
| LLM | Llama 3.3 70B (FMAPI) → Ollama qwen3:4b → plantillas |
| UI | Streamlit |
| Costes | openpyxl |
| Calidad | pytest, ruff, mypy, import-linter, pre-commit, gitleaks |

## Setup local
```bash
pipx install uv           # o: sudo pacman -S uv
make setup                # .venv + dependencias + hooks
cp .env.example .env
make check
make app
```

## Databricks
```bash
databricks auth login --host https://<workspace>.cloud.databricks.com
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run run_all -t dev      # 00_setup + 01_parse
```
Nunca pegar tokens en el repo ni en el chat.
