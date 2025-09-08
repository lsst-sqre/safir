"""Test for long polling when retrieving jobs."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from httpx import AsyncClient
from vo_models.uws import JobSummary

from safir.arq.uws import WorkerResult
from safir.datetime import current_datetime, isodatetime
from safir.testing.uws import MockUWSJobRunner, assert_job_summary_equal
from safir.uws._dependencies import UWSFactory

from ..support.uws import SimpleParameters, SimpleXmlParameters

PENDING_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>1</uws:jobId>
  <uws:ownerId>test-user</uws:ownerId>
  <uws:phase>{}</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Naomi</uws:parameter>
  </uws:parameters>
</uws:job>
"""

EXECUTING_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>1</uws:jobId>
  <uws:ownerId>test-user</uws:ownerId>
  <uws:phase>EXECUTING</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:startTime>{}</uws:startTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Naomi</uws:parameter>
  </uws:parameters>
</uws:job>
"""

FINISHED_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>1</uws:jobId>
  <uws:ownerId>test-user</uws:ownerId>
  <uws:phase>COMPLETED</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:startTime>{}</uws:startTime>
  <uws:endTime>{}</uws:endTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Naomi</uws:parameter>
  </uws:parameters>
  <uws:results>
    <uws:result id="cutout" xlink:href="https://example.com/some/path"\
 mime-type="application/fits"/>
  </uws:results>
</uws:job>
"""


@pytest.mark.asyncio
async def test_poll(
    client: AsyncClient,
    test_token: str,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
) -> None:
    job_service = uws_factory.create_job_service()
    job = await job_service.create(test_token, SimpleParameters(name="Naomi"))

    # Poll for changes for one second. Nothing will happen since nothing is
    # changing the mock arq queue.
    now = current_datetime()
    r = await client.get("/test/jobs/1", params={"WAIT": "1"})
    assert (current_datetime() - now).total_seconds() >= 1
    assert r.status_code == 200
    assert_job_summary_equal(
        JobSummary[SimpleXmlParameters],
        r.text,
        PENDING_JOB.format(
            "PENDING",
            isodatetime(job.creation_time),
            isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
        ),
    )

    # Start the job and worker.
    r = await client.post(
        "/test/jobs/1/phase", data={"PHASE": "RUN"}, follow_redirects=True
    )
    assert r.status_code == 200
    assert r.url == "https://example.com/test/jobs/1"
    assert_job_summary_equal(
        JobSummary[SimpleXmlParameters],
        r.text,
        PENDING_JOB.format(
            "QUEUED",
            isodatetime(job.creation_time),
            isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
        ),
    )

    # Poll for a change from queued, which we should see after half a second.
    now = current_datetime()
    job, r = await asyncio.gather(
        runner.mark_in_progress(test_token, "1", delay=0.5),
        client.get("/test/jobs/1", params={"WAIT": "2", "phase": "QUEUED"}),
    )
    assert r.status_code == 200
    assert job.start_time
    assert_job_summary_equal(
        JobSummary[SimpleXmlParameters],
        r.text,
        EXECUTING_JOB.format(
            isodatetime(job.creation_time),
            isodatetime(job.start_time),
            isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
        ),
    )

    # Now, wait again, in parallel with the job finishing. We should get a
    # reply after a second and a half when the job finishes.
    results = [
        WorkerResult(
            result_id="cutout",
            url="s3://some-bucket/some/path",
            mime_type="application/fits",
        )
    ]
    job, r = await asyncio.gather(
        runner.mark_complete(test_token, "1", results, delay=1.5),
        client.get("/test/jobs/1", params={"WAIT": "2", "phase": "EXECUTING"}),
    )
    assert r.status_code == 200
    assert job.start_time
    assert job.end_time
    assert_job_summary_equal(
        JobSummary[SimpleXmlParameters],
        r.text,
        FINISHED_JOB.format(
            isodatetime(job.creation_time),
            isodatetime(job.start_time),
            isodatetime(job.end_time),
            isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
        ),
    )
    assert (current_datetime() - now).total_seconds() >= 2
