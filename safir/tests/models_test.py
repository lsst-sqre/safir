"""Tests for `safir.models`."""

from __future__ import annotations

import json

from safir.models import ErrorModel, LinkData


def test_error_model() -> None:
    """Nothing much to test, but make sure the code can be imported."""
    error = {
        "detail": [
            {
                "loc": ["path", "foo"],
                "msg": "Invalid foo",
                "type": "invalid_foo",
            }
        ]
    }
    model = ErrorModel.model_validate_json(json.dumps(error))
    assert model.model_dump() == error


def test_link_data() -> None:
    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=1600000000.5_1>; rel="next"'
    )
    link = LinkData.from_header(header)
    assert not link.prev_url
    assert link.next_url == "https://example.com/query?cursor=1600000000.5_1"
    assert link.first_url == "https://example.com/query"

    header = (
        '<https://example.com/query?limit=10>; rel="first", '
        '<https://example.com/query?limit=10&cursor=15_2>; rel="next", '
        '<https://example.com/query?limit=10&cursor=p5_1>; rel="prev"'
    )
    link = LinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?limit=10&cursor=p5_1"
    assert link.next_url == "https://example.com/query?limit=10&cursor=15_2"
    assert link.first_url == "https://example.com/query?limit=10"

    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=p1510000000_2>; rel="previous"'
    )
    link = LinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?cursor=p1510000000_2"
    assert not link.next_url
    assert link.first_url == "https://example.com/query"

    header = '<https://example.com/query?foo=b>; rel="first"'
    link = LinkData.from_header(header)
    assert not link.prev_url
    assert not link.next_url
    assert link.first_url == "https://example.com/query?foo=b"

    link = LinkData.from_header("")
    assert not link.prev_url
    assert not link.next_url
    assert not link.first_url
