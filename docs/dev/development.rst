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

To develop Safir, create a virtual environment with your method of choice (like virtualenvwrapper) and then clone or fork, and install:

.. code-block:: sh

   git clone https://github.com/lsst-sqre/safir.git
   cd safir
   make init

This init step does three things:

1. Installs Safir in an editable mode with its "dev" extra that includes test and documentation dependencies.
2. Installs pre-commit and tox.
3. Installs the pre-commit hooks.

You must have Docker installed and configured so that your user can start Docker containers in order to run the test suite.

.. _pre-commit-hooks:

Pre-commit hooks
================

The pre-commit hooks, which are automatically installed by running the :command:`make init` command on :ref:`set up <dev-environment>`, ensure that files are valid and properly formatted.
Some pre-commit hooks automatically reformat code:

``seed-isort-config``
    Adds configuration for isort to the :file:`pyproject.toml` file.

``isort``
    Automatically sorts imports in Python modules.

``black``
    Automatically formats Python code.

``blacken-docs``
    Automatically formats Python code in reStructuredText documentation and docstrings.

When these hooks fail, your Git commit will be aborted.
To proceed, stage the new modifications and proceed with your Git commit.

.. _dev-run-tests:

Running tests
=============

To test the library, run tox_, which tests the library the same way that the CI workflow does:

.. code-block:: sh

   tox run

To see a listing of test environments, run:

.. code-block:: sh

   tox list

tox will start a PostgreSQL container, which is required for some tests.

To run a specific test or list of tests, you can add test file names (and any other pytest_ options) after ``--`` when executing the ``py`` tox environment.
For example:

.. code-block:: sh

   tox run -e py -- tests/database_test.py

.. _dev-build-docs:

Building documentation
======================

Documentation is built with Sphinx_:

.. _Sphinx: https://www.sphinx-doc.org/en/master/

.. code-block:: sh

   tox run -e docs

The build documentation is located in the :file:`docs/_build/html` directory.

.. _dev-change-log:

Updating the change log
=======================

Each pull request should update the change log (:file:`CHANGELOG.md`).
Add a description of new features and fixes as list items under a section at the top of the change log, using ``unreleased`` for the date portion.
The version number for that heading should be chosen or updated based on the semver_ rules.

.. _semver: https://semver.org/

.. code-block:: markdown

   ## X.Y.Z (unreleased)

   ### Subheading (see below)

   - Description of the feature or fix.

All changelog entries should be divided into sections (each starting with ``###``) chosen from the following:

- **Backward-incompatible changes** (also increase the major version except in unusual cases)
- **New features** (also increase the minor version except in unusual cases)
- **Bug fixes**
- **Other changes** (which are mostly new features that are not significant enough to call attention to, such as logging formatting changes or updates to the documentation)

If the exact version and release date is known (:doc:`because a release is being prepared <release>`), the section header is formatted as:

.. code-block:: markdown

   ## X.Y.Z (YYYY-MM-DD)

Each entry in the change log should be on one line without line breaks, even though this violates the normal rule of putting a newline after each sentence.
This allows the whole change log entry to be copied and pasted into the GitHub release page when creating a release.
Unfortunately, GitHub Markdown preserves line breaks after sentences as hard line breaks when rendering the description of a release.

.. _style-guide:

Style guide
===========

Code
----

- The code style follows :pep:`8`, though in practice lean on Black and isort to format the code for you.

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
