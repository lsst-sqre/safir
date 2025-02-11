"""Exception helpers for Sentry instrumentation."""

from typing import Any, Self

from httpx import HTTPError, HTTPStatusError
from sentry_sdk.types import Event

__all__ = [
    "SentryException",
    "SentryWebException",
]


class SentryException(Exception):
    """Enriches the Sentry context when paired with the ``enrich`` handler."""

    def __init__(self, message: str) -> None:
        # Do not call the parent Exception constructor here, because calling
        # it with a different number of arguments than the constructor
        # argument of derived exceptions breaks pickling. See the end of
        # https://github.com/python/cpython/issues/44791. This requires
        # implementing __str__ rather than relying on the default behavior.
        #
        # Arguably, this is a bug in the __reduce__ method of BaseException
        # and its interaction with constructors, but it appears to be hard to
        # fix. See https://github.com/python/cpython/issues/76877.
        self.message = message
        self.tags: dict[str, str] = {}
        self.contexts: dict[str, dict[str, Any]] = {}

    def __str__(self) -> str:
        return self.message

    def enrich(self, event: Event) -> Event:
        """Merge our tags and contexts into the event's."""
        event["tags"] = event.setdefault("tags", {})
        event["tags"].update(self.tags)
        event["contexts"] = event.get("contexts", {}) | self.contexts
        return event


class SentryWebException(SentryException):
    """Parent class of exceptions arising from HTTPX_ failures.

    Captures additional information from any HTTPX_ exception.  Intended to be
    subclassed.

    Parameters
    ----------
    message
        Exception string value, which is the default Slack message.
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
    def from_exception(cls, exc: HTTPError, user: str | None = None) -> Self:
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
            exc_name = type(exc).__name__
            message = f"{exc_name}: {exc!s}" if str(exc) else exc_name

            # All httpx.HTTPError exceptions have a slot for the request,
            # initialized to None and then sometimes added by child
            # constructors or during exception processing. The request
            # property is a property method that raises RuntimeError if
            # request has not been set, so we can't just check for None. Hence
            # this approach of attempting to use the request and falling back
            # on reporting less data if that raised any exception.
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
        method: str | None = None,
        url: str | None = None,
        user: str | None = None,
        status: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        self.user = user

        if self.method:
            self.tags["httpx_request_method"] = self.method
        if self.user:
            self.tags["gafaelfaw_user"] = self.user
        if self.url:
            self.tags["httpx_request_url"] = self.url
        if self.status:
            self.tags["httpx_request_status"] = str(self.status)
        if self.body:
            self.contexts["httpx_request_info"] = {"body": self.body}

    def __str__(self) -> str:
        result = self.message
        if self.body:
            result += f"\nBody:\n{self.body}\n"
        return result
