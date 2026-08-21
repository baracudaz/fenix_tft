.PHONY: help install develop lint test translations docker-up docker-down docker-logs docker-restart clean

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
	@echo "  docker-up        Start Home Assistant in Docker, then follow logs"
	@echo "  docker-down      Stop and remove the Docker container"
	@echo "  docker-logs      Follow Home Assistant container logs"
	@echo "  docker-restart   Restart the container, then follow recent logs"
	@echo ""
	@echo "Quality:"
	@echo "  lint             Format and lint code with ruff (auto-fix)"
	@echo "  test             Run test suite"
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

lint:
	$(RUFF) format .
	$(RUFF) check . --fix

test:
	$(PYTEST) tests/ -v

translations: ## Check translation files against translations/en.json
	$(VENV_PYTHON) scripts/translations.py

docker-up: ## Start Home Assistant container (see docker-compose.yml), then follow logs
	$(DOCKER_COMPOSE) up -d $(HA_SERVICE)
	$(DOCKER_COMPOSE) logs -f $(HA_SERVICE)

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f $(HA_SERVICE)

docker-restart:
	$(DOCKER_COMPOSE) restart $(HA_SERVICE)
	$(DOCKER_COMPOSE) logs -f -n 10 $(HA_SERVICE)

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
