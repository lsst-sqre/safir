"""Tests for arq utility functions.

Most of the arq support code is tested by testing the FastAPI dependency.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_core import Url

from safir.arq import build_arq_redis_settings


def test_build_arq_redis_settings() -> None:
    url = Url.build(scheme="redis", host="localhost")
    settings = build_arq_redis_settings(url, None)
    assert settings.host == "localhost"
    assert settings.port == 6379
    assert settings.database == 0
    assert settings.password is None

    url = Url.build(scheme="redis", host="example.com", port=7777, path="4")
    settings = build_arq_redis_settings(url, SecretStr("password"))
    assert settings.host == "example.com"
    assert settings.port == 7777
    assert settings.database == 4
    assert settings.password == "password"
