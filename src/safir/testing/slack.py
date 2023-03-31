"""Mock Slack server for testing Slack messaging."""

from __future__ import annotations

import json
from typing import Any

import respx
from httpx import Request, Response

__all__ = ["MockSlackWebhook", "mock_slack_webhook"]


class MockSlackWebhook:
    """Represents a Slack incoming webhook and remembers what was posted.

    Attributes
    ----------
    messages
        Messages that have been posted to the webhook so far.
    url
        URL that the mock has been configured to listen on.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.messages: list[dict[str, Any]] = []

    def post_webhook(self, request: Request) -> Response:
        """Callback called whenever a Slack message is posted.

        The provided message is stored in the messages attribute.

        Parameters
        ----------
        request
            Incoming request.

        Returns
        -------
        httpx.Response
            Always returns a 201 response.
        """
        self.messages.append(json.loads(request.content.decode()))
        return Response(201)


def mock_slack_webhook(
    hook_url: str, respx_mock: respx.Router
) -> MockSlackWebhook:
    """Set up a mocked Slack server.

    Parameters
    ----------
    hook_url
        URL for the Slack incoming webhook to mock.
    respx_mock
        The mock router.

    Returns
    -------
    MockSlackWebhook
        The mock Slack webhook API object.

    Examples
    --------
    To set up this mock, put a fixture in :file:`conftest.py` similar to the
    following:

    .. code-block:: python

       import pytest
       import respx
       from safir.testing.slack import MockSlackWebhook, mock_slack_webhook


       @pytest.fixture
       def mock_slack(
           config: Config, respx_mock: respx.Router
       ) -> MockWebhookSlack:
           return mock_slack_webhook(config.slack_webhook, respx_mock)

    This uses respx_ to mock the Slack webhook URL obtained from the
    configuration of the application under test. Use it in a test as follows:

    .. code-block:: python

       @pytest.mark.asyncio
       def test_something(
           client: AsyncClient, mock_slack: MockSlackWebhook
       ) -> None:
           # Do something with client that generates Slack messages.
           assert mock_slack.messages == [{...}, {...}]
    """
    mock = MockSlackWebhook(hook_url)
    respx_mock.post(hook_url).mock(side_effect=mock.post_webhook)
    return mock
