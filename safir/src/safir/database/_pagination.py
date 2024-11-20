"""Support for paginated database queries.

This pagination support uses keyset pagination rather than relying on database
cursors, since the latter interact poorly with horizontally scaled services.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, Self, TypeVar
from urllib.parse import parse_qs, urlencode

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute
from starlette.datastructures import URL

from ._datetime import datetime_to_db

C = TypeVar("C", bound="PaginationCursor")
"""Type of a cursor for a paginated list."""

E = TypeVar("E", bound="BaseModel")
"""Type of an entry in a paginated list."""

__all__ = [
    "DatetimeIdCursor",
    "PaginationCursor",
    "PaginatedList",
    "PaginatedQueryRunner",
]


@dataclass
class PaginationCursor(Generic[E], metaclass=ABCMeta):
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
        the provided entry if ``reverse`` is set to `True`.

        Parameters
        ----------
        entry
            Basis of the cursor.
        reverse
            Whether to create a previous cursor.

        Returns
        -------
        PaginationCursor
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
        PaginationCursor
            The cursor represented as an object.

        Raises
        ------
        ValueError
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
        PaginationCursor
            The inverted cursor.
        """


@dataclass
class DatetimeIdCursor(PaginationCursor[E], metaclass=ABCMeta):
    """Pagination cursor using a `~datetime.datetime` and unique column ID.

    Cursors that first order by time and then by unique column ID can subclass
    this class and only define the ``id_column`` and ``time_column`` static
    methods to return the ORM model fields for the timestamp and column ID.

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
            raise ValueError(f"Cannot parse cursor: {e!s}") from e

    @classmethod
    def apply_order(cls, stmt: Select, *, reverse: bool = False) -> Select:
        if reverse:
            return stmt.order_by(cls.time_column(), cls.id_column())
        else:
            return stmt.order_by(
                cls.time_column().desc(), cls.id_column().desc()
            )

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

    def invert(self) -> Self:
        return type(self)(
            time=self.time, id=self.id, previous=not self.previous
        )

    def __str__(self) -> str:
        previous = "p" if self.previous else ""
        timestamp = self.time.timestamp()

        # Remove a trailing .0, but keep the fractional portion if it matters.
        if int(timestamp) == timestamp:
            timestamp = int(timestamp)

        return f"{previous}{timestamp!s}_{self.id!s}"


@dataclass
class PaginatedList(Generic[E, C]):
    """Paginated SQL results with accompanying pagination metadata.

    Holds a paginated list of any Pydantic type, complete with a count and
    cursors. Can hold any type of entry and any type of cursor, but
    implicitly requires the entry type be one that is meaningfully paginated by that
    type of cursor.
    """

    entries: list[E]
    """The history entries."""

    count: int
    """Total available entries."""

    next_cursor: C | None = None
    """Cursor for the next batch of entries."""

    prev_cursor: C | None = None
    """Cursor for the previous batch of entries."""

    def link_header(self, base_url: URL) -> str:
        """Construct an RFC 8288 ``Link`` header for a paginated result.

        Parameters
        ----------
        base_url
            The starting URL of the current group of entries.
        """
        first_url = base_url.remove_query_params("cursor")
        header = f'<{first_url!s}>; rel="first"'
        params = parse_qs(first_url.query)
        if self.next_cursor:
            params["cursor"] = [str(self.next_cursor)]
            next_url = first_url.replace(query=urlencode(params, doseq=True))
            header += f', <{next_url!s}>; rel="next"'
        if self.prev_cursor:
            params["cursor"] = [str(self.prev_cursor)]
            prev_url = first_url.replace(query=urlencode(params, doseq=True))
            header += f', <{prev_url!s}>; rel="prev"'
        return header


class PaginatedQueryRunner(Generic[E, C]):
    """Construct and run database queries that return paginated results.

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

    async def query_object(
        self,
        session: async_scoped_session,
        stmt: Select[tuple[DeclarativeBase]],
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

        # No pagination was required. Run the simple query in the correct
        # sorted order and return it with no cursors.
        stmt = self._cursor_type.apply_order(stmt)
        result = await session.scalars(stmt)
        entries = [
            self._entry_type.model_validate(r, from_attributes=True)
            for r in result.all()
        ]
        return PaginatedList[E, C](
            entries=entries,
            count=len(entries),
            prev_cursor=None,
            next_cursor=None,
        )

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

        # No pagination was required. Run the simple query in the correct
        # sorted order and return it with no cursors.
        stmt = self._cursor_type.apply_order(stmt)
        result = await session.execute(stmt)
        entries = [
            self._entry_type.model_validate(r, from_attributes=True)
            for r in result.all()
        ]
        return PaginatedList[E, C](
            entries=entries,
            count=len(entries),
            prev_cursor=None,
            next_cursor=None,
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
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count = await session.scalar(count_stmt) or 0

        # Calculate the cursors and remove the extra element we asked for.
        prev_cursor = None
        next_cursor = None
        if cursor and cursor.previous:
            if limit:
                next_cursor = cursor.invert()
                if len(entries) > limit:
                    prev = entries[limit - 1]
                    prev_cursor = self._cursor_type.from_entry(prev)
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
            entries=entries,
            count=count,
            prev_cursor=prev_cursor,
            next_cursor=next_cursor,
        )
