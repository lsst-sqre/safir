"""Base classes for application settings."""

from pathlib import Path
from typing import Self, override

import yaml
from pydantic import AliasChoices, AliasGenerator
from pydantic.alias_generators import to_camel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

__all__ = ["YamlBaseSettings"]


class YamlBaseSettings(BaseSettings):
    """Base class for Pydantic settings from a YAML file.

    This class is intended to serve as the base class for application settings
    when the settings are primarily parsed from a YAML configuration file with
    optional overrides and secrets from environment variables. It enables
    camel case for validation, allowing all parameters to be specified in the
    camel-case format that is standard for Helm charts. It also forbids extra
    settings and disables settings sources other than the constructor (used
    when reading YAML files) and environment variables.

    It is normally used in conjunction with
    `~safir.dependencies.config.ConfigDependency`.
    """

    model_config = SettingsConfigDict(
        # Both the regular and the camel-case versions of the attribute name
        # must be defined as aliases for environment variable overrides to
        # work properly in pydantic-settings 2.16.2, even though the
        # documentation seems to imply this should not be necessary when
        # validate_by_name is set to True.
        alias_generator=AliasGenerator(
            validation_alias=lambda n: AliasChoices(n, to_camel(n))
        ),
        extra="forbid",
        validate_by_name=True,
    )

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Override the sources of settings.

        Deactivate :file:`.env` and secret file support, since Phalanx doesn't
        use them. Allow environment variables to override init parameters,
        since init parameters come from the YAML configuration file and we
        want environment variables to take precedent.
        """
        # Ideally, this class would use Pydantic's YamlConfigSettingsSource,
        # but unfortunately it doesn't appear to support overriding the path
        # to the configuration file dynamically, which is required by test
        # suites.
        return (env_settings, init_settings)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Construct a settings object from a configuration file.

        Parameters
        ----------
        path
            Path to the configuration file in YAML.

        Returns
        -------
        YamlBaseSettings
            The corresponding settings object.
        """
        with path.open("r") as f:
            return cls.model_validate(yaml.safe_load(f))
