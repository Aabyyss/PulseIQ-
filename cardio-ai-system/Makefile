# PulseIQ — task runner (make test / make run-backend / make run-frontend / ...)
#
# Windows notes:
#   - `make` is not in Git Bash by default. Options:
#       1) Use the bundled PowerShell launchers: .\setup.ps1 / .\run-backend.ps1 /
#          .\run-frontend.ps1 / Start-PulseIQ.cmd   (primary Windows path, ADR-008)
#       2) Install make (e.g. `winget install GnuWin32.Make` or choco install make)
#       3) Run under WSL
#   - Venv path below assumes Windows (.venv/Scripts). Under WSL/Linux make
#     will use .venv/bin — override: `make PY=.venv/bin/python <target>`

PY     := .venv/Scripts/python.exe
PIP    := $(PY) -m pip
FE     := frontend
PORT_B := 8000
PORT_F := 5173

.DEFAULT_GOAL := help
.PHONY: help setup install-backend install-frontend train run-backend run-frontend \
        test test-backend typecheck build ui-audit check docker-up docker-down clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: install-backend install-frontend ## One-time: venv + deps + spaCy model + frontend deps
	@echo "Setup complete. Next: make run-backend && make run-frontend"

install-backend: ## Create venv, install Python deps + spaCy model
	python -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	-$(PY) -m spacy download en_core_web_sm

install-frontend: ## npm install for the frontend
	cd $(FE) && npm install

train: ## Retrain the model from data/heart.csv (flips labels + asserts direction)
	$(PY) backend/train_model.py

run-backend: ## Start FastAPI on :8000
	$(PY) -m uvicorn backend.api_server:app --reload --port $(PORT_B)

run-frontend: ## Start Vite dev server on :5173
	cd $(FE) && npm run dev

test-backend: ## Backend pipeline tests (pytest)
	$(PY) -m pytest backend -q

test: test-backend typecheck ## Backend tests + frontend typecheck

typecheck: ## TypeScript check (tsc --noEmit)
	cd $(FE) && npm run typecheck

build: ## Production frontend build (tsc -b && vite build)
	cd $(FE) && npm run build

ui-audit: ## WCAG contrast/layout sweep across routes and viewports
	cd $(FE) && npm run ui-audit

check: test build ## Full local gate: tests + typecheck + build

docker-up: ## Optional parity env: backend in Linux containers (bypasses WDAC blocks)
	docker compose up --build

docker-down: ## Stop the compose stack
	docker compose down

clean: ## Remove caches and build output (keeps venv/node_modules)
	rm -rf backend/__pycache__ agents/__pycache__ .pytest_cache $(FE)/dist
