"""Initializing a Kubernetes client."""

from __future__ import annotations

import os

try:
    from kubernetes_asyncio import config
except ImportError as e:
    raise ImportError(
        "The safir.kubernetes module requires the kubernetes extra. "
        "Install it with `pip install safir[kubernetes]`."
    ) from e

__all__ = ["initialize_kubernetes"]


async def initialize_kubernetes() -> None:
    """Load the Kubernetes configuration.

    This has to be run once per process and should be run during application
    startup.  This function handles Kubernetes configuration independent of
    any given Kubernetes client so that clients can be created for each
    request.

    Notes
    -----
    If ``KUBERNETES_PORT`` is set in the environment, this will use
    ``load_incluster_config`` to get configuration information from the local
    pod metadata.  Otherwise, it will use ``load_kube_config`` to read
    configuration from the user's home directory.
    """
    if "KUBERNETES_PORT" in os.environ:
        config.load_incluster_config()
    else:
        await config.load_kube_config()
