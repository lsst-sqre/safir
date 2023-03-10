"""Send messages to Slack."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, root_validator, validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from structlog.stdlib import BoundLogger

from safir.datetime import current_datetime, format_datetime_for_logging
from safir.dependencies.http_client import http_client_dependency

__all__ = [
    "SlackClient",
    "SlackException",
    "SlackIgnoredException",
    "SlackField",
    "SlackIgnoredException",
    "SlackMessage",
    "SlackRouteErrorHandler",
]


class SlackField(BaseModel):
    """A component of a Slack message with a heading.

    Intended for use in the ``fields`` portion of a Block Kit message. If the
    formatted output is longer than 2000 characters, it will be truncated to
    avoid the strict upper limit imposed by Slack.
    """

    heading: str
    """Heading of the field (shown in bold)."""

    text: Optional[str] = None
    """Text of the field as normal text (use this or ``code``).

    This is always marked as vertabim, so channel mentions or @-mentions of
    users will not be treated as special.
    """

    code: Optional[str] = None
    """Text of the field as a code block (use this or ``text``)."""

    max_formatted_length: ClassVar[int] = 2000
    """Maximum length of formatted output, imposed by Slack.

    Used internally for validation and intended to be overridden by child
    classes that need to impose different maximum lengths.
    """

    @root_validator
    def _validate_content(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure only one of ``text`` or ``code`` is set."""
        if values["text"] and values["code"]:
            raise ValueError("Only one of text and code may be given")
        if values["text"] is None and values["code"] is None:
            raise ValueError("One of text or code must be given")
        return values

    def to_slack(self) -> Dict[str, Any]:
        """Convert to a Slack Block Kit block.

        Returns
        -------
        dict
            A Slack Block Kit block suitable for including in the ``fields``
            or ``text`` section of a ``blocks`` element.
        """
        heading = f"*{self.heading}*\n"
        if self.code:
            extra_needed = len(heading) + 8  # ```\n\n```
            max_length = self.max_formatted_length - extra_needed
            code = _truncate_string_at_start(self.code.strip(), max_length)
            body = f"```\n{code}\n```"
        else:
            if not self.text:
                # Pydantic validation should make this impossible.
                raise RuntimeError("SlackField without code or text")
            extra_needed = len(heading)
            max_length = self.max_formatted_length - extra_needed
            body = _truncate_string_at_end(self.text.strip(), max_length)
        return {"type": "mrkdwn", "text": heading + body, "verbatim": True}


class SlackAttachment(SlackField):
    """An attachment in a Slack message with a heading.

    Intended for use in the ``attachments`` portion of a Block Kit message. If
    the formatted output is longer than 3000 characters, it will be truncated
    to avoid the strict upper limit imposed by Slack.
    """

    max_formatted_length = 3000


class SlackMessage(BaseModel):
    """Message to post to Slack.

    The ``message`` attribute will be the initial part of the message.

    All fields in ``fields`` will be shown below that message, formatted in
    two columns. Order of ``fields`` is preserved; they will be laid out left
    to right and then top to bottom in the order given. Then, attachments will
    be added, if any, below the fields.

    At most ten elements are allowed in ``fields``. They should be used for
    short information, generally a single half-line at most.  Longer
    information should go into ``attachments``.
    """

    message: str
    """Main part of the message.

    This does not use ``verbatim``, so any channel references or @-mentions of
    Slack users will be honored and expanded by Slack.
    """

    verbatim: bool = False
    """Whether the main part of the message should be marked verbatim.

    Verbatim messages in Slack don't expand channel references or create user
    notifications. These are expanded in the main message by default, but this
    can be set to `True` to disable that behavior.
    """

    fields: List[SlackField] = []
    """Short key/value fields to include in the message (at most 10)."""

    attachments: List[SlackAttachment] = []
    """Longer sections to include as attachments."""

    @validator("fields")
    def _validate_fields(cls, v: List[SlackField]) -> List[SlackField]:
        """Check Slack's constraints on fields.

        Slack imposes a maximum of 10 items in a ``fields`` array.
        """
        if len(v) > 10:
            msg = f"Slack does not allow more than 10 fields ({len(v)} seen)"
            raise ValueError(msg)
        return v

    def to_slack(self) -> Dict[str, Any]:
        """Convert to a Slack Block Kit message.

        Returns
        -------
        dict
            A Slack Block Kit data structure suitable for serializing to
            JSON and sending to Slack.
        """
        fields = [f.to_slack() for f in self.fields]
        attachments = [
            {"type": "section", "text": a.to_slack()} for a in self.attachments
        ]
        message = _truncate_string_at_end(self.message.strip(), 3000)
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                    "verbatim": self.verbatim,
                },
            }
        ]
        if fields:
            blocks.append({"type": "section", "fields": fields})
        result: dict[str, Any] = {"blocks": blocks}
        if attachments:
            result["attachments"] = [{"blocks": attachments}]
        elif fields:
            result["blocks"].append({"type": "divider"})
        return result


