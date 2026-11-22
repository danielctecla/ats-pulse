SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

TF := terraform -chdir=iac/env
VENV := .venv
PY := $(VENV)/bin/python

# Optional, gitignored. Holds TF_VAR_notification_email=you@example.com (no quotes)
# and, if you use one, AWS_PROFILE=<profile>. Never committed.
-include .env
export

.PHONY: help fmt validate test-infra test run-local plan

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-11s %s\n", $$1, $$2}'

fmt: ## Format Terraform files
	terraform fmt -recursive iac

validate: ## terraform fmt -check + validate (no AWS credentials needed)
	terraform fmt -check -recursive iac
	$(TF) init -input=false -backend=false
	$(TF) validate

test-infra: ## terraform test with mocked providers (no AWS credentials needed)
	$(TF) init -input=false -backend=false
	$(TF) test

test: $(VENV)/.installed ## pytest + moto, fully local
	$(PY) -m pytest

run-local: $(VENV)/.installed ## Real job-board APIs + in-memory DynamoDB (no AWS)
	PYTHONPATH=src $(PY) scripts/run_local.py

plan: ## terraform plan (needs AWS credentials and TF_VAR_notification_email)
	$(TF) init -input=false
	$(TF) plan -input=false

$(VENV)/.installed: requirements-dev.txt
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r requirements-dev.txt
	touch $@
