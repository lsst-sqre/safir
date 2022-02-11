.PHONY: init
init:
	pip install -e ".[db,dev,kubernetes]"
	pip install tox tox-docker pre-commit
	pre-commit install
