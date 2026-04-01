####################
Parsing HTTP headers
####################

.. _http-pagination:

Parsing paginated responses
===========================

Safir provides `~safir.http.PaginationLinkData` to parse the contents of an :rfc:`8288` ``Link`` header and extract pagination links from it.

.. code-block:: python

   from safir.http import PaginationLinkData


   r = client.get("/some/url", query={"limit": 100})
   links = PaginationLinkData.from_header(r.headers["Link"])
   next_url = links.next_url
   prev_url = links.prev_url
   first_url = links.first_url

Currently, only the first, next, and previous URLs are extracted from the ``Link`` header.
If any of these URLs are not present, the corresponding attribute of `~safir.http.PaginationLinkData` will be `None`.
