"""Validation functions for Pydantic models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

__all__ = [
    "normalize_datetime",
    "normalize_isodatetime",
    "validate_exactly_one_of",
]


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
