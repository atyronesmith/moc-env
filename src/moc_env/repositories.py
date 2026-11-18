"""Canonical repository inventory and status-read request shape."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .github import GitHubClient

OAC_INFRA_REPOSITORY = "CCI-MOC/oac-infra"
OAC_APPS_REPOSITORY = "CCI-MOC/oac-apps"
MOC_ISSUES_REPOSITORY = "CCI-MOC/MOC-issues"
MOC_KEYCLOAK_REPOSITORY = "CCI-MOC/moc-keycloak"
EVERPURE_REPOSITORY = "CCI-MOC/everpure-moc"
MOC_AWS_REPOSITORY = "CCI-MOC/moc-aws"
MOC_DNS_REPOSITORY = "CCI-MOC/moc-dns"
ANSIBLE_SWITCHES_REPOSITORY = "CCI-MOC/ansible-switches"

# The status reader locates configuration through a recursive tree for these
# repositories, so each one costs a commit lookup and a tree request.
STATUS_TREE_REPOSITORIES = (
    OAC_INFRA_REPOSITORY,
    OAC_APPS_REPOSITORY,
    MOC_DNS_REPOSITORY,
)

# These readers use fixed paths. They resolve the commit and download files
# from raw.githubusercontent.com, which does not consume the GitHub API quota.
STATUS_FILE_REPOSITORIES = (
    MOC_KEYCLOAK_REPOSITORY,
    EVERPURE_REPOSITORY,
    MOC_AWS_REPOSITORY,
    ANSIBLE_SWITCHES_REPOSITORY,
)


def status_request_urls(
    client: GitHubClient, issue_number: int | None = None
) -> list[str]:
    """List the REST URLs a cold status run will count against quota."""

    urls = [
        url
        for repository in STATUS_TREE_REPOSITORIES
        for url in client.snapshot_request_urls(repository, include_tree=True)
    ]
    urls.extend(
        url
        for repository in STATUS_FILE_REPOSITORIES
        for url in client.snapshot_request_urls(repository, include_tree=False)
    )
    if issue_number is not None:
        urls.extend(
            client.snapshot_request_urls(
                MOC_ISSUES_REPOSITORY, include_tree=False
            )
        )
        urls.append(
            f"{client.base_url}/repos/{MOC_ISSUES_REPOSITORY}"
            f"/issues/{issue_number}"
        )
    return urls
