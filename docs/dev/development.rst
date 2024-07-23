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

Development of Safir should be done inside a virtual environment.

Nublado uses nox_ as its build system, which can manage a virtual environment for you.
Run:

.. prompt:: bash

   nox -s venv-init

The resulting virtual environment will be created in :file:`.venv`.
Enable it by running :command:`source .venv/bin/activate`.

Alternately, you can create a virtual environment with any other method of your choice (such as virtualenvwrapper_).
If you use a different virtual environment, run the following command after you have enabled it:

.. prompt:: bash

   nox -s init

Either ``venv-init`` or ``init`` does the following:

#. Installs build system dependencies in the virtual environment.
#. Installs package dependencies, including test and documentation dependencies.
#. Installs Safir packages in editable mode so that changes made to the Git checkout will be picked up by the virtual environment.
#. Installs pre-commit hooks.

You must have Docker installed and configured so that your user can start Docker containers in order to run the test suite.

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

.. _dev-run-tests:

Running tests
=============

To run all Safir tests, run:

.. prompt:: bash

   nox -s

This tests the library in the same way that the CI workflow does.
You may wish to run the individual sessions (``lint``, ``typing``, ``test``, ``docs``, and ``docs-linkcheck``) when iterating on a specific change.
Consider using the ``-R`` flag when you haven't updated dependencies, as discussed below.

To see a listing of nox sessions:

.. prompt:: bash

   nox --list

To run a specific test or list of tests, you can add test file names (and any other pytest_ options) after ``--`` when executing the ``test`` nox session.
For example:

.. prompt:: bash

   nox -s test -- safir/tests/database_test.py

If you are interating on a specific test failure, you may want to pass the ``-R`` flag to skip the dependency installation step.
This will make nox run much faster, at the cost of not fixing out-of-date dependencies.
For example:

.. prompt:: bash

   nox -Rs test -- safir/tests/database_test.py

.. _dev-build-docs:

Building documentation
======================

Documentation is built with Sphinx_:

.. _Sphinx: https://www.sphinx-doc.org/en/master/

.. prompt:: bash

   nox -s docs

The build documentation is located in the :file:`docs/_build/html` directory.

Additional dependencies required for the documentation build should be added as development dependencies of the ``safir`` library, in :file:`safir/pyproject.toml`.

Documentation builds are incremental, and generate and use cached descriptions of the internal Python APIs.
If you see errors in building the Python API documentation or have problems with changes to the documentation (particularly diagrams) not showing up, try a clean documentation build with:

.. prompt:: bash

   nox -s docs-clean

This will be slower, but it will ensure that the documentation build doesn't rely on any cached data.

To check the documentation for broken links, run:

.. code-block:: sh

   nox -s docs-linkcheck

.. _dev-change-log:

Updating the change log
=======================

Safir uses scriv_ to maintain its change log.

When preparing a pull request, run :command:`scriv create`.
This will create a change log fragment in :file:`changelog.d`.
Edit that fragment, removing the sections that do not apply and adding entries fo this pull request.
You can pass the ``--edit`` flag to :command:`scriv create` to open the created fragment automatically in an editor.

Change log entries use the following sections:

- **Backward-incompatible changes**
- **New features**
- **Bug fixes**
- **Other changes** (for minor, patch-level changes that are not bug fixes, such as logging formatting changes or updates to the documentation)

These entries will eventually be cut and pasted into the release description for the next release, so the Markdown for the change descriptions should be compatible with GitHub's Markdown conventions for the release description.
Specifically:

- Each bullet point should be entirely on one line, even if it contains multiple sentences.
  This is an exception to the normal documentation convention of a newline after each sentence.
  Unfortunately, GitHub interprets those newlines as hard line breaks, so they would result in an ugly release description.
- Avoid using too much complex markup, such as nested bullet lists, since the formatting in the GitHub release description may not be what you expect and manually editing it is tedious.

.. _style-guide:

Style guide
===========

Code
----

- The code style follows :pep:`8`, though in practice lean on Ruff to format the code for you.

- Use :pep:`484` type annotations.
  The ``tox run -e typing`` test environment, which runs mypy_, ensures that the project's types are consistent.

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
