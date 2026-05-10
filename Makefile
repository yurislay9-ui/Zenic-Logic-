# TITAN OMNISCALE X — Makefile
# Quick commands for development, testing, and deployment on Termux/Debian

PYTHON ?= python3
PORT ?= 5001
HOST ?= 0.0.0.0

.PHONY: help install test lint run run-fastapi clean status

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PYTHON) -m pip install -e ".[dev]" 2>/dev/null || \
		$(PYTHON) -m pip install pytest pytest-asyncio pytest-cov ruff
	$(PYTHON) -m pip install -r requirements.txt 2>/dev/null || true

test: ## Run unit tests (fast)
	$(PYTHON) -m pytest tests/unit/ -x --tb=short -q \
		--ignore=tests/unit/test_dag_orchestrator.py \
		--ignore=tests/unit/test_titan_orchestrator.py

test-all: ## Run all tests including integration
	$(PYTHON) -m pytest tests/ -x --tb=short -q

test-coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/unit/ --cov=src --cov-report=term-missing -q \
		--ignore=tests/unit/test_dag_orchestrator.py \
		--ignore=tests/unit/test_titan_orchestrator.py

lint: ## Run linter (ruff)
	$(PYTHON) -m ruff check src/ --ignore E501,F401,F811 --statistics || true

typecheck: ## Run type checker (mypy)
	$(PYTHON) -m mypy src/ --ignore-missing-imports --no-error-summary || true

import-check: ## Verify critical imports work
	@$(PYTHON) -c "from src.core.shared import ResponseSynthesizer, ConversationState, resolve_references, TITAN_VERSION; print(f'OK: shared v{TITAN_VERSION}')"
	@$(PYTHON) -c "from src.core.dag_parts import DAGOrchestrator, PIPELINE_DAG; print(f'OK: DAG {len(PIPELINE_DAG)} nodes')"
	@$(PYTHON) -c "from src.core.orchestrator_base import BaseOrchestrator; print('OK: BaseOrchestrator')"

run: ## Start headless server (stdlib, port 5001)
	$(PYTHON) main_headless.py --port $(PORT) --host $(HOST)

run-fastapi: ## Start FastAPI server (SaaS mode)
	$(PYTHON) main_headless.py --server fastapi --port $(PORT) --host $(HOST)

run-debug: ## Start server with debug logging
	$(PYTHON) main_headless.py --port $(PORT) --debug

clean: ## Clean cache and temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f .coverage

status: ## Quick project status
	@echo "=== TITAN OMNISCALE X ==="
	@$(PYTHON) -c "from src.core.shared._version import TITAN_VERSION_STR; print(f'Version: {TITAN_VERSION_STR}')"
	@echo "Python: $$($(PYTHON) --version 2>&1)"
	@echo "Tests: $$(find tests/ -name 'test_*.py' | wc -l) files"
	@echo "Source: $$(find src/ -name '*.py' | wc -l) files"
	@git log --oneline -5 2>/dev/null || echo "Not a git repo"
