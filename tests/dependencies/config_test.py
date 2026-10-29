"""Tests for ConfigDependency."""

from pathlib import Path

import pytest

from safir.dependencies.config import ConfigDependency
from safir.pydantic import YamlBaseSettings
from safir.testing.data import Data


class Config(YamlBaseSettings):
    simple: int
    multi_word: str
    env_override: str


@pytest.mark.asyncio
async def test_config_dependency(
    data: Data, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = data.path("pydantic/settings.yaml")
    config_env = "TEST_CONFIG_PATH"
    config = Config.from_file(config_path)

    config_dependency = ConfigDependency(Config, config_path, config_env)
    assert config_dependency.config() == config
    assert await config_dependency() == config
    assert config_dependency.config_path == config_path

    monkeypatch.delenv("TEST_CONFIG_PATH", raising=False)
    config_dependency = ConfigDependency(
        Config, "/nonexistent/config.yaml", config_env
    )
    assert config_dependency.config_path == Path("/nonexistent/config.yaml")
    with pytest.raises(FileNotFoundError):
        config_dependency.config()

    monkeypatch.setenv("TEST_CONFIG_PATH", str(config_path))
    config_dependency = ConfigDependency(
        Config, "/nonexistent/config.yaml", config_env
    )
    assert config_dependency.config_path == config_path
    assert config_dependency.config() == config
    assert await config_dependency() == config
    monkeypatch.delenv("TEST_CONFIG_PATH")

    config_dependency = ConfigDependency(
        Config, Path("/nonexistent/config.yaml"), config_env
    )
    assert config_dependency.config_path == Path("/nonexistent/config.yaml")
    with pytest.raises(FileNotFoundError):
        config_dependency.config()
    config_dependency.set_config_path(config_path)
    assert config_dependency.config() == config
    assert await config_dependency() == config
    assert config_dependency.config_path == config_path
