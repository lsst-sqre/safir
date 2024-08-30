"""Tests for the UWS job manipulation handlers.

These tests don't assume any given application, and therefore don't use the
API to create a job, instead inserting it directly via the UWSService.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY

import pytest
from arq.constants import default_queue_name
from arq.jobs import JobStatus
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from vo_models.uws import Results

from safir.arq import MockArqQueue
from safir.arq.uws import WorkerJobInfo
from safir.datetime import current_datetime, isodatetime
from safir.testing.uws import MockUWSJobRunner
from safir.uws import UWSConfig, UWSJob, UWSJobParameter, UWSJobResult
from safir.uws._dependencies import UWSFactory

PENDING_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>{}</uws:jobId>
  <uws:runId>some-run-id</uws:runId>
  <uws:ownerId>user</uws:ownerId>
  <uws:phase>{}</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:executionDuration>{}</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Jane</uws:parameter>
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
  <uws:runId>some-run-id</uws:runId>
  <uws:ownerId>user</uws:ownerId>
  <uws:phase>COMPLETED</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:startTime>{}</uws:startTime>
  <uws:endTime>{}</uws:endTime>
  <uws:executionDuration>{}</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Jane</uws:parameter>
  </uws:parameters>
  <uws:results>
    <uws:result id="cutout" xlink:href="https://example.com/some/path"\
 mime-type="application/fits"/>
  </uws:results>
</uws:job>
"""

ABORTED_PENDING_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>{}</uws:jobId>
  <uws:runId>some-run-id</uws:runId>
  <uws:ownerId>user</uws:ownerId>
  <uws:phase>ABORTED</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Jane</uws:parameter>
  </uws:parameters>
</uws:job>
"""

ABORTED_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>{}</uws:jobId>
  <uws:runId>some-run-id</uws:runId>
  <uws:ownerId>user</uws:ownerId>
  <uws:phase>ABORTED</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:startTime>{}</uws:startTime>
  <uws:endTime>{}</uws:endTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Jane</uws:parameter>
  </uws:parameters>
</uws:job>
"""

JOB_PARAMETERS = """
<uws:parameters
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:parameter id="name">Jane</uws:parameter>
</uws:parameters>
"""

JOB_RESULTS = """
<uws:results
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:result id="cutout" xlink:href="https://example.com/some/path"\
 mime-type="application/fits"/>
</uws:results>
"""


