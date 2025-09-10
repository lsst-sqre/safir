"""Tests for UWS exception classes."""

from __future__ import annotations

import pickle

from safir.arq.uws import (
    WorkerError,
    WorkerFatalError,
    WorkerTransientError,
    WorkerUsageError,
)
from safir.uws._exceptions import TaskError


def test_pickle() -> None:
    """Test that the `TaskError` exceptions can be pickled.

    Some care has to be taken in defining exceptions to ensure that they can
    be pickled and unpickled, since `BaseException` provides a ``__reduce__``
    implementation with somewhat unexpected properties. Make sure that this
    support doesn't regress, since arq uses pickle to convey errors from
    backend workers to anything that recovers their results.
    """

    def nonnegative(arg: int) -> int:
        if arg < 0:
            raise ValueError("Negative integers not supported")
        return arg

    def raise_exception(arg: int, exc_class: type[WorkerError]) -> None:
        try:
            nonnegative(arg)
        except Exception as e:
            raise exc_class(
                "some message", "some detail", add_traceback=True
            ) from e

    for exc_class in (
        WorkerFatalError,
        WorkerTransientError,
        WorkerUsageError,
    ):
        exc: WorkerError = exc_class("some message", "detail")
        pickled_exc = pickle.loads(pickle.dumps(exc))
        task_error = TaskError.from_worker_error(exc)
        pickled_task_error = TaskError.from_worker_error(pickled_exc)
        job_error = task_error.to_job_error()
        assert job_error == pickled_task_error.to_job_error()
        if exc_class == WorkerUsageError:
            assert task_error.slack_ignore
        else:
            assert not task_error.slack_ignore

        # Try with tracebacks.
        try:
            raise_exception(-1, exc_class)
        except WorkerError as e:
            exc = e
        assert exc.traceback
        assert "nonnegative" in exc.traceback
        assert exc_class.__name__ not in exc.traceback
        job_error = TaskError.from_worker_error(exc).to_job_error()
        assert job_error.detail
        assert "some detail\n\n" in job_error.detail
        assert "nonnegative" in job_error.detail
        pickled_exc = pickle.loads(pickle.dumps(exc))
        pickled_task_error = TaskError.from_worker_error(pickled_exc)
        assert job_error == pickled_task_error.to_job_error()
