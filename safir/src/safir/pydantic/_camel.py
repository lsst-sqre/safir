"""Camel-case attribute support for Pydantic models."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel, ConfigDict

P = ParamSpec("P")
T = TypeVar("T")


__all__ = [
    "CamelCaseModel",
    "to_camel_case",
]


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
