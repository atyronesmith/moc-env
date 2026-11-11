SHELL := /bin/sh

.DEFAULT_GOAL := help

UV ?= uv
ENV ?= bu-ist-demo
FORMAT ?= text
ARGS ?=

# Set NO_PRS=1 to avoid pull-request API calls.
ifeq ($(NO_PRS),1)
PRS_FLAG := --no-prs
else
PRS_FLAG :=
endif

RUN_ARGS := $(ENV) --format $(FORMAT) $(PRS_FLAG) $(ARGS)

.PHONY: help setup sync test run run-text run-json run-markdown \
        run-no-prs build compile diff-check check lock clean clean-all

help: ## Show available targets and common variables
	@printf 'moc-env-status Makefile\n\n'
	@printf 'Usage:\n'
	@printf '  make <target> [ENV=bu-ist-demo] [FORMAT=text|json|markdown] [ARGS="..."]\n\n'
	@printf 'Targets:\n'
	@awk 'BEGIN { FS = ":.*##" } /^[a-zA-Z0-9_.%-]+:.*##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf '\nCommon variables:\n'
	@printf '  %-18s %s\n' 'ENV' 'Environment name passed to the CLI (default: bu-ist-demo)'
	@printf '  %-18s %s\n' 'FORMAT' 'Report format: text, json, or markdown (default: text)'
	@printf '  %-18s %s\n' 'NO_PRS' 'Set to 1 to add --no-prs'
	@printf '  %-18s %s\n' 'ARGS' 'Additional CLI arguments, quoted if needed'
	@printf '  %-18s %s\n' 'UV' 'uv executable (default: uv)'
	@printf '  %-18s %s\n' 'ENV_FILE' 'Not needed; the CLI reads .env by default'
	@printf '\nCredential variables are read directly by the CLI:\n'
	@printf '  GITHUB_TOKEN, GITHUB_BWS_SECRET_ID, GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE,\n'
	@printf '  GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT, BWS_ACCESS_TOKEN,\n'
	@printf '  BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE, BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT\n'

setup: ## Install the locked virtual environment
	$(UV) sync

sync: setup ## Alias for setup

test: ## Run the unit-test suite
	$(UV) run --locked python -m unittest discover -s tests -v

run: run-text ## Run the CLI (default ENV and text format)

run-text: ## Run the CLI with text output
	$(UV) run --locked moc-env-status $(RUN_ARGS)

run-json: ## Run the CLI with JSON output
	$(UV) run --locked moc-env-status $(ENV) --format json $(PRS_FLAG) $(ARGS)

run-markdown: ## Run the CLI with Markdown output
	$(UV) run --locked moc-env-status $(ENV) --format markdown $(PRS_FLAG) $(ARGS)

run-no-prs: ## Run the CLI without pull-request discovery
	$(UV) run --locked moc-env-status $(ENV) --format $(FORMAT) --no-prs $(ARGS)

build: ## Build source distribution and wheel
	$(UV) build

compile: ## Byte-compile source and tests
	$(UV) run --locked python -m compileall -q src tests

diff-check: ## Check the Git worktree diff for whitespace errors
	git diff --check

check: test compile diff-check build ## Run tests, compilation, whitespace check, and build

lock: ## Refresh uv.lock
	$(UV) lock

clean: ## Remove build and test cache artifacts; keeps .venv
	rm -rf build dist .pytest_cache .coverage htmlcov
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

clean-all: clean ## Also remove .venv
	rm -rf .venv
