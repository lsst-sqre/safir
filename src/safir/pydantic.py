"""Utility functions for Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AbstractSet, Any, Callable, Dict, Mapping, Optional, Union

from pydantic import BaseModel

# From Pydantic internals, so copy them here so that we can use them.  See the
# comment in CamelCaseModel about better ways to copy type signatures from
# Pydantic without duplicating code, possible in Python 3.10.
AbstractSetIntStr = AbstractSet[Union[int, str]]
MappingIntStrAny = Mapping[Union[int, str], Any]

__all__ = [
    "CamelCaseModel",
    "normalize_datetime",
    "normalize_isodatetime",
    "to_camel_case",
    "validate_exactly_one_of",
]


def normalize_datetime(
    v: Optional[Union[int, datetime]]
) -> Optional[datetime]:
    """Pydantic validator for datetime fields.

    Supports `~datetime.datetime` fields given in either any format supported
    by Pydantic natively, or in seconds since epoch (which Pydantic doesn't
    support).  This validator ensures that datetimes are always stored in the
    model as timezone-aware UTC datetimes.

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
    Here is a partial model that uses this function as a validator.

    .. code-block:: python

       class Info(BaseModel):
           last_used: Optional[datetime] = Field(
               None,
               title="Last used",
               description="When last used in seconds since epoch",
               example=1614986130,
           )

           _normalize_last_used = validator(
               "last_used", allow_reuse=True, pre=True
           )(normalize_datetime)
    """
    if v is None:
        return v
    elif isinstance(v, int):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    elif v.tzinfo and v.tzinfo.utcoffset(v) is not None:
        return v.astimezone(timezone.utc)
    else:
        return v.replace(tzinfo=timezone.utc)


def normalize_isodatetime(v: Optional[str]) -> Optional[datetime]:
    """Pydantic validator for datetime fields in ISO format.

    This validator requires the ISO 8601 date and time format with ``Z`` as
    the time zone (``YYYY-MM-DDTHH:MM:SSZ``).  This format is compatible with
    Kubernetes and the ISO UWS standard and is the same format produced by
    `safir.datetime.isodatetime`.  It should be used when the ambiguous
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
    Here is a partial model that uses this function as a validator.

    .. code-block:: python

       class Info(BaseModel):
           last_used: Optional[datetime] = Field(
               None,
               title="Last used",
               description="Date and time last used",
               example="2023-01-25T15:44:34Z",
           )

           _normalize_last_used = validator(
               "last_used", allow_reuse=True, pre=True
           )(normalize_isodatetime)
    """
    if v is None:
        return None
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("Must be a string in YYYY-MM-DDTHH:MM[:SS]Z format")
    try:
        return datetime.fromisoformat(v[:-1] + "+00:00")
    except Exception as e:
        raise ValueError(f"Invalid date {v}: {str(e)}") from e


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

           class Config:
               alias_generator = to_camel_case
               allow_population_by_field_name = True

    This must be added to every class that uses ``snake_case`` for an
    attribute and that needs to be initialized from ``camelCase``.
    Alternately, inherit from `~safir.pydantic.CamelCaseModel`, which is
    derived from `pydantic.BaseModel` with those settings added.
    """
    components = string.split("_")
    return components[0] + "".join(c.title() for c in components[1:])


class CamelCaseModel(BaseModel):
    """`pydantic.BaseModel` configured to accept camel-case input.

    This is a convenience class identical to `~pydantic.BaseModel` except with
    an alias generator configured so that it can be initialized with either
    camel-case or snake-case keys. Model exports with ``dict`` or ``json``
    also default to exporting in camel-case.
    """

    class Config:
        alias_generator = to_camel_case
        allow_population_by_field_name = True

    # A better solution for typing that wouldn't require copying the arguments
    # from Pydantic and therefore would be more future-proof would be to use
    # ParamSpec plus a decorator to copy the signature from the overridden
    # method. ParamSpec requires Python 3.10 and Safir currently supports
    # versions as old as Python 3.8, so that approach isn't yet usable.

    def dict(
        self,
        *,
        include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> Dict[str, Any]:
        """Export the model as a dictionary.

        Overridden to change the default of ``by_alias`` from `False` to
        `True`, so that by default the exported dictionary uses camel-case.
        """
        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def json(
        self,
        *,
        include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        encoder: Optional[Callable[[Any], Any]] = None,
        models_as_dict: bool = True,
        **dumps_kwargs: Any,
    ) -> str:
        """Export the model as JSON.

        Overridden to change the default of ``by_alias`` from `False` to
        `True`, so that by default the exported dictionary uses camel-case.
        """
        return super().json(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            encoder=encoder,
            models_as_dict=models_as_dict,
            **dumps_kwargs,
        )


def validate_exactly_one_of(
    *settings: str,
) -> Callable[[Any, Dict[str, Any]], Any]:
    """Generate a validator imposing a one and only one constraint.

    Sometimes, models have a set of attributes of which one and only one may
    be set. Ideally this is represented properly in the type system, but
    occasionally it's more convenient to use a validator. This is a validator
    generator that can produce a validator function that ensures one and only
    one of an arbitrary set of attributes must be set.

    Parameters
    ----------
    *settings
        List of names of attributes, of which one and only one must be set.
        At least two attribute names must be listed.

    Returns
    -------
    Callable
        The validator.

    Examples
    --------
    Use this inside a Pydantic class as a validator as follows:

    .. code-block:: python

       class Foo(BaseModel):
           foo: Optional[str] = None
           bar: Optional[str] = None
           baz: Optional[str] = None

           _validate_options = validator("baz", always=True, allow_reuse=True)(
               validate_exactly_one_of("foo", "bar", "baz")
           )

    The attribute listed as the first argument to the ``validator`` call must
    be the last attribute in the model definition so that any other attributes
    have already been seen.
    """
    if len(settings) < 2:
        msg = "validate_exactly_one_of takes at least two field names"
        raise ValueError(msg)

    if len(settings) == 2:
        options = f"{settings[0]} and {settings[1]}"
    else:
        options = ", ".join(settings[:-1]) + ", and " + settings[-1]

    def validator(v: Any, values: Dict[str, Any]) -> Any:
        seen = v is not None
        for setting in settings:
            if setting in values and values[setting] is not None:
                if seen:
                    raise ValueError(f"only one of {options} may be given")
                seen = True
        if not seen:
            raise ValueError(f"one of {options} must be given")
        return v

    return validator
