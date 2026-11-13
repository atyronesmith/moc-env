"""Configuration-state checks across CCI-MOC repositories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import yaml

from .github import GitHubClient, github_url
from .model import CheckResult, Environment, StatusReport
from .observed import (
    AppsObservation,
    InfraObservation,
    IssueObservation,
    KeycloakObservation,
    OAC_INFRA_REPOSITORY,
    inventory_clusters,
    read_environment_observation,
)

ORG = "CCI-MOC"
KNOWN_ISSUES = {"bu-ist-demo": 666}
ProgressCallback = Callable[[str, str, str, str], None]

LOCAL_CLUSTER_COMPONENTS = [
    "acm.yaml",
    "acm-placements.yaml",
    "cert-manager.yaml",
    "cluster-certificates.yaml",
    "cluster-version.yaml",
    "external-dns-operator.yaml",
    "external-secrets.yaml",
    "hcp-config.yaml",
    "keycloak-oauth.yaml",
    "metallb.yaml",
    "openshift-gitops.yaml",
    "portworx.yaml",
    "user-workload-monitoring.yaml",
]


def list_environments(client: GitHubClient) -> list[dict[str, Any]]:
    """List hub and workload clusters supported by the status checker."""

    repository = OAC_INFRA_REPOSITORY
    tree = client.get_tree(repository)
    hub_inventory_path = "hub-images/inventory.yml"
    inventory_path = "infra/inventory/00hosts.yaml"

    hub_text = (
        client.get_file(repository, hub_inventory_path)
        if hub_inventory_path in tree
        else None
    )
    hub_inventory = yaml.safe_load(hub_text) if hub_text else {}
    hub_children = (
        hub_inventory.get("all", {}).get("children", {}) or {}
        if isinstance(hub_inventory, dict)
        else {}
    )
    infra_clusters = sorted(
        cluster
        for cluster in hub_children
        if isinstance(cluster, str) and cluster.endswith("-infra")
    )

    inventory_text = (
        client.get_file(repository, inventory_path)
        if inventory_path in tree
        else None
    )
    inventory = yaml.safe_load(inventory_text) if inventory_text else {}
    inventory_root = inventory.get("all", inventory) if isinstance(inventory, dict) else inventory
    all_clusters = inventory_clusters(inventory_root)

    clusters: list[dict[str, Any]] = []
    for infra_cluster in infra_clusters:
        base_name = infra_cluster[: -len("-infra")]
        workload_clusters = sorted(
            cluster
            for cluster in all_clusters
            if cluster.startswith(f"{base_name}-") and cluster != infra_cluster
        )
        status_command = f"moc-env {base_name}"
        clusters.append(
            {
                "environment": base_name,
                "cluster": infra_cluster,
                "type": "hub",
                "status_command": status_command,
                "source_repository": repository,
                "source_path": hub_inventory_path,
            }
        )
        for workload_cluster in workload_clusters:
            clusters.append(
                {
                    "environment": base_name,
                    "cluster": workload_cluster,
                    "type": "workload",
                    "status_command": status_command,
                    "source_repository": repository,
                    "source_path": inventory_path,
                }
            )
    return clusters


def _boot_image_state(url: str | None, cluster: str) -> str:
    if not url:
        return "missing"
    image_name = url.rsplit("/", 1)[-1]
    if image_name == "discovery.iso":
        return "partial"
    cluster_aliases = [cluster]
    if cluster.startswith("oac-"):
        cluster_aliases.append(cluster.removeprefix("oac-"))
    if any(alias in image_name for alias in cluster_aliases):
        return "declared_in_main"
    return "partial"


class StatusChecker:
    """Build a configuration-state report from public GitHub data."""

    def __init__(
        self,
        client: GitHubClient,
        include_prs: bool = True,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.client = client
        self.include_prs = include_prs
        self.progress = progress

    def _emit_progress(
        self, stage: str, action: str, repository: str, path: str
    ) -> None:
        if self.progress is not None:
            self.progress(stage, action, repository, path)

    def run(self, environment: Environment) -> StatusReport:
        checks: list[CheckResult] = []
        observation = read_environment_observation(
            self.client,
            environment,
            progress=self._emit_progress,
            include_pull_requests=self.include_prs,
        )
        environment = observation.environment
        if observation.issue is not None:
            checks.extend(self._issue_checks(observation.issue))
        infra_checks, environment = self._infra_checks(environment, observation.infra)
        checks.extend(infra_checks)
        checks.extend(self._keycloak_checks(environment, observation.keycloak))
        checks.extend(self._apps_checks(environment, observation.apps))
        return StatusReport(
            environment=environment,
            checks=checks,
            overall_state=self._overall_state(checks),
        )

    def _issue_checks(self, observation: IssueObservation) -> list[CheckResult]:
        repository = f"{ORG}/MOC-issues"
        path = f"issues/{observation.issue_number}"
        issue_state = observation.state.value
        state = "requested" if issue_state == "open" else "missing"
        if state == "requested":
            reason = (
                f"Issue #{observation.issue_number} is open and records the "
                "environment request."
            )
            present = {"issue_state": "open", "title": observation.title.value}
            missing = None
        else:
            reason = (
                f"Issue #{observation.issue_number} is {issue_state}; "
                "it is not an open request."
            )
            present = {"issue_state": issue_state}
            missing = "An open MOC issue"

        return [
            CheckResult(
                stage="Request",
                check="MOC issue",
                repository=repository,
                path=path,
                ref="main",
                state=state,
                expected="Open issue recording the environment request",
                actual=issue_state,
                reason=reason,
                present=present,
                missing=missing,
                evidence={
                    "state": observation.state.to_dict(),
                    "title": observation.title.to_dict(),
                    "url": observation.url.to_dict(),
                },
                url=observation.url.value,
            )
        ]

    def _infra_checks(
        self,
        environment: Environment,
        observation: InfraObservation,
    ) -> tuple[list[CheckResult], Environment]:
        repository = OAC_INFRA_REPOSITORY
        results: list[CheckResult] = []
        inventory_path = observation.inventory_path
        hub_inventory_path = observation.hub_inventory_path
        vars_path = observation.variables_path

        for cluster_observation in observation.clusters.values():
            cluster = cluster_observation.cluster.value
            group = cluster_observation.group_found.value
            hosts = cluster_observation.hosts.value
            boot_urls = cluster_observation.boot_image_urls

            if group:
                state = "declared_in_main"
                reason = f"The inventory contains a {cluster} group with {len(hosts)} hosts."
                present = {"cluster_group": cluster, "host_count": len(hosts)}
                missing = None
            elif observation.inventory_present.value:
                state = "partial"
                reason = (
                    "The inventory file is present in main, but no group has "
                    f"vars.cluster == {cluster!r}."
                )
                present = {"inventory_file": inventory_path}
                missing = {"cluster_group": cluster}
            else:
                state = "missing"
                reason = "The Ansible inventory file is absent from main."
                present = {"inventory_file": None}
                missing = {"inventory_file": inventory_path, "cluster_group": cluster}

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
                    reason=reason,
                    present=present,
                    missing=missing,
                    evidence={"hosts": cluster_observation.host_summaries()},
                    url=github_url(repository, inventory_path),
                )
            )

            if not hosts:
                continue

            selected_url = boot_urls[0] if len(boot_urls) == 1 else None
            boot_state = _boot_image_state(selected_url, cluster)
            if boot_state == "declared_in_main":
                boot_reason = f"The boot image URL is specific to {cluster}."
                boot_present = {"boot_image_url": selected_url}
                boot_missing = None
            elif len(boot_urls) > 1:
                boot_state = "partial"
                boot_reason = (
                    "The host groups declare multiple boot image URLs, so the "
                    "intended image is ambiguous."
                )
                boot_present = {"boot_image_urls": boot_urls}
                boot_missing = {"single_cluster_specific_url": True}
            elif selected_url and selected_url.endswith("discovery.iso"):
                boot_reason = (
                    "A boot image URL is present, but it points to the generic "
                    "discovery.iso rather than a cluster-specific image."
                )
                boot_present = {"boot_image_url": selected_url}
                boot_missing = {
                    "cluster_specific_image": (
                        f"an image name containing {environment.base_name}-workload0"
                        if cluster == environment.workload_cluster
                        else f"an image name containing {environment.infra_cluster}"
                    )
                }
            elif selected_url:
                boot_reason = (
                    "A boot image URL is present, but it does not identify the "
                    "expected cluster by its full name or oac-shortened name."
                )
                boot_present = {"boot_image_url": selected_url}
                boot_missing = {
                    "cluster_name_in_image": [
                        cluster,
                        cluster.removeprefix("oac-"),
                    ]
                }
            else:
                boot_reason = "No boot image URL is inherited by the cluster host group."
                boot_present = {"boot_image_url": None}
                boot_missing = {
                    "cluster_specific_image": f"{cluster}-agent-discovery.iso"
                }

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
                    reason=boot_reason,
                    present=boot_present,
                    missing=boot_missing,
                    evidence={
                        "generic_discovery_iso": bool(
                            boot_urls and boot_urls[0].endswith("discovery.iso")
                        )
                    },
                    url=github_url(repository, inventory_path),
                )
            )

        hub_found = observation.hub_inventory.cluster_key_present.value
        if hub_found:
            hub_state = "declared_in_main"
            hub_reason = (
                f"The hub-image inventory contains the "
                f"all.children.{environment.infra_cluster} key."
            )
            hub_present = {"inventory_key": environment.infra_cluster}
            hub_missing = None
        elif observation.hub_inventory.path_present.value:
            hub_state = "partial"
            hub_reason = (
                "The hub-image inventory is present, but it does not contain "
                f"the all.children.{environment.infra_cluster} key."
            )
            hub_present = {"inventory_file": hub_inventory_path}
            hub_missing = {"inventory_key": environment.infra_cluster}
        else:
            hub_state = "missing"
            hub_reason = "The hub-image inventory file is absent from main."
            hub_present = {"inventory_file": None}
            hub_missing = {"inventory_file": hub_inventory_path}

        results.append(
            CheckResult(
                stage="Cluster build",
                check="Hub image inventory",
                repository=repository,
                path=hub_inventory_path,
                ref="main",
                state=hub_state,
                expected=f"Hub-image inventory entry for {environment.infra_cluster}",
                actual={"found": hub_found},
                reason=hub_reason,
                present=hub_present,
                missing=hub_missing,
                    evidence={
                        "path_present": observation.hub_inventory.path_present.value
                    },
                url=github_url(repository, hub_inventory_path),
            )
        )

        values = observation.hub_variables.values.value
        if isinstance(values, dict) and values.get("cluster_domain_name") and values.get("base_domain"):
            environment = replace(
                environment,
                domain_override=(
                    f"{values['cluster_domain_name']}.{values['base_domain']}"
                ),
            )
        expected_fields = [
            "cluster_domain_name",
            "base_domain",
            "machine_network",
            "api_ip",
            "ingress_ip",
            "dns_ip",
        ]
        present_fields = [
            field for field in expected_fields if values.get(field) is not None
        ]
        missing_fields = [
            field for field in expected_fields if values.get(field) is None
        ]
        if observation.hub_variables.path_present.value and not missing_fields:
            state = "declared_in_main"
            reason = "All required hub-image variables are present in main."
        elif observation.hub_variables.path_present.value:
            state = "partial"
            reason = (
                "The hub-image variable file is present, but required fields are "
                "absent: " + ", ".join(missing_fields) + "."
            )
        else:
            state = "missing"
            reason = "The hub-image variable file is absent from main."

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
                reason=reason,
                present={
                    "fields": present_fields,
                    "values": {key: values.get(key) for key in present_fields},
                },
                missing={"fields": missing_fields} if missing_fields else None,
                evidence={
                    "path_present": observation.hub_variables.path_present.value,
                    "values": {
                        key: values.get(key)
                        for key in expected_fields
                        if values.get(key) is not None
                    },
                },
                url=github_url(repository, vars_path),
            )
        )
        return results, environment

    def _keycloak_checks(
        self,
        environment: Environment,
        observation: KeycloakObservation,
    ) -> list[CheckResult]:
        repository = observation.source_repository
        path = observation.source_path
        expected = {
            "client": environment.infra_cluster,
            "redirect_uri": (
                f"https://oauth-openshift.apps.{environment.domain}"
                "/oauth2callback/mocsso"
            ),
            "secret_name": f"cluster/{environment.infra_cluster}/keycloak-oidc",
        }
        client = observation.client
        if not observation.path_present.value:
            present = {name: False for name in expected}
        else:
            present = {
                "client": bool(client and client.cluster_name.value == expected["client"]),
                "redirect_uri": bool(
                    client and client.redirect_uri.value == expected["redirect_uri"]
                ),
                "secret_name": bool(
                    client and client.secret_name.value == expected["secret_name"]
                ),
            }
        present_keys = [name for name, found in present.items() if found]
        missing_keys = [name for name, found in present.items() if not found]
        if not missing_keys:
            state = "declared_in_main"
            reason = (
                "The Keycloak OIDC client, redirect URI, and secret reference "
                "are present."
            )
        elif present_keys:
            state = "partial"
            reason = (
                "Some Keycloak OIDC declarations are present, but these are "
                "missing: " + ", ".join(missing_keys) + "."
            )
        else:
            state = "missing"
            reason = "No expected Keycloak OIDC declarations were found."

        return [
            CheckResult(
                stage="Identity",
                check="Infra OIDC client",
                repository=repository,
                path=path,
                ref="main",
                state=state,
                expected=list(expected),
                actual=present_keys,
                reason=reason,
                present={"declarations": present_keys},
                missing={"declarations": missing_keys} if missing_keys else None,
                evidence={
                    "declarations": present,
                    "client": {
                        "block_name": client.block_name.to_dict(),
                        "cluster_name": client.cluster_name.to_dict(),
                        "redirect_uri": client.redirect_uri.to_dict(),
                        "secret_name": client.secret_name.to_dict(),
                    },
                } if client else {"declarations": present},
                source={
                    "repository": repository,
                    "path": path,
                    "ref": "main",
                } if client else None,
                url=github_url(repository, path),
            )
        ]

    def _apps_checks(
        self,
        environment: Environment,
        observation: AppsObservation,
    ) -> list[CheckResult]:
        repository = observation.source_repository
        tree = set(observation.paths.value)
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
            (
                "Infra hosted-cluster defaults",
                infra_defaults,
                None,
                [infra_defaults],
                "the default values for hosted clusters on this hub cluster",
            ),
            (
                "Hub-wide component values",
                None,
                hub_values_prefix,
                [hub_values_prefix + "hcp-config.yaml"],
                "hub-wide HCP and secret-selector values",
            ),
            (
                "Infra local-cluster values",
                None,
                local_prefix,
                [local_prefix + name for name in LOCAL_CLUSTER_COMPONENTS],
                "the hub cluster's local operator and shared-service values",
            ),
            (
                "Infra ArgoCD applications",
                None,
                apps_prefix,
                [apps_prefix + "keycloak-oauth.yaml"],
                "direct ArgoCD applications applied on the hub cluster",
            ),
            (
                "Workload hosted-cluster values",
                workload_values,
                None,
                [workload_values],
                "the hosted workload cluster definition",
            ),
            (
                "Workload component values",
                None,
                workload_prefix,
                [],
                "component values scoped to the workload cluster",
            ),
        ]

        results: list[CheckResult] = []
        for label, exact, prefix, required_paths, purpose in path_checks:
            search_path = exact or (prefix or "")
            found = sorted(
                path
                for path in tree
                if path == search_path or (prefix and path.startswith(prefix))
            )
            if label == "Hub-wide component values":
                found = [
                    path
                    for path in found
                    if not path.startswith(local_prefix)
                    and not path.startswith(workload_prefix)
                ]

            required_found = [path for path in required_paths if path in tree]
            required_missing = [path for path in required_paths if path not in tree]
            if required_paths:
                if not required_missing:
                    state = "declared_in_main"
                elif required_found or found:
                    state = "partial"
                else:
                    state = "missing"
            else:
                state = "declared_in_main" if found else "missing"

            if state == "declared_in_main":
                reason = f"All expected files for {purpose} are present in main."
                missing = None
            elif state == "partial":
                reason = (
                    f"Some files for {purpose} are present, but expected paths "
                    "are missing: " + ", ".join(required_missing) + "."
                )
                missing = {"paths": required_missing}
            else:
                reason = f"No merged main paths were found for {purpose}."
                missing = {"paths": required_paths or [search_path]}

            expected = (
                {
                    "file_count": len(required_paths),
                    "scope": (exact or prefix or "").rstrip("/"),
                }
                if required_paths
                else "At least one matching path"
            )
            present = {"file_count": len(found)}
            if state != "declared_in_main" and found:
                present["paths"] = found
            if missing is not None and missing.get("paths"):
                missing = {
                    "file_count": len(missing["paths"]),
                    "paths": missing["paths"],
                }

            results.append(
                CheckResult(
                    stage="GitOps configuration",
                    check=label,
                    repository=repository,
                    path=exact or (prefix or "").rstrip("/"),
                    ref="main",
                    state=state,
                    expected=expected,
                    actual={"matched_file_count": len(found)},
                    reason=reason,
                    present=present,
                    missing=missing,
                    evidence={
                        "path_count": len(found),
                        "expected_path_count": len(required_paths),
                        "expected_paths": required_paths,
                        "paths": found,
                    },
                    url=github_url(repository, exact or (prefix or "").rstrip("/")),
                )
            )

        if not self.include_prs:
            return results

        pull_requests = observation.pull_requests

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
                    reason="No open or merged PR references the environment.",
                    present={"matching_pr_count": 0},
                    missing={"matching_pull_requests": 1},
                    evidence={},
                )
            )
            return results

        open_prs = [item for item in pull_requests if item.state.value == "open"]
        merged_prs = [item for item in pull_requests if item.merged.value]
        state = "pr_open" if open_prs else "pr_merged"
        evidence = []
        for item in pull_requests:
            pull = item
            evidence.append(
                {
                    "number": pull.number.value,
                    "title": pull.title.to_dict(),
                    "state": pull.state.to_dict(),
                    "merged": pull.merged.to_dict(),
                    "head_ref": pull.head_ref.to_dict(),
                    "head_sha": pull.head_sha.to_dict(),
                    "html_url": pull.url.to_dict(),
                    "changed_files": list(pull.changed_files.value),
                }
            )

        if open_prs:
            reason = (
                f"{len(open_prs)} relevant PRs are still open; their changes "
                "are not declared in main."
            )
            missing = {"open_prs_to_merge": len(open_prs)}
        else:
            reason = f"All {len(merged_prs)} relevant PRs have been merged into main."
            missing = None

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
                reason=reason,
                present={
                    "matching_pr_count": len(pull_requests),
                    "merged_pr_count": len(merged_prs),
                },
                missing=missing,
                evidence={"pull_requests": evidence},
            )
        )
        return results

    @staticmethod
    def _overall_state(checks: list[CheckResult]) -> str:
        states = {check.state for check in checks}
        if "pr_open" in states:
            return "CONFIGURATION IN PROGRESS"
        if states and states.issubset(
            {"declared_in_main", "requested", "pr_merged"}
        ):
            return "DECLARED IN MAIN"
        if "declared_in_main" in states or "pr_merged" in states:
            return "PARTIALLY CONFIGURED"
        return "NOT CONFIGURED"
