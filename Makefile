# Shortcuts. Windows without make: run the python commands shown after each target.
PY ?= python

.PHONY: help install generate setup wave waves ingest-all ingest-dry run-now status check resume suspend reset

help:
	@echo "make install       pip install -r requirements.txt"
	@echo "make generate      build data/initial, pending/ waves and answer_key/"
	@echo "make setup         run snowflake/02..11 (after 01_account_setup.sql as ACCOUNTADMIN)"
	@echo "make waves         list waves and which are dropped"
	@echo "make wave N=1      copy wave 1 into data/incoming, commit and push"
	@echo "make ingest-all    upload every file under data/ from your laptop"
	@echo "make ingest-dry    profile every file, no Snowflake"
	@echo "make run-now       load + process + DQ immediately"
	@echo "make status        health, lineage, DQ results, alerts"
	@echo "make check         planted issues vs. what was caught"
	@echo "make resume / suspend / reset"

install:            ; $(PY) -m pip install -r requirements.txt
generate:           ; $(PY) generator/generate_data.py --clean
setup:              ; $(PY) scripts/run_sql.py --setup
waves:              ; $(PY) scripts/drop_wave.py --list
wave:               ; $(PY) scripts/drop_wave.py $(N) --push
ingest-all:         ; $(PY) scripts/ingest_files.py --all
ingest-dry:         ; $(PY) scripts/ingest_files.py --all --dry-run
run-now:            ; $(PY) scripts/run_sql.py snowflake/ops/run_now.sql
status:             ; $(PY) scripts/run_sql.py snowflake/ops/check_status.sql
check:              ; $(PY) scripts/check_planted.py
resume:             ; $(PY) scripts/run_sql.py snowflake/ops/resume_tasks.sql
suspend:            ; $(PY) scripts/run_sql.py snowflake/ops/suspend_tasks.sql
reset:              ; $(PY) scripts/run_sql.py snowflake/ops/reset_dev.sql
