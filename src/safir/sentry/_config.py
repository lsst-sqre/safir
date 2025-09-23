"""Sentry configuration helpers."""

import os
from typing import Annotated, Any

import sentry_sdk
from pydantic import Field
from pydantic_settings import BaseSettings

from safir.sentry._helpers import before_send_handler

__all__ = ["SentryConfig", "initialize_sentry", "should_enable_sentry"]


class SentryConfig(BaseSettings):
    """Values from environment variables to configure Sentry.

    Most Safir apps should define at least these paramters when initializing
    Sentry. These are taken from enviroment variables and not part of the main
    app config class because we want to initialize Sentry before the app
    configuration is initialized.
    """

    dsn: Annotated[
        str,
        Field(
            validation_alias="SENTRY_DSN",
            description="DSN for sending events to Sentry",
        ),
    ]

    environment: Annotated[
        str,
        Field(
            validation_alias="SENTRY_ENVIRONMENT",
            description=(
                "Phalanx name of the Rubin Science Platform environment"
            ),
        ),
    ]

    traces_sample_rate: Annotated[
        float,
        Field(
            validation_alias="SENTRY_TRACES_SAMPLE_RATE",
            description=(
                "Percentage of transactions to send to Sentry, expressed "
                "as a float between 0 and 1. 0 means send no traces, 1 "
                "means send every trace."
            ),
            ge=0,
            le=1,
        ),
    ] = 0


def should_enable_sentry() -> bool:
    """Return True if we should enable the Sentry integration."""
    return bool(os.environ.get("SENTRY_DSN"))


def initialize_sentry(release: str, **additional_kwargs: Any) -> None:
    """Initialize Sentry with env var values and the safir before_send handler.

    Most Safir apps should provide certain Sentry parameters. This method will
    validate and pass those parameters, as well as any additional parameters,
    to the Sentry SDK init function. It also adds
    `~safir.sentry.before_send_handler` so that
    `~safir.slack.blockkit.SlackException` values can be used.

    Parameters
    ----------
    release
        The version of this application that should be sent \
        with every Sentry event. For most Safir applications, you should pass \
        the value in ``<package>.__version__``.
    """
    if not should_enable_sentry():
        return

    config = SentryConfig()
    kwargs = config.model_dump()
    sentry_sdk.init(
        before_send=before_send_handler,
        release=release,
        **kwargs,
        **additional_kwargs,
    )
