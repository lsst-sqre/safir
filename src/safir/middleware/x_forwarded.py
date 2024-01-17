"""Update the request based on ``X-Forwarded-For`` headers."""

from __future__ import annotations

from copy import copy
from ipaddress import _BaseAddress, _BaseNetwork, ip_address

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["XForwardedMiddleware"]


class XForwardedMiddleware:
    """ASGI middleware to update the request based on ``X-Forwarded-For``.

    The remote IP address will be replaced with the right-most IP address in
    ``X-Forwarded-For`` that is not contained within one of the trusted
    proxy networks.

    If ``X-Forwarded-For`` is found and ``X-Forwarded-Proto`` is also present,
    the corresponding entry of ``X-Forwarded-Proto`` is used to replace the
    scheme in the request scope. If ``X-Forwarded-Proto`` only has one entry
    (ingress-nginx has this behavior), that one entry will become the new
    scheme in the request scope.

    The contents of ``X-Forwarded-Host`` will be stored as ``forwarded_host``
    in the request state if it and ``X-Forwarded-For`` are present. Normally
    this is not needed since NGINX will pass the original ``Host`` header
    without modification.

    Parameters
    ----------
    proxies
        The networks of the trusted proxies. If not specified, defaults to the
        empty list, which means only the immediately upstream proxy will be
        trusted.
    """

    def __init__(
        self, app: ASGIApp, *, proxies: list[_BaseNetwork] | None = None
    ) -> None:
        self._app = app
        self._proxies = proxies if proxies else []

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        scope = copy(scope)
        scope.setdefault("state", {})
        headers = Headers(scope=scope)
        forwarded_for = list(reversed(self._get_forwarded_for(headers)))
        if not forwarded_for:
            scope["state"]["forwarded_host"] = None
            await self._app(scope, receive, send)
            return

        client = None
        for n, ip in enumerate(forwarded_for):
            if any(ip in network for network in self._proxies):
                continue
            client = str(ip)
            index = n
            break

        # If all the IP addresses are from trusted networks, take the
        # left-most.
        if not client:
            client = str(forwarded_for[-1])
            index = -1

        # Update the request's understanding of the client IP.
        if scope.get("client"):
            scope["client"] = (client, scope["client"][1])
        else:
            scope["client"] = (client, None)

        # Ideally this should take the scheme corresponding to the entry in
        # X-Forwarded-For that was chosen, but some proxies (the Kubernetes
        # NGINX ingress, for example) only retain one element in
        # X-Forwarded-Proto. In that case, use what we have.
        proto = list(reversed(self._get_forwarded_proto(headers)))
        if proto:
            if index >= len(proto):
                index = -1
            scope["scheme"] = proto[index]

        # Record what appears to be the client host for logging purposes.
        scope["state"]["forwarded_host"] = self._get_forwarded_host(headers)

        # Perform the rest of the request processing.
        await self._app(scope, receive, send)
        return

    def _get_forwarded_for(self, headers: Headers) -> list[_BaseAddress]:
        """Retrieve the ``X-Forwarded-For`` entries from the request.

        Parameters
        ----------
        scope
            Request headers.

        Returns
        -------
        list of ipaddress._BaseAddress
            The list of addresses found in the header. If there are multiple
            ``X-Forwarded-For`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_for_str = headers.getlist("X-Forwarded-For")
        if not forwarded_for_str or len(forwarded_for_str) > 1:
            return []
        return [
            ip_address(addr)
            for addr in (a.strip() for a in forwarded_for_str[0].split(","))
            if addr
        ]

    def _get_forwarded_host(self, headers: Headers) -> str | None:
        """Retrieve the ``X-Forwarded-Host`` header.

        Parameters
        ----------
        headers
            Request headers.

        Returns
        -------
        str
            The value of the ``X-Forwarded-Host`` header, if present and if
            there is only one header. If there are multiple
            ``X-Forwarded-Host`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_host = headers.getlist("X-Forwarded-Host")
        if not forwarded_host or len(forwarded_host) > 1:
            return None
        return forwarded_host[0].strip()

    def _get_forwarded_proto(self, headers: Headers) -> list[str]:
        """Retrieve the ``X-Forwarded-Proto`` entries from the request.

        Parameters
        ----------
        headers
            Request headers.

        Returns
        -------
        list of str
            The list of schemes found in the header. If there are multiple
            ``X-Forwarded-Proto`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_proto_str = headers.getlist("X-Forwarded-Proto")
        if not forwarded_proto_str or len(forwarded_proto_str) > 1:
            return []
        return [p.strip() for p in forwarded_proto_str[0].split(",")]
