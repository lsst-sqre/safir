"""Assert helpers for testing services using the Safir UWS support."""

from __future__ import annotations

from vo_models.uws import JobSummary

__all__ = ["assert_job_summary_equal"]


def assert_job_summary_equal(
    job_summary_type: type[JobSummary], seen: str, expected: str
) -> None:
    """Assert that two job XML documents are equal.

    The comparison is done by converting both to a
    `~vo_models.uws.models.JobSummary` object qualified with the parameter
    type used for tests.

    Parameters
    ----------
    job_summary_type
        Type of XML job summary specialized for the XML model used for job
        parameters. For example, ``JobSummary[SomeXmlParameters]``.
    seen
        XML returned by the application under test.
    expected
        Expected XML.
    """
    seen_model = job_summary_type.from_xml(seen)
    expected_model = job_summary_type.from_xml(expected)
    assert seen_model.model_dump() == expected_model.model_dump()
