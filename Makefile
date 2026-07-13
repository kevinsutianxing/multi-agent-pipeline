PYTHON ?= python3
PIPELINE_DB ?= implementation/state/pipeline.db
PIPELINE_RUNS_DIR ?= implementation/state/runs
RUN_ID ?=

.PHONY: help compile unit shell test health deploy list status context retry

help:
	@printf '%s\n' \
	  'make test                 Compile, run tests, and validate shell syntax' \
	  'make health               Run controller and cross-host health checks' \
	  'make deploy               Deploy from SZ81 using the supported installer' \
	  'make list                 List recent pipeline runs' \
	  'make status RUN_ID=<id>   Inspect one run' \
	  'make context RUN_ID=<id>  Inspect context for the current stage' \
	  'make retry RUN_ID=<id>    Retry a blocked run after fixing its cause'

compile:
	$(PYTHON) -m compileall -q implementation/scripts implementation/plugins implementation/tests

unit:
	$(PYTHON) -m unittest discover -s implementation/tests -v

shell:
	bash -n implementation/deploy/*.sh

test: compile unit shell

health:
	implementation/deploy/healthcheck.sh

deploy:
	implementation/deploy/deploy-all.sh

list:
	$(PYTHON) implementation/scripts/reliable_ctl.py \
	  --db "$(PIPELINE_DB)" \
	  --runs-dir "$(PIPELINE_RUNS_DIR)" \
	  list --limit 20

status:
	@test -n "$(RUN_ID)" || { echo 'RUN_ID is required: make status RUN_ID=<id>' >&2; exit 2; }
	$(PYTHON) implementation/scripts/reliable_ctl.py \
	  --db "$(PIPELINE_DB)" \
	  --runs-dir "$(PIPELINE_RUNS_DIR)" \
	  status "$(RUN_ID)"

context:
	@test -n "$(RUN_ID)" || { echo 'RUN_ID is required: make context RUN_ID=<id>' >&2; exit 2; }
	$(PYTHON) implementation/scripts/reliable_ctl.py \
	  --db "$(PIPELINE_DB)" \
	  --runs-dir "$(PIPELINE_RUNS_DIR)" \
	  context "$(RUN_ID)"

retry:
	@test -n "$(RUN_ID)" || { echo 'RUN_ID is required: make retry RUN_ID=<id>' >&2; exit 2; }
	$(PYTHON) implementation/scripts/reliable_ctl.py \
	  --db "$(PIPELINE_DB)" \
	  --runs-dir "$(PIPELINE_RUNS_DIR)" \
	  retry "$(RUN_ID)"
