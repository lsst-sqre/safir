.PHONY: help
help:
	@echo "Make targets for Safir:"
	@echo "make clean - Remove generated files"
	@echo "make init - Set up dev environment (install pre-commit hooks)"
	@echo "make linkcheck - Check for broken links in documentation"
	@echo "make update - Update pre-commit dependencies and run make init"
	@echo "make update-deps - Update pre-commit dependencies"

.PHONY: clean
clean:
	rm -rf .tox
	rm -rf docs/_build
	rm -rf docs/api

.PHONY: init
init:
	pip install --upgrade uv
	uv pip install --upgrade pre-commit tox tox-docker tox-uv
	uv pip install --upgrade -e ".[arq,db,dev,gcs,kubernetes]"
	pre-commit install
	rm -rf .tox

# This is defined as a Makefile target instead of only a tox command because
# if the command fails we want to cat output.txt, which contains the
# actually useful linkcheck output. tox unfortunately doesn't support this
# level of shell trickery after failed commands.
.PHONY: linkcheck
linkcheck:
	sphinx-build --keep-going -n -T -b linkcheck docs	\
	    docs/_build/linkcheck				\
	    || (cat docs/_build/linkcheck/output.txt; exit 1)

# update and update-deps aren't that meaningful for PyPI packages that do
# not have pinned Python package dependencies, but provide the same targets
# as the FastAPI Safir app template so that people can use the same command
# to update everything at the start of development (here, just pre-commit).
.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	pip install --upgrade uv
	uv pip install --upgrade pre-commit
	pre-commit autoupdate
