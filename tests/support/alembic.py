"""Support classes for testing Alembic."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_core import Url
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from safir.logging import LogLevel
from safir.pydantic import EnvAsyncPostgresDsn

__all__ = [
    "BaseV1",
    "BaseV2",
    "UserV1",
    "UserV2",
    "config",
]


class Config(BaseSettings):
    """Just enough configuration to support the Alembic environments.

    When running Alembic via subprocess, set ``TEST_DATABASE_URL`` and
    ``TEST_DATABASE_PASSWORD`` to match the database that it should use.
    """

    model_config = SettingsConfigDict(env_prefix="TEST_", case_sensitive=False)

    database_url: EnvAsyncPostgresDsn = Url("postgresql://localhost/safir")
    database_password: SecretStr = SecretStr("INSECURE")
    log_level: LogLevel = LogLevel.DEBUG


config = Config()
"""Global config object used by Alembic."""


class BaseV1(DeclarativeBase):
    """First version of a database schema."""


class UserV1(BaseV1):
    """First version of a users table."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str | None]


class BaseV2(DeclarativeBase):
    """Second version of a database schema."""


class UserV2(BaseV2):
    """First version of a users table."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str | None]
    email: Mapped[str | None]