class SlackException(Exception):
    """Parent class of exceptions that can be reported to Slack.

    Intended to be subclassed.  Subclasses may wish to override the
    ``to_slack`` method.

    Parameters
    ----------
    message
        Exception string value, which is the default Slack message.
    user
        Identity of user triggering the exception, if known.
    failed_at
        When the exception happened. Omit to use the current time.
    """

    def __init__(
        self,
        message: str,
        user: Optional[str] = None,
        *,
        failed_at: Optional[datetime] = None,
    ) -> None:
        self.user = user
        if failed_at:
            self.failed_at = failed_at
        else:
            self.failed_at = current_datetime(microseconds=True)
        super().__init__(message)

    def to_slack(self) -> SlackMessage:
        """Format the exception as a Slack message.

        This is the generic version that only reports the text of the
        exception and the base fields. Child exceptions may want to override
        it to add more metadata.

        Returns
        -------
        SlackMessage
            Slack message suitable for posting with `SlackClient`.
        """
        failed_at = format_datetime_for_logging(self.failed_at)
        fields = [
            SlackField(heading="Exception type", text=type(self).__name__),
            SlackField(heading="Failed at", text=failed_at),
        ]
        if self.user:
            fields.append(SlackField(heading="User", text=self.user))
        return SlackMessage(message=str(self), verbatim=True, fields=fields)


class SlackIgnoredException(Exception):
    """Parent class for exceptions that should not be reported to Slack.

    This exception has no built-in behavior or meaning except to suppress
    Slack notifications if it is thrown uncaught.  Application exceptions that
    should not result in a Slack alert (because, for example, they're intended
    to be caught by exception handlers) should inherit from this class.
    """


class SlackClient:
    """Send messages to Slack.

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
        date = format_datetime_for_logging(current_datetime())
        name = type(exc).__name__
        error = f"{name}: {str(exc)}"
        message = SlackMessage(
            message=f"Uncaught {name} exception in {self._application}",
            verbatim=True,
            fields=[SlackField(heading="Failed at", text=date)],
            attachments=[SlackAttachment(heading="Exception", code=error)],
        )
        await self.post(message)


def _truncate_string_at_end(string: str, max_length: int) -> str:
    """Truncate a string at the end.

    Slack prohibits text blocks longer than a varying number of characters
    depending on where they are in the message. If this constraint is not met,
    the whole mesage is rejected with an HTTP error. Truncate a potentially
    long message at the end.

    Parameters
    ----------
    string
        String to truncate.
    max_length
        Maximum allowed length.

    Returns
    -------
    str
        The truncated string.
    """
    if len(string) <= max_length:
        return string
    truncated = "\n... truncated ..."
    last_newline = string.rfind("\n", 0, max_length - len(truncated))
    if last_newline == -1:
        return string[: max_length - len(truncated)] + truncated
    else:
        return string[:last_newline] + truncated


def _truncate_string_at_start(string: str, max_length: int) -> str:
    """Truncate a string at the start.

    Slack prohibits text blocks longer than a varying number of characters
    depending on where they are in the message. If this constraint is not met,
    the whole mesage is rejected with an HTTP error. Truncate a potentially
    long message at the start. Use this for tracebacks and similar

    Parameters
    ----------
    string
        String to truncate.
    max_length
        Maximum allowed length.

    Returns
    -------
    str
        The truncated string.
    """
    length = len(string)
    if length <= max_length:
        return string
    truncated = "... truncated ...\n"
    lines = string.split("\n")
    if len(lines) == 1:
        start = length - max_length + len(truncated)
        return truncated + string[start:]
    while length > max_length - len(truncated):
        line = lines.pop(0)
        length -= len(line) + 1
    return truncated + "\n".join(lines)


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

    _alert_client: ClassVar[Optional[SlackClient]] = None
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
        cls._alert_client = SlackClient(hook_url, application, logger)

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
