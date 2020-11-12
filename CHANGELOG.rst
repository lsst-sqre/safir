##########
Change log
##########

.. Headline template:
   X.Y.Z (YYYY-MM-DD)

0.1.0 (2020-02-26)
==================

- The first release of Safir featuring:

  - ``safir.http`` for adding an ``aiohttp.ClientSession`` to your application.
  - ``safir.logging`` for configuring structlog loggers.
  - ``safir.metadata`` helps your gather and structure metadata about your application for publishing on metadata endpoints.
  - ``safir.middleware`` includes a logging middleware that adds a logger with bound context about the request to your Request object.
  - Documentation about these features and a tutorial for starting a new application with the ``roundtable_aiohttp_bot`` template.
