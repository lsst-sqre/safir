.. currentmodule:: safir.testing.uws

########################
Testing UWS applications
########################

UWS applications are arq_ applications, and therefore should follow the testing advice in :ref:`arq-testing`.
This includes testing the frontend and the backend worker separately.

The :mod:`safir.testing.uws` module provides some additional support to make it easier to test the frontend.

Frontend testing fixtures
=========================

The frontend of a UWS application assumes that arq_ will execute both jobs and the database worker that recovers the results of a job and stores them in the database.
During testing of the frontend, arq will not be running, and therefore this execution must be simulated.
This is done with the `MockUWSJobRunner` class, but it requires some setup.

Mock the arq queue
------------------

First, the application must be configured to use a `~safir.arq.MockArqQueue` class instead of one based on Redis.
This stores all queued jobs in memory and provides some test-only methods to manipulate them.

To do this, first set up a fixture in :file:`tests/conftest.py` that provides a mock arq queue:

.. code-block:: python
   :caption: tests/conftest.py

   import pytest
   from safir.arq import MockArqQueue


   @pytest.fixture
   def arq_queue() -> MockArqQueue:
       return MockArqQueue()

Then, configure the application to use that arq queue instead of the default one in the ``app`` fixture.

.. code-block:: python
   :caption: tests/conftest.py
   :emphasize-lines: 8,14

   from collections.abc import AsyncIterator

   from asgi_lifespan import LifespanManager
   from fastapi import FastAPI
   from safir.arq import MockArqQueue

   from example import main
   from example.config import uws


   @pytest_asyncio.fixture
   async def app(arq_queue: MockArqQueue) -> AsyncIterator[FastAPI]:
       async with LifespanManager(main.app):
           uws.override_arq_queue(arq_queue)
           yield main.app

Provide a test database
-----------------------

UWS relies on database in which to store job information and results.
Follow the instructions in :doc:`/user-guide/database/testing` to use tox-docker_ to create a test PostgreSQL database, but skip the instructions there for initializing the database.
Instead, use the UWS library to initialize the resulting database:

.. code-block:: python
   :caption: tests/conftest.py
   :emphasize-lines: 3,14-15

   from collections.abc import AsyncIterator

   import structlog
   from asgi_lifespan import LifespanManager
   from fastapi import FastAPI
   from safir.arq import MockArqQueue

   from example import main
   from example.config import uws


   @pytest_asyncio.fixture
   async def app(arq_queue: MockArqQueue) -> AsyncIterator[FastAPI]:
       logger = structlog.get_logger("example")
       await uws.initialize_uws_database(logger, reset=True)
       async with LifespanManager(main.app):
           uws.override_arq_queue(arq_queue)
           yield main.app

Mock Google Cloud Storage
-------------------------

The UWS library assumes results are in Google Cloud Storage and creates signed URLs to allow the client to retrieve those results.
This support needs to be mocked out during testing.
Do this by adding the following fixture to :file:`tests/conftest.py`:

.. code-block:: python
   :caption: tests/conftest.py

   from datetime import timedelta

   import pytest
   from safir.testing.gcs import MockStorageClient, patch_google_storage


   @pytest.fixture(autouse=True)
   def mock_google_storage() -> Iterator[MockStorageClient]:
       yield from patch_google_storage(
           expected_expiration=timedelta(minutes=15), bucket_name="some-bucket"
       )

See :ref:`gcs-testing` for more information.

Provide a mock arq queue runner
-------------------------------

Finally, you can create a fixture that provides a mock arq queue runner.
This will simulate not only the execution of a backend worker that results some result, but also the collection of that result and subsequent database updates.

.. code-block:: python
   :caption: tests/conftest.py

   from collections.abc import AsyncIterator

   import pytest_asyncio
   from safir.arq import MockArqQueue
   from safir.testing.uws import MockUWSJobRunner

   from example.config import config


   @pytest_asyncio.fixture
   async def runner(
       arq_queue: MockArqQueue,
   ) -> AsyncIterator[MockUWSJobRunner]:
       async with MockUWSJobRunner(config.uws_config, arq_queue) as runner:
           yield runner

Writing a frontend test
=======================

Now, all the pieces are in place to write a meaningful test of the frontend.
You can use the methods of `MockUWSJobRunner` to change the state of a mocked backend job and set the results that it returned.
Here is an example of a test of a hypothetical cutout service.

.. code-block:: python
   :caption: tests/handlers/async_test.py

   import pytest
   from httpx import AsyncClient
   from safir.testing.uws import MockUWSJobRunner


   @pytest.mark.asyncio
   async def test_create_job(
       client: AsyncClient, runner: MockUWSJobRunner
   ) -> None:
       r = await client.post(
           "/api/cutout/jobs",
           headers={"X-Auth-Request-User": "someone"},
           data={"ID": "1:2:band:value", "Pos": "CIRCLE 0 1 2"},
       )
       assert r.status_code == 303
       assert r.headers["Location"] == "https://example.com/api/cutout/jobs/1"
       await runner.mark_in_progress("someone", "1")

       async def run_job() -> None:
           results = [
               UWSJobResult(
                   result_id="cutout",
                   url="s3://some-bucket/some/path",
                   mime_type="application/fits",
               )
           ]
           await runner.mark_complete("someone", "1", results, delay=0.2)

       _, r = await asyncio.gather(
           run_job(),
           client.get(
               "/api/cutout/jobs/1",
               headers={"X-Auth-Request-User": "someone"},
               params={"wait": 2, "phase": "EXECUTING"},
           ),
       )
       assert r.status_code == 200
       assert "https://example.com/some/path" in r.text

Note the use of `MockUWSJobRunner.mark_complete` with a ``delay`` argument and `asyncio.gather` to simulate a job that takes some time to complete so that the client request to wait for job completion can be tested.

A more sophisticated test would check the XML results returned by the API against the UWS XML schema.
This can be done using the models provided by vo-models_.

Testing the backend worker
==========================

The backend divides naturally into two pieces: the wrapper code that accepts the arguments in the format passed by the UWS library, handles exceptions, and constructs `~safir.arq.uws.WorkerResult` objects; and the code that performs the underlying operation of the service.

To make testing easier, it's usually a good idea to separate those two pieces.
The wrapper that handles talking to the UWS library and translating exceptions can be included in the source of the application.
The underlying code to perform the operation is often best maintained in a library of domain-specific code.
For example, for Rubin Observatory, this will usually be a function in a Science Pipelines package with its own separate tests.

If the code is structured this way, there won't be much to test in the backend worker wrapper and often one can get away with integration tests.
If more robust tests are desired, though, the backend worker function is a simple function that can be called and tested directly by the test suite, possibly after mocking out the underlying library function.
