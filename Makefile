.PHONY: init
init:
	pip install -e ".[dev]"
	pip install tox pre-commit
	pre-commit install
