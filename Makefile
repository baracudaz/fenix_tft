.PHONY: help install format lint check test test-cov dev develop open translations docker-up docker-down docker-logs docker-shell docker-restart clean

.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

HA_URL := http://localhost:8123

VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
VENV_HASS := $(VENV)/bin/hass
PYTEST ?= $(VENV_PYTHON) -m pytest
RUFF ?= $(VENV_PYTHON) -m ruff
DOCKER_COMPOSE ?= docker compose
HA_SERVICE ?= homeassistant

# Cross-platform browser open command
UNAME := $(shell uname -s)
ifeq ($(UNAME),Darwin)
  OPEN_CMD := open
else ifeq ($(UNAME),Linux)
  OPEN_CMD := xdg-open
else
  OPEN_CMD := start
endif

help:
	@echo "Fenix TFT - development commands"
	@echo ""
	@echo "Setup:"
	@echo "  install          Create .venv and install Python dependencies"
	@echo ""
	@echo "Run:"
	@echo "  develop          Start HA dev server from .venv, opens $(HA_URL)"
	@echo "  open             Open browser (if HA is already running)"
	@echo "  docker-up        Start Home Assistant in Docker via docker-compose"
	@echo "  docker-down      Stop and remove the Docker container"
	@echo "  docker-logs      Follow Home Assistant container logs"
	@echo "  docker-shell     Open a shell in the Home Assistant container"
	@echo "  docker-restart   Restart the Home Assistant container"
	@echo ""
	@echo "Quality:"
	@echo "  format           Format code with ruff"
	@echo "  lint             Format and lint code with ruff (auto-fix)"
	@echo "  check            Run formatting and lint checks (no auto-fix)"
	@echo "  test             Run test suite"
	@echo "  test-cov         Run test suite with HTML coverage report"
	@echo "  dev              Run format, lint and tests"
	@echo "  translations     Check translation files against translations/en.json"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean            Remove caches, coverage, and build artifacts"

install: ## Create .venv and install all dependencies (including test extras)
	set -e; \
	if [[ ! -d "$(VENV)" ]]; then \
		$(PYTHON) -m venv "$(VENV)"; \
	fi; \
	$(VENV_PYTHON) -m pip install --upgrade pip; \
	$(VENV_PYTHON) -m pip install --requirement requirements.txt --requirement requirements-test.txt

develop: ## Start Home Assistant dev server and open browser
	set -e; \
	if [[ ! -x "$(VENV_HASS)" ]]; then \
		echo "No virtualenv found at $(VENV). Run 'make install' first." >&2; \
		exit 1; \
	fi; \
	echo "Starting Home Assistant at $(HA_URL) ..."; \
	(sleep 5 && $(OPEN_CMD) "$(HA_URL)") & \
	if [[ ! -d "$${PWD}/config" ]]; then \
		mkdir -p "$${PWD}/config"; \
		"$(VENV_HASS)" --config "$${PWD}/config" --script ensure_config; \
	fi; \
	export PYTHONPATH="$${PYTHONPATH}:$${PWD}/custom_components"; \
	"$(VENV_HASS)" --config "$${PWD}/config" --debug

open: ## Open Home Assistant in browser (if already running)
	$(OPEN_CMD) "$(HA_URL)"

format:
	$(RUFF) format .

lint:
	$(RUFF) format .
	$(RUFF) check . --fix

check:
	$(RUFF) format --check .
	$(RUFF) check .

test:
	$(PYTEST) tests/ -v

test-cov:
	$(PYTEST) tests/ -v --cov=custom_components/fenix_tft --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

dev: format lint test

translations: ## Check translation files against translations/en.json
	$(VENV_PYTHON) scripts/translations.py

docker-up: ## Start Home Assistant container (see docker-compose.yml)
	$(DOCKER_COMPOSE) up -d $(HA_SERVICE)

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f $(HA_SERVICE)

docker-shell:
	$(DOCKER_COMPOSE) exec $(HA_SERVICE) /bin/sh

docker-restart:
	$(DOCKER_COMPOSE) restart $(HA_SERVICE)

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
