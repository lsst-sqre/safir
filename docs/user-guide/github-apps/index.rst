############################
Building GitHub integrations
############################

Being a software-oriented organization, Rubin Observatory applications often need to interact with GitHub, either as a source of data or to provide services to our staff and developers.
The recommended library for building GitHub integrations in Safir/FastAPI applications is with Gidgethub_.
Unlike highly opinionated GitHub libraries for Python, Gidgethub enables you to make API calls to URLs you can read about in the GitHub documentation (rather than requiring you to translate a library's documentation for GitHub into GitHub's own documentation).
Safir provides a `safir.github` subpackage that makes it easier to build GitHub integrations with Gidgethub, including:

- A factory for creating authenticated GitHub clients (`safir.github.GitHubAppClientFactory`).
- Pydantic models for GitHub v3 REST API resources (`safir.github.models`).
- Pydantic models for GitHub webhook payloads (`safir.github.webhooks`).

Guides
======

.. toctree::
   :titlesonly:

   create-a-github-client
   handling-webhooks

Reference
=========

.. toctree::
   :titlesonly:

   api-resources
   webhook-models
