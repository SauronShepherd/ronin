.PHONY: check format lint typecheck architecture test

check: format lint typecheck architecture test

format:
	ruff format --check python tests tools

lint:
	ruff check python tests tools

typecheck:
	mypy python tools

architecture:
	python tools/architecture_gate.py python/studio_core

test:
	pytest
