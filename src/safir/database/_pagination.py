"""Support for paginated database queries.

This pagination support uses keyset pagination rather than relying on database
cursors, since the latter interact poorly with horizontally scaled services.
"""

import re
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self, override
from urllib.parse import parse_qs, urlencode

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.orm import InstrumentedAttribute
from starlette.datastructures import URL

from safir.fastapi import ClientRequestError
from safir.models import ErrorLocation

from ._datetime import datetime_to_db

_LINK_REGEX = re.compile(r'\s*<(?P<target>[^>]+)>;\s*rel="(?P<type>[^"]+)"')
"""Matches a component of a valid ``Link`` header."""

__all__ = [
    "CountedPaginatedList",
    "CountedPaginatedQueryRunner",
    "DatetimeIdCursor",
    "InvalidCursorError",
    "PaginatedList",
    "PaginatedQueryRunner",
    "PaginationCursor",
    "PaginationLinkData",
]


class InvalidCursorError(ClientRequestError):
    """The provided cursor was invalid."""

    error = "invalid_cursor"

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorLocation.query, ["cursor"])


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


@dataclass
class PaginationCursor[E: BaseModel](metaclass=ABCMeta):
    """Generic pagnination cursor for keyset pagination.

    The generic type parameter is the Pydantic model into which each row will
    be converted, not the ORM model.
    """

    previous: bool
    """Whether to search backwards instead of forwards."""

    @classmethod
    @abstractmethod
    def from_entry(cls, entry: E, *, reverse: bool = False) -> Self:
        """Construct a cursor with an entry as a bound.

        Builds a cursor to get the entries after the provided entry, or before
        the provided entry if ``reverse`` is set to `True`. When the cursor is
        later applied with `~safir.database.PaginationCursor.apply_cursor`,
        forward cursors (the default) must include the entry the cursor was
        based on. Reverse cursors must exclude the given entry and return data
        starting with the entry immediately previous.

        Parameters
        ----------
        entry
            Basis of the cursor.
        reverse
            Whether to create a previous cursor.

        Returns
        -------
        safir.database.PaginationCursor
            Requested cursor.
        """

    @classmethod
    @abstractmethod
    def from_str(cls, cursor: str) -> Self:
        """Build cursor from the string serialization form.

        Parameters
        ----------
        cursor
            Serialized form of the cursor.

        Returns
        -------
        safir.database.PaginationCursor
            The cursor represented as an object.

        Raises
        ------
        safir.database.InvalidCursorError
            Raised if the cursor is invalid.
        """

    @classmethod
    @abstractmethod
    def apply_order(cls, stmt: Select, *, reverse: bool = False) -> Select:
        """Apply the sort order of the cursor to a select statement.

        This is independent of the cursor and only needs to know the
        underlying ORM fields, so it is available as a class method on the
        cursor class, allowing it to be used without a cursor (such as for the
        initial query). This does, however, mean that the caller has to
        explicitly say whether to reverse the order, which is required when
        using a previous cursor.

        Parameters
        ----------
        stmt
            SQL select statement.
        reverse
            Whether to reverse the sort order.

        Returns
        -------
        sqlalchemy.sql.expression.Select
            The same select statement but sorted in the order expected by the
            cursor.
        """

    @abstractmethod
    def apply_cursor(self, stmt: Select) -> Select:
        """Apply the restrictions from the cursor to a select statement.

        Forward cursors (the default) must include the entry the cursor was
        based on. Reverse cursors must exclude that entry and return data
        beginning with the entry immediately previous.

        Parameters
        ----------
        stmt
            Select statement to modify.

        Returns
        -------
        sqlalchemy.sql.expression.Select
            Modified select statement.
        """

    @abstractmethod
    def invert(self) -> Self:
        """Return the inverted cursor (going the opposite direction).

        Parameters
        ----------
        cursor
            Cursor to invert.

        Returns
        -------
        safir.database.PaginationCursor
            The inverted cursor.
        """


