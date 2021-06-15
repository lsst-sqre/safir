############################################
Safir is the SQuaRE Framework for Roundtable
############################################

Roundtable_ is the SQuaRE application and bot deployment platform, hosted on Kubernetes with Argo CD.
Safir is a Python package that lets you develop Roundtable bots, based on the `FastAPI`_ asyncio web framework.

Install from PyPI:

.. code-block:: bash

   pip install safir

The best way to create a new Safir-based Roundtable bot is with the `fastapi_safir_app`_ template.

Read more about Safir at https://safir.lsst.io

Features
========

- Set up an ``httpx.AsyncClient`` as part of the application start-up and shutdown lifecycle.
- Set up structlog-based logging.
- Middleware for attaching request context to the logger to include a request UUID, method, and route in all log messages.
- Process ``X-Forwarded-*`` headers to determine the source IP and related information of the request.
- Gather and structure standard metadata about your application.

Developing Safir
================

The best way to start contributing to Safir is by cloning this repository creating a virtual environment, and running the init command:

.. code-block:: bash

   git clone https://github.com/lsst-sqre/safir.git
   cd safir
   make init

For details, see https://safir.lsst.io/dev/development.html.

.. _Roundtable: https://roundtable.lsst.io
.. _FastAPI: https://fastapi.tiangolo.com/
.. _fastapi_safir_app: https://github.com/lsst/templates/tree/master/project_templates/fastapi_safir_app
