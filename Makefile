.PHONY: check format lint typecheck architecture gates-negative test

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
