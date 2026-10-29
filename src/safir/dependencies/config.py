"""Config dependency for FastAPI."""

import os
from pathlib import Path

from safir.pydantic import YamlBaseSettings

__all__ = ["ConfigDependency"]


class ConfigDependency[T: YamlBaseSettings]:
    """Provides the configuration as a dependency.

    We want a production deployment to default to one configuration path, but
    allow that path to be overridden by the test suite and, if the path
    changes, to reload the configuration (which allows sharing the same set of
    global singletons across multiple tests).  Do this by loading the config
    dynamically when it's first requested and reloading it whenever the
    configuration path is changed.

    Parameters
    ----------
    config_model
        Base model for the configuration.
    default_config_path
        Default path to the configuration file.
    path_env
        Environment variable from which to get the path to the configuration
        file, if set, overriding the default path.
    """

    def __init__(
        self,
        base_model: type[T],
        default_config_path: Path | str,
        path_env: str,
    ) -> None:
        self._base_model = base_model
        self._config_path = Path(os.getenv(path_env, default_config_path))
        self._config: T | None = None

    async def __call__(self) -> T:
        """Load the configuration if necessary and return it."""
        return self.config()

    @property
    def config_path(self) -> Path:
        """Path to the configuration file."""
        return self._config_path

    def config(self) -> T:
        """Load the configuration if necessary and return it.

        This is equivalent to using the dependency as a callable except that
        it's not async and can therefore be used from non-async functions.
        """
        if not self._config:
            self._config = self._base_model.from_file(self._config_path)
        return self._config

    def set_config_path(self, path: Path) -> None:
        """Change the configuration path and reload the config.

        Parameters
        ----------
        path
            The new configuration path.
        """
        self._config_path = path
        self._config = self._base_model.from_file(path)
