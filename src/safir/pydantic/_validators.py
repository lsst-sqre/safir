"""Validation functions for Pydantic models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from safir.datetime import parse_isodatetime

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

    Raises
    ------
    ValueError
        Raised if the input could not be parsed as a `~datetime.datetime`.

    Notes
    -----
    Prefer to use the `~safir.pydantic.UtcDatetime` type instead of using this
    function as a validator.

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


def normalize_isodatetime(v: Any) -> datetime | None:
    """Pydantic field validator for datetime fields in ISO format.

    This field validator requires a subset of the ISO 8601 date and time
    format, ``YYYY-MM-DD[THH:MM:SS[.mmm]][Z]``. Regardless of whether the
    trailing ``Z`` is included, the date and time are interpreted as being in
    UTC, not local time. This format is compatible with Kubernetes, the IVOA
    DALI standard, and the format produced by `safir.datetime.isodatetime`.

    It should be used when the other formats supported by Pydantic by default
    (such as dates and times in other timezones) shouldn't be allowed, such as
    when strict conformance with the IVOA standard is desired.

    Parameters
    ----------
    v
        Field representing a `~datetime.datetime`.

    Returns
    -------
    datetime.datetime or None
        The timezone-aware `~datetime.datetime` or `None` if the input was
        `None`.

    Raises
    ------
    ValueError
        Raised if the provided time string is not in the correct format.

    Notes
    -----
    Prefer to use the `~safir.pydantic.IvoaIsoDatetime` type instead of using
    this function as a validator.

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
    if not isinstance(v, str):
        msg = "Must be a string in YYYY-MM-DD[THH:MM:SS[:mmm]][Z] format"
        raise ValueError(msg)
    return parse_isodatetime(v)


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

    def validator[T: BaseModel](model: T) -> T:
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