@dataclass
class DatetimeIdCursor[E: BaseModel](PaginationCursor[E], metaclass=ABCMeta):
    """Pagination cursor using a `~datetime.datetime` and unique column ID.

    Cursors that first order by time and then by a unique integer column ID
    can subclass this class and only define the ``id_column`` and
    ``time_column`` static methods to return the ORM model fields for the
    timestamp and column ID.

    Examples
    --------
    Here is a specialization of this cursor class for a simple ORM model where
    the timestamp field to order by is named ``creation_time`` and the unique
    row ID is named ``id``.

    .. code-block:: python

       class TableCursor(DatetimeIdCursor):
           @staticmethod
           def id_column() -> InstrumentedAttribute:
               return Table.id

           @staticmethod
           def time_column() -> InstrumentedAttribute:
               return Table.creation_time
    """

    time: datetime
    """Time position."""

    id: int
    """Unique ID position."""

    @staticmethod
    @abstractmethod
    def id_column() -> InstrumentedAttribute:
        """Return SQL model attribute holding the ID."""

    @staticmethod
    @abstractmethod
    def time_column() -> InstrumentedAttribute:
        """Return SQL model attribute holding the time position."""

    @override
    @classmethod
    def from_str(cls, cursor: str) -> Self:
        previous = cursor.startswith("p")
        if previous:
            cursor = cursor[1:]
        try:
            time, id = cursor.split("_")
            return cls(
                time=datetime.fromtimestamp(float(time), tz=UTC),
                id=int(id),
                previous=previous,
            )
        except Exception as e:
            raise InvalidCursorError(f"Cannot parse cursor: {e!s}") from e

    @override
    @classmethod
    def apply_order(cls, stmt: Select, *, reverse: bool = False) -> Select:
        if reverse:
            return stmt.order_by(cls.time_column(), cls.id_column())
        else:
            return stmt.order_by(
                cls.time_column().desc(), cls.id_column().desc()
            )

    @override
    def apply_cursor(self, stmt: Select) -> Select:
        time = datetime_to_db(self.time)
        time_column = self.time_column()
        id_column = self.id_column()
        if self.previous:
            return stmt.where(
                or_(
                    time_column > time,
                    and_(time_column == time, id_column > self.id),
                )
            )
        else:
            return stmt.where(
                or_(
                    time_column < time,
                    and_(time_column == time, id_column <= self.id),
                )
            )

    @override
    def invert(self) -> Self:
        return type(self)(
            time=self.time, id=self.id, previous=not self.previous
        )

    def __str__(self) -> str:
        previous = "p" if self.previous else ""
        timestamp = self.time.timestamp()

        # Remove a trailing .0, but keep the fractional portion if it matters.
        # This is entirely unnecessary, but it looks nicer in the common case
        # where the database doesn't store milliseconds.
        if int(timestamp) == timestamp:
            timestamp = int(timestamp)

        return f"{previous}{timestamp!s}_{self.id!s}"


