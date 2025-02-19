.. currentmodule:: safir.arq.uws

########################
Write the backend worker
########################

The backend worker is the heart of the application.
This is where you do the real work of the service.

A backend worker is a sync Python function that takes three arguments as input:

#. The worker parameters model (see :ref:`uws-worker-model`).
#. Metadata about the UWS job, including authentication credentials from the user's request that can be used to make requests of other services.
#. A structlog_ `~structlog.stdlib.BoundLogger` to use for logging.

The backend worker must return a list of `WorkerResult` objects.
Each contains a name for the result, the ``s3`` or ``gs`` URL to where the result is stored in a Google Cloud Storage bucket, and the MIME type and (optionally) the size of the result.

All results must be stored in Google Cloud Storage currently.
No other backend store for results is supported.
The frontend for your application will use signed GCS URLs to allow the client to retrieve the results.

The backend worker will need the safir-arq PyPI package installed, and usually will need the google-cloud-storage PyPI package as well.

Structure of the worker
=======================

The backend worker should be defined in a single file in the :file:`workers` directory of your application source.
This file may include other modules in your application source.
It will, for example, generally include the module that defines the worker parameter model created in :ref:`uws-worker-model`.

However, be aware that the worker will run in a different Python environment than the frontend (usually a Rubin pipelines container).
It therefore must not include any portion of the application source that requires additional dependencies such as FastAPI, and it must not include general Safir modules.
Normally it should only include the worker parameter model, `safir.arq`, `safir.arq.uws`, `safir.logging`, and any other Python modules that are available in the backend Python environment.

The backend worker should also target the version of Python provided by its base container, which may be different (usually older) than the version of Python used by the frontend.

Here is the rough shape of the module that defines this worker:

.. code-block:: python
   :caption: workers/example.py

   import os

   import structlog
   from safir.arq.uws import (
       WorkerConfig,
       WorkerJobInfo,
       WorkerResult,
       build_worker,
   )
   from safir.logging import configure_logging


   def example(
       params: WorkerCutout, info: WorkerJobInfo, logger: BoundLogger
   ) -> list[WorkerResult]: ...


   configre_logging(
       name="example",
       profile=os.getenv("EXAMPLE_PROFILE", "development"),
       log_level=os.getenv("EXAMPLE_LOG_LEVEL", "INFO"),
   )

   WorkerSettings = build_worker(
       example,
       WorkerConfig(
           arq_mode=ArqMode.production,
           arq_queue_url=os.environ["EXAMPLE_ARQ_QUEUE_URL"],
           arq_queue_password=os.getenv("EXAMPLE_ARQ_QUEUE_PASSWORD"),
           grace_period=timedelta(
               seconds=int(os.environ["EXAMPLE_GRACE_PERIOD"])
           ),
           parameters_class=WorkerCutout,
           timeout=timedelta(seconds=int(os.environ["EXAMPLE_TIMEOUT"])),
       ),
       structlog.get_logger("example"),
   )

In this case, the worker function is ``example``.
It must return a list of `WorkerResult` objects.
For sync requests, if supported, the first element of that list is the one that will be returned as the result of the request.

The call to `build_worker` creates the necessary arq_ configuration that allows this module to be used as the module defining an arq worker.
Notice that some configuration information has to be duplicated from the main application configuration, but cannot reuse the same model because pydantic-settings may not be available in the worker.
The corresponding environment variables are therefore used directly.

The ``parameters_class`` argument must be the model defined in :ref:`uws-worker-model`.

Reporting errors
================

The :mod:`safir.arq.uws` module provides exceptions that should be used to wrap all errors encountered during backend processing.
These exceptions ensure that the backtrace of the error is serialized properly and included in the job results so that it can be reported to the user via the frontend.
They are `WorkerFatalError`, `WorkerTransientError`, `WorkerTimeoutError`, and `WorkerUsageError`.

Their meanings are somewhat obvious.
A transient error is one that may resolve if the user simply submits the job again.
`WorkerUsageError` should be used in cases where the job parameters are invalid in a way that couldn't be detected in the frontend.

Except for `WorkerTimeoutError`, all of these exceptions take two arguments and a flag.
The first argument is the normal exception message.
The second, optional argument can be used to provide additional details about the failure.

