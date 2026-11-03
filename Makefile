UV ?= uv
PROFILE ?= emerson

.PHONY: help setup check lint imports typecheck test test-contracts pipeline-local eval app excel clean

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Create .venv (Python 3.12), install deps and git hooks
	$(UV) sync
	$(UV) run pre-commit install

check: lint imports test ## Lint + dependency contracts + tests (stubs xfail)

lint: ## Ruff lint and format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

imports: ## import-linter dependency direction
	$(UV) run lint-imports

typecheck: ## mypy strict on src
	$(UV) run mypy src

test: ## All tests
	$(UV) run pytest

test-contracts: ## Contract tests only
	$(UV) run pytest tests/contracts

pipeline-local: ## Build artifacts locally from datos/pdfs (stubs until implemented)
	$(UV) run advisor-pipeline

eval: ## Run evaluation over evaluation/gold_set.yaml
	$(UV) run python evaluation/run_eval.py

app: ## Streamlit UI (uses MockAdvisorAgent until the agent exists)
	$(UV) run streamlit run app/streamlit_app.py

excel: ## Build TCO workbook into cost/
	$(UV) run python scripts/build_tco_excel.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
