"""Utility functions for Pydantic models."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ParamSpec, TypeAlias, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    UrlConstraints,
)
from pydantic_core import Url

from safir.datetime import parse_timedelta

P = ParamSpec("P")
T = TypeVar("T")

__all__ = [
    "CamelCaseModel",
    "EnvAsyncPostgresDsn",
    "EnvRedisDsn",
    "HumanTimedelta",
    "SecondsTimedelta",
    "normalize_datetime",
    "normalize_isodatetime",
    "to_camel_case",
    "validate_exactly_one_of",
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
    timedelta, BeforeValidator(_validate_human_timedelta)
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
    BeforeValidator(lambda v: v if not isinstance(v, str) else int(v)),
]
"""Parse a float number of seconds into a `datetime.timedelta`.

Accepts as input an integer or float (or stringified integer or float) number
of seconds or an already-parsed `~datetime.timedelta`. Compared to the
built-in Pydantic handling of `~datetime.timedelta`, an integer number of
seconds as a string is accepted, and ISO 8601 durations are not supported.
"""


def normalize_datetime(v: Any) -> datetime | None:
    """Pydantic field validator for datetime fields.

    Supports `~datetime.datetime` fields given as either datetime objects or
    seconds since epoch (not the other types Pydantic natively supports) and
    ensures that the resulting datetime object is timezone-aware and in the
    UTC timezone.

    Parameters
    ----------
    v
        Field representing a `~datetime.datetime`.

    Returns
    -------
    datetime.datetime or None
        The timezone-aware `~datetime.datetime` or `None` if the input was
        `None`.

    Examples
    --------
    Here is a partial model that uses this function as a field validator.

    .. code-block:: python

       class Info(BaseModel):
           last_used: datetime | None = Field(
               None,
               title="Last used",
               description="When last used in seconds since epoch",
               examples=[1614986130],
           )

           _normalize_last_used = field_validator("last_used", mode="before")(
               normalize_datetime
           )
    """
    if v is None:
        return v
    elif isinstance(v, int):
        return datetime.fromtimestamp(v, tz=UTC)
    elif not isinstance(v, datetime):
        raise ValueError("Must be a datetime or seconds since epoch")
    elif v.tzinfo and v.tzinfo.utcoffset(v) is not None:
        return v.astimezone(UTC)
    else:
        return v.replace(tzinfo=UTC)


def normalize_isodatetime(v: str | None) -> datetime | None:
    """Pydantic field validator for datetime fields in ISO format.

    This field validator requires the ISO 8601 date and time format with ``Z``
    as the time zone (``YYYY-MM-DDTHH:MM:SSZ``). This format is compatible
    with Kubernetes and the ISO UWS standard and is the same format produced
    by `safir.datetime.isodatetime`. It should be used when the ambiguous
    formats supported by Pydantic by default (such as dates and times without
    time zone information) shouldn't be allowed.

    Parameters
    ----------
    v
        The field representing a `~datetime.datetime`.

    Returns
    -------
    datetime.datetime or None
        The timezone-aware `~datetime.datetime` or `None` if the input was
        `None`.

    Examples
    --------
    Here is a partial model that uses this function as a field validator.

    .. code-block:: python

       class Info(BaseModel):
           last_used: datetime | None = Field(
               None,
               title="Last used",
               description="Date and time last used",
               examples=["2023-01-25T15:44:34Z"],
           )

           _normalize_last_used = field_validator("last_used", mode="before")(
               normalize_isodatetime
           )
    """
    if v is None:
        return None
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("Must be a string in YYYY-MM-DDTHH:MM[:SS]Z format")
    try:
        return datetime.fromisoformat(v[:-1] + "+00:00")
    except Exception as e:
        raise ValueError(f"Invalid date {v}: {e!s}") from e


def to_camel_case(string: str) -> str:
    """Convert a string to camel case.

    Intended for use with Pydantic as an alias generator so that the model can
    be initialized from camel-case input, such as Kubernetes objects or
    settings from Helm charts.

    Parameters
    ----------
    string
        Input string.

    Returns
    -------
    str
        String converted to camel-case with the first character in lowercase.

    Examples
    --------
    To support ``camelCase`` input to a model, use the following settings:

    .. code-block:: python

       class Model(BaseModel):
           some_field: str

           model_config = ConfigDict(
               alias_generator=to_camel_case, populate_by_name=True
           )

    This must be added to every class that uses ``snake_case`` for an
    attribute and that needs to be initialized from ``camelCase``.
    Alternately, inherit from `~safir.pydantic.CamelCaseModel`, which is
    derived from `pydantic.BaseModel` with those settings added.
    """
    components = string.split("_")
    return components[0] + "".join(c.title() for c in components[1:])


def _copy_type(
    parent: Callable[P, T],
) -> Callable[[Callable[..., T]], Callable[P, T]]:
    """Copy the type of a parent method.

    Used to avoid duplicating the prototype of `pydantic.BaseModel.dict` and
    `pydantic.BaseModel.json` when overriding them in `CamelCaseModel`.

    Parameters
    ----------
    parent
        Method from which to copy a type signature.

    Returns
    -------
    Callable
        Decorator that will replace the type signature of a function with the
        type signature of its parent.
    """
    return lambda x: x


class CamelCaseModel(BaseModel):
    """`pydantic.BaseModel` configured to accept camel-case input.

    This is a convenience class identical to `~pydantic.BaseModel` except with
    an alias generator configured so that it can be initialized with either
    camel-case or snake-case keys. Model exports with ``model_dump`` or
    ``model_dump_json`` also default to exporting in camel-case.
    """

    model_config = ConfigDict(
        alias_generator=to_camel_case, populate_by_name=True
    )

    @_copy_type(BaseModel.model_dump)
    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Export the model as a dictionary.

        Overridden to change the default of ``by_alias`` from `False` to
        `True`, so that by default the exported dictionary uses camel-case.
        """
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        return super().model_dump(**kwargs)

    @_copy_type(BaseModel.model_dump_json)
    def model_dump_json(self, **kwargs: Any) -> str:
        """Export the model as JSON.

        Overridden to change the default of ``by_alias`` from `False` to
        `True`, so that by default the exported dictionary uses camel-case.
        """
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        return super().model_dump_json(**kwargs)