The flag, ``add_traceback``, should be set to `True` if the traceback of the underlying exception should be reported to the user.
The default is `False`.
Do not set this to `True` if the traceback may contain secrets or other private data that shouldn't be exposed to the user.
If set to true, make sure that the exception is raised with a ``from`` clause that references the underlying exception.
It is the traceback of that exception that will be reported to the user.

`WorkerTimeoutError` takes two arguments: the total elapsed time and the timeout that was exceeded.
It is normally handled automatically by the wrapper added by `build_worker`, but it can be thrown directly by the backend code if it detects a timeout.
The relevant timeout should be the ``timeout`` member of the `WorkerJobInfo` object described below.

Here is a simple example that calls a ``do_work`` function and translates all exceptions into `WorkerFatalError` with tracebacks reported to the user:

.. code-block:: python

   from safir.arq.uws import WorkerFatalError, WorkerJobInfo, WorkerResult
   from structlog.stdlib import BoundLogger

   from ..models.domain.cutout import WorkerCutout


   def example(
       params: WorkerCutout, info: WorkerJobInfo, logger: BoundLogger
   ) -> list[WorkerResult]:
       try:
           result_url = do_work()
       except Exception as e:
           raise WorkerFatalError(f"{type(e).__name__}: {e!s}") from e
       return [WorkerResult(result_id="example", url=result_url)]

Job metadata
============

The second argument to the worker function is a `WorkerJobInfo` object.
It includes things like the user who submitted the job, the UWS job ID and (if given) run ID, and so forth.
See its documentation for a full list.
There are two attributes that deserve special mention, however.

The ``token`` attribute contains a delegated Gafaelfawr_ token to act on behalf of the user.
This token must be included in an :samp:`Authorization: bearer {token}` header in any web request that the backend makes to other Rubin Science Platform services.

The ``timeout`` attribute contains a `~datetime.timedelta` representation of the timeout for the job.
The backend ideally should arrange to not exceed that total wall clock interval when executing.
If it does take longer, it will be killed.
See :ref:`uws-aborted-jobs`.

.. _uws-aborted-jobs:

Aborting jobs
=============

The arq_ queuing system normally assumes that all job handlers are async.
The UWS library is designed to instead support sync backend worker functions, since the Rubin Observatory scientific code is generally written in sync Python.
This unfortunately means that the normal asyncio mechanisms for handling timeouts and canceling jobs do not work with these backend workers.

The Safir UWS library works around this with a somewhat ugly hack.
The backend job is run in a separate process, using `concurrent.futures.ProcessPoolExecutor` with a single pool process.
If the job times out or is aborted by arq_, the process running the backend code is killed with SIGINT and then the process pool is cleaned up and recreated.

This should mostly be transparent to you when writing backend worker functions.
The only caveat to be aware of is that your function may receive a SIGINT if it has to be aborted, which Python by default will translate into a `KeyboardInterrupt` exception.
Any temporary resources which need to be cleaned up when the job is aborted should be handled with context managers or ``finally`` blocks.

If you replace the default SIGINT handler, you will need to take your own steps to ensure that the backend worker exits quickly and cleans up properly on receipt of a SIGINT signal.
Otherwise, you may hang the arq backend worker and prevent the service from working correctly.

Register the worker
===================

Now that you have written the worker, add the name of the worker function to the `~safir.uws.UWSAppSettings.build_uws_config` call in your ``Config`` class, as mentioned in :ref:`uws-config`.
It should be passed as the value of the ``worker`` argument.

This argument should be the name of the backend worker function as a string.
In the above example, it would be ``"example"``.
It is *not* the function itself, just the name of the function as a Python string.

Build the backend worker Docker image
=====================================

The backend worker will generally use a separate Docker image from the frontend and database worker.
This allows it to use a different software stack, such as the Science Pipelines Docker image.
You will then need to install the backend worker code and its prerequisites so that it's suitable for use as an arq worker.

The backend worker image must have a suitable Python 3.12 or later with Pydantic_ and structlog_.
On top of this, install the safir-arq PyPI package, which contains just the portions of Safir required to talk to arq and create a backend worker, and the safir-logging PyPI package, which contains the code to configure structlog.

Finally, install your application, but without its dependencies.
This will ensure the worker code and the models it uses are available, but will not require all of the application dependencies such as Safir and FastAPI to be installed.
You can do this with a command such as:

.. code-block:: bash

   pip install --no-cache-dir --no-deps .

Next steps
==========

- Write a test suite :doc:`testing`
