##########################
GitHub API resource models
##########################

The `safir.github.models` module contains Pydantic models for GitHub API resources.
This page lists the GitHub endpoints that correspond to models included in Safir.
Note that :doc:`webhooks <webhook-models>` often include data modelled by `safir.github.models` as well (see :doc:`webhook-models`).

.. note::

   The `safir.github.models` module is not exhaustive.
   Only models used by Safir applications are included.
   To expand the coverage, you can contribute them to Safir.

   As well, the models are not guaranteed to be complete.
   Fields not relevant to Safir applications may not be included (Pydantic ignores undeclared fields when it parses responses from GitHub).
   You can include additional fields in your application either by subclassing these models or by contributing them to Safir.

Response resources
==================

.. list-table::
   :header-rows: 1

   * - Endpoint
     - Model
   * - `GET /repos/{owner}/{repo}/ <https://docs.github.com/en/rest/repos/repos#get-a-repository>`__
     - `~safir.github.models.GitHubRepositoryModel`
   * - `GET /repos/{owner}/{repo}/branches/{branch} <https://docs.github.com/en/rest/branches/branches#get-a-branch>`__
     - `~safir.github.models.GitHubBranchModel`
   * - `GET /repos/{owner}/{repo}/check-runs/{check_run_id} <https://docs.github.com/en/rest/checks/runs#get-a-check-run>`__
     - `~safir.github.models.GitHubCheckRunModel`
   * - `GET /repos/{owner}/{repo}/check-suites/{check_suite_id} <https://docs.github.com/en/rest/checks/suites#get-a-check-suite>`__
     - `~safir.github.models.GitHubCheckSuiteModel`
   * - `GET /repos/{owner}/{repo}/git/blobs/{file_sha} <https://docs.github.com/en/rest/git/blobs#get-a-blob>`__
     - `~safir.github.models.GitHubBlobModel`
   * - `GET /repos/{owner}/{repo}/pulls/{pull_number} <https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request>`__
     - `~safir.github.models.GitHubPullRequestModel`

Related documentation
=====================

- :doc:`webhook-models`
- :doc:`create-a-github-client`
