"""Support functions for testing UWS code."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from arq.connections import RedisSettings
from fastapi import Form, Query
from pydantic import BaseModel, SecretStr
from vo_models.uws import JobSummary, Parameter, Parameters

from safir.arq import ArqMode
from safir.uws import ParametersModel, UWSConfig, UWSRoute

__all__ = [
    "SimpleParameters",
    "SimpleXmlParameters",
    "build_uws_config",
]


class SimpleXmlParameters(Parameters):
    name: Parameter = Parameter(id="name")


class SimpleWorkerParameters(BaseModel):
    name: str


class SimpleParameters(
    ParametersModel[SimpleWorkerParameters, SimpleXmlParameters]
):
    name: str

    def to_worker_parameters(self) -> SimpleWorkerParameters:
        return SimpleWorkerParameters(name=self.name)

    def to_xml_model(self) -> SimpleXmlParameters:
        return SimpleXmlParameters(name=Parameter(id="name", value=self.name))


async def _get_dependency(
    name: Annotated[str, Query()],
) -> SimpleParameters:
    return SimpleParameters(name=name)


async def _post_dependency(
    name: Annotated[str, Form()],
) -> SimpleParameters:
    return SimpleParameters(name=name)


def build_uws_config() -> UWSConfig:
    """Set up a test configuration."""
    return UWSConfig(
        arq_mode=ArqMode.test,
        arq_redis_settings=RedisSettings(host="localhost", port=6379),
        async_post_route=UWSRoute(
            dependency=_post_dependency, summary="Create async job"
        ),
        execution_duration=timedelta(minutes=10),
        job_summary_type=JobSummary[SimpleXmlParameters],
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
        wobbly_url="https://example.com/wobbly",
        worker="hello",
    )
