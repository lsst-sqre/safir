"""Utiility functions for managing an external Uvicorn test process.

Normally, ASGI apps are tested via the built-in support in HTTPX for running
an ASGI app directly. However, sometimes the app has to be spawned in a
separate process so that it can be accessed over HTTP, such as when testing it
with Selenium or when testing Uvicorn integration. This module provides
utility functions to aid with that test setup.
"""

from __future__ import annotations

import errno
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "ServerNotListeningError",
    "UvicornProcess",
    "spawn_uvicorn",
]


class ServerNotListeningError(Exception):
    """Timeout waiting for the server to start listening."""


@dataclass
class UvicornProcess:
    """Properties of the running Uvicorn service."""

    process: subprocess.Popen
    """Running Uvicorn process."""

    url: str
    """URL (on localhost) on which the process is listening."""


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    """Wait until a server accepts connections on the specified port.

    Parameters
    ----------
    port
        Port on localhost on which the server will listen.
    timeout
        How long to wait in seconds.

    Raises
    ------
    ServerNotListeningError
        The server did not start within the specified timeout.
    """
    deadline = time.time() + timeout
    while True:
        socket_timeout = deadline - time.time()
        if socket_timeout < 0.0:
            msg = f"Server did not start on port {port} in {timeout}s"
            raise ServerNotListeningError(msg)
        try:
            sock = socket.socket()
            sock.settimeout(socket_timeout)
            sock.connect(("localhost", port))
        except socket.timeout:
            pass
        except socket.error as e:
            if e.errno not in (errno.ETIMEDOUT, errno.ECONNREFUSED):
                raise
        else:
            sock.close()
            return
        time.sleep(0.1)


def spawn_uvicorn(
    *,
    working_directory: str | Path,
    app: Optional[str] = None,
    factory: Optional[str] = None,
    capture: bool = False,
    timeout: float = 5.0,
    env: Optional[dict[str, str]] = None,
) -> UvicornProcess:
    """Spawn an ASGI app as a separate Uvicorn process.

    The current working directory will always be added to the Python path, so
    ``app`` and ``factory`` can point to modules found relative to the current
    working directory, or relative to the ``working_directory`` parameter.

    Parameters
    ----------
    working_directory
        Directory in which Uvicorn should run. Normally this should come from
        the ``tmp_path`` fixture.
    app
        Module and variable name of the app. Either this or ``factory`` must
        be given.
    factory
        Module name and callable that will create the app object. Either this
        or ``app`` must be given.
    capture
        Whether to capture standard output and standard error of Uvicorn. If
        set to true, both will be automatically decoded as UTF-8 text and will
        be available in the ``process`` attribute of the returned object.
    timeout
        How long to wait in seconds.
    env
        Extra environment variable settings.

    Returns
    -------
    UvicornProcess
        Properties of the running Uvicorn service.

    Raises
    ------
    ServerNotListeningError
        Server did not start within the timeout. Generally this means it had
        some fatal error during startup.
    ValueError
        Either both or neither of app and factory were given.
    """
    if app and factory:
        raise ValueError("Only one of app or factory may be given")
    if not app and not factory:
        raise ValueError("Neither of app nor factory was given")
    if env:
        env = {**os.environ, **env}
    else:
        env = {**os.environ}

    # Get a random port for the app to listen on.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    # Spawn the app.
    cmd = ["uvicorn", "--fd", "0"]
    if app:
        cmd.append(app)
    elif factory:
        cmd.extend(("--factory", factory))
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] += f":{os.getcwd()}"
    else:
        env["PYTHONPATH"] = os.getcwd()
    logging.info("Starting server with command %s", " ".join(cmd))
    if capture:
        process = subprocess.Popen(
            cmd,
            cwd=str(working_directory),
            stdin=sock.fileno(),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    else:
        process = subprocess.Popen(
            cmd,
            cwd=str(working_directory),
            stdin=sock.fileno(),
            env=env,
            text=True,
        )
    sock.close()

    # Wait for it to start listening.
    logging.info("Waiting for server to start")
    _wait_for_server(port, timeout)

    # Server successfully started. Return its properties.
    return UvicornProcess(process=process, url=f"http://127.0.0.1:{port}")
