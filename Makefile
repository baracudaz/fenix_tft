.DEFAULT_GOAL := help
HA_URL := http://localhost:8123

# Cross-platform browser open command
UNAME := $(shell uname -s)
ifeq ($(UNAME),Darwin)
  OPEN_CMD := open
else ifeq ($(UNAME),Linux)
  OPEN_CMD := xdg-open
else
  OPEN_CMD := start
endif

.PHONY: help setup develop open lint test translations clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' | \
		sort

setup: ## Install all dependencies into .venv using uv
	uv sync --all-extras

develop: ## Start Home Assistant dev server and open browser
	@echo "Starting Home Assistant at $(HA_URL) ..."
	@(sleep 5 && $(OPEN_CMD) "$(HA_URL)") &
	scripts/develop

open: ## Open Home Assistant in browser (if already running)
	$(OPEN_CMD) "$(HA_URL)"

lint: ## Format and lint source code
	scripts/lint

test: ## Run all tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=custom_components/fenix_tft --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

translations: ## Sync translations from strings.json to all language files
	scripts/translations.py

clean: ## Remove Python cache files and coverage artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml .pytest_cache
