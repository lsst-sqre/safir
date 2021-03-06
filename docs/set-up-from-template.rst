#################################
Creating an app from the template
#################################

The best way to create a new Safir-based application for Roundtable_ is with the roundtable_aiohttp_bot_ template.
This page describes how to directly use the template to set up a new application.
In the future you will be able to create new applications more quickly with the ``@sqrbot-jr create project`` Slack command.

1. Install templatekit
======================

In a clean Python virtual environment, install templatekit_:

.. prompt:: bash

   python -m pip install templatekit

2. Start the project with the template
======================================

Next, you'll actually create the project files using the template.

.. prompt:: bash

   git clone https://github.com/lsst/templates
   templatekit -r templates make roundtable_aiohttp_bot

Answer the prompts, and move into that directory in your shell.

The rest of this tutorial uses ``safirdemo`` as the repository (and package) name:

.. prompt:: bash

   cd safirdemo

3. Initialize the repository
============================

From the root of the project directory, initialize the Git repository:

.. prompt:: bash

   git init .
   git add .
   git commit

4. Initialize the dependencies
==============================

Create a new Python virtual environment for application development (don't reuse the existing environment with templatekit).
This is important so that your dependencies resolve reliably.

Now run the initialization command:

.. prompt:: bash

   make update

This command does several important things for you:

1. Compiles the direct dependencies listed in :file:`requirements/*.in` into resolved dependencies in :file:`requirements/*.txt` files.
2. Installs your project in a locally editable mode, along with the third-party dependencies listed in the :file:`requirements/*.txt` files.
3. Installs tox_
4. Installs pre-commit_ hooks

After the requirements are resolved, commit those files:

.. prompt:: bash

   git add requirements/*.txt
   git commit

.. note::

   In the future you can update your project's dependencies by re-running ``make update`` and re-committing the requirements files.

   To install the project for development *without* updating dependencies, run:

   .. prompt:: bash

      make init

5. Format code with Black
=========================

The Python code generated by the template is good, but there may be minor formatting issues related to line length and your application's chosen name.
You can format the code and by running tox_:

.. prompt:: bash

   tox -e lint
   git commit -a

6. Push to GitHub
=================

Now `create your application's repository on GitHub <https://help.github.com/en/github/creating-cloning-and-archiving-repositories/creating-a-new-repository>`__ and push to it.

7. Configure Docker Hub credentials
===================================

The first push to GitHub will fail.
That's because the Docker build step doesn't credentials for Docker Hub.

To set those credentials, follow GitHub's help page `Creating and storing encrypted secrets <https://help.github.com/en/actions/configuring-and-managing-workflows/creating-and-storing-encrypted-secrets>`__.
The variables are:

``DOCKER_USERNAME``
    A Docker Hub username that has access to the lsstsqre organization on Docker Hub.

``DOCKER_TOKEN``
    A Docker Hub Personal Access Token associated with ``DOCKER_USERNAME``.
    `Create a dedicated token <https://docs.docker.com/docker-hub/access-tokens/>`__ specifically for your project's GitHub Actions workflow.

After setting these secrets, re-run the GitHub Action by `re-running the workflow job from the GitHub Actions UI <https://help.github.com/en/actions/configuring-and-managing-workflows/managing-a-workflow-run>`__ or by pushing a new commit to GitHub.

8. Try the local test commands
==============================

The roundtable_aiohttp_bot_ template is set up to help you successfully test and maintain your bot.
There are two ways for you to run tests.

First, you can run pytest_ directly from your local development environment:

.. prompt:: bash

   pytest

An even better, and more robust approach is with tox:

.. prompt:: bash

   tox

Tox runs several test steps, each in their own virtual environment.
To learn about these test steps:

.. prompt:: bash

   tox -av

For example, to only run mypy to check type annotations:

.. prompt:: bash

   tox -e typing

Or to only lint the code (and reformat it):

.. prompt:: bash

   tox -e lint

To run all the default test steps, but in parallel:

.. prompt:: bash

   tox -p auto

9. Try the local development server
===================================

In addition to running tests, tox is also configured with a command to spin up a development server:

.. prompt:: bash

   tox -e run

In another shell, send an HTTP GET request to the development server:

.. prompt:: bash

   curl http://localhost:8000/ | python -m json.tool

This development server auto-reloads, so any time you change the code, the server will restart for you.

Next steps
==========

Now that you have a working application repository, the next steps are to develop your application's logic and interface, and then deploy it to Roundtable.

To learn learn more about developing Safir-based applications like yours, refer to the :doc:`guides in this documentation <index>` and the `aiohttp Server documentation <https://docs.aiohttp.org/en/stable/web.html>`__.

To learn how to deploy your application to Roundtable, see the `Roundtable documentation <https://roundtable.lsst.io>`__.
