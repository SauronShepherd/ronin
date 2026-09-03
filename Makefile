.PHONY: check format lint typecheck architecture gates-negative test mutation

check: format lint typecheck architecture gates-negative test

format:
	ruff format --check python tests tools

lint:
	ruff check python tests tools

typecheck:
	mypy python tools

architecture:
	python -m tools.architecture_gate python

gates-negative:
	python -m tools.gates_negative

test:
	python -m pytest

mutation:
	@rm -rf mutants
	@test ! -e src && test ! -L src
	@ln -s python src; trap 'rm -f src' 0; mutmut run && mutmut export-cicd-stats
	@python -m tools.mutation_gate mutants/mutmut-cicd-stats.json
