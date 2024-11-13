"""Additional types for Pydantic models."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Annotated, TypeAlias

from pydantic import (
    AfterValidator,
    BeforeValidator,
    PlainSerializer,
    UrlConstraints,
)
from pydantic_core import Url

from safir.datetime import isodatetime, parse_timedelta

from ._validators import normalize_datetime, normalize_isodatetime

__all__ = [
    "EnvAsyncPostgresDsn",
    "EnvRedisDsn",
    "HumanTimedelta",
    "IvoaIsoDatetime",
    "SecondsTimedelta",
    "UtcDatetime",
]


def _validate_env_async_postgres_dsn(v: Url) -> Url:
    """Possibly adjust a PostgreSQL DSN based on environment variables.

    When run via tox and tox-docker, the PostgreSQL hostname and port will be
    randomly selected and exposed only in environment variables. We have to
    patch that into the database URL at runtime since `tox doesn't have a way
    of substituting it into the environment
    <https://github.com/tox-dev/tox-docker/issues/55>`__.
    """
    if port := os.getenv("POSTGRES_5432_TCP_PORT"):
        return Url.build(
            scheme=v.scheme,
            username=v.username,
            password=v.password,
            host=os.getenv("POSTGRES_HOST", v.unicode_host() or "localhost"),
            port=int(port),
            path=v.path.lstrip("/") if v.path else v.path,
            query=v.query,
            fragment=v.fragment,
        )
    else:
        return v


EnvAsyncPostgresDsn: TypeAlias = Annotated[
    Url,
    UrlConstraints(
        host_required=True,
        allowed_schemes=["postgresql", "postgresql+asyncpg"],
    ),
    AfterValidator(_validate_env_async_postgres_dsn),
]
"""Async PostgreSQL data source URL honoring Docker environment variables.

Unlike the standard Pydantic ``PostgresDsn`` type, this type does not support
multiple hostnames because Safir's database library does not support multiple
hostnames.
"""


def _validate_env_redis_dsn(v: Url) -> Url:
    """Possibly adjust a Redis DSN based on environment variables.

    When run via tox and tox-docker, the Redis hostname and port will be
    randomly selected and exposed only in environment variables. We have to
    patch that into the Redis URL at runtime since `tox doesn't have a way of
    substituting it into the environment
    <https://github.com/tox-dev/tox-docker/issues/55>`__.
    """
    if port := os.getenv("REDIS_6379_TCP_PORT"):
        return Url.build(
            scheme=v.scheme,
            username=v.username,
            password=v.password,
            host=os.getenv("REDIS_HOST", v.unicode_host() or "localhost"),
            port=int(port),
            path=v.path.lstrip("/") if v.path else v.path,
            query=v.query,
            fragment=v.fragment,
        )
    else:
        return v


EnvRedisDsn: TypeAlias = Annotated[
    Url,
    UrlConstraints(
        allowed_schemes=["redis"],
        default_host="localhost",
        default_port=6379,
        default_path="/0",
    ),
    AfterValidator(_validate_env_redis_dsn),
]
"""Redis data source URL honoring Docker environment variables.

Unlike the standard Pydantic ``RedisDsn`` type, this does not support the
``rediss`` scheme, which indicates the use of TLS.
"""


def _validate_human_timedelta(v: str | float | timedelta) -> float | timedelta:
    if not isinstance(v, str):
        return v
    try:
        return float(v)
    except ValueError:
        return parse_timedelta(v)


HumanTimedelta: TypeAlias = Annotated[
    timedelta,
    BeforeValidator(_validate_human_timedelta),
    PlainSerializer(
        lambda t: t.total_seconds(), return_type=float, when_used="json"
    ),
]
"""Parse a human-readable string into a `datetime.timedelta`.

Accepts as input an integer or float (or stringified integer or float) number
of seconds, an already-parsed `~datetime.timedelta`, or a string consisting of
one or more sequences of numbers and duration abbreviations, separated by
optional whitespace.  Whitespace at the beginning and end of the string is
ignored. The supported abbreviations are:

- Week: ``weeks``, ``week``, ``w``
- Day: ``days``, ``day``, ``d``
- Hour: ``hours``, ``hour``, ``hr``, ``h``
- Minute: ``minutes``, ``minute``, ``mins``, ``min``, ``m``
- Second: ``seconds``, ``second``, ``secs``, ``sec``, ``s``

If several are present, they must be given in the above order. Example
valid strings are ``8d`` (8 days), ``4h 3minutes`` (four hours and three
minutes), and ``5w4d`` (five weeks and four days).
"""

SecondsTimedelta: TypeAlias = Annotated[
    timedelta,
    BeforeValidator(lambda v: v if not isinstance(v, str) else float(v)),
    PlainSerializer(
        lambda t: t.total_seconds(), return_type=float, when_used="json"
    ),
]
"""Parse a float number of seconds into a `datetime.timedelta`.

Accepts as input an integer or float (or stringified integer or float) number
of seconds or an already-parsed `~datetime.timedelta`. Compared to the
built-in Pydantic handling of `~datetime.timedelta`, an integer number of
seconds as a string is accepted, and ISO 8601 durations are not supported.
"""

UtcDatetime: TypeAlias = Annotated[
    datetime, AfterValidator(normalize_datetime)
]
"""Coerce a `~datetime.datetime` to UTC.

Accepts as input all of the normal Pydantic representations of a
`~datetime.datetime`, but then forces the result to be timezone-aware and in
UTC.
"""

IvoaIsoDatetime: TypeAlias = Annotated[
    datetime,
    BeforeValidator(normalize_isodatetime),
    PlainSerializer(isodatetime, return_type=str, when_used="json"),
]
"""Accept the ISO datetime format required by IVOA standards.

The IVOA DALI standard requires timestamps to be formatted as in ISO 8601 but
without full timezone information. Either the timezone should be omitted or
the time portion should end in ``Z``, and in either case the timestamp should
be interpreted as UTC.

This type accepts the input formats that DALI accepts, provides a
timezone-aware `~datetime.datetime` in UTC, and always serializes to the ISO
8601 format ending in ``Z``.
"""
