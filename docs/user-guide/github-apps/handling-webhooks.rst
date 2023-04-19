########################
Handling GitHub webhooks
########################

A common use for a GitHub App integration in Safir/FastAPI applications is to handle webhooks from GitHub.
With webhooks, your app can be triggered by events like pushes or pull requests to a repository, and even implement a GitHub Check for pull requests.
Gidgethub_ provides a routing system for handling webhooks.
This page shows how to integrate Gidgethub into a Safir/FastAPI application and use the resource models in `safir.github`.

Adding FastAPI handler for GitHub webhooks
==========================================

The first step is to add a FastAPI handler for the webhook endpoint.
The URL path for this endpoint corresponds to the webhook callback URL you set up in the GitHub App's settings.

.. code-block:: python
   :caption: handlers.py

   import httpx
   from fastapi import APIRouter, Depends, Request, Response, status
   from gidgethub.sansio import Event
   from safir.dependencies.logger import logger_dependency
   from structlog.stdlib import BoundLogger

   external_router = APIRouter()
   """FastAPI router for all external handlers."""


   @external_router.post(
       "/github/webhook",
       summary="GitHub App webhook",
       description=("This endpoint receives webhook events from GitHub"),
       status_code=status.HTTP_200_OK,
   )
   async def post_github_webhook(
       request: Request,
       logger: BoundLogger = Depends(logger_dependency),
   ) -> Response:
       """Process GitHub webhook events."""
       webhook_secret = config.github_webhook_secret.get_secret_value()
       event = Event.from_http(request.headers, body, secret=webhook_secret)

       # Bind the X-GitHub-Delivery header to the logger context; this identifies
       # the webhook request in GitHub's API and UI for diagnostics
       logger = logger.bind(github_delivery=event.delivery_id)

       logger.debug("Received GitHub webhook", payload=event.data)
       # Give GitHub some time to reach internal consistency.
       await asyncio.sleep(1)
       await webhook_router.dispatch(event, logger)

       return Response(status_code=status.HTTP_202_ACCEPTED)

Note how a webhook_secret is passed to the ``Event.from_http`` contrucstor.
You'll set up this secret in the GitHub App's settings, and its used to verify that the webhook request is coming from GitHub.

The ``webhook_router`` is a Gidgethub_ ``Router`` instance that dispatches webhook events to the appropriate handler in your application, as you'll see next.

.. tip::

   Notice how the FastAPI handler sleeps for one second before dispatching the webhook event to the ``webhook_router``.
   This is based on common advice to wait for the GitHub API to reach consistency before processing the webhook event and making API calls to GitHub based on the new event.
   You can experiement with delay, move it to other parts of the app (for example, to right before submitting a new requests to GitHub) or drop the delay altogether.

.. _webhook-handler-functions:

Adding a GitHub webhook handler
===============================

Just as your FastAPI application has a "handler" module containing a FastAPI ``APIRouter`` and individual FastAPI handler functions, your GitHub App integration will have a "webhook" module containing a Gidgethub_ ``Router`` and individual webhook handlers.

The Gidgethub_ `~gidgethub.routing.Router` class should be set up as a module-level variable:

.. code-block:: python
   :caption: webhooks.py

   from gidgethub import routing

   webhook_router = routing.Router()

The ``webhook_router`` is then used to register webhook handlers for specific events.
For example, to handle the ``push`` event, you would add a handler function like this:

.. code-block:: python
   :caption: webhooks.py

   @webhook_router.register("push")
   async def handle_push(
       event: gidgethub.sansio.Event, logger: BoundLogger
   ) -> None:
       """Handle push events."""
       logger.info("Received push event", payload=event.data)

The argument to the ``register`` decorator is the name of the GitHub event that the decorated function should handle.
GitHub provides `a listing of all the events <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads>`__ that can be handled by a GitHub App.

Many events have multiple *actions* associated with them.
For example, a pull request could be opened, closed, or merged, among other possibilities.
The names of these actions correspond to the ``action`` field in the event's webhook payload.
To scope a handler to a specific action, you can pass its name to the ``action`` keyword argument of the ``register`` decorator:

.. code-block:: python
   :caption: webhooks.py

   @webhook_router.register("pull_request", action="opened")
   async def handle_pull_request_opened(
       event: gidgethub.sansio.Event, logger: BoundLogger
   ) -> None:
       """Handle pull request opened events."""
       logger.info(
           f"Received {event.event} {event.data.action} event",
           event=event.event,
           action=event.data.action,
           payload=event.data,
       )

Parsing webhook payloads into Pydantic objects
==============================================

Safir provides Pydantic models for relevant GitHub event payloads.
You can find a listing of these models and their corresponding webhook events in :doc:`webhook-models`.
You can parse the ``event.data`` attribute into a Pydantic model using the ``parse_obj`` method:

.. code-block:: python
   :caption: webhooks.py

   from safir.github.webhooks import GitHubPullRequestEventModel


   @webhook_router.register("pull_request", action="opened")
   async def handle_pull_request_opened(
       event: gidgethub.sansio.Event, logger: BoundLogger
   ) -> None:
       """Handle pull request opened events."""
       pull_request_event = GitHubPullRequestEventModel.parse_obj(event.data)
       logger.info(
           f"Received {event.event} {event.data.action} event",
           event=event.event,
           action=event.data.action,
           payload=pull_request_event.dict(),
           number=pull_request_event.number,
       )

Now your application can access the parsed payload as a Pydantic model, with type hints and validation.

Handling webhook events with resiliance
=======================================

A good webhook client needs to handle a webhook event quickly and return a response (usually a 202 Accepted) to GitHub as soon as possible, regardless of whether the action triggered by the event succeeded or not.
The best way to do this is to have the webhook handler (as discussed in :ref:`webhook-handler-functions`) simply parse the event data and spawn a background task to handle the event.
There are many ways to create a background task.

In-process background task
--------------------------

The simplest background tasks are handled in-process with asyncio-based task managers.
In FastAPI applications, you can create a `Starlette BackgroundTask <https://www.starlette.io/background/>`__ (see also the `FastAPI BackgroundTasks <https://fastapi.tiangolo.com/tutorial/background-tasks/>`__ documentation).
Another option is to use `aiojobs <https://aiojobs.readthedocs.io/en/stable/index.html>`_, which is a more general-purpose asyncio background task library.
The downside of both these approaches is that the background tasks run in the same process as the API server.
This can cause the server to become loaded with tasks.
And if the server crashes, the tasks are lost.

Distributed queue
-----------------

The recommended approach for handling webhooks is to process them in a distributed queue.
This has the advantage of decoupling the API server from background task processing.
Multiple workers (typically an independent ``Deployment`` in Kubernetes) can be configured to process the queue.
Further, a persistent store like Redis holds the task queue and its results so that event processing is resiliant to individual pod restarts.
For Safir/FastAPI applications, the recommended queue library is arq_, which is a Redis-backed queue library that is built on top of asyncio.
See the :doc:`../arq` documentation for more information.

Next steps
==========

More documentation for integrating with GitHub webhooks:

- :doc:`webhook-models` — Pydantic models for GitHub webhook payloads
- :doc:`api-resources` — Pydantic models for GitHub API resources, often found in webhooks and API responses
- :doc:`create-a-github-client` — Often webhook handlers need to make requests back to GitHub. This documentation shows how to create an authenticated client to do so.
