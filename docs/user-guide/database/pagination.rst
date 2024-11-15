#################
Paginated queries
#################

Pagination in a web API is the mechanism for returning a partial answer to a query with many results, alongside an easy way for the client to retrieve the next batch of results.
Implementing pagination for any query that may return a large number of results is considered best practice for web APIs.
Most clients will only need the first batch or two of results, batching results reduces latency, and shorter replies are easier to manage and create less memory pressure on both the server and client.

There are numerous ways to manage pagination (see `this blog post <https://www.citusdata.com/blog/2016/03/30/five-ways-to-paginate/>`__ for a good introductory overview).
Safir provides a generic implementation of keyset pagination with client-side cursors, which is often a reasonable choice.

Elements of a paginated query
=============================

A paginated query is a fairly complex operation that usually goes through multiple layers of data types.

First, your application will construct a SQL query that returns the full, unpaginated data set.
This may use other query parameters or information from the client to limit the results in ways unrelated to pagination.
This SQL query should not order the results; the order will be applied when the paginated query is done.

Second, your application optionally may provide either a limit on the number of results to return or a cursor indicating where in the overall list of results to pick up from.
If neither a limit nor a cursor is provided, the query is not paginated; you can still use the facilities discussed here for simplicity (and to avoid needing special cases for the non-paginated case), but pagination will not be done.

Third, your application passes the SQL query and any limit or cursor, along with a database session, into `~safir.database.PaginatedQueryRunner` to perform the query.
This will apply the sort order and any restrictions from the limit or cursor and then execute the query in that session.
It will return a `~safir.database.PaginatedList`, which holds the results along with pagination information.

Finally, the application will return, via the API handler, the list of entries included in the `~safir.database.PaginatedList` along with information about how to obtain the next or previous group of entries and the total number of records.
This pagination information is generally returned in HTTP headers, although if you wish to return it in a data structure wrapper around the results, you can do that instead.

Defining the cursor
===================

To use the generic paginated query support, first you must define the cursor that will be used for the queries.
The cursor class defines the following information needed for paginated queries:

#. How to construct a cursor to get all entries before or after a given entry.
#. How to serialize to and deserialize from a string so that the cursor can be returned to an API client and sent back to retrieve the next batch of results.
#. The sort order the cursor represents.
   A cursor class represents one and only one sort order, since keyset cursors rely on the sort order not changing.
   (Your application can use multiple cursors and thus support multiple sort orders, however.)
#. How to apply the cursor to limit a SQL statement.
#. How to invert a cursor (change it from going down the full list of results to going up the full list of results for previous links).

In the general case, your application must define the cursor by creating a subclass of `~safir.database.PaginationCursor` and implementing its abstract methods.

In the very common case that the API results are sorted first by some timestamp in descending order (most recent first) and then by an auto-increment unique key (most recently inserted row first), Safir provides `~safir.database.DatetimeIdCursor`, which is a generic cursor implementation that implements that ordering and keyset pagination policy.
In this case, you need only subclass `~safir.database.DatetimeIdCursor` and provide the SQLAlchemy ORM model columns that correspond to the timestamp and the unique key.

For example, if you are requesting paginated results from a table whose ORM model is named ``Job``, whose timestamp field is ``Job.creation_time``, and whose unique key is ``Job.id``, you can use the following cursor:

.. code-block:: python

   from safir.database import DatetimeIdCursor
   from sqlalchemy.orm import InstrumentedAttribute


   class JobCursor(DatetimeIdCursor):
       @staticmethod
       def id_column() -> InstrumentedAttribute:
           return Job.id

       @staticmethod
       def time_column() -> InstrumentedAttribute:
           return Job.creation_time

