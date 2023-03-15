"""Send messages to Slack."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, ClassVar, Optional

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from structlog.stdlib import BoundLogger

from ..datetime import current_datetime, format_datetime_for_logging
from ..dependencies.http_client import http_client_dependency
from .blockkit import (
    SlackCodeBlock,
    SlackException,
    SlackMessage,
    SlackTextField,
)

__all__ = [
    "SlackIgnoredException",
    "SlackRouteErrorHandler",
    "SlackWebhookClient",
]


class SlackIgnoredException(Exception):
    """Parent class for exceptions that should not be reported to Slack.

    This exception has no built-in behavior or meaning except to suppress
    Slack notifications if it is thrown uncaught.  Application exceptions that
    should not result in a Slack alert (because, for example, they're intended
    to be caught by exception handlers) should inherit from this class.
    """


class SlackWebhookClient:
    """Send messages to a Slack webhook.

    Provides a simple Slack client to publish structured messages to a Slack
    channel via an incoming webhook using the Block Kit API. This is a
    write-only client and cannot be used for prompting or more complex apps.

    Parameters
    ----------
    hook_url
        URL of the Slack incoming webhook to use for publishing messages.
    application
        Name of the application reporting an error, used by the error
        reporting methods.
    logger
        Logger to which to report errors sending messages to Slack.
    """

    def __init__(
        self, hook_url: str, application: str, logger: BoundLogger
    ) -> None:
        self._hook_url = hook_url
        self._application = application
        self._logger = logger

    async def post(self, message: SlackMessage) -> None:
        """Post a message to Slack.

        Any exceptions encountered while posting the message will be logged
        but not raised. From the perspective of the caller, the message will
        silently disappear.

        Parameters
        ----------
        message
            Message to post.
        """
        self._logger.debug("Sending message to Slack")
        body = message.to_slack()
        try:
            client = await http_client_dependency()
            r = await client.post(self._hook_url, json=body)
            r.raise_for_status()
        except Exception:
            msg = "Posting Slack message failed"
            self._logger.exception(msg, message=body)

    async def post_exception(self, exc: SlackException) -> None:
        """Post an alert to Slack about an exception.

        This method intentionally does not provide a way to include the
        traceback, since it's hard to ensure that the traceback is entirely
        free of secrets or other information that should not be disclosed on
        Slack. Only the exception message is reported.

        Parameters
        ----------
        exc
            The exception to report.
        """
        message = exc.to_slack()
        message.message = f"Error in {self._application}: {message.message}"
        await self.post(message)

    async def post_uncaught_exception(self, exc: Exception) -> None:
        """Post an alert to Slack about an uncaught webapp exception.

        Parameters
        ----------
        exc
            The exception to report.
        """
        if isinstance(exc, SlackException):
            message = exc.to_slack()
            msg = f"Uncaught exception in {self._application}: {str(exc)}"
            message.message = msg
        else:
            date = format_datetime_for_logging(current_datetime())
            name = type(exc).__name__
            error = f"{name}: {str(exc)}"
            message = SlackMessage(
                message=f"Uncaught exception in {self._application}",
                fields=[
                    SlackTextField(heading="Exception type", text=name),
                    SlackTextField(heading="Failed at", text=date),
                ],
                blocks=[SlackCodeBlock(heading="Exception", code=error)],
            )
        await self.post(message)


class SlackRouteErrorHandler(APIRoute):
    """Custom `fastapi.routing.APIRoute` that reports exceptions to Slack.

    Dynamically wrap FastAPI route handlers in an exception handler that
    reports uncaught exceptions (other than :exc:`fastapi.HTTPException`,
    :exc:`fastapi.exceptions.RequestValidationError`,
    :exc:`starlette.exceptions.HTTPException`, and exceptions inheriting from
    `SlackIgnoredException`) to Slack.

    This class must be initialized by calling its `initialize` method to send
    alerts. Until that has been done, it will silently do nothing.

    Examples
    --------
    Specify this class when creating a router. All uncaught exceptions from
    handlers managed by that router will be reported to Slack, if Slack alerts
    are configured.

    .. code-block:: python

       router = APIRouter(route_class=SlackRouteErrorHandler)

    Notes
    -----
    Based on `this StackOverflow question
    <https://stackoverflow.com/questions/61596911/>`__.
    """

    _IGNORED_EXCEPTIONS = (
        HTTPException,
        RequestValidationError,
        StarletteHTTPException,
        SlackIgnoredException,
    )
    """Uncaught exceptions that should not be sent to Slack."""

    _alert_client: ClassVar[Optional[SlackWebhookClient]] = None
    """Global Slack alert client used by `SlackRouteErrorHandler`.

    Initialize with `initialize`. This object caches the alert confguration
    and desired logger for the use of `SlackRouteErrorHandler` as a
    process-global variable, since the route handler only has access to the
    incoming request and global variables.
    """

    @classmethod
    def initialize(
        cls, hook_url: str, application: str, logger: BoundLogger
    ) -> None:
        """Configure Slack alerting.

        Until this function is called, all Slack alerting for uncaught
        exceptions will be disabled.

        Parameters
        ----------
        hook_url
            The URL of the incoming webhook to use to publish the message.
        application
            Name of the application reporting an error.
        logger
            Logger to which to report errors sending messages to Slack.
        """
        cls._alert_client = SlackWebhookClient(hook_url, application, logger)

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap route handler with an exception handler."""
        original_route_handler = super().get_route_handler()

        async def wrapped_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except Exception as e:
                if isinstance(e, self._IGNORED_EXCEPTIONS):
                    raise
                if not self._alert_client:
                    raise
                await self._alert_client.post_uncaught_exception(e)
                raise

        return wrapped_route_handler
