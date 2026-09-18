.PHONY: check format lint typecheck architecture gates-negative route-consistency test \
	coverage-t1 coverage-t2 coverage-t3 coverage-t4 coverage-broker coverage-storage-files coverage-storage-files-full coverage-tools mutation performance \
	canonical-json-check runner-protocol-check dependency-surfaces-check

CODE_PATHS := python tests tools packages docker

check: format lint typecheck architecture gates-negative route-consistency canonical-json-check runner-protocol-check test performance

route-consistency:
	PYTHONPATH=python python -m tools.route_consistency

format:
	ruff format --check $(CODE_PATHS)

lint:
	ruff check $(CODE_PATHS)

typecheck:
	mypy python tools packages/pyronin/src docker

architecture:
	python -m tools.architecture_gate python

gates-negative:
	python -m tools.gates_negative

canonical-json-check:
	@command -v go >/dev/null 2>&1 || { echo "go toolchain required for canonical JSON cross-language check"; exit 1; }
	go run tools/canonical_json_check.go tests/golden/canonical_json_v1.json

dependency-surfaces-check:
	python -m tools.dependency_surfaces

runner-protocol-check:
	@command -v go >/dev/null 2>&1 || { echo "go toolchain required for runner protocol check"; exit 1; }
	go run tools/runner_protocol_check.go tests/golden/runner_protocol_v1.json

test:
	python -m pytest --ignore=tests/perf --cov --cov-branch --cov-report=
	$(MAKE) coverage-t1 coverage-t2 coverage-t3 coverage-t4 coverage-broker coverage-storage-files coverage-tools

performance:
	python -m pytest tests/perf -q

coverage-t1:
	# Core contracts currently qualify at 82%; keep an explicit regression margin.
	coverage report --fail-under=80 \
		--include="*/studio_core/*,*/studio_notebook/*,*/studio_orchestrator/*"

coverage-t2:
	# Runtime/storage foundations currently qualify at 75%; keep a regression margin.
	coverage report --fail-under=70 \
		--include="*/studio_kernel/*,*/studio_runners/*,*/studio_storage/*,*/studio_vcs/*,*/studio_worker/*"

coverage-t3:
	coverage report --fail-under=75 \
		--include="*/studio_execution/*,*/studio_server/*,*/studio_cli/*,*/pyronin/*"

coverage-t4:
	# Public v1 domain packages currently qualify at 65%; keep a five-point regression margin.
	coverage report --fail-under=60 \
		--include="*/studio_connectors/*,*/studio_finops/*,*/studio_genai/*,*/studio_lakehouse/*,*/studio_ml/*,*/studio_migration/*,*/studio_observability/*,*/studio_quality/*,*/studio_security/*,*/studio_semantic/*,*/studio_sql/*,*/studio_streaming/*"

coverage-broker:
	# The Docker-authority broker currently measures 49%; keep a five-point regression margin.
	coverage report --fail-under=45 --include="*/studio_runner_broker/*"

coverage-tools:
	# Release and qualification tools are measured separately from product tiers.
	coverage report --fail-under=60 --include="*/tools/*.py"

coverage-storage-files:
	coverage json --include="*/studio_storage/*" -o coverage-storage.json
	python -m tools.coverage_file_gate coverage-storage.json python/studio_storage \
		--exclude=postgres_core.py \
		--exclude=postgres_jobs.py \
		--threshold=80 \
		--ratchet-margin=2 \
		--baseline=artifacts.py=77.30 \
		--baseline=backup.py=76.00 \
		--baseline=bundle_workflow_import.py=77.55 \
		--baseline=catalog.py=72.88 \
		--baseline=connections.py=64.44 \
		--baseline=environments.py=75.51 \
		--baseline=genai.py=63.08 \
		--baseline=local_files.py=77.22 \
		--baseline=ml.py=73.47 \
		--baseline=ontology.py=35.84 \
		--baseline=quality.py=30.34 \
		--baseline=s3_artifacts.py=71.05 \
		--baseline=scheduler.py=78.68 \
		--baseline=scheduler_backfill.py=50.48 \
		--baseline=scheduler_backfill_runtime.py=66.53 \
		--baseline=scheduler_cancellation.py=70.76 \
		--baseline=scheduler_controller.py=73.94 \
		--baseline=scheduler_events.py=75.30 \
		--baseline=scheduler_execution.py=70.49 \
		--baseline=scheduler_fencing.py=77.41 \
		--baseline=scheduler_leadership.py=76.28 \
		--baseline=scheduler_schedule.py=74.00 \
		--baseline=scheduler_timeout.py=62.50 \
		--baseline=sqlite.py=79.12 \
		--baseline=workspaces.py=61.62

coverage-storage-files-full:
	coverage json --include="*/studio_storage/*" -o coverage-storage.json
	python -m tools.coverage_file_gate coverage-storage.json python/studio_storage \
		--threshold=80 \
		--ratchet-margin=2 \
		--baseline=artifacts.py=77.30 \
		--baseline=backup.py=76.00 \
		--baseline=bundle_workflow_import.py=77.55 \
		--baseline=catalog.py=72.88 \
		--baseline=connections.py=64.44 \
		--baseline=environments.py=75.51 \
		--baseline=genai.py=63.08 \
		--baseline=local_files.py=77.22 \
		--baseline=ml.py=73.47 \
		--baseline=ontology.py=35.84 \
		--baseline=postgres_core.py=18.68 \
		--baseline=postgres_jobs.py=47.80 \
		--baseline=quality.py=30.34 \
		--baseline=s3_artifacts.py=71.05 \
		--baseline=scheduler.py=78.68 \
		--baseline=scheduler_backfill.py=50.48 \
		--baseline=scheduler_backfill_runtime.py=66.53 \
		--baseline=scheduler_cancellation.py=70.76 \
		--baseline=scheduler_controller.py=73.94 \
		--baseline=scheduler_events.py=75.30 \
		--baseline=scheduler_execution.py=70.49 \
		--baseline=scheduler_fencing.py=77.41 \
		--baseline=scheduler_leadership.py=76.28 \
		--baseline=scheduler_schedule.py=74.00 \
		--baseline=scheduler_timeout.py=62.50 \
		--baseline=sqlite.py=79.12 \
		--baseline=workspaces.py=61.62
	@rm -f coverage-storage.json

mutation:
	@rm -rf mutants
	@test ! -e src && test ! -L src
	@ln -s python src; trap 'rm -f src' 0; PYTHONPATH=python:packages/pyronin/src mutmut run && mutmut export-cicd-stats
	@python -m tools.mutation_gate mutants/mutmut-cicd-stats.json
