.PHONY: check format lint typecheck architecture gates-negative test \
	coverage-t1 coverage-t2 coverage-t3 coverage-t4 coverage-storage-files mutation performance \
	canonical-json-check dependency-surfaces-check

CODE_PATHS := python tests tools packages docker

check: format lint typecheck architecture gates-negative test performance

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

test:
	python -m pytest --ignore=tests/perf --cov --cov-branch --cov-report=
	$(MAKE) coverage-t1 coverage-t2 coverage-t3 coverage-t4 coverage-storage-files

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
	coverage report --fail-under=10 \
		--include="*/studio_connectors/*,*/studio_finops/*,*/studio_genai/*,*/studio_lakehouse/*,*/studio_ml/*,*/studio_migration/*,*/studio_observability/*,*/studio_quality/*,*/studio_security/*,*/studio_semantic/*,*/studio_sql/*,*/studio_streaming/*"

coverage-storage-files:
	coverage json --include="*/studio_storage/*" -o coverage-storage.json
	python -m tools.coverage_file_gate coverage-storage.json python/studio_storage \
		--threshold=80
	@rm -f coverage-storage.json

mutation:
	@rm -rf mutants
	@test ! -e src && test ! -L src
	@ln -s python src; trap 'rm -f src' 0; mutmut run && mutmut export-cicd-stats
	@python -m tools.mutation_gate mutants/mutmut-cicd-stats.json
