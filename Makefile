UV ?= uv
PROFILE ?= emerson

.PHONY: help setup install check lint format imports typecheck test test-contracts pipeline-local eval eval-blind eval-databricks app app-databricks excel clean

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Create .venv (Python 3.12), install deps and git hooks
	$(UV) sync
	$(UV) run pre-commit install

install: setup ## Alias of setup

check: lint imports test ## Lint + dependency contracts + tests (stubs xfail)

lint: ## Ruff lint + format check + mypy strict
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy src

format: ## Auto-format and fix lint
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

imports: ## import-linter dependency direction
	$(UV) run lint-imports

typecheck: ## mypy strict on src
	$(UV) run mypy src

test: ## All tests
	$(UV) run pytest

test-contracts: ## Contract tests only
	$(UV) run pytest tests/contracts

pipeline-local: ## Build artifacts/ from data/raw (products, chunks, graph, compat matrix)
	$(UV) run advisor-pipeline

eval: ## Run evaluation over evaluation/gold_set.yaml
	$(UV) run python -m evaluation.run_eval

eval-blind: ## Run evaluation over the blind set (evaluation/blind_set.yaml)
	$(UV) run python -m evaluation.run_eval --gold evaluation/blind_set.yaml

app: ## Streamlit chat UI over the real agent (artifacts/ or in-memory build)
	$(UV) run streamlit run app/streamlit_app.py

DATABRICKS_ENV = ADVISOR_DATABRICKS_PROFILE=$(PROFILE) ADVISOR_REPOSITORY_BACKEND=databricks_sql \
	ADVISOR_RETRIEVAL_BACKEND=hybrid ADVISOR_LLM_PROVIDERS=databricks,template

app-databricks: ## Chat UI fully on Databricks: Delta tables, AI Search, Llama (PROFILE=lmrcolin)
	$(DATABRICKS_ENV) $(UV) run streamlit run app/streamlit_app.py

eval-databricks: ## Evaluation fully on Databricks (Delta + hybrid search + Llama), no report rewrite
	$(DATABRICKS_ENV) $(UV) run python -m evaluation.run_eval --retriever hybrid --llm configured --no-report

excel: ## Build TCO workbook into cost/
	$(UV) run python scripts/build_tco_excel.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
