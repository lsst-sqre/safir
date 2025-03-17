"""Tests for mock publishers."""

from typing import cast

import pytest
from pydantic import ConfigDict

from safir.metrics import (
    ANY,
    NOT_NONE,
    EventPayload,
    EventsConfiguration,
    MockEventPublisher,
    MockMetricsConfiguration,
    NotPublishedConsecutivelyError,
    NotPublishedError,
    PublishedCountError,
    PublishedList,
)


async def publish() -> PublishedList:
    """Mock publish some events and return the PublishedList."""
    config = MockMetricsConfiguration(
        enabled=False,
        mock=True,
        application="testapp",
        events=EventsConfiguration(topic_prefix="what.ever"),
    )
    manager = config.make_manager()

    class SomeEvent(EventPayload):
        model_config = ConfigDict(ser_json_timedelta="float")

        foo: str
        count: int
        duration: float | None

    await manager.initialize()
    pub = await manager.create_publisher("someevent", SomeEvent)

    await pub.publish(SomeEvent(foo="foo1", count=1, duration=1.234))
    await pub.publish(SomeEvent(foo="foo2", count=2, duration=2.345))
    await pub.publish(SomeEvent(foo="foo3", count=3, duration=3.456))
    await pub.publish(SomeEvent(foo="foo4", count=4, duration=None))
    await pub.publish(SomeEvent(foo="foo5", count=5, duration=5.678))

    await manager.aclose()

    return cast("MockEventPublisher", pub).published


@pytest.mark.asyncio
async def test_assert_one() -> None:
    pub = await publish()
    pub.assert_published(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
        ]
    )
    pub.assert_published(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
        ],
        any_order=False,
    )

    with pytest.raises(NotPublishedError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1},
            ]
        )


@pytest.mark.asyncio
async def test_assert_unordered() -> None:
    pub = await publish()
    pub.assert_published(
        [
            {"foo": "foo2", "count": 2, "duration": 2.345},
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo3", "count": 3, "duration": 3.456},
        ],
        any_order=True,
    )

    with pytest.raises(NotPublishedConsecutivelyError):
        pub.assert_published(
            [
                {"foo": "foo2", "count": 2, "duration": 2.345},
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo3", "count": 3, "duration": 3.456},
            ],
        )


@pytest.mark.asyncio
async def test_only_counted_once() -> None:
    pub = await publish()

    with pytest.raises(NotPublishedError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo1", "count": 1, "duration": 1.234},
            ],
            any_order=True,
        )


@pytest.mark.asyncio
async def test_assert_ordered() -> None:
    pub = await publish()
    pub.assert_published(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo2", "count": 2, "duration": 2.345},
            {"foo": "foo3", "count": 3, "duration": 3.456},
        ]
    )

    with pytest.raises(NotPublishedConsecutivelyError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo3", "count": 3, "duration": 3.456},
            ],
        )


@pytest.mark.asyncio
async def test_assert_extra() -> None:
    pub = await publish()
    with pytest.raises(NotPublishedError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo2", "count": 2, "duration": 2.345},
                {"foo": "foo3", "count": 3, "duration": 3.456},
                {"foo": "nope", "count": 3, "duration": 3.456},
            ]
        )
    with pytest.raises(NotPublishedError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo2", "count": 2, "duration": 2.345},
                {"foo": "foo3", "count": 3, "duration": 3.456},
                {"foo": "nope", "count": 3, "duration": 3.456},
            ],
            any_order=False,
        )


@pytest.mark.asyncio
async def test_assert_all() -> None:
    pub = await publish()
    pub.assert_published_all(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo2", "count": 2, "duration": 2.345},
            {"foo": "foo4", "count": 4, "duration": None},
            {"foo": "foo3", "count": 3, "duration": 3.456},
            {"foo": "foo5", "count": 5, "duration": 5.678},
        ],
        any_order=True,
    )

    pub.assert_published_all(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo2", "count": 2, "duration": 2.345},
            {"foo": "foo3", "count": 3, "duration": 3.456},
            {"foo": "foo4", "count": 4, "duration": None},
            {"foo": "foo5", "count": 5, "duration": 5.678},
        ],
    )

    with pytest.raises(PublishedCountError):
        pub.assert_published_all(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo2", "count": 2, "duration": 2.345},
                {"foo": "foo4", "count": 4, "duration": None},
                {"foo": "foo3", "count": 3, "duration": 3.456},
            ]
        )

    with pytest.raises(NotPublishedConsecutivelyError):
        pub.assert_published_all(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo2", "count": 2, "duration": 2.345},
                {"foo": "foo4", "count": 4, "duration": None},
                {"foo": "foo3", "count": 3, "duration": 3.456},
                {"foo": "foo5", "count": 5, "duration": 5.678},
            ],
        )


@pytest.mark.asyncio
async def test_any_and_not_none() -> None:
    pub = await publish()
    pub.assert_published(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo2", "count": 2, "duration": ANY},
            {"foo": "foo3", "count": 3, "duration": 3.456},
            {"foo": "foo4", "count": 4, "duration": ANY},
        ]
    )

    pub.assert_published(
        [
            {"foo": "foo1", "count": 1, "duration": 1.234},
            {"foo": "foo2", "count": 2, "duration": NOT_NONE},
            {"foo": "foo3", "count": 3, "duration": 3.456},
            {"foo": "foo4", "count": 4, "duration": ANY},
        ]
    )

    with pytest.raises(NotPublishedError):
        pub.assert_published(
            [
                {"foo": "foo1", "count": 1, "duration": 1.234},
                {"foo": "foo2", "count": 2, "duration": NOT_NONE},
                {"foo": "foo3", "count": 3, "duration": 3.456},
                {"foo": "foo4", "count": 4, "duration": NOT_NONE},
            ]
        )