@pytest.mark.asyncio
async def test_job_run(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
    uws_config: UWSConfig,
) -> None:
    job_service = uws_factory.create_job_service()

    # Create the job.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    job = await job_service.get("user", "1")
    assert job.creation_time.microsecond == 0

    # Check the retrieval of the job configuration.
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert r.text == PENDING_JOB.strip().format(
        "1",
        "PENDING",
        isodatetime(job.creation_time),
        "600",
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )

    # Try to put the job in an invalid phase.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "EXECUTING"},
    )
    assert r.status_code == 422
    assert r.text.startswith("UsageError")

    # Start the job.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "RUN"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.url == "https://example.com/test/jobs/1"
    assert r.text == PENDING_JOB.strip().format(
        "1",
        "QUEUED",
        isodatetime(job.creation_time),
        "600",
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )
    await runner.mark_in_progress("user", "1")

    # Check that the correct data was passed to the backend worker.
    metadata = await runner.get_job_metadata("user", "1")
    assert metadata.name == uws_config.worker
    assert metadata.args[0] == {"name": "Jane"}
    assert metadata.args[1] == WorkerJobInfo(
        job_id="1",
        user="user",
        token="sometoken",
        timeout=ANY,
        run_id="some-run-id",
    )
    assert not metadata.kwargs
    now = datetime.now(tz=UTC)
    assert now - timedelta(seconds=2) <= metadata.enqueue_time <= now
    assert metadata.status == JobStatus.in_progress
    assert metadata.queue_name == default_queue_name

    # Tell the queue the job is finished.
    results = [
        UWSJobResult(
            result_id="cutout",
            url="s3://some-bucket/some/path",
            mime_type="application/fits",
        )
    ]
    job = await runner.mark_complete("user", "1", results)

    # Check the job results.
    assert job.start_time
    assert job.start_time.microsecond == 0
    assert job.end_time
    assert job.end_time.microsecond == 0
    assert job.end_time >= job.start_time >= job.creation_time
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert r.text == FINISHED_JOB.strip().format(
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        "600",
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )

    # Check that the phase is now correct.
    r = await client.get(
        "/test/jobs/1/phase", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == "COMPLETED"

    # Retrieve them directly through the results resource.
    r = await client.get(
        "/test/jobs/1/results", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert Results.from_xml(r.text) == Results.from_xml(JOB_RESULTS)

    # There should be no error message.
    r = await client.get(
        "/test/jobs/1/error", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_abort(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    arq_queue: MockArqQueue,
    uws_factory: UWSFactory,
    uws_config: UWSConfig,
) -> None:
    job_service = uws_factory.create_job_service()

    # Create the job.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane"},
    )
    assert r.status_code == 303
    job = await job_service.get("user", "1")

    # Immediately abort the job.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "ABORT"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.url == "https://example.com/test/jobs/1"
    assert r.text == ABORTED_PENDING_JOB.strip().format(
        "1",
        isodatetime(job.creation_time),
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )

    # Create a second job and start it running.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane", "phase": "RUN"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/2"
    await runner.mark_in_progress("user", "2")

    # Abort that job.
    r = await client.post(
        "/test/jobs/2/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "ABORT"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.url == "https://example.com/test/jobs/2"
    job = await job_service.get("user", "2")
    assert job.start_time
    assert job.end_time
    assert r.text == ABORTED_JOB.strip().format(
        "2",
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )
    job_result = await runner.get_job_result("user", "2")
    assert not job_result.success
    assert isinstance(job_result.result, asyncio.CancelledError)

    # Deleting a job should also abort it. Also test a weird capitalization of
    # the phase parameter and the POST form of the delete support.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane", "PHAse": "RUN"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/3"
    await runner.mark_in_progress("user", "3")
    job = await job_service.get("user", "3")
    r = await client.post(
        "/test/jobs/3",
        headers={"X-Auth-Request-User": "user"},
        data={"action": "DELETE"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs"
    assert job.message_id
    job_result = await arq_queue.get_job_result(job.message_id)
    assert not job_result.success
    assert isinstance(job_result.result, asyncio.CancelledError)


@pytest.mark.asyncio
async def test_job_api(
    client: AsyncClient,
    uws_factory: UWSFactory,
) -> None:
    job_service = uws_factory.create_job_service()

    # Create the job.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    job = await job_service.get("user", "1")

    # Check the retrieval of the job configuration.
    destruction_time = job.creation_time + timedelta(seconds=24 * 60 * 60)
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert r.text == PENDING_JOB.strip().format(
        "1",
        "PENDING",
        isodatetime(job.creation_time),
        "600",
        isodatetime(destruction_time),
    )

    # Check retrieving each part separately.
    r = await client.get(
        "/test/jobs/1/destruction", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == isodatetime(destruction_time)

    r = await client.get(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == "600"

    r = await client.get(
        "/test/jobs/1/owner", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == "user"

    r = await client.get(
        "/test/jobs/1/parameters", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert r.text == JOB_PARAMETERS.strip()

    r = await client.get(
        "/test/jobs/1/phase", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == "PENDING"

    r = await client.get(
        "/test/jobs/1/quote", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert r.text == ""

    # Modify various settings. Validators will be tested elsewhere.
    now = current_datetime()
    r = await client.post(
        "/test/jobs/1/destruction",
        headers={"X-Auth-Request-User": "user"},
        data={"DESTRUCTION": isodatetime(now)},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"

    r = await client.post(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
        data={"ExecutionDuration": 300},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"

    # Retrieve the modified job and check that the new values are recorded.
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/xml"
    assert r.text == PENDING_JOB.strip().format(
        "1",
        "PENDING",
        isodatetime(job.creation_time),
        "300",
        isodatetime(now),
    )

    # Delete the job.
    r = await client.delete(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs"
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 404

    # Create a new job and then delete it via POST.
    r = await client.post(
        "/test/jobs",
        headers={"X-Auth-Request-User": "user"},
        data={"name": "Jane", "RUNID": "some-run-id"},
    )
    assert r.status_code == 303
    job = await job_service.get("user", "2")
    r = await client.get(
        "/test/jobs/2", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == PENDING_JOB.strip().format(
        "2",
        "PENDING",
        isodatetime(job.creation_time),
        "600",
        isodatetime(job.destruction_time),
    )
    r = await client.post(
        "/test/jobs/2",
        headers={"X-Auth-Request-User": "user"},
        data={"ACTION": "DELETE"},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs"
    r = await client.get(
        "/test/jobs/2", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_redirects(
    app: FastAPI,
    uws_factory: UWSFactory,
) -> None:
    """Test the scheme in the redirect URLs.

    When running in a Kubernetes cluster behind an ingress that terminates
    TLS, the request as seen by the application will be ``http``, but we want
    the redirect URLs to honor ``X-Forwarded-Proto`` and thus use ``https``.
    We also want to honor the ``Host`` header.
    """
    job_service = uws_factory.create_job_service()
    await job_service.create(
        "user",
        run_id="some-run-id",
        params=[UWSJobParameter(parameter_id="name", value="Peter")],
    )

    # Try various actions that result in redirects and ensure the redirect is
    # correct.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://foo.com/"
    ) as client:
        r = await client.post(
            "/test/jobs/1/destruction",
            headers={
                "X-Auth-Request-User": "user",
                "Host": "example.com",
                "X-Forwarded-For": "10.10.10.10",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "foo.com",
            },
            data={"DESTRUCTION": "2021-09-10T10:01:02Z"},
        )
        assert r.status_code == 303
        assert r.headers["Location"] == "https://example.com/test/jobs/1"

        r = await client.post(
            "/test/jobs/1/executionduration",
            headers={
                "X-Auth-Request-User": "user",
                "Host": "example.com",
                "X-Forwarded-For": "10.10.10.10",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "foo.com",
            },
            data={"ExecutionDuration": 300},
        )
        assert r.status_code == 303
        assert r.headers["Location"] == "https://example.com/test/jobs/1"

        r = await client.delete(
            "/test/jobs/1",
            headers={
                "X-Auth-Request-User": "user",
                "Host": "example.com",
                "X-Forwarded-For": "10.10.10.10",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "foo.com",
            },
        )
        assert r.status_code == 303
        assert r.headers["Location"] == "https://example.com/test/jobs"


@pytest.mark.asyncio
async def test_presigned_url(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
    uws_config: UWSConfig,
) -> None:
    r = await client.post(
        "/test/jobs?phase=RUN",
        headers={"X-Auth-Request-User": "user"},
        data={"runid": "some-run-id", "name": "Jane"},
    )
    assert r.status_code == 303
    await runner.mark_in_progress("user", "1")

    # Tell the queue the job is finished, with an https URL.
    results = [
        UWSJobResult(
            result_id="cutout",
            url="https://example.com/some/path",
            mime_type="application/fits",
        )
    ]
    job = await runner.mark_complete("user", "1", results)

    # Check the job results, which should pass that URL through unchanged.
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert job.start_time
    assert job.end_time
    assert r.text == FINISHED_JOB.strip().format(
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        "600",
        isodatetime(job.creation_time + timedelta(seconds=24 * 60 * 60)),
    )


def validate_destruction(destruction: datetime, job: UWSJob) -> datetime:
    max_destruction = current_datetime() + timedelta(days=1)
    return min(destruction, max_destruction)


def validate_execution_duration(duration: timedelta, job: UWSJob) -> timedelta:
    max_duration = timedelta(seconds=200)
    return min(duration, max_duration)


@pytest.mark.asyncio
async def test_validators(
    client: AsyncClient,
    arq_queue: MockArqQueue,
    uws_factory: UWSFactory,
    uws_config: UWSConfig,
) -> None:
    uws_config.validate_destruction = validate_destruction
    uws_config.validate_execution_duration = validate_execution_duration
    job_service = uws_factory.create_job_service()
    await job_service.create(
        "user", params=[UWSJobParameter(parameter_id="name", value="Tiffany")]
    )

    # Change the destruction time, first to something that should be honored
    # and then something that should be overridden.
    destruction = current_datetime() + timedelta(hours=1)
    r = await client.post(
        "/test/jobs/1/destruction",
        headers={"X-Auth-Request-User": "user"},
        data={"desTRUcTiON": isodatetime(destruction)},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    r = await client.get(
        "/test/jobs/1/destruction", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == isodatetime(destruction)
    destruction = current_datetime() + timedelta(days=5)
    expected = current_datetime() + timedelta(days=1)
    r = await client.post(
        "/test/jobs/1/destruction",
        headers={"X-Auth-Request-User": "user"},
        data={"destruction": isodatetime(destruction)},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    r = await client.get(
        "/test/jobs/1/destruction", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    seen = datetime.fromisoformat(r.text[:-1] + "+00:00")
    assert seen >= expected - timedelta(seconds=5)
    assert seen <= expected + timedelta(seconds=5)

    # Now do the same thing for execution duration.
    r = await client.post(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
        data={"exECUTionduRATION": 100},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    r = await client.get(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
    )
    assert r.status_code == 200
    assert r.text == "100"
    r = await client.post(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
        data={"exECUTionduRATION": 250},
    )
    assert r.status_code == 303
    assert r.headers["Location"] == "https://example.com/test/jobs/1"
    r = await client.get(
        "/test/jobs/1/executionduration",
        headers={"X-Auth-Request-User": "user"},
    )
    assert r.status_code == 200
    assert r.text == "200"
