.PHONY: init
init:
	pip install --upgrade pip tox tox-docker pre-commit
	pip install --upgrade -e ".[db,dev,kubernetes]"
	pre-commit install
