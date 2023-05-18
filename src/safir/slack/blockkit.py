"""Slack Block Kit message models."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Optional, Self

from httpx import HTTPError, HTTPStatusError
from pydantic import BaseModel, validator

from safir.datetime import current_datetime, format_datetime_for_logging

__all__ = [
    "SlackBaseBlock",
    "SlackBaseField",
    "SlackCodeBlock",
    "SlackCodeField",
    "SlackException",
    "SlackMessage",
    "SlackTextBlock",
    "SlackTextField",
    "SlackWebException",
]


class SlackBaseBlock(BaseModel, metaclass=ABCMeta):
    """Base class for any Slack Block Kit block."""

    max_formatted_length: ClassVar[int] = 3000
    """Maximum length of formatted output, imposed by Slack.

    Intended to be overridden by child classes that need to impose different
    maximum lengths.
    """

    @abstractmethod
    def to_slack(self) -> dict[str, Any]:
        """Convert to a Slack Block Kit block.

        Returns
        -------
        dict
            A Slack Block Kit block suitable for including in the ``fields``
            or ``text`` section of a ``blocks`` element.
        """


class SlackTextBlock(SlackBaseBlock):
    """A component of a Slack message with a heading and a text body.

    If the formatted output is longer than 3000 characters, it will be
    truncated to avoid the strict uppper limit imposed by Slack.
    """

    heading: str
    """Heading of the field (shown in bold)."""

    text: str
    """Text of the field as normal text.

    This is always marked as vertabim, so channel mentions or @-mentions of
    users will not be treated as special.
    """

    def to_slack(self) -> dict[str, Any]:
        """Convert to a Slack Block Kit block.

        Returns
        -------
        dict
            A Slack Block Kit block suitable for including in the ``fields``
            or ``text`` section of a ``blocks`` element.
        """
        heading = f"*{self.heading}*\n"
        max_length = self.max_formatted_length - len(heading)
        body = _format_and_truncate_at_end(self.text, max_length)
        return {"type": "mrkdwn", "text": heading + body, "verbatim": True}


class SlackCodeBlock(SlackBaseBlock):
    """A component of a Slack message with a heading and a code block.

    If the formatted output is longer than 3000 characters, it will be
    truncated to avoid the strict upper limit imposed by Slack.
    """

    heading: str
    """Heading of the field (shown in bold)."""

    code: str
    """Text of the field as a code block."""

    def to_slack(self) -> dict[str, Any]:
        """Convert to a Slack Block Kit block.

        Returns
        -------
        dict
            A Slack Block Kit block suitable for including in the ``fields``
            or ``text`` section of a ``blocks`` element.
        """
        heading = f"*{self.heading}*\n"
        extra_needed = len(heading) + 8  # ```\n\n```
        max_length = self.max_formatted_length - extra_needed
        code = _format_and_truncate_at_start(self.code, max_length)
        text = f"{heading}```\n{code}\n```"
        return {"type": "mrkdwn", "text": text, "verbatim": True}


class SlackBaseField(SlackBaseBlock):
    """Base class for Slack Block Kit blocks for the ``fields`` section."""

    max_formatted_length: ClassVar[int] = 2000


class SlackTextField(SlackTextBlock, SlackBaseField):
    """One field in a Slack message with a heading and text body.

    Intended for use in the ``fields`` portion of a Block Kit message. If the
    formatted output is longer than 2000 characters, it will be truncated to
    avoid the strict upper limit imposed by Slack.
    """


class SlackCodeField(SlackCodeBlock, SlackBaseField):
    """An attachment in a Slack message with a heading and text body.

    Intended for use in the ``fields`` portion of a Block Kit message. If
    the formatted output is longer than 2000 characters, it will be truncated
    to avoid the strict upper limit imposed by Slack.
    """


class SlackMessage(BaseModel):
    """Message to post to Slack.

    The ``message`` attribute will be the initial part of the message.

    All fields in ``fields`` will be shown below that message, formatted in
    two columns. Order of ``fields`` is preserved; they will be laid out left
    to right and then top to bottom in the order given. Then, ``blocks`` will
    be added, if any, in one column below the fields. Finally, ``attachments``
    will be added to the end as attachments, which get somewhat different
    formatting (for example, long attachments are collapsed by default).

    At most ten elements are allowed in ``fields``. They should be used for
    short information, generally a single half-line at most.  Longer
    information should go into ``blocks`` or ``attachments``.
    """

    message: str
    """Main part of the message."""

    verbatim: bool = True
    """Whether the main part of the message should be marked verbatim.

    Verbatim messages in Slack don't expand channel references or create user
    notifications. This is the default, but can be set to `False` to allow
    any such elements in the message to be recognized by Slack. Do not set
    this to `False` with untrusted input.
    """

    fields: list[SlackBaseField] = []
    """Short key/value fields to include in the message (at most 10)."""

    blocks: list[SlackBaseBlock] = []
    """Additional text blocks to include in the message (after fields)."""

    attachments: list[SlackBaseBlock] = []
    """Longer sections to include as attachments.

    Notes
    -----
    Slack has marked attachments as legacy and warns that future changes may
    reduce their visibility or utility. Unfortunately, there is no other way
    to attach possibly-long text where Slack will hide long content by default
    but allow the user to expand it. We therefore continue to use attachments
    for long text for want of a better alternative.
    """

    @validator("fields")
    def _validate_fields(cls, v: list[SlackBaseField]) -> list[SlackBaseField]:
        """Check constraints on fields.

        Slack imposes a maximum of 10 items in a ``fields`` array. Also ensure
        that no fields are actually attachments, since in that case they may
        not be truncated to the correct length. (The type system we're using
        doesn't allow Pydantic to check this directly.)
        """
        if len(v) > 10:
            msg = f"Slack does not allow more than 10 fields ({len(v)} seen)"
            raise ValueError(msg)
        return v

    def to_slack(self) -> dict[str, Any]:
        """Convert to a Slack Block Kit message.

        Returns
        -------
        dict
            A Slack Block Kit data structure suitable for serializing to
            JSON and sending to Slack.
        """
        attachments = [
            {"type": "section", "text": a.to_slack()} for a in self.attachments
        ]
        message = _format_and_truncate_at_end(self.message, 3000)
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
        fields = [f.to_slack() for f in self.fields]
        if fields:
            blocks.append({"type": "section", "fields": fields})
        blocks.extend(
            [{"type": "section", "text": b.to_slack()} for b in self.blocks]
        )
        result: dict[str, Any] = {"blocks": blocks}
        if attachments:
            result["attachments"] = [{"blocks": attachments}]
        elif fields or self.blocks:
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
        fields: list[SlackBaseField] = [
            SlackTextField(heading="Exception type", text=type(self).__name__),
            SlackTextField(heading="Failed at", text=failed_at),
        ]
        if self.user:
            fields.append(SlackTextField(heading="User", text=self.user))
        return SlackMessage(message=str(self), fields=fields)


class SlackWebException(SlackException):
    """Parent class of exceptions arising from HTTPX_ failures.

    Captures additional information from any HTTPX_ exception.  Intended to be
    subclassed.  Subclasses may wish to override the ``to_slack`` method.

    Parameters
    ----------
    message
        Exception string value, which is the default Slack message.
    failed_at
        When the exception happened. Omit to use the current time.
    method
        Method of request.
    url
        URL of the request.
    user
        Username on whose behalf the request is being made.
    status
        Status code of failure, if any.
    body
        Body of failure message, if any.
    """

    @classmethod
    def from_exception(
        cls, exc: HTTPError, user: Optional[str] = None
    ) -> Self:
        """Create an exception from an HTTPX_ exception.

        Parameters
        ----------
        exc
            Exception from HTTPX.
        user
            User on whose behalf the request is being made, if known.

        Returns
        -------
        SlackWebException
            Newly-constructed exception.
        """
        if isinstance(exc, HTTPStatusError):
            status = exc.response.status_code
            method = exc.request.method
            message = f"Status {status} from {method} {exc.request.url}"
            return cls(
                message,
                method=exc.request.method,
                url=str(exc.request.url),
                user=user,
                status=status,
                body=exc.response.text,
            )
        else:
            message = f"{type(exc).__name__}: {str(exc)}"

            # All httpx.HTTPError exceptions have a slot for the request,
            # initialized to None and then sometimes added by child
            # constructors or during exception processing. The request
            # property is a property method that raises RuntimeError if
            # request has not been set, so we can't just check for None.
            # Hence this approach of attempting to use the request and falling
            # back on reporting less data if that raised any exception.
            try:
                return cls(
                    message,
                    method=exc.request.method,
                    url=str(exc.request.url),
                    user=user,
                )
            except Exception:
                return cls(message, user=user)

    def __init__(
        self,
        message: str,
        *,
        failed_at: Optional[datetime] = None,
        method: Optional[str] = None,
        url: Optional[str] = None,
        user: Optional[str] = None,
        status: Optional[int] = None,
        body: Optional[str] = None,
    ) -> None:
        self.message = message
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(message, user, failed_at=failed_at)

    def __str__(self) -> str:
        result = self.message
        if self.body:
            result += f"\nBody:\n{self.body}\n"
        return result

    def to_slack(self) -> SlackMessage:
        """Convert to a Slack message for Slack alerting.

        Returns
        -------
        SlackMessage
            Slack message suitable for posting as an alert.
        """
        message = super().to_slack()
        message.message = self.message
        if self.url:
            if self.method:
                text = f"{self.method} {self.url}"
            else:
                text = self.url
            message.blocks.append(SlackTextBlock(heading="URL", text=text))
        if self.body:
            block = SlackCodeBlock(heading="Response", code=self.body)
            message.attachments.append(block)
        return message


def _format_and_truncate_at_end(string: str, max_length: int) -> str:
    """Format a string for Slack, truncating at the end.

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
        The truncated string with special characters escaped.
    """
    string = (
        string.strip()
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    if len(string) <= max_length:
        return string
    truncated = "\n... truncated ..."
    last_newline = string.rfind("\n", 0, max_length - len(truncated))
    if last_newline == -1:
        return string[: max_length - len(truncated)] + truncated
    else:
        return string[:last_newline] + truncated


def _format_and_truncate_at_start(string: str, max_length: int) -> str:
    """Format a string for Slack, truncating at the start.

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
        The truncated string with special characters escaped.
    """
    string = (
        string.strip()
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
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
