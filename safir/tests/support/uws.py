"""Support functions for testing UWS code."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Self

from arq.connections import RedisSettings
from fastapi import Form, Query
from pydantic import BaseModel, SecretStr

from safir.arq import ArqMode
from safir.uws import ParametersModel, UWSConfig, UWSJobParameter, UWSRoute

__all__ = [
    "SimpleParameters",
    "build_uws_config",
]


class SimpleWorkerParameters(BaseModel):
    name: str


class SimpleParameters(ParametersModel[SimpleWorkerParameters]):
    name: str

    @classmethod
    def from_job_parameters(cls, params: list[UWSJobParameter]) -> Self:
        assert len(params) == 1
        assert params[0].parameter_id == "name"
        return cls(name=params[0].value)

    def to_worker_parameters(self) -> SimpleWorkerParameters:
        return SimpleWorkerParameters(name=self.name)


async def _get_dependency(
    name: Annotated[str, Query()],
) -> list[UWSJobParameter]:
    return [UWSJobParameter(parameter_id="name", value=name)]


async def _post_dependency(
    name: Annotated[str, Form()],
) -> list[UWSJobParameter]:
    return [UWSJobParameter(parameter_id="name", value=name)]


def build_uws_config(database_url: str, database_password: str) -> UWSConfig:
    """Set up a test configuration."""
    return UWSConfig(
        arq_mode=ArqMode.test,
        arq_redis_settings=RedisSettings(host="localhost", port=6379),
        async_post_route=UWSRoute(
            dependency=_post_dependency, summary="Create async job"
        ),
        database_url=database_url,
        database_password=SecretStr(database_password),
        execution_duration=timedelta(minutes=10),
        lifetime=timedelta(days=1),
        parameters_type=SimpleParameters,
        signing_service_account="signer@example.com",
        slack_webhook=SecretStr("https://example.com/fake-webhook"),
        sync_get_route=UWSRoute(
            dependency=_get_dependency, summary="Sync request"
        ),
        sync_post_route=UWSRoute(
            dependency=_post_dependency, summary="Sync request"
        ),
        worker="hello",
    )
