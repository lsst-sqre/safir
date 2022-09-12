# Safir

Safir is Rubin Observatory's library for building [FastAPI](https://fastapi.tiangolo.com/) services for the [Rubin Science Platform (Phalanx)](https://github.com/lsst-sqre/phalanx) and [Roundtable](https://github.com/lsst-sqre/roundtable) Kubernetes clusters.
Safir is developed, maintained, and field tested by the SQuaRE team.

Safir is available from [PyPI](https://pypi.org/project/safir/):

```sh
pip install safir
```

The best way to create a new FastAPI/Safir service is with the [`fastapi_safir_app` template](https://github.com/lsst/templates/blob/main/project_templates/fastapi_safir_app).

Read more about Safir at https://safir.lsst.io.

## Features

- Set up an `httpx.AsyncClient` as part of the application start-up and shutdown lifecycle.
- Set up structlog-based logging.
- Middleware for attaching request context to the logger to include a request UUID, method, and route in all log messages.
- Process `X-Forwarded-*` headers to determine the source IP and related information of the request.
- Gather and structure standard metadata about your application.
- Operate a distributed Redis job queue with [arq](https://arq-docs.helpmanual.io) using convenient clients, testing mocks, and a FastAPI dependency.

## Developing Safir

The best way to start contributing to Safir is by cloning this repository creating a virtual environment, and running the init command:

```sh
git clone https://github.com/lsst-sqre/safir.git
cd safir
make init
```

For details, see https://safir.lsst.io/dev/development.html.
