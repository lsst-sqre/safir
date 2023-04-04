"""Pydantic models for GitHub webhook payloads."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .models import (
    GitHubCheckRunModel,
    GitHubCheckSuiteModel,
    GitHubPullRequestModel,
    GitHubRepositoryModel,
)

__all__ = [
    "GitHubAppInstallationModel",
    "GitHubPushEventModel",
    "GitHubAppInstallationEventRepoModel",
    "GitHubAppInstallationEventAction",
    "GitHubAppInstallationEventModel",
    "GitHubAppInstallationRepositoriesEventAction",
    "GitHubAppInstallationRepositoriesEventModel",
    "GitHubPullRequestEventAction",
    "GitHubPullRequestEventModel",
    "GitHubCheckSuiteEventAction",
    "GitHubCheckSuiteEventModel",
    "GitHubCheckRunEventAction",
    "GitHubCheckRunEventModel",
]


class GitHubAppInstallationModel(BaseModel):
    """A Pydantic model for the ``installation`` field found in webhook
    payloads for GitHub Apps.
    """

    id: str = Field(description="The installation ID.")


class GitHubPushEventModel(BaseModel):
    """A Pydantic model for the ``push`` event webhook when a commit or
    tag is pushed.

    https://docs.github.com/webhooks-and-events/webhooks/webhook-events-and-payloads#push
    """

    repository: GitHubRepositoryModel = Field(
        description="The repository that was pushed to."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )

    ref: str = Field(
        description=(
            "The full git ref that was pushed. Example: refs/heads/main or "
            "refs/tags/v3.14.1."
        ),
        example="refs/heads/main",
    )

    before: str = Field(
        description="The SHA of the most recent commit on ref before the push."
    )

    after: str = Field(
        description="The SHA of the most recent commit on ref after the push."
    )


class GitHubAppInstallationEventRepoModel(BaseModel):
    """A pydantic model for repository objects used by
    `GitHubAppInstallationRepositoriesEventModel`.

    https://docs.github.com/webhooks-and-events/webhooks/webhook-events-and-payloads#installation
    """

    name: str = Field(
        description="The name of the repository, e.g. 'times-square'."
    )

    full_name: str = Field(
        description=(
            "The full name of the repository, e.g. 'lsst-sqre/times-square'."
        )
    )

    @property
    def owner_name(self) -> str:
        """The name of the repository owner."""
        return self.full_name.split("/")[0]


class GitHubAppInstallationEventAction(str, Enum):
    """The action performed on an GitHub App ``installation`` webhook
    (`GitHubAppInstallationEventModel`).
    """

    #: Someone installed a GitHub App on a user or organization account.
    created = "created"

    #: Someone uninstalled a GitHub App on a user or organization account.
    deleted = "deleted"

    #: Someone granted new permissions to a GitHub App.
    new_permissions_accepted = "new_permissions_accepted"

    #: Someone blocked access by a GitHub App to their user or org account.
    suspend = "suspend"

    #: Someone unblocked access by a GitHub App to their user or org account.
    unsuspend = "unsuspend"


class GitHubAppInstallationEventModel(BaseModel):
    """A Pydantic model for an ``installation`` webhook.

    https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#installation
    """

    action: GitHubAppInstallationEventAction = Field(
        description="Action performed."
    )

    repositories: list[GitHubAppInstallationEventRepoModel] = Field(
        description="Repositories accessible to this installation."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )


class GitHubAppInstallationRepositoriesEventAction(str, Enum):
    """The action performed on a GitHub App ``installation_repositories``
    webhook (`GitHubAppInstallationRepositoriesEventModel`).
    """

    #: Someone added a repository to an installation.
    added = "added"

    #: Someone removed a repository from an installation.
    removed = "removed"


class GitHubAppInstallationRepositoriesEventModel(BaseModel):
    """A Pydantic model for a ``installation_repositories`` webhook.

    https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#installation_repositories
    """

    action: GitHubAppInstallationRepositoriesEventAction = Field(
        description="Action performed on the installation."
    )

    repositories_added: list[GitHubAppInstallationEventRepoModel] = Field(
        description="Repositories added to the installation."
    )

    repositories_removed: list[GitHubAppInstallationEventRepoModel] = Field(
        description="Repositories removed from the installation."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )


class GitHubPullRequestEventAction(str, Enum):
    """The action performed on a GitHub ``pull_request`` webhook
    (`GitHubPullRequestEventModel`).
    """

    #: A pull request was assigned to a user.
    assigned = "assigned"

    #: Auto merge was disabled for a pull request.
    auto_merge_disabled = "auto_merge_disabled"

    #: Auto merge was enabled for a pull request.
    auto_merge_enabled = "auto_merge_enabled"

    #: A pull request was closed.
    closed = "closed"

    #: A pull request was converted to a draft.
    converted_to_draft = "converted_to_draft"

    #: A pull request was removed from a milestone.
    demilestoned = "demilestoned"

    #: A pull request was removed from the merge queue.
    dequeued = "dequeued"

    #: The title or body of a pull request was edited.
    edited = "edited"

    #: A label was added to a pull request.
    labeled = "labeled"

    #: Conversation on a pull request was locked.
    locked = "locked"

    #: A pull request was added to a milestone.
    milestoned = "milestoned"

    #: A pull request was created.
    opened = "opened"

    #: A draft pull request was marked as ready for review.
    ready_for_review = "ready_for_review"

    #: A pull request was reopened.
    reopened = "reopened"

    #: A request for review by a person or team was removed from a pull
    #: request.
    review_request_removed = "review_request_removed"

    #: Review by a person or team was requested for a pull request.
    review_requested = "review_requested"

    #: A pull request's head branch was updated. For example, the head branch
    #: was updated from the base branch or new commits were pushed to the head
    #: branch.
    synchronize = "synchronize"

    #: A user was unassigned from a pull request.
    unassigned = "unassigned"

    #: A label was removed from a pull request.
    unlabeled = "unlabeled"

    #: Conversation on a pull request was unlocked.
    unlocked = "unlocked"


class GitHubPullRequestEventModel(BaseModel):
    """A Pydantic model for a ``pull_request`` webhook.

    https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#pull_request
    """

    repository: GitHubRepositoryModel = Field(
        description="The repository that the pull request was opened against."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )

    action: GitHubPullRequestEventAction = Field(
        description="The action that was performed.",
    )

    number: int = Field(description="Pull request number")

    pull_request: GitHubPullRequestModel = Field(
        description="Information about the pull request."
    )


class GitHubCheckSuiteEventAction(str, Enum):
    """The action performed in a GitHub ``check_suite`` webhook
    (`GitHubCheckSuiteEventModel`).
    """

    #: All check runs in a check suite have completed, and a conclusion is
    #: available.
    completed = "completed"

    #: Someone requested to run a check suite.
    requested = "requested"

    #: Someone requested to re-run the check runs in a check suite.
    rerequested = "rerequested"


class GitHubCheckSuiteEventModel(BaseModel):
    """A Pydantic model for the ``check_suite`` webhook payload.

    https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#check_suite
    """

    action: GitHubCheckSuiteEventAction = Field(
        description="The action performed.",
    )

    check_suite: GitHubCheckSuiteModel = Field(
        description="Information about the check suite."
    )

    repository: GitHubRepositoryModel = Field(
        description="The repository that the check suite was run against."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )


class GitHubCheckRunEventAction(str, Enum):
    """The action performed in a GitHub ``check_run`` webhook
    (`GitHubCheckRunEventModel`).
    """

    #: A check run was completed and a conclusion is available.
    completed = "completed"

    #: A new check run was created.
    created = "created"

    #: A check run completed, and someone requested a followup action that
    #: your app provides.
    requested_action = "requested_action"

    #: Someone requested to re-run a check run.
    rerequested = "rerequested"


class GitHubCheckRunEventModel(BaseModel):
    """A Pydantic model for the ``check_run`` webhook payload.

    https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#check_run
    """

    action: GitHubCheckRunEventAction = Field(
        description="The action that was performed.",
    )

    repository: GitHubRepositoryModel = Field(
        description="The repository that the check run was run against."
    )

    installation: GitHubAppInstallationModel = Field(
        description="Information about the GitHub App installation."
    )

    check_run: GitHubCheckRunModel = Field(
        description="Information about the check run."
    )
