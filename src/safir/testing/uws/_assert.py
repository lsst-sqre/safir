"""Assert helpers for testing services using the Safir UWS support."""

from datetime import datetime, timedelta

try:
    from vo_models.uws import JobSummary
except ImportError as e:
    raise ImportError(
        "The safir.testing.uws module requires the uws extra. "
        "Install it with `pip install safir[uws]`."
    ) from e

__all__ = ["assert_job_summary_equal"]


def assert_job_summary_equal(
    job_summary_type: type[JobSummary],
    seen: str,
    expected: str,
    *,
    fuzzy_destruction: bool = True,
) -> None:
    """Assert that two job XML documents are equal.

    The comparison is done by converting both to a
    `~vo_models.uws.models.JobSummary` object qualified with the parameter
    type used for tests.
    The timestamp comparison for destruction time accepts a difference of 1
    second to avoid a rare flaky test condition.

    Parameters
    ----------
    job_summary_type
        Type of XML job summary specialized for the XML model used for job
        parameters. For example, ``JobSummary[SomeXmlParameters]``.
    seen
        XML returned by the application under test.
    expected
        Expected XML.
    fuzzy_destruction
        Whether to allow a +/- 1 second difference in expected and seen
        destruction timestamps.
    """
    seen_model = job_summary_type.from_xml(seen)
    expected_model = job_summary_type.from_xml(expected)

    # Our tests assume that the destruction time is always some constant time
    # ahead of the job creation time, but that might not be true. The safir UWS
    # storage sets the destruction time in the JobCreate request that it sends
    # to Wobbly based on the current time + the lifetime offset. It is Wobbly
    # (or the Wobbly mock) that sets the job creation time when it gets the
    # request based on the current time when it recieves the request. In our
    # tests, where we're mocking wobbly, these two current times are almost
    # exactly the same, but in rare cases, a second may flip between them. If
    # the actual and expected timestamps for destruction time differ by one
    # second, just set one to the other so the comparison passes.
    if (
        isinstance(seen_model.destruction, datetime)
        and isinstance(expected_model.destruction, datetime)
        and fuzzy_destruction
    ):
        destruction_delta = seen_model.destruction - expected_model.destruction
        if abs(destruction_delta) <= timedelta(seconds=1):
            expected_model.destruction = seen_model.destruction
    assert seen_model.model_dump() == expected_model.model_dump()
