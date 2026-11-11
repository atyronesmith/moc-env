"""Configuration-state checks across CCI-MOC repositories."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import yaml

from .github import GitHubClient, github_url
from .model import CheckResult, Environment, StatusReport

ORG = "CCI-MOC"
KNOWN_ISSUES = {"bu-ist-demo": 666}


def _flatten_host(group: dict[str, Any], inherited: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    values = dict(inherited or {})
    values.update(group.get("vars", {}))
    hosts: list[dict[str, Any]] = []

    for name, details in group.get("hosts", {}).items():
        if not isinstance(details, dict):
            continue
        host = {"name": name, **values, **details}
        hosts.append(host)

    for child in group.get("children", {}).values():
        if isinstance(child, dict):
            hosts.extend(_flatten_host(child, values))
    return hosts


def _find_cluster_group(node: Any, cluster: str) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    variables = node.get("vars")
    if isinstance(variables, dict) and variables.get("cluster") == cluster:
        return node
    for child in node.get("children", {}).values():
        found = _find_cluster_group(child, cluster)
        if found is not None:
            return found
    return None


def _host_summary(hosts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for host in hosts:
        summary.append(
            {
                "name": host.get("name"),
                "node_name": host.get("node_name"),
                "bmc_addr": host.get("bmc_addr"),
                "boot_image_url": host.get("boot_image_url"),
            }
        )
    return summary


def _boot_image_state(url: str | None, cluster: str) -> str:
    if not url:
        return "missing"
    if url.endswith("discovery.iso"):
        return "partial"
    if cluster in url:
        return "declared_in_main"
    return "partial"


def _state_from_paths(paths: set[str], exact: str | None = None, prefix: str | None = None) -> tuple[str, list[str]]:
    if exact is not None:
        found = sorted(path for path in paths if path == exact)
    elif prefix is not None:
        found = sorted(path for path in paths if path.startswith(prefix))
    else:
        found = []
    return ("declared_in_main" if found else "missing"), found


class StatusChecker:
    """Build a configuration-state report from public GitHub data."""

    def __init__(self, client: GitHubClient, include_prs: bool = True) -> None:
        self.client = client
        self.include_prs = include_prs

    def run(self, environment: Environment) -> StatusReport:
        checks: list[CheckResult] = []
        if environment.issue_number is not None:
            checks.extend(self._issue_checks(environment))
        checks.extend(self._infra_checks(environment))
        checks.extend(self._keycloak_checks(environment))
        checks.extend(self._apps_checks(environment))

        overall = self._overall_state(checks)
        return StatusReport(environment=environment, checks=checks, overall_state=overall)

    def _issue_checks(self, environment: Environment) -> list[CheckResult]:
        assert environment.issue_number is not None
        issue = self.client.get_json(
            f"/repos/{ORG}/MOC-issues/issues/{environment.issue_number}"
        )
        state = "requested" if issue.get("state") == "open" else "missing"
        return [
            CheckResult(
                stage="Request",
                check="MOC issue",
                repository=f"{ORG}/MOC-issues",
                path=f"issues/{environment.issue_number}",
                ref="main",
                state=state,
                expected="Open issue recording the environment request",
                actual=issue.get("state"),
                evidence={"title": issue.get("title"), "url": issue.get("html_url")},
                url=issue.get("html_url"),
            )
        ]

    def _infra_checks(self, environment: Environment) -> list[CheckResult]:
        repository = f"{ORG}/oac-infra"
        tree = self.client.get_tree(repository)
        inventory_path = "infra/inventory/00hosts.yaml"
        hub_inventory_path = "hub-images/inventory.yml"
        vars_path = f"hub-images/group_vars/{environment.infra_cluster}/vars.yml"
        results: list[CheckResult] = []

        inventory_text = (
            self.client.get_file(repository, inventory_path)
            if inventory_path in tree
            else None
        )
        inventory = yaml.safe_load(inventory_text) if inventory_text else None

        for cluster in (environment.infra_cluster, environment.workload_cluster):
            inventory_root = inventory.get("all", inventory) if isinstance(inventory, dict) else inventory
            group = _find_cluster_group(inventory_root, cluster)
            hosts = _flatten_host(group) if group else []
            state = "declared_in_main" if group else ("partial" if inventory else "missing")
            boot_urls = sorted({host.get("boot_image_url") for host in hosts if host.get("boot_image_url")})
            results.append(
                CheckResult(
                    stage="Hardware and inventory",
                    check=f"{cluster} host inventory",
                    repository=repository,
                    path=inventory_path,
                    ref="main",
                    state=state,
                    expected=f"Inventory group for {cluster}",
                    actual={"found": group is not None, "host_count": len(hosts)},
                    evidence={"hosts": _host_summary(hosts)},
                    url=github_url(repository, inventory_path),
                )
            )
            if hosts:
                boot_state = _boot_image_state(boot_urls[0] if len(boot_urls) == 1 else None, cluster)
                results.append(
                    CheckResult(
                        stage="Hardware and inventory",
                        check=f"{cluster} boot image",
                        repository=repository,
                        path=inventory_path,
                        ref="main",
                        state=boot_state,
                        expected=f"Cluster-specific discovery image for {cluster}",
                        actual=boot_urls,
                        evidence={"generic_discovery_iso": "discovery.iso" in boot_urls[0]} if boot_urls else {},
                        url=github_url(repository, inventory_path),
                    )
                )

        hub_inventory_text = (
            self.client.get_file(repository, hub_inventory_path)
            if hub_inventory_path in tree
            else None
        )
        hub_inventory = yaml.safe_load(hub_inventory_text) if hub_inventory_text else {}
        hub_found = environment.infra_cluster in (hub_inventory.get("all", {}).get("children", {}) or {})
        results.append(
            CheckResult(
                stage="Cluster build",
                check="Hub image inventory",
                repository=repository,
                path=hub_inventory_path,
                ref="main",
                state="declared_in_main" if hub_found else ("partial" if hub_inventory else "missing"),
                expected=f"Hub-image inventory entry for {environment.infra_cluster}",
                actual={"found": hub_found},
                evidence={"path_present": hub_inventory_path in tree},
                url=github_url(repository, hub_inventory_path),
            )
        )

        vars_text = self.client.get_file(repository, vars_path) if vars_path in tree else None
        values = yaml.safe_load(vars_text) if vars_text else {}
        expected_fields = [
            "cluster_domain_name",
            "base_domain",
            "machine_network",
            "api_ip",
            "ingress_ip",
            "dns_ip",
        ]
        present_fields = [field for field in expected_fields if values.get(field) is not None]
        state = (
            "declared_in_main"
            if vars_path in tree and len(present_fields) == len(expected_fields)
            else "partial"
            if vars_path in tree
            else "missing"
        )
        results.append(
            CheckResult(
                stage="Cluster build",
                check="Hub image variables",
                repository=repository,
                path=vars_path,
                ref="main",
                state=state,
                expected=expected_fields,
                actual=present_fields,
                evidence={
                    "path_present": vars_path in tree,
                    "values": {
                        key: values.get(key)
                        for key in expected_fields
                        if values.get(key) is not None
                    },
                },
                url=github_url(repository, vars_path),
            )
        )
        return results

    def _keycloak_checks(self, environment: Environment) -> list[CheckResult]:
        repository = f"{ORG}/moc-keycloak"
        path = "main.tf"
        text = self.client.get_file(repository, path)
        expected = {
            "client": environment.infra_cluster,
            "redirect_uri": (
                f"openshift_redirect_uri = \"https://oauth-openshift.apps."
                f"{environment.domain}/oauth2callback/mocsso\""
            ),
            "secret_name": f'"cluster/{environment.infra_cluster}/keycloak-oidc"',
        }
        present = {name: value in text for name, value in expected.items()}
        state = (
            "declared_in_main"
            if all(present.values())
            else "partial"
            if any(present.values())
            else "missing"
        )
        return [
            CheckResult(
                stage="Identity",
                check="Infra OIDC client",
                repository=repository,
                path=path,
                ref="main",
                state=state,
                expected=list(expected),
                actual=[name for name, found in present.items() if found],
                evidence=present,
                url=github_url(repository, path),
            )
        ]

    def _apps_checks(self, environment: Environment) -> list[CheckResult]:
        repository = f"{ORG}/oac-apps"
        tree = self.client.get_tree(repository)
        infra_defaults = f"hosted-clusters/{environment.infra_cluster}/values.yaml"
        hub_values_prefix = f"values/{environment.infra_cluster}/"
        local_prefix = f"values/{environment.infra_cluster}/local-cluster/"
        apps_prefix = f"apps/{environment.infra_cluster}/"
        workload_values = (
            f"hosted-clusters/{environment.infra_cluster}/"
            f"{environment.workload_cluster}/values.yaml"
        )
        workload_prefix = (
            f"values/{environment.infra_cluster}/{environment.workload_cluster}/"
        )

        path_checks = [
            ("Infra hosted-cluster defaults", infra_defaults, None),
            ("Hub-wide component values", None, hub_values_prefix),
            ("Infra local-cluster values", None, local_prefix),
            ("Infra ArgoCD applications", None, apps_prefix),
            ("Workload hosted-cluster values", workload_values, None),
            ("Workload component values", None, workload_prefix),
        ]
        results: list[CheckResult] = []
        for label, exact, prefix in path_checks:
            state, found = _state_from_paths(set(tree), exact=exact, prefix=prefix)
            if label == "Hub-wide component values":
                found = [
                    path
                    for path in found
                    if not path.startswith(local_prefix)
                    and not path.startswith(workload_prefix)
                ]
                state = "declared_in_main" if found else "missing"
            results.append(
                CheckResult(
                    stage="GitOps configuration",
                    check=label,
                    repository=repository,
                    path=exact or (prefix.rstrip("/") + "/"),
                    ref="main",
                    state=state,
                    expected="Present in merged main",
                    actual={"matched_paths": found},
                    evidence={"path_count": len(found)},
                    url=github_url(repository, exact or prefix.rstrip("/") + "/"),
                )
            )

        if not self.include_prs:
            return results

        pull_requests = []
        for pull in self.client.pulls(repository):
            searchable = " ".join(
                [
                    str(pull.get("title") or ""),
                    str(pull.get("body") or ""),
                    str(pull.get("head", {}).get("ref") or ""),
                ]
            )
            if any(term in searchable for term in (environment.name, environment.infra_cluster, environment.workload_cluster)):
                files = list(self.client.pr_files(repository, pull["number"]))
                pull_requests.append({"pull_request": pull, "files": files})

        if not pull_requests:
            results.append(
                CheckResult(
                    stage="GitOps configuration",
                    check="Relevant pull requests",
                    repository=repository,
                    path="pulls",
                    ref="all",
                    state="missing",
                    expected="PR referencing the environment",
                    actual={"matching_pr_count": 0},
                    evidence={},
                )
            )
            return results

        open_prs = [item for item in pull_requests if item["pull_request"].get("state") == "open"]
        merged_prs = [item for item in pull_requests if item["pull_request"].get("merged_at")]
        state = "pr_open" if open_prs else "pr_merged"
        evidence = []
        for item in pull_requests:
            pull = item["pull_request"]
            evidence.append(
                {
                    "number": pull["number"],
                    "title": pull.get("title"),
                    "state": pull.get("state"),
                    "merged": bool(pull.get("merged_at")),
                    "head_sha": pull.get("head", {}).get("sha"),
                    "html_url": pull.get("html_url"),
                    "changed_files": [file.get("filename") for file in item["files"]],
                }
            )
        results.append(
            CheckResult(
                stage="GitOps configuration",
                check="Relevant pull requests",
                repository=repository,
                path="pulls",
                ref="all",
                state=state,
                expected="No open PRs; relevant changes merged into main",
                actual={
                    "matching_pr_count": len(pull_requests),
                    "open_count": len(open_prs),
                    "merged_count": len(merged_prs),
                },
                evidence={"pull_requests": evidence},
            )
        )
        return results

    @staticmethod
    def _overall_state(checks: list[CheckResult]) -> str:
        states = {check.state for check in checks}
        if "pr_open" in states:
            return "CONFIGURATION IN PROGRESS"
        if states and states.issubset({"declared_in_main", "requested", "pr_merged"}):
            return "DECLARED IN MAIN"
        if "declared_in_main" in states or "pr_merged" in states:
            return "PARTIALLY CONFIGURED"
        return "NOT CONFIGURED"
