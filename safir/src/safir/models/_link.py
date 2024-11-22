"""Representation for a ``Link`` HTTP header."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self

__all__ = ["LinkData"]

_LINK_REGEX = re.compile(r'\s*<(?P<target>[^>]+)>;\s*rel="(?P<type>[^"]+)"')
"""Matches a component of a valid ``Link`` header."""


@dataclass
class LinkData:
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
        LinkData
            Parsed form of that header.
        """
        links = {}
        if header:
            for element in header.split(","):
                if m := re.match(_LINK_REGEX, element):
                    if m.group("type") in ("prev", "next", "first"):
                        links[m.group("type")] = m.group("target")
                    elif m.group("type") == "previous":
                        links["prev"] = m.group("target")

        return cls(
            prev_url=links.get("prev"),
            next_url=links.get("next"),
            first_url=links.get("first"),
        )