@dataclass
class PaginatedList[E: BaseModel, C: PaginationCursor]:
    """Paginated SQL results with accompanying pagination metadata.

    Holds a paginated list of any Pydantic type with pagination cursors. Can
    hold any type of entry and any type of cursor, but implicitly requires the
    entry type be one that is meaningfully paginated by that type of cursor.
    """

    entries: list[E]
    """A batch of entries."""

    next_cursor: C | None
    """Cursor for the next batch of entries."""

    prev_cursor: C | None
    """Cursor for the previous batch of entries."""

    def first_url(self, current_url: URL) -> str:
        """Construct a URL to the first group of results for this query.

        Parameters
        ----------
        current_url
            The starting URL of the current group of entries.

        Returns
        -------
        str
            URL to the first group of entries for this query.
        """
        return str(current_url.remove_query_params("cursor"))

    def next_url(self, current_url: URL) -> str | None:
        """Construct a URL to the next group of results for this query.

        Parameters
        ----------
        current_url
            The starting URL of the current group of entries.

        Returns
        -------
        str or None
            URL to the next group of entries for this query or `None` if there
            are no further entries.
        """
        if not self.next_cursor:
            return None
        first_url = current_url.remove_query_params("cursor")
        params = parse_qs(first_url.query)
        params["cursor"] = [str(self.next_cursor)]
        return str(first_url.replace(query=urlencode(params, doseq=True)))

    def prev_url(self, current_url: URL) -> str | None:
        """Construct a URL to the previous group of results for this query.

        Parameters
        ----------
        current_url
            The starting URL of the current group of entries.

        Returns
        -------
        str or None
            URL to the previous group of entries for this query or `None` if
            there are no further entries.
        """
        if not self.prev_cursor:
            return None
        first_url = current_url.remove_query_params("cursor")
        params = parse_qs(first_url.query)
        params["cursor"] = [str(self.prev_cursor)]
        return str(first_url.replace(query=urlencode(params, doseq=True)))

    def link_header(self, current_url: URL) -> str:
        """Construct an RFC 8288 ``Link`` header for a paginated result.

        Parameters
        ----------
        current_url
            The starting URL of the current group of entries.

        Returns
        -------
        str
            Contents of an RFC 8288 ``Link`` header.
        """
        first_url = self.first_url(current_url)
        next_url = self.next_url(current_url)
        prev_url = self.prev_url(current_url)
        header = f'<{first_url!s}>; rel="first"'
        if next_url:
            header += f', <{next_url!s}>; rel="next"'
        if prev_url:
            header += f', <{prev_url!s}>; rel="prev"'
        return header


