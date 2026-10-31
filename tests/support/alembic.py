"""Support classes for testing Alembic."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from safir.database import DatabaseConfig
from safir.logging import LogLevel

__all__ = [
    "BaseV1",
    "BaseV2",
    "UserV1",
    "UserV2",
    "config",
]


class Config(BaseSettings):
    """Just enough configuration to support the Alembic environments.

    When running Alembic via subprocess, set ``TEST_DATABASE__URL`` and
    ``TEST_DATABASE__PASSWORD`` to match the database that it should use.
    """

    model_config = SettingsConfigDict(
        env_prefix="TEST_", env_nested_delimiter="__"
    )

    database: DatabaseConfig | None = None
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
