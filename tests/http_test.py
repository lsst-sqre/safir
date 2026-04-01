"""Tests for the HTTP utility functions."""

from safir.http import PaginationLinkData


def test_pagination_link_data() -> None:
    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=1600000000.5_1>; rel="next"'
    )
    link = PaginationLinkData.from_header(header)
    assert not link.prev_url
    assert link.next_url == "https://example.com/query?cursor=1600000000.5_1"
    assert link.first_url == "https://example.com/query"

    header = (
        "<https://example.com/query?limit=10>; rel=first, "
        "<https://example.com/query?limit=10&cursor=15_2>; rel=next, "
        "<https://example.com/query?limit=10&cursor=p5_1>; rel=prev"
    )
    link = PaginationLinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?limit=10&cursor=p5_1"
    assert link.next_url == "https://example.com/query?limit=10&cursor=15_2"
    assert link.first_url == "https://example.com/query?limit=10"

    header = (
        '<https://example.com/query>; rel="first", '
        '<https://example.com/query?cursor=p1510000000_2>; rel="previous"'
    )
    link = PaginationLinkData.from_header(header)
    assert link.prev_url == "https://example.com/query?cursor=p1510000000_2"
    assert not link.next_url
    assert link.first_url == "https://example.com/query"

    header = '<https://example.com/query?foo=b>; rel="first"'
    link = PaginationLinkData.from_header(header)
    assert not link.prev_url
    assert not link.next_url
    assert link.first_url == "https://example.com/query?foo=b"

    link = PaginationLinkData.from_header("")
    assert not link.prev_url
    assert not link.next_url
    assert not link.first_url