class PaginatedQueryRunner[E: BaseModel, C: PaginationCursor]:
    """Run database queries that return paginated results.

    This class implements the logic for keyset pagination based on arbitrary
    SQLAlchemy ORM where clauses.

    Parameters
    ----------
    entry_type
        Type of each entry returned by the queries. This must be a Pydantic
        model.
    cursor_type
        Type of the pagination cursor, which encapsulates the logic of how
        entries are sorted and what set of keys is used to retrieve the next
        or previous batch of entries.
    """

    def __init__(self, entry_type: type[E], cursor_type: type[C]) -> None:
        self._entry_type = entry_type
        self._cursor_type = cursor_type

    async def query_count(
        self, session: async_scoped_session, stmt: Select[tuple]
    ) -> int:
        """Count the number of objects that match a query.

        There is nothing particular to pagination about this query, but it is
        often used in conjunction with pagination to provide the total count
        of matching entries, often in an ``X-Total-Count`` HTTP header.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute.

        Returns
        -------
        int
            Count of matching rows.
        """
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return await session.scalar(count_stmt) or 0

    async def query_object(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        cursor: C | None = None,
        limit: int | None = None,
    ) -> PaginatedList[E, C]:
        """Perform a query for objects with an optional cursor and limit.

        Perform the query provided in ``stmt`` with appropriate sorting and
        pagination as determined by the cursor type.

        This method should be used with queries that return a single
        SQLAlchemy model. The provided query will be run with the session
        `~sqlalchemy.ext.asyncio.async_scoped_session.scalars` method and the
        resulting object passed to Pydantic's ``model_validate`` to convert to
        ``entry_type``. For queries returning a tuple of attributes, use
        `query_row` instead.

        Unfortunately, this distinction cannot be type-checked, so be careful
        to use the correct method.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied. This statement must return a list of SQLAlchemy
            ORM models that can be converted to ``entry_type`` by Pydantic.
        cursor
            If present, continue from the provided keyset cursor.
        limit
            If present, limit the result count to at most this number of rows.

        Returns
        -------
        PaginatedList
            Results of the query wrapped with pagination information.
        """
        if cursor or limit:
            return await self._paginated_query(
                session, stmt, cursor=cursor, limit=limit, scalar=True
            )
        else:
            return await self._full_query(session, stmt, scalar=True)

    async def query_row(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        cursor: C | None = None,
        limit: int | None = None,
    ) -> PaginatedList[E, C]:
        """Perform a query for attributes with an optional cursor and limit.

        Perform the query provided in ``stmt`` with appropriate sorting and
        pagination as determined by the cursor type.

        This method should be used with queries that return a list of
        attributes that can be converted to the ``entry_type`` Pydantic model.
        For queries returning a single ORM object, use `query_object` instead.

        Unfortunately, this distinction cannot be type-checked, so be careful
        to use the correct method.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied. This statement must return a tuple of attributes
            that can be converted to ``entry_type`` by Pydantic's
            ``model_validate``.
        cursor
            If present, continue from the provided keyset cursor.
        limit
            If present, limit the result count to at most this number of rows.

        Returns
        -------
        PaginatedList
            Results of the query wrapped with pagination information.
        """
        if cursor or limit:
            return await self._paginated_query(
                session, stmt, cursor=cursor, limit=limit
            )
        else:
            return await self._full_query(session, stmt)

    async def _full_query(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        scalar: bool = False,
    ) -> PaginatedList[E, C]:
        """Perform a full, unpaginated query.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied.
        scalar
            If `True`, the query returns one ORM object for each row instead
            of a tuple of columns.

        Returns
        -------
        PaginatedList
            Results of the query wrapped with pagination information.
        """
        stmt = self._cursor_type.apply_order(stmt)
        if scalar:
            result = await session.scalars(stmt)
        else:
            result = await session.execute(stmt)
        entries = [
            self._entry_type.model_validate(r, from_attributes=True)
            for r in result.all()
        ]
        return PaginatedList[E, C](
            entries=entries, prev_cursor=None, next_cursor=None
        )

    async def _paginated_query(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        cursor: C | None = None,
        limit: int | None = None,
        scalar: bool = False,
    ) -> PaginatedList[E, C]:
        """Perform a paginated query.

        The internal implementation details of the complicated case for
        `query`, where either a cursor or a limit is in play.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied.
        cursor
            If present, continue from the provided keyset cursor.
        limit
            If present, limit the result count to at most this number of rows.
        scalar
            If `True`, the query returns one ORM object for each row instead
            of a tuple of columns.

        Returns
        -------
        PaginatedList
            Results of the query wrapped with pagination information.
        """
        limited_stmt = stmt

        # Apply the cursor, if there is one.
        if cursor:
            limited_stmt = cursor.apply_cursor(limited_stmt)

        # When retrieving a previous set of results using a previous cursor,
        # we have to reverse the sort algorithm so that the cursor boundary
        # can be applied correctly. We'll then later reverse the result set to
        # return it in proper forward-sorted order.
        if cursor and cursor.previous:
            limited_stmt = cursor.apply_order(limited_stmt, reverse=True)
        else:
            limited_stmt = self._cursor_type.apply_order(limited_stmt)

        # Grab one more element than the query limit so that we know whether
        # to create a cursor (because there are more elements) and what the
        # cursor value should be (for forward cursors).
        if limit:
            limited_stmt = limited_stmt.limit(limit + 1)

        # Execute the query twice, once to get the next bach of results and
        # once to get the count of all entries without pagination.
        if scalar:
            result = await session.scalars(limited_stmt)
        else:
            result = await session.execute(limited_stmt)
        entries = [
            self._entry_type.model_validate(r, from_attributes=True)
            for r in result.all()
        ]

        # Calculate the cursors and remove the extra element we asked for.
        prev_cursor = None
        next_cursor = None
        if cursor and cursor.previous:
            next_cursor = cursor.invert()
            if limit and len(entries) > limit:
                prev = entries[limit - 1]
                prev_cursor = self._cursor_type.from_entry(prev, reverse=True)
                entries = entries[:limit]

            # Reverse the results again if we did a reverse sort because we
            # were using a previous cursor.
            entries.reverse()
        else:
            if cursor:
                prev_cursor = cursor.invert()
            if limit and len(entries) > limit:
                next_cursor = self._cursor_type.from_entry(entries[limit])
                entries = entries[:limit]

        # Return the results.
        return PaginatedList[E, C](
            entries=entries, prev_cursor=prev_cursor, next_cursor=next_cursor
        )


