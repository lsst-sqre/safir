"""Assert helpers for testing services using the Safir UWS support."""

from datetime import timedelta

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
    type used for tests. The timestamp comparison for destruction time accepts
    a difference of 1 second to avoid a rare flaky test condition.

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
        destruction timestamps. The default of true allows tests to assume
        that the destruction time is a fixed interval after the job creation
        time, although due to internal details of the Wobbly protocol they
        may vary slightly.

    Notes
    -----
    The Safir UWS storage sets the destruction time in the JobCreate request
    that it sends to Wobbly based on the current time plus the lifetime
    offset. It is Wobbly (or the Wobbly mock) that sets the job creation time
    when it gets the request based on the current time when it recieves the
    request. The creation time may therefore be somewhat later than what the
    Safir UWS storage layer assumed when constructing the destruction time,
    and thus the destruction time may be slightly less than a fixed offset
    from the creation time.
    """
    seen_model = job_summary_type.from_xml(seen)
    expected_model = job_summary_type.from_xml(expected)
    if fuzzy_destruction:
        if seen_model.destruction and expected_model.destruction:
            delta = seen_model.destruction - expected_model.destruction
            if abs(delta) <= timedelta(seconds=1):
                expected_model.destruction = seen_model.destruction
    assert seen_model.model_dump() == expected_model.model_dump()
