SHELL := /bin/sh

.DEFAULT_GOAL := help

UV ?= uv
COMPLETION_SHELL ?= $(shell basename "$${SHELL:-/bin/bash}")
COMPLETION_RC ?= $(if $(filter zsh,$(COMPLETION_SHELL)),$(HOME)/.zshrc,$(HOME)/.bashrc)
ARGS ?=
SAMPLE_DIR ?= reports/samples
EXAMPLE_DIR ?= docs/examples

.PHONY: help setup completion-init test lint typecheck coverage check \
        build lock clean clean-all sample-reports cli sample-live update-samples

help: ## Show available targets and common variables
	@printf 'moc-env Makefile\n\n'
	@printf 'Usage:\n'
	@printf '  make <target> [ARGS="..."] [SAMPLE_DIR=reports/samples] [EXAMPLE_DIR=docs/examples]\n\n'
	@printf 'Targets:\n'
	@awk 'BEGIN { FS = ":.*##" } /^[a-zA-Z0-9_.%-]+:.*##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf '\nCommon variables:\n'
	@printf '  %-18s %s\n' 'UV' 'uv executable (default: uv)'
	@printf '  %-18s %s\n' 'COMPLETION_SHELL' 'Completion shell (default: current shell name)'
	@printf '  %-18s %s\n' 'COMPLETION_RC' 'Completion startup file (default: shell rc file)'
	@printf '  %-18s %s\n' 'ARGS' 'CLI subcommand and arguments, quoted if needed'
	@printf '  %-18s %s\n' 'SAMPLE_DIR' 'Generated live samples (default: reports/samples)'
	@printf '  %-18s %s\n' 'EXAMPLE_DIR' 'Reviewed live examples (default: docs/examples)'
	@printf '\nCredential variables are read directly by the CLI:\n'
	@printf '  GITHUB_TOKEN, GITHUB_BWS_SECRET_ID, GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE,\n'
	@printf '  GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT, BWS_ACCESS_TOKEN,\n'
	@printf '  BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE, BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT\n'

setup: ## Install the locked virtual environment
	$(UV) sync

completion-init: setup ## Initialize tab completion in the current shell's startup file
	@set -eu; \
	case "$(COMPLETION_SHELL)" in \
	  bash|zsh) ;; \
	  *) printf 'Unsupported shell: %s\n' "$(COMPLETION_SHELL)" >&2; exit 2; ;; \
	esac; \
	rc="$(COMPLETION_RC)"; \
	command="$(CURDIR)/.venv/bin/moc-env"; \
	project_bin="$(CURDIR)/.venv/bin"; \
	marker="# moc-env completion v2 (managed by make completion-init)"; \
	mkdir -p "$$(dirname "$$rc")"; \
	if [ ! -f "$$rc" ] || ! grep -Fq "$$marker" "$$rc"; then \
	  { \
	    printf '%s\n' "$$marker"; \
	    printf "MOC_ENV_COMPLETION_COMMAND='%s'\n" "$$command"; \
	    printf '%s\n' "export MOC_ENV_COMPLETION_COMMAND"; \
	    printf 'case ":$$PATH:" in *":%s:"*) ;; *) PATH="%s:$$PATH";; esac\n' "$$project_bin" "$$project_bin"; \
	    printf '%s\n' "export PATH"; \
	    printf 'eval "$$(%s completion $(COMPLETION_SHELL))"\n' "$$command"; \
	  } >> "$$rc"; \
	fi; \
	printf 'Added moc-env completion to %s\n' "$$rc"; \
	printf 'Run "source %s" or start a new shell, then run "moc-env list" once.\n' "$$rc"

test: ## Run the unit-test suite
	$(UV) run --locked python -m unittest discover -s tests -v

lint: ## Run Ruff checks
	$(UV) run --locked ruff check src tests tools

typecheck: ## Run mypy over the package
	$(UV) run --locked mypy

coverage: ## Run the tests under coverage and enforce the baseline threshold
	$(UV) run --locked coverage run -m unittest discover -s tests
	$(UV) run --locked coverage report

build: ## Build source distribution and wheel
	$(UV) build

check: lint typecheck coverage ## Run lint, type checks, tests, coverage, compilation, checks, and build
	$(UV) run --locked python -m compileall -q src tests
	git diff --check
	$(UV) run --locked python tools/check_pii.py
	$(UV) build

sample-reports: ## Regenerate deterministic offline sample reports
	$(UV) run --locked python tools/generate_sample_reports.py

cli: ## Run the CLI: make cli ARGS="charts --view page"
	$(UV) run --locked moc-env $(ARGS)

sample-live: ## Generate live charts and status samples into $(SAMPLE_DIR)
	@mkdir -p "$(SAMPLE_DIR)"
	$(UV) run --locked moc-env charts --output "$(SAMPLE_DIR)/charts-summary.md"
	$(UV) run --locked moc-env charts --view page --output "$(SAMPLE_DIR)/charts-page.md"
	$(UV) run --locked moc-env status oac-prod --output "$(SAMPLE_DIR)/status-oac-prod.md"
	$(UV) run --locked moc-env status compliant-dev --output "$(SAMPLE_DIR)/status-compliant-dev.md"

update-samples: ## Copy generated samples into $(EXAMPLE_DIR)
	@set -eu; \
	samples="charts-summary.md charts-page.md status-oac-prod.md status-compliant-dev.md"; \
	for sample in $$samples; do \
	  if [ ! -f "$(SAMPLE_DIR)/$$sample" ]; then \
	    printf 'Missing sample in SAMPLE_DIR=%s: %s. Run make sample-live first.\n' "$(SAMPLE_DIR)" "$$sample" >&2; \
	    exit 1; \
	  fi; \
	done; \
	mkdir -p "$(EXAMPLE_DIR)"; \
	for sample in $$samples; do \
	  cp "$(SAMPLE_DIR)/$$sample" "$(EXAMPLE_DIR)/$$sample"; \
	done; \
	printf 'Copied samples to %s. Review the diff before committing.\n' "$(EXAMPLE_DIR)"

lock: ## Refresh uv.lock
	$(UV) lock

clean: ## Remove build and test cache artifacts; keeps .venv
	rm -rf build dist .pytest_cache .coverage htmlcov
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

clean-all: clean ## Also remove .venv
	rm -rf .venv
