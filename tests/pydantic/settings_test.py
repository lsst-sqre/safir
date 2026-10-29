"""Tests for YAML base settings."""

import pytest
import yaml
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from safir.pydantic import YamlBaseSettings
from safir.testing.data import Data


class Config(YamlBaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEST_CONFIG_")

    simple: int
    multi_word: str
    env_override: str


def test_yaml_base_settings(
    data: Data, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config.from_file(data.path("pydantic/settings.yaml"))
    with data.path("pydantic/settings.yaml").open("r") as fh:
        raw = yaml.safe_load(fh)
    assert config.model_dump(mode="json") == {
        "simple": raw["simple"],
        "multi_word": raw["multiWord"],
        "env_override": raw["envOverride"],
    }

    monkeypatch.setenv("TEST_CONFIG_ENV_OVERRIDE", "other value")
    config = Config.from_file(data.path("pydantic/settings.yaml"))
    assert config.env_override != raw["envOverride"]
    assert config.env_override == "other value"

    with pytest.raises(ValidationError):
        Config.from_file(data.path("pydantic/settings-extra.yaml"))
