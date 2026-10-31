"""Configuration models for database settings."""

from typing import Annotated, Any, Literal
from urllib.parse import quote, urlsplit

from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    MySQLDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from safir.pydantic import EnvAsyncPostgresDsn

__all__ = [
    "BaseDatabaseConfig",
    "CloudSqlConfig",
    "DatabaseConfig",
]


class BaseDatabaseConfig(BaseModel):
    """Base settings for database connections."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(validation_alias=to_camel),
        extra="forbid",
        populate_by_name=True,
    )

    type: Annotated[str, Field(title="Database type")]

    isolation_level: Annotated[
        str | None,
        Field(
            title="Isolation level",
            description=(
                "Non-default isolation level for the database engine if"
                " specified"
            ),
        ),
    ] = None

    max_overflow: Annotated[
        int | None,
        Field(
            title="Surge connections",
            description=(
                "Maximum number of connections over the pool size for surge"
                " traffic"
            ),
        ),
    ] = None

    pool_pre_ping: Annotated[
        bool | None,
        Field(
            title="Check connections",
            description=(
                "Check that a connection is alive before returning it to a"
                " session"
            ),
        ),
    ] = None

    pool_recycle: Annotated[
        int | None,
        Field(
            title="Recycle lifetime",
            description=(
                "Discard any idle connection open for longer than the"
                " provided number of seconds rather than attempting to reuse"
                " it. If the connection idle timeout on the database server"
                " is known, setting this to slightly less than that timeout"
                " will produce the best results."
            ),
        ),
    ] = None

    pool_size: Annotated[
        int | None,
        Field(title="Pool size", description="Connection pool size"),
    ] = None

    pool_timeout: Annotated[
        int | None,
        Field(
            title="Pool timeout",
            description=(
                "How long to wait for a connection from the connection pool"
                " before giving up."
            ),
        ),
    ] = None

    def engine_kwargs(
        self, connect_args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Construct the keyword arguments to SQLAlchemy engine creation."""
        kwargs: dict[str, Any] = {}
        if connect_args:
            kwargs["connect_args"] = connect_args

        # Go to some extra effort to avoid passing default None arguments into
        # SQLAlchemy because sometimes they can override a different default.
        if self.isolation_level:
            kwargs["isolation_level"] = self.isolation_level
        if self.max_overflow is not None:
            kwargs["max_overflow"] = self.max_overflow
        if self.pool_pre_ping is not None:
            kwargs["pool_pre_ping"] = self.pool_pre_ping
        if self.pool_recycle is not None:
            kwargs["pool_recycle"] = self.pool_recycle
        if self.pool_size is not None:
            kwargs["pool_size"] = self.pool_size
        if self.pool_timeout is not None:
            kwargs["pool_timeout"] = self.pool_timeout
        return kwargs

    @model_validator(mode="before")
    @classmethod
    def _remove_none(cls, data: Any) -> Any:
        """Remove configuration parameters set to `None`.

        The Helm chart sets a bunch of values explicitly to `None`, which may
        interfere with detection of whether the database configuration is for
        Cloud SQL or for an external database. It's never necessary to
        explicitly set a value to `None`, so strip all `None` values before
        validation.
        """
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if v is not None}


class CloudSqlConfig(BaseDatabaseConfig):
    """Configuration for a Cloud SQL database."""

    type: Literal["cloudsql"]

    project: Annotated[
        str,
        Field(
            title="Project",
            description="Google Cloud Platform project of Cloud SQL instance",
        ),
    ]

    region: Annotated[
        str,
        Field(
            title="Region",
            description="Region of the Cloud SQL instance",
        ),
    ]

    instance: Annotated[
        str, Field(title="Instance", description="Cloud SQL instance name")
    ]

    database: Annotated[
        str, Field(title="Database name", description="Name of the database")
    ]

    service_account: Annotated[
        str,
        Field(
            title="Service account",
            description=(
                "Google service account to use for authentication. This must"
                " be mapped to a Kubernetes service account through workload"
                " identity and be available as the default credentials. This"
                " service account must have the cloudsql.client and"
                " cloudsql.instanceUser roles."
            ),
        ),
    ]

    @property
    def instance_connection_name(self) -> str:
        """Instance connection name used for connecting to Cloud SQL."""
        return f"{self.project}:{self.region}:{self.instance}"

    @property
    def mock_url(self) -> str:
        """URL for mock connections."""
        return "postgresql+asyncpg://"

    @property
    def user(self) -> str:
        """Database user to connect as.

        This must match the Google service account name except that for
        PostgreSQL databases, such as the one Gafaelfawr users, the trailing
        ``.gserviceaccount.com`` must be removed.
        """
        return self.service_account.removesuffix(".gserviceaccount.com")


class DatabaseConfig(BaseDatabaseConfig):
    """Configuration for an external database."""

    type: Literal["external"] = "external"

    url: Annotated[
        EnvAsyncPostgresDsn | MySQLDsn,
        Field(
            title="Database DSN", description="DSN for the PostgreSQL database"
        ),
    ]

    password: Annotated[
        SecretStr,
        Field(
            title="Database password",
            description="Password for the PostgreSQL database",
        ),
    ]

    @property
    def mock_url(self) -> str:
        return str(self.url)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: EnvAsyncPostgresDsn) -> EnvAsyncPostgresDsn:
        """Ensure the URL contains a username."""
        parsed_url = urlsplit(str(v))
        if not parsed_url.username:
            raise ValueError(f"No username in database URL {v}")
        return v

    def build_url(self, *, is_async: bool = True) -> str:
        """Build the authenticated URL for the database.

        Unless ``is_async`` is set to `False`, the database scheme is forced
        to ``postgresql+asyncpg`` if it is ``postgresql``, and
        ``mysql+asyncmy`` if it is ``mysql``.

        Parameters
        ----------
        is_async
            Whether to force an async driver.

        Returns
        -------
        url
            URL including the password.

        Raises
        ------
        ValueError
            Raised if a password was provided but the connection URL has no
            username.
        """
        parsed_url = urlsplit(str(self.url))

        # Force an async driver if requested.
        if is_async:
            if parsed_url.scheme == "postgresql":
                parsed_url = parsed_url._replace(scheme="postgresql+asyncpg")
            elif parsed_url.scheme == "mysql":
                parsed_url = parsed_url._replace(scheme="mysql+asyncmy")

        # urlsplit doesn't decode URL escaping of components, so we should not
        # quote the username or we will get double-quoting.
        password = quote(self.password.get_secret_value(), safe="")
        netloc = f"{parsed_url.username}:{password}@{parsed_url.hostname}"
        if parsed_url.port:
            netloc = f"{netloc}:{parsed_url.port}"
        parsed_url = parsed_url._replace(netloc=netloc)
        return parsed_url.geturl()