def validate_exactly_one_of(
    *settings: str,
) -> Callable[[BaseModel], BaseModel]:
    """Generate a model validator imposing a one and only one constraint.

    Sometimes, models have a set of attributes of which one and only one may
    be set. Ideally this is represented properly in the type system, but
    occasionally it's more convenient to use a model validator. This is a
    model validator generator that can produce a model validator function that
    ensures one and only one of an arbitrary set of attributes must be set.

    Parameters
    ----------
    *settings
        List of names of attributes, of which one and only one must be set.
        At least two attribute names must be listed.

    Returns
    -------
    Callable
        Resulting model validator.

    Examples
    --------
    Use this inside a Pydantic class as a model validator as follows:

    .. code-block:: python

       class Foo(BaseModel):
           foo: Optional[str] = None
           bar: Optional[str] = None
           baz: Optional[str] = None

           _validate_options = model_validator(mode="after")(
               validate_exactly_one_of("foo", "bar", "baz")
           )

    The attribute listed as the first argument to the ``model_validator`` call
    must be the last attribute in the model definition so that any other
    attributes have already been seen.
    """
    if len(settings) < 2:
        msg = "validate_exactly_one_of takes at least two field names"
        raise ValueError(msg)

    if len(settings) == 2:
        options = f"{settings[0]} and {settings[1]}"
    else:
        options = ", ".join(settings[:-1]) + ", and " + settings[-1]

    def validator(model: T) -> T:
        seen = False
        for setting in settings:
            if getattr(model, setting, None) is not None:
                if seen:
                    raise ValueError(f"only one of {options} may be given")
                seen = True
        if not seen:
            raise ValueError(f"one of {options} must be given")
        return model

    return validator
