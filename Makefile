SHELL := /bin/sh

.DEFAULT_GOAL := help

UV ?= uv
ENV ?= bu-ist-demo
COMPLETION_SHELL ?= $(shell basename "$${SHELL:-/bin/bash}")
COMPLETION_RC ?= $(if $(filter zsh,$(COMPLETION_SHELL)),$(HOME)/.zshrc,$(HOME)/.bashrc)
WORKLOAD ?= workload0
FORMAT ?= text
ARGS ?=
OUTPUT ?= reports/$(ENV).md
FILE ?= desired-state/infra-clusters/$(ENV)-infra.yaml
WORKLOAD_FILE ?= desired-state/workload-clusters/$(ENV)-$(WORKLOAD).yaml
VALIDATION_OUTPUT ?= reports/$(ENV)-validation.md
COMPARISON_OUTPUT ?= reports/$(ENV)-infra-comparison.md
PLAN_OUTPUT ?= reports/$(ENV)-infra-plan.md
WORKLOAD_COMPARISON_OUTPUT ?= reports/$(ENV)-$(WORKLOAD)-comparison.md

# Set NO_PRS=1 to avoid pull-request API calls.
ifeq ($(NO_PRS),1)
PRS_FLAG := --no-prs
else
PRS_FLAG :=
endif

RUN_ARGS := status $(ENV) --format $(FORMAT) $(PRS_FLAG) $(ARGS)

.PHONY: help setup completion-init sync test lint typecheck coverage list export-infra export-infra-file \
        export-workload export-workload-file validate validate-markdown \
        check-infra check-infra-markdown plan-infra \
        plan-infra-markdown check-workload \
        check-workload-markdown run run-text run-json run-markdown \
        run-no-prs report-markdown \
        report-gist-secret report-gist-public build compile \
        diff-check pii-check check lock sample-reports \
        clean clean-all

help: ## Show available targets and common variables
	@printf 'moc-env Makefile\n\n'
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
	@printf '  %-18s %s\n' 'OUTPUT' 'Report or YAML export destination (default: reports/ENV.md)'
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

sync: setup ## Alias for setup

test: ## Run the unit-test suite
	$(UV) run --locked python -m unittest discover -s tests -v

lint: ## Run Ruff checks
	$(UV) run --locked ruff check src tests tools

typecheck: ## Run mypy over the package
	$(UV) run --locked mypy

coverage: ## Run the tests under coverage and enforce the baseline threshold
	$(UV) run --locked coverage run -m unittest discover -s tests
	$(UV) run --locked coverage report

list: ## List environment names that can be passed to the CLI
	$(UV) run --locked moc-env list

export-infra: ## Print a deterministic draft InfraCluster YAML snapshot
	$(UV) run --locked moc-env export-infra $(ENV) $(ARGS)

export-infra-file: ## Write a draft InfraCluster YAML snapshot to OUTPUT
	$(UV) run --locked moc-env export-infra $(ENV) --output $(OUTPUT) $(ARGS)

export-workload: ## Print a draft WorkloadCluster YAML snapshot
	$(UV) run --locked moc-env export-workload $(ENV) $(WORKLOAD) $(ARGS)

export-workload-file: ## Write a draft WorkloadCluster YAML snapshot to OUTPUT
	$(UV) run --locked moc-env export-workload $(ENV) $(WORKLOAD) \
	  --output $(OUTPUT) $(ARGS)

validate: ## Validate the desired-state document in FILE
	$(UV) run --locked moc-env validate $(FILE) $(ARGS)

validate-markdown: ## Write a Markdown validation report to VALIDATION_OUTPUT
	$(UV) run --locked moc-env validate $(FILE) --format markdown \
	  --output $(VALIDATION_OUTPUT)

check-infra: ## Compare FILE against merged main
	$(UV) run --locked moc-env check-infra $(FILE) $(ARGS)

check-infra-markdown: ## Write a Markdown infra comparison to COMPARISON_OUTPUT
	$(UV) run --locked moc-env check-infra $(FILE) --format markdown \
	  --output $(COMPARISON_OUTPUT)

plan-infra: ## Print a read-only infra change plan for FILE
	$(UV) run --locked moc-env plan-infra $(FILE) $(ARGS)

plan-infra-markdown: ## Write a Markdown infra change plan to PLAN_OUTPUT
	$(UV) run --locked moc-env plan-infra $(FILE) --format markdown \
	  --output $(PLAN_OUTPUT)

check-workload: ## Compare WORKLOAD_FILE against merged main
	$(UV) run --locked moc-env check-workload $(WORKLOAD_FILE) $(ARGS)

check-workload-markdown: ## Write a Markdown workload comparison
	$(UV) run --locked moc-env check-workload $(WORKLOAD_FILE) --format markdown \
	  --output $(WORKLOAD_COMPARISON_OUTPUT)

run: run-text ## Run the CLI (default ENV and text format)

run-text: ## Run the environment status command with text output
	$(UV) run --locked moc-env $(RUN_ARGS)

run-json: ## Run the environment status command with JSON output
	$(UV) run --locked moc-env status $(ENV) --format json $(PRS_FLAG) $(ARGS)

run-markdown: ## Run the environment status command with Markdown output
	$(UV) run --locked moc-env status $(ENV) --format markdown $(PRS_FLAG) $(ARGS)

run-no-prs: ## Run the environment status command without pull-request discovery
	$(UV) run --locked moc-env status $(ENV) --format $(FORMAT) --no-prs $(ARGS)

report-markdown: ## Write a verbose Markdown report to OUTPUT
	$(UV) run --locked moc-env status $(ENV) --format markdown --output $(OUTPUT)

report-gist-secret: report-markdown ## Create a secret GitHub gist from OUTPUT
	gh gist create $(OUTPUT)

report-gist-public: report-markdown ## Create a public GitHub gist from OUTPUT
	gh gist create $(OUTPUT) --public

build: ## Build source distribution and wheel
	$(UV) build

compile: ## Byte-compile source and tests
	$(UV) run --locked python -m compileall -q src tests

diff-check: ## Check the Git worktree diff for whitespace errors
	git diff --check

pii-check: ## Check tracked files for personal identifiers
	$(UV) run --locked python tools/check_pii.py

check: lint typecheck coverage compile diff-check pii-check build ## Run lint, type checks, tests, coverage, compilation, checks, and build

sample-reports: ## Regenerate deterministic offline sample reports
	$(UV) run --locked python tools/generate_sample_reports.py

lock: ## Refresh uv.lock
	$(UV) lock

clean: ## Remove build and test cache artifacts; keeps .venv
	rm -rf build dist .pytest_cache .coverage htmlcov
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

clean-all: clean ## Also remove .venv
	rm -rf .venv
