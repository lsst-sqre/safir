"""Slack Block Kit message models."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, validator

from safir.datetime import current_datetime, format_datetime_for_logging

__all__ = [
    "SlackBaseAttachment",
    "SlackBaseField",
    "SlackCodeAttachment",
    "SlackCodeField",
    "SlackException",
    "SlackMessage",
    "SlackTextAttachment",
    "SlackTextField",
]


class SlackBaseField(BaseModel, metaclass=ABCMeta):
    """Base class for any Slack Block Kit block."""

    @abstractmethod
    def to_slack(self) -> Dict[str, Any]:
        """Convert to a Slack Block Kit block.

        Returns
        -------
        dict
            A Slack Block Kit block suitable for including in the ``fields``
            or ``text`` section of a ``blocks`` element.
        """


class SlackTextField(SlackBaseField):
    """A component of a Slack message with a heading and a text body.

    Intended for use in the ``fields`` portion of a Block Kit message. If the
    formatted output is longer than 2000 characters, it will be truncated to
    avoid the strict upper limit imposed by Slack.
    """

    heading: str
    """Heading of the field (shown in bold)."""

    text: str
    """Text of the field as normal text.

    This is always marked as vertabim, so channel mentions or @-mentions of
    users will not be treated as special.
    """

    max_formatted_length: ClassVar[int] = 2000
    """Maximum length of formatted output, imposed by Slack.

    Used internally for validation and intended to be overridden by child
    classes that need to impose different maximum lengths.
    """

    def to_slack(self) -> Dict[str, Any]:
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


class SlackCodeField(SlackBaseField):
    """A component of a Slack message with a heading and a code block.

    Intended for use in the ``fields`` portion of a Block Kit message. If the
    formatted output is longer than 2000 characters, it will be truncated to
    avoid the strict upper limit imposed by Slack.
    """

    heading: str
    """Heading of the field (shown in bold)."""

    code: str
    """Text of the field as a code block."""

    max_formatted_length: ClassVar[int] = 2000
    """Maximum length of formatted output, imposed by Slack.

    Used internally for validation and intended to be overridden by child
    classes that need to impose different maximum lengths.
    """

    def to_slack(self) -> Dict[str, Any]:
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


class SlackBaseAttachment(SlackBaseField):
    """Base class for attachment Slack Block Kit blocks.

    Notes
    -----
    This is used only for type checking and doesn't add any behavior.
    """


class SlackTextAttachment(SlackTextField, SlackBaseAttachment):
    """An attachment in a Slack message with a heading and text body.

    Intended for use in the ``attachments`` portion of a Block Kit message. If
    the formatted output is longer than 3000 characters, it will be truncated
    to avoid the strict upper limit imposed by Slack.

    Notes
    -----
    Slack has marked attachments as legacy and warns that future changes may
    reduce their visibility or utility. Unfortunately, there is no other way
    to attach possibly-long text where Slack will hide long content by default
    but allow the user to expand it. We therefore continue to use attachments
    for long text for want of a better alternative.
    """

    max_formatted_length = 3000


class SlackCodeAttachment(SlackCodeField, SlackBaseAttachment):
    """An attachment in a Slack message with a heading and text body.

    Intended for use in the ``attachments`` portion of a Block Kit message. If
    the formatted output is longer than 3000 characters, it will be truncated
    to avoid the strict upper limit imposed by Slack.

    Notes
    -----
    Slack has marked attachments as legacy and warns that future changes may
    reduce their visibility or utility. Unfortunately, there is no other way
    to attach possibly-long text where Slack will hide long content by default
    but allow the user to expand it. We therefore continue to use attachments
    for long code blocks for want of a better alternative.
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

    verbatim: bool = True
    """Whether the main part of the message should be marked verbatim.

    Verbatim messages in Slack don't expand channel references or create user
    notifications. This is the default, but can be set to `False` to allow
    any such elements in the message to be recognized by Slack. Do not set
    this to `False` with untrusted input.
    """

    fields: List[SlackBaseField] = []
    """Short key/value fields to include in the message (at most 10)."""

    attachments: List[SlackBaseAttachment] = []
    """Longer sections to include as attachments."""

    @validator("fields")
    def _validate_fields(cls, v: List[SlackBaseField]) -> List[SlackBaseField]:
        """Check constraints on fields.

        Slack imposes a maximum of 10 items in a ``fields`` array. Also ensure
        that no fields are actually attachments, since in that case they may
        not be truncated to the correct length. (The type system we're using
        doesn't allow Pydantic to check this directly.)
        """
        if len(v) > 10:
            msg = f"Slack does not allow more than 10 fields ({len(v)} seen)"
            raise ValueError(msg)
        for field in v:
            if isinstance(field, SlackBaseAttachment):
                raise ValueError("Attachment included in fields list")
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
            SlackTextField(heading="Exception type", text=type(self).__name__),
            SlackTextField(heading="Failed at", text=failed_at),
        ]
        if self.user:
            fields.append(SlackTextField(heading="User", text=self.user))
        return SlackMessage(message=str(self), fields=fields)


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
