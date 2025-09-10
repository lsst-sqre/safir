#################
Development guide
#################

This page provides procedures and guidelines for developing and contributing to Safir.

Scope of contributions
======================

Safir is an open source package, meaning that you can contribute to Safir itself, or fork Safir for your own purposes.

Since Safir is intended for internal use by Rubin Observatory, community contributions can only be accepted if they align with Rubin Observatory's aims.
For that reason, it's a good idea to propose changes with a new `GitHub issue`_ before investing time in making a pull request.

Safir is developed by the LSST SQuaRE team.

.. _GitHub issue: https://github.com/lsst-sqre/safir/issues/new

.. _dev-environment:

Setting up a local development environment
==========================================

Prerequisites
-------------

Safir is developed using `uv workspaces`_ so that the various Safir packages can be maintained and tested together.
You will therefore need uv_ installed to set up a development environment.
See the `uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`__ for details.

.. _uv workspaces: https://docs.astral.sh/uv/concepts/projects/workspaces/

You must have Docker installed and configured so that your user can start Docker containers in order to run the test suite.

Set up
------

To develop Safir, clone the repository and set up a virtual environment:

.. code-block:: sh

   git clone https://github.com/lsst-sqre/safir.git
   cd safir
   make init

This init step does three things:

1. Creates a Python virtual environment in the :file:`.venv` subdirectory with the packages needed to do Repertoire development installed.
2. Installs the Safir packages in an editable mode in that virtual environment.
3. Installs the pre-commit hooks.

You can activate the Repertoire virtual environment if you wish with:

.. prompt:: bash

   source .venv/bin/activate

This is optional; you do not have to activate the virtual environment to do development.
However, if you do, you can omit :command:`uv run` from the start of all commands described below.
Also, editors with Python integration, such as VSCode, may work more smoothly if you activate the virtualenv before starting them.

.. _pre-commit-hooks:

Pre-commit hooks
================

The pre-commit hooks, which are automatically installed by running the :command:`make init` command on :ref:`set up <dev-environment>`, ensure that files are valid and properly formatted.
Some pre-commit hooks automatically reformat code:

``ruff``
    Lint and reformat Python code and attempt to automatically fix some problems.

``blacken-docs``
    Automatically formats Python code in reStructuredText documentation and docstrings.

When these hooks fail, your Git commit will be aborted.
To proceed, stage the new modifications and proceed with your Git commit.

If the ``uv-lock`` pre-commit hook fails, that indicates that the :file:`uv.lock` file is out of sync with the declared dependencies.
To fix this, run :command:`make update-deps` as described in :ref:`dev-updating-dependencies`.

.. _dev-run-tests:

Running tests
=============

Safir uses nox_ as its automation tool for testing.

To run all Safir tests, run:

.. prompt:: bash

   uv run nox

This tests the library in the same way that the CI workflow does.
You may wish to run the individual sessions (``lint``, ``typing``, ``test``, ``docs``, and ``docs-linkcheck``) when iterating on a specific change.

To see a listing of nox sessions:

.. prompt:: bash

   uv run nox --list

To run a specific test or list of tests, you can add test file names (and any other pytest_ options) after ``--`` when executing the ``test`` nox session.
For example:

.. prompt:: bash

   uv run nox -s test -- tests/database_test.py

.. _dev-build-docs:

Building documentation
======================

Documentation is built with Sphinx_.
It is built as part of a normal test run to check that the documentation can still build without warnings, or can be built explicitly with:

.. prompt:: bash

   uv run nox -s docs

The build documentation is located in the :file:`docs/_build/html` directory.

Additional dependencies required for the documentation build should be added to the ``docs`` dependency group in :file:`pyproject.toml`.

Documentation builds are incremental, and generate and use cached descriptions of the internal Python APIs.
If you see errors in building the Python API documentation or have problems with changes to the documentation (particularly diagrams) not showing up, try a clean documentation build with:

.. prompt:: bash

   uv run nox -s docs-clean

This will be slower, but it will ensure that the documentation build doesn't rely on any cached data.

To check the documentation for broken links, run:

.. code-block:: sh

   uv run nox -s docs-linkcheck

.. _dev-updating-dependencies:

Updating dependencies
=====================

The Safir packages are libraries and therefore do not pin dependency versions in the packages uploaded to PyPI.
However, the Safir project does pin dependencies using :file:`uv.lock` for development.
This ensures stable testing and frozen dependencies for development support tools, such as Sphinx_, nox_, and mypy_.

To update dependencies, run:

.. prompt:: bash

   make update

This will update all pinned Python dependencies, update the versions of the pre-commit hooks, and, if needed, update the version of uv pinned in the GitHub Actions configuration and :file:`Dockerfile`.

You may wish to do this at the start of a development cycle so that you're using the latest versions of the linters.

.. _dev-change-log:

Updating the change log
=======================

Safir uses scriv_ to maintain its change log.

When preparing a pull request, run :command:`uv run scriv create`.
This will create a change log fragment in :file:`changelog.d`.
Edit that fragment, removing the sections that do not apply and adding entries fo this pull request.
You can pass the ``--edit`` flag to :command:`uv run scriv create` to open the created fragment automatically in an editor.

Change log entries use the following sections:

- **Backward-incompatible changes**
- **New features**
- **Bug fixes**
- **Other changes** (for minor, patch-level changes that are not bug fixes, such as logging formatting changes or updates to the documentation)

Changes that are not visible to the user, including minor documentation changes, should not have a change log fragment to avoid clutttering the change log with changes the user doesn't need to care about.

These entries will eventually be cut and pasted into the release description for the next release, so the Markdown for the change descriptions should be compatible with GitHub's Markdown conventions for the release description.
Specifically:

- Each bullet point should be entirely on one line, even if it contains multiple sentences.
  This is an exception to the normal documentation convention of a newline after each sentence.
  Unfortunately, GitHub interprets those newlines as hard line breaks, so they would result in an ugly release description.
- Be cautious with complex markup, such as nested bullet lists, since the formatting in the GitHub release description may not be what you expect and manually repairing it is tedious.

.. _style-guide:

Style guide
===========

Code
----

- The code style follows :pep:`8`, though in practice lean on Ruff to format the code for you.

- Use :pep:`484` type annotations.
  The :command:`uv run nox -s typing` test session, which runs mypy_, ensures that the project's types are consistent.

- Write tests for Pytest_.

Documentation
-------------

- Follow the `LSST DM User Documentation Style Guide`_, which is primarily based on the `Google Developer Style Guide`_.

- Document the Python API with numpydoc-formatted docstrings.
  See the `LSST DM Docstring Style Guide`_.

- Follow the `LSST DM ReStructuredTextStyle Guide`_.
  In particular, ensure that prose is written **one-sentence-per-line** for better Git diffs.

.. _`LSST DM User Documentation Style Guide`: https://developer.lsst.io/user-docs/index.html
.. _`Google Developer Style Guide`: https://developers.google.com/style/
.. _`LSST DM Docstring Style Guide`: https://developer.lsst.io/python/style.html
.. _`LSST DM ReStructuredTextStyle Guide`: https://developer.lsst.io/restructuredtext/style.html
