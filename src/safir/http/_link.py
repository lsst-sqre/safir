"""Parse HTTP ``Link`` headers."""

import re
from dataclasses import dataclass
from typing import Self

_LINK_REGEX = re.compile(r'\s*<(?P<target>[^>]+)>;\s*rel="(?P<type>[^"]+)"')
"""Matches a component of a valid ``Link`` header with a quoted type."""

_LINK_TOKEN_REGEX = re.compile(
    r"\s*<(?P<target>[^>]+)>;\s*rel=(?P<type>[A-Za-z0-9!#$%&\'*+.^_`|~-]+)"
)
"""Matches a component of a valid ``Link`` header with a quoted type."""

__all__ = ["PaginationLinkData"]


@dataclass
class PaginationLinkData:
    """Holds the data returned in an :rfc:`8288` ``Link`` header."""

    prev_url: str | None
    """URL of the previous page, or `None` for the first page."""

    next_url: str | None
    """URL of the next page, or `None` for the last page."""

    first_url: str | None
    """URL of the first page."""

    @classmethod
    def from_header(cls, header: str | None) -> Self:
        """Parse an :rfc:`8288` ``Link`` with pagination URLs.

        Parameters
        ----------
        header
            Contents of an RFC 8288 ``Link`` header.

        Returns
        -------
        PaginationLinkData
            Parsed form of that header.
        """
        links = {}
        if header:
            for element in header.split(","):
                m = re.match(_LINK_REGEX, element)
                if not m:
                    m = re.match(_LINK_TOKEN_REGEX, element)
                if m:
                    if m.group("type") in ("prev", "next", "first"):
                        links[m.group("type")] = m.group("target")
                    elif m.group("type") == "previous":
                        links["prev"] = m.group("target")

        return cls(
            prev_url=links.get("prev"),
            next_url=links.get("next"),
            first_url=links.get("first"),
        )
