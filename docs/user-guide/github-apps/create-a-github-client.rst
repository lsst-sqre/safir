.. currentmodule:: safir.github

############################################
Creating clients with GitHubAppClientFactory
############################################

Gidgethub_ is the recommended library for building GitHub integrations with Safir applications.
To create a Gidgethub client for a GitHub App, Safir provides the `safir.github.GitHubAppClientFactory` class.

.. note::

   GitHub provides multiple way of building integrations, each with slightly different capabilities and authentication flows.
   The `GitHubAppClientFactory` is designed to work with `GitHub Apps <https://docs.github.com/en/apps/creating-github-apps/setting-up-a-github-app>`__, which are the recommended way of building integrations.
   GitHub Apps are specifically installed into an organization or user account, and can be granted access to specific repositories.

   Another common way of building an integration is as an OAuth app (particularly before the introduction of GitHub Apps).
   OAuth app integrations are still useful if your app needs to access a user's GitHub account (such as to provide a GitHub login for your application).
   However, it is not generally recommended since it requires users to grant your app access to their account.

   A third way of building a GitHub integration is to authenticate as a user with a personal access token (usually for a bot account).
   GitHub Apps generally replace this use case for all but the simplest integrations.
   Note in particular that a GitHub App can be `authenticated on behalf of a user <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user>`__.

   For a comparison of the different ways of building integrations, see `GitHub's documentation <https://docs.github.com/en/apps/creating-github-apps/setting-up-a-github-app/about-creating-github-apps>`__.

Setting up the factory
======================

The `GitHubAppClientFactory` requires information about the GitHub App, which you will normally include in your application's configuration, and an instance of `httpx.AsyncClient`, which your application will typically create with the `~safir.dependencies.http_client.http_client_dependency` dependency (see :doc:`../http-client`).
For information about creating a GitHub App, retrieving its App ID and generating a private key, see `GitHub's documentation <https://docs.github.com/en/apps/creating-github-apps/setting-up-a-github-app/creating-a-github-app>`__.

.. code-block:: python

   from pydantic import BaseSettings, Field, SecretStr

   from safir.github import GitHubAppClientFactory


   class Config(BaseSettings):
       """Application configuration showing common configurations needed for
       GitHub App functionality.
       """

       github_app_id: str = Field(env="GITHUB_APP_ID")

       github_webhook_secret: SecretStr = Field(env="GITHUB_WEBHOOK_SECRET")

       github_app_private_key: SecretStr = Field(env="GITHUB_APP_PRIVATE_KEY")


   config = Config()

   github_client_factory = GitHubAppClientFactory(
       app_id=config.github_app_id,
       private_key=config.github_app_private_key.get_secret_value(),
       name="lsst-sqre/example",
       http_client=http_client,  # from http_client dependency
   )

.. tip::

   The ``name`` parameter is the name of your GitHub App.
   It is used to generate the ``User-Agent`` header for requests made by the client.
   There isn't a hard-and-fast rule for what to use here, but it is recommended to use the name of the repository your app is built from (like ``lsst-sqre/example``).

Authenticating as the app
=========================

Your app can authenticate to GitHub in two modes: as the *app itself*, or as an *installation* of the app.
Authenticating as the GitHub App enables your app to access information about the app itself, such as its installations.

.. code-block:: python

   app_client = github_client_factory.create_app_client()

Authenticating as the app installation
======================================

To authenticate as an installation of the app, you need to know the installation ID.
Dependening on the scenario, there are multiple ways of getting the installation ID.

In a webhook handler
--------------------

If your app recieves a webhook from GitHub, the installation ID will be included in the payload (as the ``installation.id`` field, see the `~safir.github.webhooks.GitHubAppInstallationModel`).

.. code-block:: python

   installation_client = (
       await github_client_factory.create_installation_client(
           installation_id=webhook_data.installation.id,
       )
   )

For a known repository
----------------------

If the repository is known to your app (through configuration, a database, an API request, etc.), you can use the `GitHubAppClientFactory.create_installation_client_for_repo` method.
This method gets the installation ID for you:

.. code-block:: python

   installation_client = (
       await github_client_factory.create_installation_client_for_repo(
           owner="lsst-sqre",
           repo="example",
       )
   )

Using the Gidgethub client
==========================

Once you have an authenticated Gidgethub_ client (an instance of `gidgethub.httpx.GitHubAPI`), you can use it to make requests to the GitHub API using GitHub REST API endpoints.
Where possible, you can also parse the response data into Pydantic models (see :doc:`api-resources`):

.. code-block:: python

   from safir.github.models import GitHubRepositoryModel

   response = await installation_client.getitem(
       "/repos/{owner}/{repo}/",
       url_vars={"owner": "lsst-sqre", "repo": "example"},
   )
   repository = GitHubRepositoryModel.parse_obj(response)

For more information on using Gidgethub, see the `Gidgethub documentation <https://gidgethub.readthedocs.io/en/latest/>`__.

Related documentation
=====================

- :doc:`api-resources`
- :doc:`handling-webhooks`
