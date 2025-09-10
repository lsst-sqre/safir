"""Pydantic models for GitHub v3 REST API resources."""

from __future__ import annotations

from base64 import b64decode
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl

__all__ = [
    "GitHubBlobModel",
    "GitHubBranchCommitModel",
    "GitHubBranchModel",
    "GitHubCheckRunAnnotationLevel",
    "GitHubCheckRunConclusion",
    "GitHubCheckRunModel",
    "GitHubCheckRunOutput",
    "GitHubCheckRunPrInfoModel",
    "GitHubCheckRunStatus",
    "GitHubCheckSuiteConclusion",
    "GitHubCheckSuiteId",
    "GitHubCheckSuiteModel",
    "GitHubCheckSuiteStatus",
    "GitHubPullRequestHeadModel",
    "GitHubPullRequestModel",
    "GitHubPullState",
    "GitHubRepoOwnerModel",
    "GitHubRepositoryModel",
    "GitHubUserModel",
]


class GitHubRepoOwnerModel(BaseModel):
    """A Pydantic model for the ``owner`` field found in repository objects.

    https://docs.github.com/en/rest/repos/repos#get-a-repository
    """

    login: str = Field(
        title="Login name",
        description=(
            "Login name of the owner (either a user or an organization)."
        ),
        examples=["lsst-sqre"],
    )


class GitHubUserModel(BaseModel):
    """A Pydantic model for the ``user`` field found in GitHub API resources.

    This contains brief (public) info about a user.
    """

    login: str = Field(title="Login name", description="GitHub username.")

    html_url: HttpUrl = Field(
        title="Profile URL", description="Homepage for the user on GitHub."
    )

    url: HttpUrl = Field(
        title="API URL",
        description="URL for the user's resource in the GitHub API.",
    )

    avatar_url: HttpUrl = Field(
        title="Avatar image URL", description="URL to the user's avatar."
    )


class GitHubRepositoryModel(BaseModel):
    """A Pydantic model for the ``repository`` field, often found in webhook
    payloads.

    https://docs.github.com/en/rest/repos/repos#get-a-repository
    """

    name: str = Field(
        title="Repository name",
        description="Excludes owner prefix.",
        examples=["times-square-demo"],
    )

    full_name: str = Field(
        title="Full name",
        description=(
            "Full name, including owner prefix "
            "(e.g. ``lsst-sqre/times-square-demo``).)"
        ),
        examples=["lsst-sqre/times-square-demo"],
    )

    owner: GitHubRepoOwnerModel = Field(description="The repository's owner.")

    default_branch: str = Field(
        description="The default branch (e.g. main).", examples=["main"]
    )

    html_url: HttpUrl = Field(
        description="URL of the repository for browsers.",
        examples=["https://github.com/lsst-sqre/times-square-demo"],
    )

    branches_url: str = Field(
        description="URI template for the repo's branches endpoint.",
        examples=[
            "https://github.com/lsst-sqre/times-square-demo/branches{/branch}"
        ],
    )

    contents_url: str = Field(
        description="URI template for the contents endpoint.",
        examples=[
            "https://github.com/lsst-sqre/times-square-demo/contents/{+path}"
        ],
    )

    trees_url: str = Field(
        description="URI template for the Git tree API.",
        examples=[
            "https://github.com/lsst-sqre/times-square-demo/git/trees{/sha}"
        ],
    )

    blobs_url: str = Field(
        description="URI template for the Git blobs API.",
        examples=[
            "https://github.com/lsst-sqre/times-square-demo/git/blobs{/sha}"
        ],
    )


class GitHubPullState(StrEnum):
    """The state of a GitHub pull request (PR).

    https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    """

    open = "open"
    """The PR is open."""

    closed = "closed"
    """The PR is closed."""


class GitHubPullRequestHeadModel(BaseModel):
    """A Pydantic model for the last commit to the head branch of a PR."""

    sha: str = Field(description="Last commit SHA of the PR head branch.")


class GitHubPullRequestModel(BaseModel):
    """A Pydantic model for a GitHub Pull Request.

    This is also the ``pull_request`` field inside the
    `~safir.github.webhooks.GitHubPullRequestEventModel`.

    https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    """

    html_url: HttpUrl = Field(description="Web URL of the PR.")

    number: int = Field(description="Pull request number.")

    title: str = Field(description="Title of the PR.")

    state: GitHubPullState = Field(
        description="Whether the PR is opened or closed."
    )

    draft: bool = Field(description="True if the PR is a draft.")

    merged: bool = Field(description="True if the PR is merged.")

    user: GitHubUserModel = Field(description="The user that opened the PR.")

    head: GitHubPullRequestHeadModel = Field(
        description="The last commit to the head branch of the PR."
    )


class GitHubBranchCommitModel(BaseModel):
    """A Pydantic model for the commit field found in `GitHubBranchModel`."""

    sha: str = Field(description="Git commit SHA.")

    url: HttpUrl = Field(description="URL for commit resource.")


class GitHubBranchModel(BaseModel):
    """A Pydantic model for a GitHub branch.

    https://docs.github.com/en/rest/branches/branches#get-a-branch
    """

    name: str = Field(description="Branch name (e.g. main)", examples=["main"])

    commit: GitHubBranchCommitModel = Field(description="HEAD commit info.")


