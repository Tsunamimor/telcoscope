# telcoscope — convenience targets
# All commands run from the project root.

SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker/docker-compose.yml --env-file .env

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: up
up:  ## Bring up the Docker stack (postgres, grafana, adminer)
	$(COMPOSE) up -d
	@echo ""
	@echo "Services starting. Once ready:"
	@echo "  Grafana:  http://localhost:$${GRAFANA_PORT:-3000}  (admin / admin)"
	@echo "  Adminer:  http://localhost:$${ADMINER_PORT:-8080}"
	@echo "  Postgres: localhost:$${POSTGRES_PORT:-5432}"

.PHONY: down
down:  ## Stop the stack (keeps volumes)
	$(COMPOSE) down

.PHONY: destroy
destroy:  ## Stop the stack AND delete all volumes (full reset)
	$(COMPOSE) down -v

.PHONY: ps
ps:  ## Show running containers
	$(COMPOSE) ps

.PHONY: logs
logs:  ## Tail logs from all services
	$(COMPOSE) logs -f

.PHONY: install
install:  ## Install Python dependencies (uv preferred, falls back to pip)
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	else \
		pip install -e ".[dev]"; \
	fi

.PHONY: seed
seed:  ## Generate synthetic data and load into Postgres
	python -m telcoscope.synth.generator

.PHONY: dbt
dbt:  ## Run dbt build (deps, run, test)
	cd dbt && dbt deps && dbt build

.PHONY: dbt-docs
dbt-docs:  ## Generate and serve dbt docs
	cd dbt && dbt docs generate && dbt docs serve

.PHONY: app
app:  ## Run the Streamlit incident inspector
	streamlit run apps/streamlit/app.py

.PHONY: api
api:  ## Run the FastAPI service
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: test
test:  ## Run pytest
	pytest -v

.PHONY: lint
lint:  ## Run ruff + mypy
	ruff check src tests apps
	mypy src

.PHONY: format
format:  ## Run ruff formatter + black
	ruff format src tests apps
	ruff check --fix src tests apps

.PHONY: precommit
precommit:  ## Run pre-commit on all files
	pre-commit run --all-files

.PHONY: clean
clean:  ## Remove Python build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	rm -rf dbt/target dbt/logs dbt/dbt_packages
