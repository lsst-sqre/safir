"""Tests for the `safir.github.webhooks` module."""

from __future__ import annotations

from pathlib import Path

from safir.github.models import (
    GitHubCheckRunStatus,
    GitHubCheckSuiteConclusion,
    GitHubCheckSuiteStatus,
)
from safir.github.webhooks import (
    GitHubAppInstallationEventAction,
    GitHubAppInstallationEventModel,
    GitHubAppInstallationRepositoriesEventModel,
    GitHubCheckRunEventAction,
    GitHubCheckRunEventModel,
    GitHubCheckSuiteEventModel,
    GitHubPullRequestEventAction,
    GitHubPullRequestEventModel,
    GitHubPushEventModel,
)


def read_webhook_data(filename: str) -> str:
    return (
        Path(__file__).parent.joinpath("data/webhooks", filename).read_text()
    )


def test_push_event() -> None:
    """Test parsing a push event webhook payload."""
    data = GitHubPushEventModel.model_validate_json(
        read_webhook_data("push_event.json")
    )

    assert data.ref == "refs/tags/simple-tag"
    assert data.repository.name == "Hello-World"


def test_installation_event() -> None:
    """Test parsing an installation event webhook payload."""
    data = GitHubAppInstallationEventModel.model_validate_json(
        read_webhook_data("installation.json")
    )

    assert data.action == GitHubAppInstallationEventAction.deleted
    assert data.repositories[0].name == "Hello-World"
    assert data.repositories[0].owner_name == "octocat"


def test_installation_repositories_event() -> None:
    """Test parsing an installation_repositories event webhook payload."""
    data = GitHubAppInstallationRepositoriesEventModel.model_validate_json(
        read_webhook_data("installation_repositories.json")
    )

    assert data.action == "added"
    assert data.repositories_added[0].name == "Space"
    assert data.repositories_added[0].owner_name == "Codertocat"


def test_pull_request_event() -> None:
    """Test parsing a pull_request event webhook payload."""
    data = GitHubPullRequestEventModel.model_validate_json(
        read_webhook_data("pull_request_event.json")
    )

    assert data.number == 2
    assert data.action == GitHubPullRequestEventAction.opened
    assert data.pull_request.number == 2
    assert data.pull_request.title == "Update the README with new information."
    expected_sha = "ec26c3e57ca3a959ca5aad62de7213c562f8c821"
    assert data.pull_request.head.sha == expected_sha


def test_check_suite_completed_event() -> None:
    """Test parsing a check_suite completed event webhook payload."""
    data = GitHubCheckSuiteEventModel.model_validate_json(
        read_webhook_data("check_suite_completed.json")
    )

    assert data.action == "completed"
    assert data.check_suite.id == 118578147
    assert data.check_suite.head_branch == "changes"
    assert data.check_suite.head_sha == (
        "ec26c3e57ca3a959ca5aad62de7213c562f8c821"
    )
    assert data.check_suite.status == GitHubCheckSuiteStatus.completed
    assert data.check_suite.conclusion == GitHubCheckSuiteConclusion.success


def test_check_run_created_event() -> None:
    """Test parsing a check_run created event webhook payload."""
    data = GitHubCheckRunEventModel.model_validate_json(
        read_webhook_data("check_run_created.json")
    )

    assert data.action == GitHubCheckRunEventAction.created
    assert data.check_run.id == 128620228
    assert data.check_run.external_id == ""
    assert str(data.check_run.url) == (
        "https://api.github.com/repos/Codertocat/Hello-World"
        "/check-runs/128620228"
    )
    assert str(data.check_run.html_url) == (
        "https://github.com/Codertocat/Hello-World/runs/128620228"
    )
    assert data.check_run.status == GitHubCheckRunStatus.queued
    assert data.check_run.check_suite.id == 118578147