@dataclass
class CountedPaginatedList[E: BaseModel, C: PaginationCursor](
    PaginatedList[E, C]
):
    """Paginated SQL results with pagination metadata and total count.

    Holds a paginated list of any Pydantic type, complete with a count and
    cursors. Can hold any type of entry and any type of cursor, but implicitly
    requires the entry type be one that is meaningfully paginated by that type
    of cursor.
    """

    count: int
    """Total number of entries if queried without pagination."""


class CountedPaginatedQueryRunner[E: BaseModel, C: PaginationCursor](
    PaginatedQueryRunner[E, C]
):
    """Run database queries that return paginated results with counts.

    This variation of `PaginatedQueryRunner` always runs a second query to
    count the total number of available entries if queried without pagination.
    It should only be used on small tables or with queries that can be
    satisfied from the table indices; otherwise, the count query could be
    undesirably slow.

    Parameters
    ----------
    entry_type
        Type of each entry returned by the queries. This must be a Pydantic
        model.
    cursor_type
        Type of the pagination cursor, which encapsulates the logic of how
        entries are sorted and what set of keys is used to retrieve the next
        or previous batch of entries.
    """

    @override
    async def query_object(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        cursor: C | None = None,
        limit: int | None = None,
    ) -> CountedPaginatedList[E, C]:
        """Perform a query for objects with an optional cursor and limit.

        Perform the query provided in ``stmt`` with appropriate sorting and
        pagination as determined by the cursor type. Also performs a second
        query to get the total count of entries if retrieved without
        pagination.

        This method should be used with queries that return a single
        SQLAlchemy model. The provided query will be run with the session
        `~sqlalchemy.ext.asyncio.async_scoped_session.scalars` method and the
        resulting object passed to Pydantic's ``model_validate`` to convert to
        ``entry_type``. For queries returning a tuple of attributes, use
        `query_row` instead.

        Unfortunately, this distinction cannot be type-checked, so be careful
        to use the correct method.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied. This statement must return a list of SQLAlchemy
            ORM models that can be converted to ``entry_type`` by Pydantic.
        cursor
            If present, continue from the provided keyset cursor.
        limit
            If present, limit the result count to at most this number of rows.

        Returns
        -------
        CountedPaginatedList
            Results of the query wrapped with pagination information and a
            count of the total number of entries.
        """
        result = await super().query_object(
            session, stmt, cursor=cursor, limit=limit
        )
        count = await self.query_count(session, stmt)
        return CountedPaginatedList[E, C](
            entries=result.entries,
            next_cursor=result.next_cursor,
            prev_cursor=result.prev_cursor,
            count=count,
        )

    @override
    async def query_row(
        self,
        session: async_scoped_session,
        stmt: Select[tuple],
        *,
        cursor: C | None = None,
        limit: int | None = None,
    ) -> CountedPaginatedList[E, C]:
        """Perform a query for attributes with an optional cursor and limit.

        Perform the query provided in ``stmt`` with appropriate sorting and
        pagination as determined by the cursor type. Also performs a second
        query to get the total count of entries if retrieved without
        pagination.

        This method should be used with queries that return a list of
        attributes that can be converted to the ``entry_type`` Pydantic model.
        For queries returning a single ORM object, use `query_object` instead.

        Unfortunately, this distinction cannot be type-checked, so be careful
        to use the correct method.

        Parameters
        ----------
        session
            Database session within which to run the query.
        stmt
            Select statement to execute. Pagination and ordering will be
            added, so this statement should not already have limits or order
            clauses applied. This statement must return a tuple of attributes
            that can be converted to ``entry_type`` by Pydantic's
            ``model_validate``.
        cursor
            If present, continue from the provided keyset cursor.
        limit
            If present, limit the result count to at most this number of rows.

        Returns
        -------
        CountedPaginatedList
            Results of the query wrapped with pagination information and a
            count of the total number of entries.
        """
        result = await super().query_row(
            session, stmt, cursor=cursor, limit=limit
        )
        count = await self.query_count(session, stmt)
        return CountedPaginatedList[E, C](
            entries=result.entries,
            next_cursor=result.next_cursor,
            prev_cursor=result.prev_cursor,
            count=count,
        )
