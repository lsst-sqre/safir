.. currentmodule:: safir.arq

###############################################
Using the arq Redis queue client and dependency
###############################################

Distributed queues allow your application to decouple slow-running processing tasks from your user-facing endpoint handlers.
arq_ is a simple distributed queue library with an asyncio API that uses Redis to store both queue metadata and results.
To simplify integrating arq_ into your FastAPI application and test suites, Safir both an arq client (`~safir.arq.ArqQueue`) with a drop-in mock for testing and an endpoint handler dependency (`safir.dependencies.arq`) that provides an arq_ client.

For information on using arq in general, see the `arq documentation <https://arq-docs.helpmanual.io>`_.
For real-world examples of how this dependency, and arq-based distributed queues in general are used in FastAPI apps, see our `Times Square <https://github.com/lsst-sqre/times-square>`__ and `Noteburst <https://github.com/lsst-sqre/noteburst>`__ applications.

Quick start
===========

.. _arq-dependency-setup:

Dependency set up and configuration
-----------------------------------

In your application's FastAPI setup module, typically :file:`main.py`, you need to initialize `safir.dependencies.arq.ArqDependency` during the start up event:

.. code-block:: python

    from fastapi import Depends, FastAPI
    from safir.dependencies.arq import arq_dependency

    app = FastAPI()


    @app.on_event("startup")
    async def startup() -> None:
        await arq_dependency.initialize(
            mode=config.arq_mode, redis_settings=config.arq_redis_settings
        )

The ``mode`` parameter for `safir.dependencies.arq.ArqDependency.initialize` takes `ArqMode` enum values of either ``"production"`` or ``"test"``. The ``"production"`` mode configures a real arq_ queue backed by Redis, whereas ``"test"`` configures a mock version of the arq_ queue.

Running under the regular ``"production"`` mode, you need to provide a `arq.connections.RedisSettings` instance.
If your app uses a configuration system like ``pydantic.BaseSettings``, this example ``Config`` class shows how to create a `~arq.connections.RedisSettings` object from a regular Redis URI:

.. code-block:: python

    from urllib.parse import urlparse

    from arq.connections import RedisSettings
    from pydantic import BaseSettings, Field, RedisDsn
    from safir.arq import ArqMode


    class Config(BaseSettings):
        arq_queue_url: RedisDsn = Field(
            "redis://localhost:6379/1", env="APP_ARQ_QUEUE_URL"
        )

        arq_mode: ArqMode = Field(ArqMode.production, env="APP_ARQ_MODE")

        @property
        def arq_redis_settings(self) -> RedisSettings:
            """Create a Redis settings instance for arq."""
            url_parts = urlparse(self.redis_queue_url)
            redis_settings = RedisSettings(
                host=url_parts.hostname or "localhost",
                port=url_parts.port or 6379,
                database=int(url_parts.path.lstrip("/"))
                if url_parts.path
                else 0,
            )
            return redis_settings

Worker set up
-------------