class GitHubBlobModel(BaseModel):
    """A Pydantic model for a blob, returned by the GitHub blob endpoint.

    See https://docs.github.com/en/rest/git/blobs#get-a-blob
    """

    content: str = Field(
        description=(
            "The blob's encoded content. Use the `decode` method to decode."
        )
    )

    encoding: str = Field(description="Content encoding (typically base64).")

    url: HttpUrl = Field(description="API URL of this resource.")

    sha: str = Field(description="Git SHA of tree object.")

    size: int = Field(description="Size of the content in bytes.")

    def decode(self) -> str:
        """Decode the `content` field.

        Currently supports these encodings:

        - base64

        Returns
        -------
        str
            The decoded content.
        """
        if self.encoding == "base64":
            return b64decode(self.content).decode()
        else:
            raise NotImplementedError(
                f"GitHub blob content encoding {self.encoding} "
                f"is unknown by GitHubBlobModel for url {self.url}"
            )


class GitHubCheckSuiteStatus(StrEnum):
    """The status of a GitHub check suite."""

    queued = "queued"
    """The check suite is queued."""

    in_progress = "in_progress"
    """The check suite is in progress."""

    completed = "completed"
    """The check suite has completed."""


class GitHubCheckSuiteConclusion(StrEnum):
    """The conclusion state of a GitHub check suite."""

    success = "success"
    """The check suite has succeeded."""

    failure = "failure"
    """The check suite has failed."""

    neutral = "neutral"
    """The check suite has a neutral outcome, perhaps because the check was
    skipped.
    """

    cancelled = "cancelled"
    """The check suite was cancelled."""

    timed_out = "timed_out"
    """The check suite timed out."""

    action_required = "action_required"
    """The check suite requires an action to be taken before it can
    continue.
    """

    stale = "stale"
    """The check suite is stale."""


class GitHubCheckSuiteModel(BaseModel):
    """A Pydantic model for the ``check_suite`` field in a ``check_suite``
    webhook (`~safir.github.webhooks.GitHubCheckSuiteEventModel`).
    """

    id: int = Field(description="Identifier for this check run.")

    head_branch: str = Field(
        description="Name of the branch the changes are on.",
    )

    head_sha: str = Field(
        description="The SHA of the most recent commit for this check suite.",
    )

    url: HttpUrl = Field(
        description="GitHub API URL for the check suite resource."
    )

    status: GitHubCheckSuiteStatus = Field(
        description="The status of the check suite."
    )

    conclusion: GitHubCheckSuiteConclusion | None = Field(
        description="The conclusion of the check suite."
    )

    pull_requests: list[GitHubCheckRunPrInfoModel] = Field(
        description="A list of pull requests associated with this check suite."
    )


class GitHubCheckRunStatus(StrEnum):
    """The check run status."""

    queued = "queued"
    """The check run is queued."""

    in_progress = "in_progress"
    """The check run is in progress."""

    completed = "completed"
    """The check run has completed."""


class GitHubCheckRunConclusion(StrEnum):
    """The check run conclusion state."""

    success = "success"
    """The check run has succeeded."""

    failure = "failure"
    """The check run has failed."""

    neutral = "neutral"
    """The check run has a neutral outcome, perhaps because the check was
    skipped.
    """

    cancelled = "cancelled"
    """The check run was cancelled."""

    timed_out = "timed_out"
    """The check run timed out."""

    action_required = "action_required"
    """The check run requires an action to be taken before it can continue."""

    stale = "stale"
    """The check run is stale."""


class GitHubCheckRunAnnotationLevel(StrEnum):
    """The level of a check run output annotation."""

    notice = "notice"
    """A notice annotation."""

    warning = "warning"
    """A warning annotation."""

    failure = "failure"
    """An annotation that indicates a failure."""


class GitHubCheckSuiteId(BaseModel):
    """Brief information about a check suite in the `GitHubCheckRunModel`."""

    id: int = Field(description="Check suite ID")


class GitHubCheckRunOutput(BaseModel):
    """Check run output report."""

    title: str | None = Field(None, description="Title of the report")

    summary: str | None = Field(
        None, description="Summary information (markdown formatted)."
    )

    text: str | None = Field(None, description="Extended report (markdown)")


class GitHubCheckRunPrInfoModel(BaseModel):
    """A Pydantic model of the ``pull_requests[]`` items in a check run
    GitHub API model (`GitHubCheckRunModel`).

    https://docs.github.com/en/rest/checks/runs#get-a-check-run
    """

    url: HttpUrl = Field(description="GitHub API URL for this pull request.")

    number: int = Field(
        description="The number that identifies the pull request."
    )


class GitHubCheckRunModel(BaseModel):
    """A Pydantic model for the "check_run" field in a check_run webhook
    payload (`~safir.github.webhooks.GitHubCheckRunEventModel`).
    """

    id: int = Field(description="Identifier for this check run.")

    external_id: str | None = Field(
        description="Identifier set by the check runner."
    )

    head_sha: str = Field(
        title="Head sha",
        description="The SHA of the most recent commit for this check suite.",
    )

    status: GitHubCheckRunStatus = Field(
        description="Status of the check run."
    )

    conclusion: GitHubCheckRunConclusion | None = Field(
        None, description="Conclusion status, if completed."
    )

    name: str = Field(description="Name of the check run.")

    url: HttpUrl = Field(description="URL of the check run API resource.")

    html_url: HttpUrl = Field(description="URL of the check run webpage.")

    check_suite: GitHubCheckSuiteId = Field(
        description="Brief information about the check suite."
    )

    output: GitHubCheckRunOutput | None = Field(
        None, title="Output", description="Check run output, if available."
    )

    pull_requests: list[GitHubCheckRunPrInfoModel] = Field(
        default_factory=list,
        description="List of pull requests associated with this check run.",
    )
