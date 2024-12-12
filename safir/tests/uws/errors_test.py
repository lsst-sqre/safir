"""Tests for errors from the UWS API."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import AsyncClient

from safir.testing.slack import MockSlackWebhook
from safir.testing.uws import MockWobbly
from safir.uws._dependencies import UWSFactory

from ..support.uws import SimpleParameters


@dataclass
class PostTest:
    """Encapsulates the data a test POST."""

    url: str
    data: dict[str, str]


@pytest.mark.asyncio
async def test_errors(
    client: AsyncClient,
    test_token: str,
    test_service: str,
    uws_factory: UWSFactory,
    mock_slack: MockSlackWebhook,
    mock_wobbly: MockWobbly,
) -> None:
    job_service = uws_factory.create_job_service()
    await job_service.create(
        test_token, SimpleParameters(name="June"), run_id="some-run-id"
    )

    # No token provided.
    routes = [
        "/test/jobs/1",
        "/test/jobs/1/destruction",
        "/test/jobs/1/error",
        "/test/jobs/1/executionduration",
        "/test/jobs/1/owner",
        "/test/jobs/1/parameters",
        "/test/jobs/1/phase",
        "/test/jobs/1/quote",
        "/test/jobs/1/results",
    ]
    for route in routes:
        request = client.build_request("GET", route)
        del request.headers["X-Auth-Request-Token"]
        r = await client.send(request)
        assert r.status_code == 422
        assert r.text.startswith("UsageError")

    # Wrong user specified.
    other_token = MockWobbly.make_token(test_service, "other-user")
    for route in routes:
        r = await client.get(
            route, headers={"X-Auth-Request-Token": other_token}
        )
        assert r.status_code == 404
        assert r.text.startswith("UsageError")

    # Job does not exist.
    for route in (r.replace("/1", "/2") for r in routes):
        r = await client.get(route)
        assert r.status_code == 404
        assert r.text.startswith("UsageError")

    # Check no user specified with POST routes.
    tests = [
        PostTest("/test/jobs/1", {"action": "DELETE"}),
        PostTest(
            "/test/jobs/1/destruction", {"destruction": "2021-09-10T10:01:02Z"}
        ),
        PostTest(
            "/test/jobs/1/executionduration", {"executionduration": "1200"}
        ),
        PostTest("/test/jobs/1/phase", {"phase": "RUN"}),
    ]
    for test in tests:
        request = client.build_request("POST", test.url, data=test.data)
        del request.headers["X-Auth-Request-Token"]
        r = await client.send(request)
        assert r.status_code == 422
        assert r.text.startswith("UsageError")

    # Wrong user specified.
    for test in tests:
        r = await client.post(
            test.url,
            data=test.data,
            headers={"X-Auth-Request-Token": other_token},
        )
        assert r.status_code == 404
        assert r.text.startswith("UsageError")

    # Job does not exist.
    for test in tests:
        url = test.url.replace("/1", "/2")
        r = await client.post(url, data=test.data)
        assert r.status_code == 404
        assert r.text.startswith("UsageError")

    # Finally, test all the same things with the one supported DELETE.
    request = client.build_request("DELETE", "/test/jobs/1")
    del request.headers["X-Auth-Request-Token"]
    r = await client.send(request)
    assert r.status_code == 422
    assert r.text.startswith("UsageError")
    r = await client.delete(
        "/test/jobs/1", headers={"X-Auth-Request-Token": other_token}
    )
    assert r.status_code == 404
    assert r.text.startswith("UsageError")
    r = await client.delete("/test/jobs/2")
    assert r.status_code == 404
    assert r.text.startswith("UsageError")

    # Try some bogus destruction and execution duration parameters.
    tests = [
        PostTest("/test/jobs/1/destruction", {"destruction": "next tuesday"}),
        PostTest("/test/jobs/1/destruction", {"DESTruction": "next tuesday"}),
        PostTest(
            "/test/jobs/1/destruction", {"destruction": "2021-09-10 10:01:02"}
        ),
        PostTest(
            "/test/jobs/1/destruction",
            {"destrucTION": "2021-09-10T10:01:02+00:00:00"},
        ),
        PostTest(
            "/test/jobs/1/executionduration", {"executionduration": "-1"}
        ),
        PostTest(
            "/test/jobs/1/executionduration", {"executionDUration": "-1"}
        ),
        PostTest(
            "/test/jobs/1/executionduration", {"executionduration": "fred"}
        ),
        PostTest(
            "/test/jobs/1/executionduration", {"executionDUration": "fred"}
        ),
    ]
    for test in tests:
        r = await client.post(test.url, data=test.data)
        assert r.status_code == 422, f"{test.url} {test.data}"
        assert r.text.startswith("UsageError"), r.text

    # Test bogus phase for async job creation.
    r = await client.post(
        "/test/jobs?phase=START",
        data={"runid": "some-run-id", "name": "Jane"},
    )
    assert r.status_code == 422
    r = await client.post(
        "/test/jobs",
        data={"runid": "some-run-id", "name": "Jane", "phase": "START"},
    )
    assert r.status_code == 422

    # None of these errors should have produced Slack errors.
    assert mock_slack.messages == []
