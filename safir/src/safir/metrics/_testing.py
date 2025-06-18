"""Helpers working with metrics events in unit tests."""

from abc import ABC, abstractmethod
from pprint import pformat
from typing import Any, override
from unittest.mock import ANY as MOCK_ANY

from ._models import EventPayload

__all__ = [
    "ANY",
    "NOT_NONE",
    "BaseAssertionError",
    "NotPublishedConsecutivelyError",
    "NotPublishedError",
    "PublishedCountError",
    "PublishedList",
    "PublishedTooFewError",
]

ANY = MOCK_ANY
"""An object that compares equal to anything, reexported from unittest.mock."""

type ModelDumpList = list[dict[str, Any]]
"""Type alias for a list of dumped Pydantic models."""


class _NotNone:
    """A helper object that compares equal to everything except None."""

    def __eq__(self, other: object) -> bool:
        return other is not None

    def __repr__(self) -> str:
        return "<NOT NONE>"

    __hash__ = object.__hash__


NOT_NONE = _NotNone()
"""An object to indicate that a value can be anything except None."""


class BaseAssertionError[P: EventPayload](ABC, AssertionError):
    """Base assertion error with common attributes and messaging."""

    def __init__(
        self,
        expected: ModelDumpList,
        actual: ModelDumpList,
        actual_models: list[P],
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.actual_models = actual_models
        message = (
            f"{self.errormsg()}\n"
            f"Expected:\n"
            f"{pformat(self.expected)}\n"
            f"Actual:\n"
            f"{pformat(self.actual)}\n"
            f"Actual models: {pformat(self.actual_models)}"
        )
        super().__init__(message)

    @abstractmethod
    def errormsg(self) -> str:
        """Return a string to be added to the exception message."""


class PublishedTooFewError[P: EventPayload](BaseAssertionError[P]):
    """Expected more events than have actually been published."""

    @override
    def errormsg(self) -> str:
        return "Expected more events than have actually been published"


class PublishedCountError[P: EventPayload](BaseAssertionError[P]):
    """Expected has a different number of items than were published."""

    @override
    def errormsg(self) -> str:
        return "Expected has a different number of items than were published"


class NotPublishedConsecutivelyError[P: EventPayload](BaseAssertionError[P]):
    """Expected events were not published consecutively."""

    @override
    def errormsg(self) -> str:
        return "Expected events were not published consecutively"


class NotPublishedError[P: EventPayload](BaseAssertionError[P]):
    """Some expected items were not published."""

    def __init__(
        self,
        *,
        expected: ModelDumpList,
        actual: ModelDumpList,
        actual_models: list[P],
        not_found: ModelDumpList,
    ) -> None:
        self.not_found = not_found
        super().__init__(expected, actual, actual_models)

    @override
    def errormsg(self) -> str:
        return (
            f"Some expected items not published\n"
            f"Not published:"
            f"{pformat(self.not_found)}"
        )


class PublishedList[P: EventPayload](list[P]):
    """A list of event payload models with assertion helpers.

    All assertion helpers take lists of dicts as expected items and use the
    ``model_dump(mode="json")`` serialization of the models for comparison.
    """

    def assert_published(
        self,
        expected: ModelDumpList,
        *,
        any_order: bool = False,
    ) -> None:
        """Assert that all of the expected payloads were published.


        Parameters
        ----------
        expected
            A list of expected event payload dicts, to be compared with the
            ``model_dump(format="json")`` serialization of the actual published
            payloads.
        any_order
            If true, then the expected payload list must be an ordered subset
            of the actual published payloads. This is like the ``any_order``
            parameter in `unittest.mock.Mock` methods.

        Raises
        ------
        PublishedTooFewError
            Expected more events than have actually been published
        NotPublishedError
            Some expected items were not published
        NotPublishedConsecutivelyError
            Expected events were not published consecutively
        """
        if len(expected) > len(self):
            actual = [model.model_dump(mode="json") for model in self]
            raise PublishedTooFewError(expected, actual, self)

        if any_order:
            self._check_unordered(expected)
        else:
            # Try unordered first to differentiate between the cases where some
            # expected events were not published at all, vs all of the expected
            # events were published, just not in the expected order.
            self._check_unordered(expected)
            self._check_ordered(expected)

    def assert_published_all(
        self,
        expected: ModelDumpList,
        *,
        any_order: bool = False,
    ) -> None:
        """Assert that all of the expected payloads, and only the expected
        payloads, were published.

        Parameters
        ----------
        expected
            A list of expected event payload dicts, to be compared with the
            ``model_dump(format="json")`` serialization of the actual published
            payloads.
        any_order
            If true, then the expected payloads must be in the same order as
            the actual published payloads. This is like the ``any_order``
            parameter in `unittest.mock.Mock` methods.

        Raises
        ------
        NotPublishedError
            Some expected items were not published
        NotPublishedConsecutivelyError
            Expected events were not published consecutively
        PublishedCountError
            A different number of events were published than were expected
        """
        if len(expected) != len(self):
            actual = [model.model_dump(mode="json") for model in self]
            raise PublishedCountError(expected, actual, self)
        self.assert_published(expected, any_order=any_order)

    def _check_unordered(
        self,
        expected: ModelDumpList,
    ) -> None:
        """Assert that each expected event was published.

        Each published event is matched only once. Taken from the
        ``unittest.mock`` ``assert_has_calls`` method.
        """
        actual = [model.model_dump(mode="json") for model in self]
        not_found = []
        tmp_actual = actual.copy()
        for item in expected:
            try:
                tmp_actual.remove(item)
            except ValueError:
                not_found.append(item)
        if not_found:
            raise NotPublishedError(
                expected=expected,
                actual=actual,
                actual_models=self,
                not_found=not_found,
            )

    def _check_ordered(self, expected: ModelDumpList) -> None:
        """Assert that the list of expected events is an ordered subset of the
        list of published events.

        Taken from the ``unittest.mock`` ``assert_has_calls`` method.
        """
        len_expected = len(expected)
        len_self = len(self)
        actual = [model.model_dump(mode="json") for model in self]
        for i in range(len_self - len_expected + 1):
            sub_list = actual[i : i + len_expected]
            if sub_list == expected:
                return
        raise NotPublishedConsecutivelyError(expected, actual, self)
