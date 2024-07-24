"""Test handling of jobs that fail."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from safir.arq.uws import WorkerFatalError, WorkerTransientError
from safir.datetime import isodatetime
from safir.testing.slack import MockSlackWebhook
from safir.testing.uws import MockUWSJobRunner
from safir.uws import UWSJobParameter
from safir.uws._dependencies import UWSFactory
from safir.uws._exceptions import TaskError

ERRORED_JOB = """
<uws:job
    version="1.1"
    xsi:schemaLocation="http://www.ivoa.net/xml/UWS/v1.0 UWS.xsd"
    xmlns:xml="http://www.w3.org/XML/1998/namespace"
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <uws:jobId>1</uws:jobId>
  <uws:ownerId>user</uws:ownerId>
  <uws:phase>ERROR</uws:phase>
  <uws:creationTime>{}</uws:creationTime>
  <uws:startTime>{}</uws:startTime>
  <uws:endTime>{}</uws:endTime>
  <uws:executionDuration>600</uws:executionDuration>
  <uws:destruction>{}</uws:destruction>
  <uws:parameters>
    <uws:parameter id="name">Sarah</uws:parameter>
  </uws:parameters>
  <uws:errorSummary type="{}" hasDetail="{}">
    <uws:message>{}</uws:message>
  </uws:errorSummary>
</uws:job>
"""

JOB_ERROR_SUMMARY = """
<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <INFO name="QUERY_STATUS" value="ERROR">
{}
  </INFO>
</VOTABLE>
"""


@pytest.mark.asyncio
async def test_temporary_error(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
    mock_slack: MockSlackWebhook,
) -> None:
    job_service = uws_factory.create_job_service()
    await job_service.create(
        "user", params=[UWSJobParameter(parameter_id="name", value="Sarah")]
    )

    # The pending job has no error.
    r = await client.get(
        "/test/jobs/1/error", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 404

    # Execute the job.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "RUN"},
    )
    assert r.status_code == 303
    await runner.mark_in_progress("user", "1")
    exc = WorkerTransientError("Something failed")
    result = TaskError.from_worker_error(exc)
    job = await runner.mark_complete("user", "1", result)

    # Check the results.
    assert job.start_time
    assert job.end_time
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == ERRORED_JOB.strip().format(
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        isodatetime(job.destruction_time),
        "transient",
        "false",
        "ServiceUnavailable Something failed",
    )

    # Retrieve the error separately.
    r = await client.get(
        "/test/jobs/1/error", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == JOB_ERROR_SUMMARY.strip().format(
        "ServiceUnavailable Something failed"
    )

    # For now, this shouldn't have resulted in Slack errors.
    assert mock_slack.messages == []


@pytest.mark.asyncio
async def test_fatal_error(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
    mock_slack: MockSlackWebhook,
) -> None:
    job_service = uws_factory.create_job_service()
    await job_service.create(
        "user", params=[UWSJobParameter(parameter_id="name", value="Sarah")]
    )

    # Start the job.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "RUN"},
    )
    assert r.status_code == 303
    await runner.mark_in_progress("user", "1")
    exc = WorkerFatalError("Whoops", "Some details")
    result = TaskError.from_worker_error(exc)
    job = await runner.mark_complete("user", "1", result)

    # Check the results.
    assert job.start_time
    assert job.end_time
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == ERRORED_JOB.strip().format(
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        isodatetime(job.destruction_time),
        "fatal",
        "true",
        "Error Whoops",
    )

    # Retrieve the error separately.
    r = await client.get(
        "/test/jobs/1/error", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == JOB_ERROR_SUMMARY.strip().format(
        "Error Whoops\n\nSome details"
    )

    # For now, this shouldn't have resulted in Slack errors.
    assert mock_slack.messages == []


@pytest.mark.asyncio
async def test_unknown_error(
    client: AsyncClient,
    runner: MockUWSJobRunner,
    uws_factory: UWSFactory,
    mock_slack: MockSlackWebhook,
) -> None:
    job_service = uws_factory.create_job_service()
    await job_service.create(
        "user", params=[UWSJobParameter(parameter_id="name", value="Sarah")]
    )

    # Start the job.
    r = await client.post(
        "/test/jobs/1/phase",
        headers={"X-Auth-Request-User": "user"},
        data={"PHASE": "RUN"},
    )
    assert r.status_code == 303
    await runner.mark_in_progress("user", "1")
    result = ValueError("Unknown exception")
    job = await runner.mark_complete("user", "1", result)

    # Check the results.
    assert job.start_time
    assert job.end_time
    r = await client.get(
        "/test/jobs/1", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == ERRORED_JOB.strip().format(
        isodatetime(job.creation_time),
        isodatetime(job.start_time),
        isodatetime(job.end_time),
        isodatetime(job.destruction_time),
        "fatal",
        "true",
        "Error Unknown error executing task",
    )

    # Retrieve the error separately.
    r = await client.get(
        "/test/jobs/1/error", headers={"X-Auth-Request-User": "user"}
    )
    assert r.status_code == 200
    assert r.text == JOB_ERROR_SUMMARY.strip().format(
        "Error Unknown error executing task\n\n"
        "ValueError: Unknown exception"
    )

    # For now, this shouldn't have resulted in Slack errors.
    assert mock_slack.messages == []
