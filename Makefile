UV ?= uv

.PHONY: help install install-spark install-mlops test test-unit cov lint format typecheck app clean

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

install: ## Create venv (Python 3.12) with core, dev and app deps
	$(UV) sync --extra app

install-spark: ## Add local PySpark + Delta (needs Java 17/21)
	$(UV) sync --extra app --extra spark

install-mlops: ## Add MLflow for local evaluation tracking
	$(UV) sync --extra app --extra mlops

test: ## Run all tests
	$(UV) run pytest

test-unit: ## Run unit tests only
	$(UV) run pytest tests/unit

cov: ## Tests with coverage report
	$(UV) run pytest --cov=emerson_agent --cov-report=term-missing

lint: ## Ruff lint + mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy src

format: ## Auto-format and fix lint
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: ## mypy only
	$(UV) run mypy src

app: ## Launch Streamlit UI
	$(UV) run streamlit run app/streamlit_app.py

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
