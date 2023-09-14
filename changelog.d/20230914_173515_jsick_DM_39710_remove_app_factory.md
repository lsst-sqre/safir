### Backwards-incompatible changes

- Remove the `GitHubAppClientFactory.create_app_client` method, which does not work with the Gidgethub API. Instead, the documentation shows how to create a JWT with the `GitHubAppClientFactory` and pass it with requests.
