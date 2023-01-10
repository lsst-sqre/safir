.PHONY: init
init:
	pip install --upgrade pip tox tox-docker pre-commit
	pip install --upgrade -e ".[arq,db,dev,gcs,kubernetes]"
	pre-commit install
	rm -rf .tox