Workers that run queued tasks are separate application deployments, though they can (but don't necessarily need to) operate from the same codebase as the FastAPI-based front-end application.
A convenient pattern is to co-locate the worker inside a ``worker`` sub-package:

.. code-block:: text

   .
   ├── src
   │   └── yourapp
   │       ├── __init__.py
   │       ├── config.py
   │       ├── main.py
   │       └── worker
   │           ├── __init__.py
   │           ├── functions
   │           │   ├── __init__.py
   │           │   ├── function_a.py
   │           │   └── function_b.py
   │           ├── main.py

The :file:`src/yourapp/worker/main.py` module looks like:

.. code-block:: python

    from __future__ import annotations

    import uuid
    from typing import Any

    import httpx
    import structlog
    from safir.logging import configure_logging

    from ..config import config
    from .functions import function_a, function_b


    async def startup(ctx: dict[Any, Any]) -> None:
        """Runs during worker start-up to set up the worker context."""
        configure_logging(
            profile=config.profile,
            log_level=config.log_level,
            name="yourapp",
        )
        logger = structlog.get_logger("yourapp")
        # The instance key uniquely identifies this worker in logs
        instance_key = uuid.uuid4().hex
        logger = logger.bind(worker_instance=instance_key)

        http_client = httpx.AsyncClient()
        ctx["http_client"] = http_client

        ctx["logger"] = logger
        logger.info("Worker start up complete")


    async def shutdown(ctx: dict[Any, Any]) -> None:
        """Runs during worker shutdown to cleanup resources."""
        if "logger" in ctx.keys():
            logger = ctx["logger"]
        else:
            logger = structlog.get_logger("yourapp")
        logger.info("Running worker shutdown.")

        try:
            await ctx["http_client"].aclose()
        except Exception as e:
            logger.warning("Issue closing the http_client: %s", str(e))

        logger.info("Worker shutdown complete.")


    class WorkerSettings:
        """Configuration for the arq worker.

        See `arq.worker.Worker` for details on these attributes.
        """

        functions = [function_a, function_b]

        redis_settings = config.arq_redis_settings

        on_startup = startup

        on_shutdown = shutdown

The ``WorkerSettings`` class is where you configure the queue and declare worker functions.
See `arq.worker.Worker` for details.

The ``on_startup`` and ``on_shutdown`` handlers are ideal places to set up (and tear down) worker state, including network and database clients.
The context variable, ``ctx``, passed to these functions are also passed to the worker functions.

To run a worker, you run your application's Docker image with the ``arq`` command, followed by the fully-qualified namespace of the ``WorkerSettings`` class.

Using the arq dependency in endpoint handlers
---------------------------------------------

The `safir.dependencies.arq.arq_dependency` dependency provides your FastAPI endpoint handlers with an `ArqQueue` client that you can use to add jobs (`ArqQueue.enqueue`) to the queue, and get metadata (`ArqQueue.get_job_metadata`) and results (`ArqQueue.get_job_result`) from the queue:

.. code-block:: python

    from typing import Any

    from fastapi import Depends, HTTPException
    from safir.arq import ArqQueue
    from safir.dependencies.arq import arq_dependency


    @app.post("/jobs")
    async def post_job(
        arq_queue: ArqQueue = Depends(arq_dependency),
        a: str = "hello",
        b: int = 42,
    ) -> dict[str, Any]:
        """Create a job."""
        job = await arq_queue.enqueue("test_task", a, a_number=b)
        return {"job_id": job.id}


    @app.get("/jobs/{job_id}")
    async def get_job(
        job_id: str,
        arq_queue: ArqQueue = Depends(arq_dependency),
    ) -> dict[str, Any]:
        """Get metadata about a job."""
        try:
            job = await arq_queue.get_job_metadata(
                job_id, queue_name=queue_name
            )
        except JobNotFound:
            raise HTTPException(status_code=404)

        response = {
            "id": job.id,
            "status": job.status,
            "name": job.name,
            "args": job.args,
            "kwargs": job.kwargs,
        }

        if job.status == JobStatus.complete:
            try:
                job_result = await arq_queue.get_job_result(
                    job_id, queue_name=queue_name
                )
            except (JobNotFound, JobResultUnavailable):
                raise HTTPException(status_code=404)
            response["result"] = job_result.result

        return response

For information on the metadata available from jobs, see `JobMetadata` and `JobResult`.

Testing applications with an arq queue
======================================

Unit testing an application with a running distributed queue is difficult since three components (two instances of the application and a redis database) must coordinate.
A better unit testing approach is to test the front-end application separately from the worker functions.
To help you do this, the arq dependency allows you to run a mocked version of an arq queue.
With the mocked client, your front-end application can run the three basic client methods as normal: `ArqQueue.enqueue`, `ArqQueue.get_job_metadata`, and `ArqQueue.get_job_result`).
This mocked client is a subclass of `ArqQueue` called `MockArqQueue`.

Configuring the test mode
-------------------------

You get a `MockArqQueue` from the `safir.dependencies.arq.arq_dependency` instance by passing a `ArqMode.test` value to the ``mode`` argument of `safir.dependencies.arq.ArqDependency.initialize` in your application's start up (see :ref:`arq-dependency-setup`).
As the above example shows, you can make this an environment variable configuration, and then set the arq mode in your tox settings.

Interacting with the queue state
--------------------------------

Your tests can add jobs and get job metadata or results using the normal code paths.
Since queue jobs never run, your test code needs to manually change the status of jobs and set job results.
You can do this by manually calling the `safir.dependencies.arq.arq_dependency` instance from your test (a `MockArqQueue`) and using the `MockArqQueue.set_in_progress` and `MockArqQueue.set_complete` methods.

This example adapted from Noteburst shows how this works:

.. code-block:: python

    from safir.arq import MockArqQueue
    from safir.dependencies.arq import arq_dependency


    @pytest.mark.asyncio
    async def test_post_nbexec(
        client: AsyncClient, sample_ipynb: str, sample_ipynb_executed: str
    ) -> None:
        arq_queue = await arq_dependency()
        assert isinstance(arq_queue, MockArqQueue)

        response = await client.post(
            "/noteburst/v1/notebooks/",
            json={
                "ipynb": sample_ipynb,
                "kernel_name": "LSST",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        job_url = response.headers["Location"]
        job_id = data["job_id"]

        # Toggle the job to in-progress; the status should update
        await arq_queue.set_in_progress(job_id)

        response = await client.get(job_url)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"

        # Toggle the job to complete
        await arq_queue.set_complete(job_id, result=sample_ipynb_executed)

        response = await client.get(job_url)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["success"] is True
        assert data["ipynb"] == sample_ipynb_executed
