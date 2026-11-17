"""Tests for VOSI functionality provided by the UWS library."""

import pytest
from httpx2 import AsyncClient
from vo_models.vosi.availability import Availability

AVAILABILITY = """
<vosi:availability xmlns:vosi="http://www.ivoa.net/xml/VOSIAvailability/v1.0">
  <vosi:available>true</vosi:available>
</vosi:availability>
"""


@pytest.mark.httpx2(assert_all_called=False)
@pytest.mark.asyncio
async def test_availability(client: AsyncClient) -> None:
    r = await client.get("/test/availability")
    assert r.status_code == 200
    assert Availability.from_xml(r.text) == Availability.from_xml(AVAILABILITY)
