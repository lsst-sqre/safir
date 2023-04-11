from __future__ import annotations

from typing import Optional

import gidgethub.apps
import httpx
from gidgethub.httpx import GitHubAPI


class GitHubAppClientFactory:
    """Factory for creating GitHub App clients authenticated either as an app
    or as an installation of that app.

    Parameters
    ----------
    id
        The GitHub App ID.
    key
        The GitHub App private key.
    name
        The GitHub App name. This identifies the app in the user agent string,
        and is typically the name of the GitHub repository the app is built
        from (e.g. ``lsst-sqre/times-square``).
    http_client
        The httpx client.
    """

    def __init__(
        self, *, id: str, key: str, name: str, http_client: httpx.AsyncClient
    ) -> None:
        self.app_id = id
        self.app_key = key
        self.app_name = name
        self._http_client = http_client

    def get_app_jwt(self) -> str:
        """Create the GitHub App's JWT based on application configuration.

        This token is for authenticating as the GitHub App itself, as opposed
        to an installation of the app.

        Returns
        -------
        str
            The JWT token.
        """
        return gidgethub.apps.get_jwt(
            app_id=self.app_id, private_key=self.app_key
        )

    def _create_client(
        self, *, oauth_token: Optional[str] = None
    ) -> GitHubAPI:
        return GitHubAPI(
            self._http_client, self.app_name, oauth_token=oauth_token
        )

    def create_anonymous_client(self) -> GitHubAPI:
        """Create an anonymous client.

        Returns
        -------
        gidgethub.httpx.GitHubAPI
            The anonymous client.
        """
        return self._create_client()

    def create_app_client(self) -> GitHubAPI:
        """Create a client authenticated as the GitHub App.

        Returns
        -------
        gidgethub.httpx.GitHubAPI
            The app client.
        """
        return self._create_client(oauth_token=self.get_app_jwt())

    async def create_installation_client(
        self, installation_id: str
    ) -> GitHubAPI:
        """Create a client authenticated as an installation of the GitHub App
        for a specific repository or organization.

        Parameters
        ----------
        installation_id
            The installation ID. This can be retrieved from the
            ``installation.id`` field of a webhook payload or from the
            ``id`` field of the ``GET "/repos/{owner}/{repo}/installation"``
            GitHub endpoint.

        Returns
        -------
        gidgethub.httpx.GitHubAPI
            The installation client.
        """
        anon_client = self.create_anonymous_client()
        token_info = await gidgethub.apps.get_installation_access_token(
            anon_client,
            installation_id=installation_id,
            app_id=self.app_id,
            private_key=self.app_key,
        )
        return self._create_client(oauth_token=token_info["token"])

    async def create_installation_client_for_repo(
        self, owner: str, repo: str
    ) -> GitHubAPI:
        """Create a client authenticated as an installation of the GitHub App
        for a specific repository or organization.

        Parameters
        ----------
        owner
            The owner of the repository.
        repo
            The repository name.

        Returns
        -------
        gidgethub.httpx.GitHubAPI
            The installation client.
        """
        app_jwt = self.get_app_jwt()
        anon_client = self.create_anonymous_client()
        installation_data = await anon_client.getitem(
            "/repos/{owner}/{repo}/installation",
            url_vars={"owner": owner, "repo": repo},
            jwt=app_jwt,
        )
        installation_id = installation_data["id"]
        return await self.create_installation_client(installation_id)
