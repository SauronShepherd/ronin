.PHONY: check format lint typecheck architecture gates-negative test \
	coverage-t1 coverage-t2 coverage-t3 mutation

CODE_PATHS := python tests tools packages docker

check: format lint typecheck architecture gates-negative test

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

test:
	python -m pytest --cov --cov-branch --cov-report=
	$(MAKE) coverage-t1 coverage-t2 coverage-t3

coverage-t1:
	coverage report --fail-under=100 \
		--include="*/studio_core/*,*/studio_notebook/*,*/studio_orchestrator/*"

coverage-t2:
	coverage report --fail-under=90 \
		--include="*/studio_kernel/*,*/studio_runners/*,*/studio_storage/*,*/studio_vcs/*"

coverage-t3:
	coverage report --fail-under=75 \
		--include="*/studio_server/*,*/studio_cli/*,*/pyronin/*"

mutation:
	@rm -rf mutants
	@test ! -e src && test ! -L src
	@ln -s python src; trap 'rm -f src' 0; mutmut run && mutmut export-cicd-stats
	@python -m tools.mutation_gate mutants/mutmut-cicd-stats.json
