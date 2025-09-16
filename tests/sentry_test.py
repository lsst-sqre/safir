"""Tests for Sentry helpers."""

from typing import override

import sentry_sdk

from safir.slack.blockkit import SentryEventInfo, SlackException
from safir.testing.sentry import Captured


class SomeError(SlackException):
    """An exception type to test before_send handling."""

    def __init__(self, woo: str, bar: str, user: str | None = None) -> None:
        self.woo = woo
        self.bar = bar
        self.user = user

    @override
    def to_sentry(self) -> SentryEventInfo:
        info = super().to_sentry()
        info.tags["woo"] = self.woo
        info.contexts["foo"] = {"bar": self.bar}
        return info


def test_env_fingerprint_before_send(
    sentry_fingerprint_items: Captured,
) -> None:
    sentry_sdk.capture_exception(Exception("some error"))
    (error,) = sentry_fingerprint_items.errors
    assert error["fingerprint"] == ["{{ default }}", "some_env"]


def test_sentry_exception_before_send(
    sentry_exception_items: Captured,
) -> None:
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_exception_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"


def test_combined_before_send(sentry_combo_items: Captured) -> None:
    exc = SomeError(woo="hoo", bar="baz", user="someuser")

    sentry_sdk.capture_exception(exc)

    (error,) = sentry_combo_items.errors
    assert error["contexts"]["foo"] == {"bar": "baz"}
    assert error["fingerprint"] == ["{{ default }}", "some_env"]
    assert error["tags"] == {"woo": "hoo"}
    assert error["user"]["username"] == "someuser"
