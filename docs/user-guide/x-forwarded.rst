.. _x-forwarded:

##################################
Handling ``X-Forwarded-*`` headers
##################################

Kubernetes applications run behind an HTTP proxy server called the Kubernetes ingress.
This means that (in a typical configuration) the IP address from which they receive an HTTP request is the IP address of the ingress, not of the client.
However, for logging and trace purposes, applications would prefer to associate requests with the actual client IP.

There is a protocol for a proxy server to communicate the original IP and other information about the original request to the application behind the proxy.
This uses a set of headers starting with ``X-Forwarded-``.
The primary header is ``X-Forwarded-For``, which includes each IP address that has handled the request, starting with the original IP address.

Safir provides Starlette middleware, usable by FastAPI applications, to analyze the incoming request and update information about its origin before passing it to the request handler.
This is available as `safir.middleware.x_forwarded.XForwardedMiddleware`.

Setting up XForwardedMiddleware
===============================

For a typical application behind a single ingress proxy, just add the middleware to the FastAPI application:

.. code-block:: python

    from safir.middleware.x_forwarded import XForwardedMiddleware

    app = FastAPI()
    app.add_middleware(XForwardedMiddleware)

Sometimes there are multiple proxies upstream of an application.
Each proxy through which the request travels appends a new source IP entry to the ``X-Forwarded-For`` header.
The true client IP can therefore be found by removing the proxies and using the rightmost non-proxy IP address.

However, analysis of ``X-Forwarded-*`` headers must be done with some caution since a malicious client can include inaccurate ``X-Forwarded-*`` headers in its request to attempt to disguise the true origin of the request.
Middleware that processes those headers must therefore not blindly trust their entire contents, but instead only trust the entries that come from trusted proxies.
This is done by starting from the rightmost entry of that header and removing entries for trusted proxies.
The first untrusted IP address (which would have been added by the outermost trusted proxy) is taken as the true origin of the request.

This unfortunately requires configuring the middleware with a list of trusted proxies when initializing the middleware.
For an application in this situation, pass in a list of trusted proxy IP ranges to the middleware:

.. code-block:: python

    proxies = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    app = FastAPI()
    app.add_middleware(XForwardedMiddleware, proxies=proxies)

It normally makes sense to get this list of proxies from the application configuration, since it may change in different deployments.

Using XForwardedMiddleware
==========================

The middleware will update ``request.client`` transparently before the request handler is called, so the application can use it as normal.
The IP address stored in the first element of the tuple will be the original client IP as determined from the ``X-Forwarded-For`` header.

The port number associated with the client is not updated and will be the client port on the proxy.
(This port number is generally not useful.)

If the necessary ``X-Forwarded-Proto`` header is present and appears to be valid, the scheme of the request URL will be set to the original scheme used by the client before the request handler is called.
This will cause ``request.url_for()`` and similar request methods and attributes to use the scheme of the original request rather than the scheme seen by the server.
(Generally this means using ``https`` instead of ``http``.)
If there are multiple ``X-Forwarded-Proto`` headers, there is no way of knowing which is correct, so they are all ignored.

The middleware will store the original value of the ``Host`` header in the client request in ``request.state.forwarded_host``.
(This is usually not needed, since NGINX generally preserves the ``Host`` header of the original request when proxying.)
This may be ``None`` if ``X-Forwarded-Host`` is missing or invalid.
If there are multiple ``X-Forwarded-Host`` headers, there is no way of knowing which is correct, so they are all ignored.

Note that ``X-Forwarded-Host``, unlike the other headers, does not accumulate values as it passes through multiple proxies.
``request.state.forwarded_host`` may therefore be incorrect if there are multiple proxies in front of the application.

``Forwarded`` header
====================

``Forwarded`` is the standardized header that is intended to replace ``X-Forwarded-For``, ``X-Forwarded-Proto``, and ``X-Forwarded-Host``.
However, support for it is less common.
For example, it is not supported by the standard Kubernetes NGINX ingress.

It is not supported by this middleware.
