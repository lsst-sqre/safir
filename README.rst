############################################
Safir is the SQuaRE Framework for Roundtable
############################################

Roundtable_ is the SQuaRE application and bot deployment platform, hosted on Kubernetes with Argo CD.
Safir is a Python package that lets you develop Roundtable bots, based on the `aiohttp.web`_ asyncio web framework.

Install from PyPI:

.. code-block:: bash

   pip install safir

The best way to create a new Safir-based Roundtable bot is with the `roundtable_aiohttp_bot`_ template.

Read more about Safir at https://safir.lsst.io

Features
========

- Set up an aiohttp.ClientSession as part of the application start up an tear-down lifecycle.
- Set up structlog-based logging.
- Middleware for attaching request context to the logger to include a request UUID, method, and route in all log messages.
- Gather and structure Roundtable-standard metadata about your application.

Developing Safir
================

The best way to start contributing to Safir is by cloning this repository creating a virtual environment, and running the init command:

.. code-block:: bash

   git clone https://github.com/lsst-sqre/safir.git
   cd safir
   make init

For details, see https://safir.lsst.io/v/dev/development.html.

.. _Roundtable: https://roundtable.lsst.io
.. _aiohttp.web: https://docs.aiohttp.org/en/stable/web.html
.. _roundtable_aiohttp_bot: https://github.com/lsst/templates/tree/master/project_templates/roundtable_aiohttp_bot