(These are essentially class properties, but due to limitations in Python abstract data types and property decorators, they're implemented as static methods.)

In this case, `~safir.database.DatetimeIdCursor` will handle all of the other details for you, including serialization and deserialization.

Performing paginated queries
============================

Parse the cursor and limit
--------------------------

Handlers for routes that return paginated results should take an optional pagination cursor as a query parameter.
This will be used by the client to move forward and backwards through the results.

The parameter declaration should generally look something like the following:

.. code-block:: python

   @router.get("/query", response_class=Model)
   async def query(
       *,
       cursor: Annotated[
           ModelCursor | None,
           Query(
               title="Pagination cursor",
               description=(
                   "Optional cursor used when moving between pages of results"
               ),
           ),
           BeforeValidator(lambda c: ModelCursor.from_str(c) if c else None),
       ] = None,
       limit: Annotated[
           int,
           Query(
               title="Row limit",
               description="Maximum number of entries to return",
               examples=[100],
               ge=1,
               le=100,
           ),
       ] = 100,
       request: Request,
       response: Response,
   ) -> list[Model]: ...

You should be able to use your class's implementation of `~safir.database.PaginationCursor.from_str` as a validator, which lets FastAPI validate the syntax of the cursor for you and handle syntax errors.
Since the cursor is optional (the first query won't have a cursor), you'll need a small wrapper to handle `None`, as shown above.

Also note the ``limit`` parameter, which should also be used on any paginated route.
This sets the size of each block of results.

As shown here, you will generally want to set some upper limit on how large the limit can be and set a default limit if none was provided.
This ensures that clients cannot retrieve the full list of results with one query.

If the clients are sufficiently trusted or if you're certain the application can handle returning the full list of objects without creating resource problems, you can allow ``limit`` to be omitted and default it to `None`.
The paginated query support in Safir will treat that as an unlimited query and will return all of the available results.
In this case, you should change the type to ``int | None`` and remove the ``le`` constraint on the parameter.

Create the runner
-----------------

The first step of performing a paginated query is to create a `~safir.database.PaginatedQueryRunner` object.
Its constructor takes as arguments the type of the Pydantic model that will hold each returned object and the type of the cursor that will be used for pagination.

.. code-block:: python

   runner = PaginatedQueryRunner(Job, JobCursor)

Construct the query
-------------------

Then, define the SQL query as a SQLAlchemy `~sqlalchemy.sql.expression.Select` statement.
You can do this in two ways: either a query that returns a single SQLAlchemy ORM model, or a query for a list of specific columns.
Other combinations are not supported.

For example:

.. code-block:: python

   stmt = select(Job).where(Job.username == "someuser")

Or, an example of selecting specific columns:

.. code-block:: python

   stmt = select(Job.id, Job.timestamp, Job.description)

Ensure that all of the attributes required to create a cursor are included in the query and in the Pydantic model.

In either case, the data returned by the query must be sufficient to construct the Pydantic model passed as the first argument to the `~safir.database.PaginatedQueryRunner` constructor.
The query result will be passed into the ``model_validate`` method of that model.
Among other things, this means that all necessary attributes must be present and the model must be able to handle any data conversion required.

If the model includes any timestamps, the model validation must be able to convert them from the time format stored in the database (see :doc:`datetime`) to an appropriate Python `~datetime.datetime`.
The easiest way to do this is to declare those fields as having the `safir.pydantic.UtcDatetime` type.
See :ref:`pydantic-datetime` for more information.

Run the query
-------------

Finally, you can run the query.
There are two ways to do this depending on how the query is structured.

If the SQL query returns a single ORM model for each result row, use `~safir.database.PaginatedQueryRunner.query_object`:

.. code-block:: python

   results = await runner.query_object(
       session, stmt, cursor=cursor, limit=limit
   )

If the SQL query returns a tuple of individually selected attributes that correspond to the fields of the result model (the first parameter to the `~safir.database.PaginatedQueryRunner` constructor), use `~safir.database.PaginatedQueryRunner.query_row`:

.. code-block:: python

   results = await runner.query_row(session, stmt, cursor=cursor, limit=limit)

Either way, the results will be a `~safir.database.PaginatedList` wrapping a list of Pydantic models of the appropriate type.

Returning paginated results
===========================

HTTP provides the ``Link`` header (:rfc:`8288`) to declare relationships between multiple web responses.
Using a ``Link`` header with relation types ``first``, ``next``, and ``prev`` is a standard way of providing the client with pagination information.

The Safir `~safir.database.PaginatedList` type provides a method, `~safir.database.PaginatedList.link_header`, which returns the contents of an HTTP ``Link`` header for a given paginated result.
It takes as its argument the base URL for the query (usually the current URL of a route handler).
This is the recommended way to return pagination information alongside a result.

Here is a very simplified example of a route handler that sets this header:

.. code-block:: python

   @router.get("/query", response_class=Model)
   async def query(
       *,
       cursor: Annotated[
           ModelCursor | None,
           Query(),
           BeforeValidator(lambda c: ModelCursor.from_str(c) if c else None),
       ] = None,
       limit: Annotated[int | None, Query()] = None,
       session: Annotated[
           async_scoped_session, Depends(db_session_dependency)
       ],
       request: Request,
       response: Response,
   ) -> list[Model]:
       runner = PydanticQueryRunner(Model, ModelCursor)
       stmt = build_query(...)
       results = await runner.query_object(
           session, stmt, cursor=cursor, limit=limit
       )
       if cursor or limit:
           response.headers["Link"] = results.link_header(request.url)
           response.headers["X-Total-Count"] = str(results.count)
       return results.entries

Here, ``perform_query`` is a wrapper around `~safir.database.PaginatedQueryRunner` that constructs and runs the query.
A real route handler would have more query parameters and more documentation.

Note that this example also sets a non-standard ``X-Total-Count`` header containing the total count of entries returned by the underlying query without pagination.
`~safir.database.PaginatedQueryRunner` obtains this information by default, since the count query is often fast for databases to perform.
There is no standard way to return this information to the client, but ``X-Total-Count`` is a widely-used informal standard.
