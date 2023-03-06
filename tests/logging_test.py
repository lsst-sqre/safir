"""Tests for the safir.logging module."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY

import pytest
import structlog
from _pytest.capture import CaptureFixture
from _pytest.logging import LogCaptureFixture
from httpx import AsyncClient

from safir import logging as safir_logging
from safir.logging import LogLevel, Profile, configure_logging
from safir.testing.uvicorn import spawn_uvicorn

# Small app used to test Uvicorn logging configuration.
_UVICORN_APP = """
from fastapi import FastAPI
from safir.logging import configure_uvicorn_logging


app = FastAPI()
configure_uvicorn_logging()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/fail")
async def fail():
    raise TypeError("Uncaught exception")
"""


def _strip_color(string: str) -> str:
    """Strip ANSI color escape sequences.

    See https://stackoverflow.com/questions/14693701/
    """
    return re.sub(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]", "", string)


def test_configure_logging_development(caplog: LogCaptureFixture) -> None:
    """Test that development-mode logging is key-value formatted."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp", profile=Profile.development, log_level=LogLevel.INFO
    )
    assert safir_logging.logger_name == "myapp"

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    app, level, line = caplog.record_tuples[0]
    assert app == "myapp"
    assert level == logging.INFO
    expected = "[info     ] Hello world                    [myapp] answer=42"
    assert _strip_color(line) == expected


def test_configure_logging_dev_timestamp(caplog: LogCaptureFixture) -> None:
    """Test development-mode logging with an added timestamp."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp",
        profile="development",
        log_level="info",
        add_timestamp=True,
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.INFO
    match = re.match(
        (
            r"(\d+-\d+-\d+T\d+:\d+:[\d.]+Z) \[info\s+\] Hello world \s+"
            r" \[myapp\] answer=42"
        ),
        _strip_color(caplog.record_tuples[0][2]),
    )
    assert match
    isotimestamp = match.group(1)
    assert isotimestamp.endswith("Z")
    timestamp = datetime.fromisoformat(isotimestamp[:-1])
    timestamp = timestamp.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=5) < timestamp < now


def test_configure_logging_production(caplog: LogCaptureFixture) -> None:
    """Test that production-mode logging is JSON formatted."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp", profile=Profile.production, log_level=LogLevel.INFO
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0] == (
        "myapp",
        logging.INFO,
        '{"answer": 42, "event": "Hello world", "logger": "myapp", '
        '"severity": "info"}',
    )


def test_configure_logging_prod_timestamp(caplog: LogCaptureFixture) -> None:
    """Test development-mode logging with an added timestamp."""
    caplog.set_level(logging.INFO)

    configure_logging(
        name="myapp",
        profile="production",
        log_level="info",
        add_timestamp=True,
    )

    logger = structlog.get_logger("myapp")
    logger = logger.bind(answer=42)
    logger.info("Hello world")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.INFO
    data = json.loads(caplog.record_tuples[0][2])
    assert data == {
        "answer": 42,
        "event": "Hello world",
        "logger": "myapp",
        "severity": "info",
        "timestamp": ANY,
    }
    assert data["timestamp"].endswith("Z")
    timestamp = datetime.fromisoformat(data["timestamp"][:-1])
    timestamp = timestamp.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    assert now - timedelta(seconds=5) < timestamp < now


def test_configure_logging_level(caplog: LogCaptureFixture) -> None:
    """Test that the logging level is set."""
    caplog.set_level(logging.DEBUG)

    configure_logging(name="myapp", log_level=LogLevel.INFO)
    logger = structlog.get_logger("myapp")

    logger.info("INFO message")
    assert len(caplog.record_tuples) == 1

    # debug-level shouldn't get logged
    logger.debug("DEBUG message")
    assert len(caplog.record_tuples) == 1


def test_duplicate_handlers(capsys: CaptureFixture[str]) -> None:
    """Test that configuring logging more than once doesn't duplicate logs."""
    configure_logging(name="myapp", profile="production", log_level="info")
    configure_logging(name="myapp", profile="production", log_level="info")

    logger = structlog.get_logger("myapp")

    logger.info("INFO not duplicate message")
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1


def test_dev_exception_logging(caplog: LogCaptureFixture) -> None:
    """Test that exceptions are properly logged in the development logger."""
    configure_logging(
        name="myapp", profile=Profile.development, log_level=LogLevel.INFO
    )
    logger = structlog.get_logger("myapp")

    try:
        raise ValueError("this is some exception")
    except Exception:
        logger.exception("exception happened", foo="bar")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.ERROR
    assert "Traceback (most recent call last)" in caplog.record_tuples[0][2]
    assert '"this is some exception"' in caplog.record_tuples[0][2]


def test_production_exception_logging(caplog: LogCaptureFixture) -> None:
    """Test that exceptions are properly logged in the production logger."""
    configure_logging(
        name="myapp", profile=Profile.production, log_level=LogLevel.INFO
    )
    logger = structlog.get_logger("myapp")

    try:
        raise ValueError("this is some exception")
    except Exception:
        logger.exception("exception happened", foo="bar")

    assert caplog.record_tuples[0][0] == "myapp"
    assert caplog.record_tuples[0][1] == logging.ERROR
    data = json.loads(caplog.record_tuples[0][2])
    assert data == {
        "event": "exception happened",
        "exception": ANY,
        "foo": "bar",
        "logger": "myapp",
        "severity": "error",
    }
    assert "Traceback (most recent call last)" in data["exception"]
    assert '"this is some exception"' in data["exception"]


@pytest.mark.asyncio
async def test_uvicorn_logging(tmp_path: Path) -> None:
    """Test the Uvicorn logging configuration."""
    app_path = tmp_path / "test.py"
    app_path.write_text(_UVICORN_APP)
    uvicorn = spawn_uvicorn(
        working_directory=tmp_path, app="test:app", capture=True
    )

    # Perform some operations against the app. Assume the pipe buffers are
    # large enough to hold all of the Uvicorn logging output generated by
    # this. (If they're ever not, we'll have to call communicate on the Popen
    # object.)
    try:
        async with AsyncClient() as client:
            r = await client.get(f"{uvicorn.url}/")
            assert r.status_code == 200
            r = await client.get(f"{uvicorn.url}/fail")
            assert r.status_code == 500
    finally:
        uvicorn.process.terminate()
        stdout, stderr = uvicorn.process.communicate()

    # stdout will be the access log. The raw event will contain the client
    # port, to which we do not have easy access, so only examine the
    # additional fields that should be added by Safir's custom Uvicorn log
    # handling.
    messages = [json.loads(line) for line in stdout.strip().split("\n")]
    assert messages == [
        {
            "event": ANY,
            "severity": "info",
            "httpRequest": {
                "protocol": "HTTP/1.1",
                "requestMethod": "GET",
                "requestUrl": "/",
                "status": "200",
            },
        },
        {
            "event": ANY,
            "severity": "info",
            "httpRequest": {
                "protocol": "HTTP/1.1",
                "requestMethod": "GET",
                "requestUrl": "/fail",
                "status": "500",
            },
        },
    ]

    # stderr will be the error log. There will be a bunch of random Uvicorn
    # messages here; just make sure they're all valid JSON. But make sure that
    # the log for the exception we raised includes the full traceback.
    messages = [json.loads(line) for line in stderr.strip().split("\n")]
    for message in messages:
        if "Exception in ASGI application" in message["event"]:
            assert "TypeError" in message["exception"]
            assert "in fail" in message["exception"]
