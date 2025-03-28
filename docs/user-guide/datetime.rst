#################
datetime handling
#################

There are an unfortunately large number of ways to represent dates and times in Python and in serialization formats.
Unless they're used consistently, conflicting expectations may lead to bugs.
Applications using Safir may wish to follow these rules:

- All internal representations of dates and times should be converted to `~datetime.datetime` objects as early as possible, and converted back to other formats as late as possible.
  All internal APIs should expect `~datetime.datetime` objects.

- All `~datetime.datetime` objects used internally by the application should be time zone aware and in the UTC time zone.

- All time intervals should be converted to `~datetime.timedelta` objects as early as possible, and all internal APIs should expect `~datetime.timedelta` objects.
  The one exception is when the time interval is a constant used as a validation parameter in contexts (such as some Pydantic and FastAPI cases) where a `~datetime.timedelta` is not supported.

Safir provides several small utility functions for `~datetime.datetime` handling to help ensure consistency with these rules.
Also see the Pydantic validation functions at :ref:`pydantic-datetime` and the utility functions for handling `~datetime.datetime` objects in database schemas in :doc:`database/datetime`.

Getting the current date and time
=================================

To get the current date and time as a `~datetime.datetime` object, use `safir.datetime.current_datetime`.

In addition to ensuring that the returned object is time zone aware and uses the UTC time zone, this function sets microseconds to zero by default.
This is useful for database-based applications, since databases may or may not store milliseconds or, worse, accept non-zero milliseconds and then silently discard them.
Mixing `~datetime.datetime` objects with and without microseconds can lead to confusing bugs, which using this function consistently can avoid.

If microseconds are needed for a particular use (presumably one where the timestamps will never be stored in a database), pass ``microseconds=True`` as an argument.

Date and time serialization
===========================

There are two reasonable serialization formats for dates and times: seconds since epoch, and ISO 8601.
Both are also supported by Pydantic.

Seconds since epoch has the advantage of extreme simplicity and clarity, since by UNIX convention seconds since epoch is always in UTC and easy to both generate and parse.
However, it's not very friendly to humans, who usually can't convert seconds since epoch into a human-meaningful date or time in their head.

ISO 8601 is a large and complex standard that supports numerous partial date or time representations, time zone information, week numbers, and time intervals.
However, its most basic date and time format, ``YYYY-MM-DDTHH:MM:SSZ`` (where the ``T`` and ``Z`` are fixed letters and the other letters represent their normal date and time components), provides a good balance of unambiguous parsing and human readability.
The trailing ``Z`` indicates UTC.

This subset of ISO 8601 is used by both Kubernetes and the IVOA DALI standard, but the IVOA DALI standard allows omitting ``Z`` (the time is still interpreted as UTC) and omitting the time portion entirely.

Safir provides two utility functions for this subset of ISO 8601.
`safir.datetime.isodatetime` converts a `~datetime.datetime` to this format.
`safir.datetime.parse_isodatetime` goes the opposite direction, converting this format to a time zone aware `~datetime.datetime` in UTC.

If, as is more often the case, you are accepting or generating `~datetime.datetime` fields as part of a Pydantic model, see :ref:`pydantic-datetime`.

Formatting datetimes for logging
================================

While the ISO 8601 format is recommended for dates that need to be read by both computers and humans, it is not ideal for humans.
The ``T`` in the middle and the trailing ``Z`` can make it look cluttered, and some timestamps (such as for error events) benefit from the precision of milliseconds.

Safir therefore also provides `safir.datetime.format_datetime_for_logging`, which formats a `~datetime.datetime` object as ``YYYY-MM-DD HH:MM:SS[.sss]``, where the milliseconds are included only if the `~datetime.datetime` object has non-zero microseconds.
(That last rule avoids adding spurious ``.000`` strings to every formatted timestamp when the program only tracks times to second precision, such as when `~safir.datetime.current_datetime` is used.)

As the name of the function indicates, this function should only be used when formatting dates for logging and other human display.
Dates that may need to be parsed again by another program should use `~safir.datetime.isodatetime` instead.

.. _datetime-timedelta:

Parsing time intervals
======================

Pydantic by default supports specifying `datetime.timedelta` fields as either a floating-point number of seconds or as an ISO 8601 duration.
The syntax for ISO 8601 durations is unambiguous but obscure.
For example, ``P23DT23H`` represents a duration of 23 days and 23 hours.

Safir provides a function, `safir.datetime.parse_timedelta` that parses an alternative syntax for specifying durations that's easier for humans to read and is similar to the syntax supported by other languages and libraries.
Its input is a list of numbers and duration abbreviations, optionally separated by whitespace.
The supported abbreviations are:

- Week: ``weeks``, ``week``, ``w``
- Day: ``days``, ``day``, ``d``
- Hour: ``hours``, ``hour``, ``hr``, ``h``
- Minute: ``minutes``, ``minute``, ``mins``, ``min``, ``m``
- Second: ``seconds``, ``second``, ``secs``, ``sec``, ``s``

So, for example, the duration mentioned above could be given as ``23d23h`` or ``23days 23hours``.

To accept this syntax as input for a Pydantic model, declare the field to have the type `safir.pydantic.HumanTimedelta`.
This will automatically convert input strings using the `~safir.datetime.parse_timedelta` function.
See :ref:`pydantic-timedelta` for more information.
