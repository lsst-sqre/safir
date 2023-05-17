##################################
Models for GitHub webhook payloads
##################################

This page provides a quick reference for the Pydantic models provided in `safir.github.webhooks` with the corresponding GitHub webhook events.

.. note::

    Safir's coverage of GitHub webhooks is not exhaustive.
    You can contribute additional models as needed.
    
    Additionally, the models are not necessarily complete.
    GitHub may provide additional fields that are not parsed by these models because they were not deemed relevant.
    To use additional fields documented by GitHub, you can either subclass these models and add additional fields, or contribute updates to the models in Safir.

GitHub events
=============

.. list-table::
   :header-rows: 1

   * - Event
     - Model
   * - `check_run <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#check_run>`__
     - `~safir.github.webhooks.GitHubCheckRunEventModel`
   * - `check_suite <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#check_suite>`__
     - `~safir.github.webhooks.GitHubCheckSuiteEventModel`
   * - `installation <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#installation>`__
     - `~safir.github.webhooks.GitHubAppInstallationEventModel`
   * - `installation_repositories <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#installation_repositories>`__
     - `~safir.github.webhooks.GitHubAppInstallationRepositoriesEventModel`
   * - `pull_request <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#pull_request>`__
     - `~safir.github.webhooks.GitHubPullRequestEventModel`
   * - `push <https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#push>`__
     - `~safir.github.webhooks.GitHubPushEventModel`

Related documentation
=====================

- :doc:`api-resources`
- :doc:`handling-webhooks`
