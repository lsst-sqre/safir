"""Update the request based on ``X-Forwarded-For`` headers."""

from __future__ import annotations

from ipaddress import ip_address
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from ipaddress import _BaseAddress, _BaseNetwork
    from typing import Awaitable, Callable, List, Optional

    from fastapi import FastAPI

__all__ = ["XForwardedMiddleware"]


class XForwardedMiddleware(BaseHTTPMiddleware):
    """Middleware to update the request based on ``X-Forwarded-For``.

    The remote IP address will be replaced with the right-most IP address in
    ``X-Forwarded-For`` that is not contained within one of the trusted
    proxy networks.

    If ``X-Forwarded-For`` is found and ``X-Forwarded-Proto`` is also present,
    the corresponding entry of ``X-Forwarded-Proto`` is stored as
    ``forwarded_proto`` in the request state.  If ``X-Forwarded-Proto`` only
    has one entry (ingress-nginx has this behavior), that one entry will be
    stored as ``forwarded_proto``.

    The contents of ``X-Forwarded-Host`` will be stored as ``forwarded_host``
    in the request state if it and ``X-Forwarded-For`` are present.

    Parameters
    ----------
    proxies : List[`ipaddress._BaseNetwork`], optional
        The networks of the trusted proxies.  If not specified, defaults to
        the empty list, which means only the immediately upstream proxy will
        be trusted.
    """

    def __init__(
        self, app: FastAPI, *, proxies: Optional[List[_BaseNetwork]] = None
    ) -> None:
        super().__init__(app)
        if proxies:
            self.proxies = proxies
        else:
            self.proxies = []

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Middleware to update the request based on ``X-Forwarded-For``.

        Parameters
        ----------
        request : ``fastapi.Request``
            The incoming request.
        call_next : `typing.Callable`
            The next step in the processing stack.

        Returns
        -------
        response : ``fastapi.Response``
            The response with additional information about proxy headers.
        """
        forwarded_for = list(reversed(self._get_forwarded_for(request)))
        if not forwarded_for:
            request.state.forwarded_host = None
            request.state.forwarded_proto = None
            return await call_next(request)

        client = None
        for n, ip in enumerate(forwarded_for):
            if any((ip in network for network in self.proxies)):
                continue
            client = str(ip)
            index = n
            break

        # If all the IP addresses are from trusted networks, take the
        # left-most.
        if not client:
            client = str(forwarded_for[-1])
            index = -1

        # Update the request's understanding of the client IP.  This uses an
        # undocumented interface; hopefully it will keep working.
        request.scope["client"] = (client, request.client.port)

        # Ideally this should take the scheme corresponding to the entry in
        # X-Forwarded-For that was chosen, but some proxies (the Kubernetes
        # NGINX ingress, for example) only retain one element in
        # X-Forwarded-Proto.  In that case, use what we have.
        proto = list(reversed(self._get_forwarded_proto(request)))
        if proto:
            if index >= len(proto):
                index = -1
            request.state.forwarded_proto = proto[index]
        else:
            request.state.forwarded_proto = None

        # Rather than one entry per hop, NGINX seems to add only a single
        # X-Forwarded-Host header with the original hostname.
        request.state.forwarded_host = self._get_forwarded_host(request)

        return await call_next(request)

    def _get_forwarded_for(self, request: Request) -> List[_BaseAddress]:
        """Retrieve the ``X-Forwarded-For`` entries from the request.

        Parameters
        ----------
        request : ``fastapi.Request``
            The incoming request.

        Returns
        -------
        forwarded_for : List[`ipaddress._BaseAddress`]
            The list of addresses found in the header.  If there are multiple
            ``X-Forwarded-For`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_for_str = request.headers.getlist("X-Forwarded-For")
        if not forwarded_for_str or len(forwarded_for_str) > 1:
            return []
        return [
            ip_address(addr)
            for addr in (a.strip() for a in forwarded_for_str[0].split(","))
            if addr
        ]

    def _get_forwarded_host(self, request: Request) -> Optional[str]:
        """Retrieve the ``X-Forwarded-Host`` header.

        Parameters
        ----------
        request : ``fastapi.Request``
            The incoming request.

        Returns
        -------
        forwarded_host : str
            The value of the ``X-Forwarded-Host`` header, if present and if
            there is only one header.  If there are multiple
            ``X-Forwarded-Host`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_host = request.headers.getlist("X-Forwarded-Host")
        if not forwarded_host or len(forwarded_host) > 1:
            return None
        return forwarded_host[0].strip()

    def _get_forwarded_proto(self, request: Request) -> List[str]:
        """Retrieve the ``X-Forwarded-Proto`` entries from the request.

        Parameters
        ----------
        request : ``fastapi.Request``
            The incoming request.

        Returns
        -------
        forwarded_for : List[``ipaddress._BaseAddress``]
            The list of addresses found in the header.  If there are multiple
            ``X-Forwarded-Proto`` headers, we don't know which one is correct,
            so act as if there are no headers.
        """
        forwarded_proto_str = request.headers.getlist("X-Forwarded-Proto")
        if not forwarded_proto_str or len(forwarded_proto_str) > 1:
            return []
        return [p.strip() for p in forwarded_proto_str[0].split(",")]
