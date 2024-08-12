"""Configuration for arq_ clients and workers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arq.connections import RedisSettings
from arq.constants import default_queue_name as arq_default_queue_name
from arq.cron import CronJob
from arq.typing import SecondsTimedelta, StartupShutdown, WorkerCoroutine
from arq.worker import Function
from pydantic import SecretStr
from pydantic_core import Url

__all__ = [
    "WorkerSettings",
    "build_arq_redis_settings",
]


def build_arq_redis_settings(
    url: Url, password: SecretStr | None
) -> RedisSettings:
    """Construct Redis settings for arq.

    Parameters
    ----------
    url
        Redis DSN.
    password
        Password for the Redis connection.

    Returns
    -------
    arq.connections.RedisSettings
        Settings for the arq Redis pool.

    Examples
    --------
    This function is normally used from a property in the application
    configuration. The application should usually use
    `~safir.pydantic.EnvRedisDsn` as the type for the Redis DSN.

    .. code-block:: python

       from arq.connections import RedisSettings
       from pydantic_settings import BaseSettings
       from safir.pydantic import EnvRedisDsn


       class Config(BaseSettings):
           arq_queue_url: EnvRedisDsn
           arq_queue_password: SecretStr | None

           @property
           def arq_redis_settings(self) -> RedisSettings:
               return build_arq_redis_settings(
                   self.arq_queue_url, self_arq_queue_password
               )
    """
    return RedisSettings(
        host=url.unicode_host() or "localhost",
        port=url.port or 6379,
        database=int(url.path.lstrip("/")) if url.path else 0,
        password=password.get_secret_value() if password else None,
    )


@dataclass
class WorkerSettings:
    """Configuration class for an arq worker.

    The arq command-line tool reads a class of the name ``WorkerSettings`` in
    the module it was given on the command line and turns its attributes into
    parameters to `arq.worker.Worker`. This dataclass represents the subset of
    the available settings that Safir applications have needed to date, as an
    aid for constructing that configuration object.
    """

    functions: Sequence[Function | WorkerCoroutine]
    """Coroutines to register as arq worker entry points."""

    redis_settings: RedisSettings
    """Redis configuration for arq."""

    job_completion_wait: SecondsTimedelta
    """How long to wait for jobs to complete before cancelling them."""

    job_timeout: SecondsTimedelta
    """Maximum timeout for all jobs."""

    max_jobs: int
    """Maximum number of jobs that can be run at one time."""

    allow_abort_jobs: bool = False
    """Whether to allow jobs to be aborted."""

    queue_name: str = arq_default_queue_name
    """Name of arq queue to listen to for jobs."""

    on_startup: StartupShutdown | None = None
    """Coroutine to run on startup."""

    on_shutdown: StartupShutdown | None = None
    """Coroutine to run on shutdown."""

    cron_jobs: Sequence[CronJob] | None = None
    """Cron jobs to run."""
