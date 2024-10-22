"""Tests for sync cutout requests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_params_multiple_params(client: AsyncClient) -> None:
    """Test that the post dependency correctly handles multiple
    occurences of the same parameter.
    """
    params = [
        {"parameter_id": "id", "value": "image1"},
        {"parameter_id": "id", "value": "image2"},
        {"parameter_id": "pos", "value": "RANGE 10 20 30 40"},
        {"parameter_id": "pos", "value": "CIRCLE 10 20 5"},
    ]

    response = await client.post("/test/params", json=params)
    assert response.status_code == 200
    assert response.json() == {
        "params": [
            {"id": "id", "value": "image1"},
            {"id": "id", "value": "image2"},
            {"id": "pos", "value": "RANGE 10 20 30 40"},
            {"id": "pos", "value": "CIRCLE 10 20 5"},
        ]
    }
