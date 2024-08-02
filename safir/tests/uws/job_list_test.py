"""Tests for the job list.

These tests don't assume any given application, and therefore don't use the
API to create a job, instead inserting it directly via the UWSService.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from vo_models.uws import Jobs

from safir.database import datetime_to_db
from safir.datetime import current_datetime, isodatetime
from safir.uws import UWSJobParameter
from safir.uws._dependencies import UWSFactory
from safir.uws._schema import Job as SQLJob

FULL_JOB_LIST = """
<uws:jobs
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobref id="3" xlink:href="https://example.com/test/jobs/3">
    <uws:phase>PENDING</uws:phase>
    <uws:ownerId>user</uws:ownerId>
    <uws:creationTime>{}</uws:creationTime>
  </uws:jobref>
  <uws:jobref id="2" xlink:href="https://example.com/test/jobs/2">
    <uws:phase>PENDING</uws:phase>
    <uws:runId>some-run-id</uws:runId>
    <uws:ownerId>user</uws:ownerId>
    <uws:creationTime>{}</uws:creationTime>
  </uws:jobref>
  <uws:jobref id="1" xlink:href="https://example.com/test/jobs/1">
    <uws:phase>PENDING</uws:phase>
    <uws:ownerId>user</uws:ownerId>
    <uws:creationTime>{}</uws:creationTime>
  </uws:jobref>
</uws:jobs>
"""

RECENT_JOB_LIST = """
<uws:jobs
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobref id="3" xlink:href="https://example.com/test/jobs/3">
    <uws:phase>PENDING</uws:phase>
    <uws:ownerId>user</uws:ownerId>
    <uws:creationTime>{}</uws:creationTime>
  </uws:jobref>
</uws:jobs>
"""

QUEUED_JOB_LIST = """
<uws:jobs
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobref id="2" xlink:href="https://example.com/test/jobs/2">
    <uws:phase>QUEUED</uws:phase>
    <uws:runId>some-run-id</uws:runId>
    <uws:ownerId>user</uws:ownerId>
    <uws:creationTime>{}</uws:creationTime>
  </uws:jobref>
</uws:jobs>
"""


@pytest.mark.asyncio
async def test_job_list(client: AsyncClient, uws_factory: UWSFactory) -> None:
    job_service = uws_factory.create_job_service()
    jobs = [
        await job_service.create(
            "user", params=[UWSJobParameter(parameter_id="name", value="Joe")]
        ),
        await job_service.create(
            "user",
            run_id="some-run-id",
            params=[UWSJobParameter(parameter_id="name", value="Catherine")],
        ),
        await job_service.create(
            "user", params=[UWSJobParameter(parameter_id="name", value="Pat")]
        ),
    ]

    # Create an additional job for a different user, which shouldn't appear in
    # any of the lists.
    await job_service.create(
        "otheruser",
        params=[UWSJobParameter(parameter_id="name", value="Dominique")],
    )

    # Adjust the creation time of the jobs so that searches are more
    # interesting.
    async with uws_factory.session.begin():
        for i, job in enumerate(jobs):
            hours = (2 - i) * 2
            creation = current_datetime() - timedelta(hours=hours)
            stmt = (
                update(SQLJob)
                .where(SQLJob.id == int(job.job_id))
                .values(creation_time=datetime_to_db(creation))
            )
            await uws_factory.session.execute(stmt)
            job.creation_time = creation

    # Retrieve the job list and check it.
    r = await client.get("/test/jobs", headers={"X-Auth-Request-User": "user"})
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    creation_times = [isodatetime(j.creation_time) for j in jobs]
    creation_times.reverse()
    expected = FULL_JOB_LIST.strip().format(*creation_times)
    assert Jobs.from_xml(r.text) == Jobs.from_xml(expected)

    # Filter by recency.
    threshold = current_datetime() - timedelta(hours=1)
    r = await client.get(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        params={"after": isodatetime(threshold)},
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    expected = RECENT_JOB_LIST.strip().format(creation_times[0])
    assert Jobs.from_xml(r.text) == Jobs.from_xml(expected)

    # Check case-insensitivity.
    result = r.text
    r = await client.get(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        params={"AFTER": isodatetime(threshold)},
    )
    assert r.text == result
    r = await client.get(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        params={"aFTer": isodatetime(threshold)},
    )
    assert r.text == result

    # Filter by count.
    r = await client.get(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        params={"last": 1},
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    expected = RECENT_JOB_LIST.strip().format(creation_times[0])
    assert Jobs.from_xml(r.text) == Jobs.from_xml(expected)

    # Start the job.
    r = await client.post(
        "/test/jobs/2/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "RUN"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/2"

    # Filter by phase.
    r = await client.get(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        params=[("PHASE", "EXECUTING"), ("PHASE", "QUEUED")],
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    expected = QUEUED_JOB_LIST.strip().format(creation_times[1])
    assert Jobs.from_xml(r.text) == Jobs.from_xml(expected)
