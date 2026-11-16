"""Configuration-state checks across CCI-MOC repositories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import yaml

from .github import GitHubClient, github_url
from .cross_repo import cross_repository_checks
from .model import (
    CheckResult,
    Environment,
    ReportMetadata,
    SourceSnapshot,
    StatusReport,
)
from .observed import (
    AppsObservation,
    ClusterInventoryObservation,
    InfraObservation,
    IssueObservation,
    KeycloakObservation,
    OAC_INFRA_REPOSITORY,
    HARDWARE_NETWORK_DOC_PATH,
    SourceValue,
    UPDATE_AGENTS_PATH,
    inventory_clusters,
    read_environment_observation,
)
from .phases import annotate_and_sort_checks
from .registry import DEFAULT_REGISTRY_PATH, EnvironmentRegistry

ORG = "CCI-MOC"
ProgressCallback = Callable[[str, str, str, str], None]
Clock = Callable[[], datetime]


_NEXT_ACTIONS = {
    "request.issue": (
        "Open or reopen the environment request issue in CCI-MOC/MOC-issues."
    ),
    "hub.inventory": (
        "Edit CCI-MOC/oac-infra at infra/inventory/00hosts.yaml and add or "
        "correct the hub cluster group with vars.cluster set to the hub name."
    ),
    "workload.inventory": (
        "Edit CCI-MOC/oac-infra at infra/inventory/00hosts.yaml and add or "
        "correct the workload cluster group with vars.cluster set to the workload name."
    ),
    "hub.boot_image": (
        "Generate and publish a hub-specific discovery ISO, then replace the "
        "generic boot_image_url for every host in the hub cluster group."
    ),
    "workload.boot_image": (
        "Generate and publish the parent hub's agent discovery ISO, then "
        "replace the generic boot_image_url for every host in the workload "
        "cluster group."
    ),
    "workload.agent_labels_inputs": (
        "Edit the inventory inputs used by infra/update-agents.yaml."
    ),
    "hub.image_inventory": (
        "Edit CCI-MOC/oac-infra at hub-images/inventory.yml and add the hub "
        "entry under all.children."
    ),
    "hub.image_vars": (
        "Edit CCI-MOC/oac-infra at hub-images/group_vars/<hub>/vars.yml and "
        "provide cluster_domain_name, base_domain, machine_network, api_ip, "
        "ingress_ip, and dns_ip."
    ),
    "hub.oidc_client": (
        "Edit CCI-MOC/moc-keycloak at main.tf and add the hub's OIDC client, "
        "redirect URI, and secret reference."
    ),
    "hub.hosted_cluster_defaults": (
        "Create or complete the hub hosted-cluster defaults file at "
        "hosted-clusters/<hub>/values.yaml in CCI-MOC/oac-infra."
    ),
    "hub.component_values": (
        "Create or complete values/<hub>/hcp-config.yaml in CCI-MOC/oac-infra "
        "for hub-wide HCP and secret-selector values."
    ),
    "hub.local_cluster_values": (
        "Copy the required local-cluster component files from an existing hub "
        "environment and adjust cluster-specific names and addresses."
    ),
    "hub.argocd_apps": (
        "Add Argo CD application manifests for the hub after its hosted-cluster, "
        "hub-wide component, and local-cluster values are present, and reference "
        "the correct clusters."
    ),
    "workload.hosted_cluster_values": (
        "Create the missing hosted-cluster values file from the closest "
        "existing environment; set the cluster name, parent hub, networking, "
        "and node pools before adding components."
    ),
    "workload.component_values": (
        "Create the workload component-values directory, starting with "
        "hcp-config.yaml and only the shared components this workload needs."
    ),
    "pull_requests": (
        "Review the relevant pull requests; merge or close any open PR after "
        "confirming it is the intended repository change."
    ),
}


def _next_action(check_id: str, state: str) -> str | None:
    if state in {"declared_in_main", "requested", "pr_merged"}:
        return None
    return _NEXT_ACTIONS[check_id]


def _package_version() -> str:
    try:
        return version("moc-env")
    except PackageNotFoundError:
        return "unknown"


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
        hub_status_command = f"moc-env status-hub {base_name}"
        workload_status_command = f"moc-env status-workload {base_name}"
        clusters.append(
            {
                "environment": base_name,
                "cluster": infra_cluster,
                "type": "hub",
                "status_command": hub_status_command,
                "source_repository": repository,
                "source_path": hub_inventory_path,
            }
        )
        for workload_cluster in workload_clusters:
            workload_name = workload_cluster.removeprefix(f"{base_name}-")
            clusters.append(
                {
                    "environment": base_name,
                    "cluster": workload_cluster,
                    "type": "workload",
                    "status_command": (
                        f"{workload_status_command} --workload {workload_name}"
                    ),
                    "source_repository": repository,
                    "source_path": inventory_path,
                }
            )
    return clusters


def _boot_image_state(
    url: str | None,
    cluster: str,
    hub_cluster: str | None = None,
) -> str:
    if not url:
        return "missing"
    image_name = url.rsplit("/", 1)[-1]
    if image_name == "discovery.iso":
        return "partial"
    cluster_aliases = [cluster]
    if cluster.startswith("oac-"):
        cluster_aliases.append(cluster.removeprefix("oac-"))
    if hub_cluster is not None:
        cluster_aliases.extend((hub_cluster, hub_cluster.removeprefix("oac-")))
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
        registry: EnvironmentRegistry | None = None,
        command: tuple[str, ...] | list[str] | None = None,
        clock: Clock | None = None,
        tool_version: str | None = None,
    ) -> None:
        self.client = client
        self.include_prs = include_prs
        self.progress = progress
        self.registry = registry or EnvironmentRegistry.load(DEFAULT_REGISTRY_PATH)
        self.command = tuple(command or ())
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.tool_version = tool_version or _package_version()

    def _emit_progress(
        self, stage: str, action: str, repository: str, path: str
    ) -> None:
        if self.progress is not None:
            self.progress(stage, action, repository, path)

    def run(
        self,
        environment: Environment,
        path_scope: str = "environment",
    ) -> StatusReport:
        checks: list[CheckResult] = []
        observation = read_environment_observation(
            self.client,
            environment,
            progress=self._emit_progress,
            include_pull_requests=self.include_prs,
            path_scope=path_scope,
            keycloak_client_name=self.registry.keycloak_client_name(
                environment.name
            ),
        )
        environment = observation.environment
        if observation.issue is not None:
            checks.extend(self._issue_checks(observation.issue))
        infra_checks, environment = self._infra_checks(environment, observation.infra)
        checks.extend(infra_checks)
        checks.extend(self._keycloak_checks(environment, observation.keycloak))
        checks.extend(self._apps_checks(environment, observation.apps))
        checks.extend(
            cross_repository_checks(
                self.client,
                environment,
                observation.infra,
                observation.apps,
                self._emit_progress,
            )
        )
        self._apply_boot_image_severities(checks)
        checks = annotate_and_sort_checks(checks)
        return StatusReport(
            environment=environment,
            checks=checks,
            overall_state=self._overall_state(checks),
            metadata=self._metadata(),
        )

    def _metadata(self) -> ReportMetadata:
        generated_at = self.clock().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        sources = tuple(
            SourceSnapshot(**source) for source in self.client.sources()
        )
        return ReportMetadata(
            schema_version=2,
            generated_at=generated_at,
            tool_version=self.tool_version,
            command=self.command,
            sources=sources,
            authenticated=self.client.authenticated,
            rate_limit_remaining=self.client.rate_limit_remaining,
        )

    def run_hub(self, environment: Environment) -> StatusReport:
        """Return the repository-status report scoped to the hub cluster."""

        report = self.run(environment, path_scope="hub")
        checks = [
            check
            for check in report.checks
            if check.scope in {"hub", "shared"}
        ]
        return replace(
            report,
            checks=checks,
            overall_state=self._overall_state(checks),
            scope="hub",
        )

    def run_workload(
        self,
        environment: Environment,
        workload: str | None = None,
    ) -> StatusReport:
        """Return the repository-status report scoped to the workload cluster."""

        if workload is not None:
            if environment.workload_clusters is None:
                environment = replace(
                    environment,
                    workload_clusters=(environment.workload_cluster,),
                )
            if workload not in environment.workload_clusters:
                raise ValueError(f"unknown workload cluster: {workload}")
            environment = replace(environment, workload_clusters=(workload,))
        report = self.run(environment, path_scope="workload")
        checks = [
            check
            for check in report.checks
            if check.scope in {"workload", "shared"}
        ]
        return replace(
            report,
            checks=checks,
            overall_state=self._overall_state(checks),
            scope="workload",
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
                id="request.issue",
                stage="Request",
                check="MOC issue",
                scope="shared",
                repository=repository,
                path=path,
                ref="main",
                state=state,
                severity="info",
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
                next_action=_next_action("request.issue", state),
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
            inventory_id = (
                "hub.inventory"
                if cluster == environment.infra_cluster
                else "workload.inventory"
            )
            inventory_scope = (
                "hub" if cluster == environment.infra_cluster else "workload"
            )
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
                    id=inventory_id,
                    stage="Hardware and inventory",
                    check=f"{cluster} host inventory",
                    scope=inventory_scope,
                    repository=repository,
                    path=inventory_path,
                    ref="main",
                    state=state,
                    severity=(
                        "info" if state == "declared_in_main" else "blocking"
                    ),
                    expected=f"Inventory group for {cluster}",
                    actual={"found": group is not None, "host_count": len(hosts)},
                    reason=reason,
                    present=present,
                    missing=missing,
                    evidence={"hosts": cluster_observation.host_summaries()},
                    url=github_url(repository, inventory_path),
                    next_action=_next_action(inventory_id, state),
                )
            )

            if inventory_scope == "workload":
                results.append(
                    self._workload_agent_labels_check(
                        cluster,
                        cluster_observation,
                        observation.update_agents_present,
                        observation.hardware_resource_classes,
                    )
                )

            if not hosts:
                continue

            is_hub = cluster == environment.infra_cluster
            selected_url = boot_urls[0] if len(boot_urls) == 1 else None
            boot_state = _boot_image_state(
                selected_url,
                cluster,
                hub_cluster=None if is_hub else environment.infra_cluster,
            )
            boot_id = (
                "hub.boot_image"
                if is_hub
                else "workload.boot_image"
            )
            boot_scope = "hub" if is_hub else "workload"
            if boot_state == "declared_in_main":
                boot_reason = (
                    f"The boot image URL is specific to {cluster}."
                    if is_hub
                    else (
                        "The boot image URL identifies the workload or its parent "
                        f"hub {environment.infra_cluster}."
                    )
                )
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
            elif selected_url and selected_url.rsplit("/", 1)[-1] == "discovery.iso":
                expected_image = (
                    f"{cluster}-agent-discovery.iso"
                    if is_hub
                    else f"{environment.infra_cluster}-agent-discovery.iso"
                )
                boot_reason = (
                    "A boot image URL is present, but the workload is still on the "
                    f"generic discovery.iso rather than the expected "
                    f"`{expected_image}`."
                    if not is_hub
                    else (
                        "A boot image URL is present, but it points to the generic "
                        "discovery.iso rather than a cluster-specific image."
                    )
                )
                boot_present = {"boot_image_url": selected_url}
                boot_missing = {
                    "cluster_specific_image": expected_image
                }
            elif selected_url:
                image_name = selected_url.rsplit("/", 1)[-1]
                boot_reason = (
                    "A boot image URL is present, but the filename "
                    f"`{image_name}` does not consistently identify this workload "
                    "or its parent hub."
                    if not is_hub
                    else (
                        "A boot image URL is present, but it does not identify the "
                        "expected cluster by its full name or oac-shortened name."
                    )
                )
                boot_present = {"boot_image_url": selected_url}
                boot_missing = {
                    "cluster_name_in_image": (
                        [cluster, cluster.removeprefix("oac-")]
                        if is_hub
                        else [
                            cluster,
                            cluster.removeprefix("oac-"),
                            environment.infra_cluster,
                            environment.infra_cluster.removeprefix("oac-"),
                        ]
                    )
                }
            else:
                boot_reason = "No boot image URL is inherited by the cluster host group."
                boot_present = {"boot_image_url": None}
                boot_missing = {
                    "cluster_specific_image": f"{cluster}-agent-discovery.iso"
                }

            results.append(
                CheckResult(
                    id=boot_id,
                    stage="Hardware and inventory",
                    check=f"{cluster} boot image",
                    scope=boot_scope,
                    repository=repository,
                    path=inventory_path,
                    ref="main",
                    state=boot_state,
                    severity=(
                        "info"
                        if boot_state == "declared_in_main"
                        else (
                            "advisory"
                            if (
                                not is_hub
                                and selected_url is not None
                                and selected_url.rsplit("/", 1)[-1]
                                != "discovery.iso"
                            )
                            else "blocking"
                        )
                    ),
                    expected=f"Cluster-specific discovery image for {cluster}",
                    actual=boot_urls,
                    reason=boot_reason,
                    present=boot_present,
                    missing=boot_missing,
                    evidence={
                        "generic_discovery_iso": bool(
                            boot_urls and boot_urls[0].endswith("discovery.iso")
                        ),
                        "check_rule": (
                            (
                                "The boot-image filename must contain the full cluster "
                                f"name `{cluster}`"
                                + (
                                    f" (or the oac-shortened name "
                                    f"`{cluster.removeprefix('oac-')}`)"
                                    if cluster.startswith("oac-")
                                    else ""
                                )
                                + "; generic `discovery.iso` does not satisfy this rule."
                            )
                            if is_hub
                            else (
                                "The workload boot-image filename may contain the "
                                f"workload name `{cluster}`, its oac-shortened name, "
                                f"the parent hub name `{environment.infra_cluster}`, "
                                "or the hub's oac-shortened name. Unrecognized "
                                "names are advisory because naming is not consistent "
                                "across environments; generic `discovery.iso` "
                                "remains a gap."
                            )
                        ),
                    },
                    url=github_url(repository, inventory_path),
                    next_action=_next_action(boot_id, boot_state),
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
                id="hub.image_inventory",
                stage="Cluster build",
                check="Hub image inventory",
                scope="hub",
                repository=repository,
                path=hub_inventory_path,
                ref="main",
                state=hub_state,
                severity="info" if hub_state == "declared_in_main" else "blocking",
                expected=f"Hub-image inventory entry for {environment.infra_cluster}",
                actual={"found": hub_found},
                reason=hub_reason,
                present=hub_present,
                missing=hub_missing,
                    evidence={
                        "path_present": observation.hub_inventory.path_present.value
                    },
                url=github_url(repository, hub_inventory_path),
                next_action=_next_action("hub.image_inventory", hub_state),
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
                id="hub.image_vars",
                stage="Cluster build",
                check="Hub image variables",
                scope="hub",
                repository=repository,
                path=vars_path,
                ref="main",
                state=state,
                severity="info" if state == "declared_in_main" else "blocking",
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
                next_action=_next_action("hub.image_vars", state),
            )
        )
        return results, environment

    def _workload_agent_labels_check(
        self,
        cluster: str,
        cluster_observation: ClusterInventoryObservation,
        update_agents_present: SourceValue,
        hardware_resource_classes: SourceValue,
    ) -> CheckResult:
        """Check host inputs consumed by infra/update-agents.yaml."""

        repository = OAC_INFRA_REPOSITORY
        hosts = cluster_observation.hosts.value
        documented_resource_classes = hardware_resource_classes.value
        rows = [
            {
                "host": host.get("name"),
                "node_name": host.get("node_name"),
                "bm_management": host.get("bm_management"),
                "mac_addr": host.get("mac_addr"),
                "resource_class": host.get("resource_class"),
                "documented_resource_class": documented_resource_classes.get(
                    host.get("node_name")
                ),
            }
            for host in hosts
        ]
        checked_rows = [
            row for row in rows if row["bm_management"] != "openstack"
        ]
        missing_by_host = {
            row["host"]: [
                name
                for name in ("mac_addr", "resource_class")
                if row[name] is None
            ]
            for row in checked_rows
        }

        resource_class_mismatches = [
            {
                "host": row["host"],
                "node_name": row["node_name"],
                "inventory_resource_class": row["resource_class"],
                "documented_resource_class": row["documented_resource_class"],
            }
            for row in checked_rows
            if row["resource_class"] is not None
            and row["documented_resource_class"] is not None
            and row["resource_class"] != row["documented_resource_class"]
        ]
        missing_by_host = {
            host: variables
            for host, variables in missing_by_host.items()
            if variables
        }

        if not update_agents_present.value:
            state = "missing"
            reason = "The infra/update-agents.yaml playbook is absent from main."
        elif not hosts:
            state = "missing"
            reason = f"No hosts are declared for the {cluster} workload cluster."
        elif not checked_rows:
            state = "declared_in_main"
            reason = (
                "All hosts use bm_management openstack, so update-agents.yaml "
                "does not require mac_addr or resource_class for them."
            )
        elif missing_by_host:
            state = "partial"
            reason = (
                "Some non-openstack hosts are missing mac_addr or "
                "resource_class inputs required by infra/update-agents.yaml."
            )
            if len(rows) - len(checked_rows):
                reason += " Hosts using bm_management openstack are not checked."
        else:
            state = "declared_in_main"
            reason = (
                "Every non-openstack host has the mac_addr and resource_class "
                "inputs required by infra/update-agents.yaml."
            )
            if resource_class_mismatches:
                mismatch = resource_class_mismatches[0]
                reason += (
                    " The documented resource class differs for "
                    f"{mismatch['host']}: inventory has "
                    f"`{mismatch['inventory_resource_class']}`, documentation "
                    f"has `{mismatch['documented_resource_class']}`."
                )

        next_action = _next_action("workload.agent_labels_inputs", state)
        if next_action is not None:
            affected_hosts = ", ".join(sorted(missing_by_host)) or "none"
            missing_variables = (
                ", ".join(
                    sorted({name for names in missing_by_host.values() for name in names})
                )
                or "mac_addr, resource_class"
            )
            next_action += (
                f" For hosts {affected_hosts}, provide {missing_variables}. "
                "resource_class must match the value the NodePool selects on."
            )
            for row in checked_rows:
                if (
                    row["resource_class"] is None
                    and row["documented_resource_class"] is not None
                ):
                    next_action += (
                        f" Set {row['host']} resource_class to "
                        f"`{row['documented_resource_class']}`."
                    )
        elif resource_class_mismatches:
            mismatch = resource_class_mismatches[0]
            next_action = (
                "Review the resource_class mismatch for "
                f"{mismatch['host']}: inventory has "
                f"`{mismatch['inventory_resource_class']}`, documentation has "
                f"`{mismatch['documented_resource_class']}`. resource_class "
                "must match the value the NodePool selects on."
            )

        return CheckResult(
            id="workload.agent_labels_inputs",
            stage="Hardware and inventory",
            check=f"{cluster} update-agents inputs",
            scope="workload",
            repository=repository,
            path=UPDATE_AGENTS_PATH,
            ref="main",
            state=state,
            severity=(
                "advisory"
                if resource_class_mismatches and state == "declared_in_main"
                else "info"
                if state == "declared_in_main"
                else "blocking"
            ),
            expected=["mac_addr", "resource_class"],
            actual=rows,
            reason=reason,
            present={
                "checked_host_count": len(checked_rows),
                "complete_host_count": len(checked_rows) - len(missing_by_host),
            },
            missing={"hosts": missing_by_host} if missing_by_host else None,
            evidence={
                "agent_label_hosts": rows,
                "missing_variables": missing_by_host,
                "resource_class_mismatches": resource_class_mismatches,
                "resource_class_documentation_path": HARDWARE_NETWORK_DOC_PATH,
                "openstack_hosts_skipped": len(rows) - len(checked_rows),
            },
            url=github_url(repository, UPDATE_AGENTS_PATH),
            next_action=next_action,
        )

    def _keycloak_checks(
        self,
        environment: Environment,
        observation: KeycloakObservation,
    ) -> list[CheckResult]:
        repository = observation.source_repository
        path = observation.source_path
        keycloak_client_name = self.registry.keycloak_client_name(environment.name)
        expected = {
            "client": keycloak_client_name,
            "redirect_uri": (
                f"https://oauth-openshift.apps.{environment.domain}"
                "/oauth2callback/mocsso"
            ),
            "secret_name": f"cluster/{environment.infra_cluster}/keycloak-oidc",
        }
        client = observation.client
        near_match = observation.near_match_client
        selected_client = client or near_match
        observed = {
            "client": selected_client.cluster_name.value if selected_client else None,
            "redirect_uri": (
                selected_client.redirect_uri.value if selected_client else None
            ),
            "secret_name": (
                selected_client.secret_name.value if selected_client else None
            ),
        }
        fields = {
            name: {
                "expected": expected_value,
                "observed": observed[name],
                "status": (
                    "match"
                    if observed[name] == expected_value
                    else ("mismatch" if observed[name] is not None else "absent")
                ),
            }
            for name, expected_value in expected.items()
        }
        nonmatching_fields = [
            name for name, result in fields.items() if result["status"] != "match"
        ]
        if selected_client is None:
            state = "missing"
        elif nonmatching_fields:
            state = "partial"
        else:
            state = "declared_in_main"

        if state == "declared_in_main":
            reason = "All expected Keycloak OIDC client fields match."
        elif selected_client is not None:
            reason = (
                "A Keycloak OIDC client block exists, but these fields are "
                "mismatched or absent: " + ", ".join(nonmatching_fields) + "."
            )
            if near_match is not None and client is None:
                reason += (
                    f" The near-match block `{near_match.block_name.value}` was "
                    "found instead of an exact client declaration."
                )
        else:
            reason = "No Keycloak OIDC client block exists for this hub."

        next_action = _next_action("hub.oidc_client", state)
        if next_action is not None:
            next_action += (
                " Set cluster_name = "
                f"`{expected['client']}`, openshift_redirect_uri = "
                f"`{expected['redirect_uri']}`, and client_secret_name = "
                f"`{expected['secret_name']}`."
            )

        evidence: dict[str, Any] = {"fields": fields}
        if client is not None:
            evidence["client"] = {
                "block_name": client.block_name.to_dict(),
                "cluster_name": client.cluster_name.to_dict(),
                "redirect_uri": client.redirect_uri.to_dict(),
                "secret_name": client.secret_name.to_dict(),
            }
        if near_match is not None:
            evidence["near_match_client"] = {
                "block_name": near_match.block_name.to_dict(),
                "cluster_name": near_match.cluster_name.to_dict(),
                "redirect_uri": near_match.redirect_uri.to_dict(),
                "secret_name": near_match.secret_name.to_dict(),
            }

        return [
            CheckResult(
                id="hub.oidc_client",
                stage="Identity",
                check="Infra OIDC client",
                scope="hub",
                repository=repository,
                path=path,
                ref="main",
                state=state,
                severity="info" if state == "declared_in_main" else "blocking",
                expected={name: result["expected"] for name, result in fields.items()},
                actual={name: result["observed"] for name, result in fields.items()},
                reason=reason,
                present={
                    "fields": {
                        name: result["status"] for name, result in fields.items()
                    }
                },
                missing={"fields": nonmatching_fields} if nonmatching_fields else None,
                evidence=evidence,
                source={
                    "repository": repository,
                    "path": path,
                    "ref": "main",
                } if selected_client is not None else None,
                url=github_url(repository, path),
                next_action=next_action,
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

        workload_checks = []
        for workload_cluster in environment.workload_clusters or ():
            workload_values = (
                f"hosted-clusters/{environment.infra_cluster}/"
                f"{workload_cluster}/values.yaml"
            )
            workload_prefix = (
                f"values/{environment.infra_cluster}/{workload_cluster}/"
            )
            workload_checks.extend(
                [
                    (
                        "workload.hosted_cluster_values",
                        "workload",
                        "Workload hosted-cluster values",
                        workload_values,
                        None,
                        [workload_values],
                        "the hosted workload cluster definition",
                    ),
                    (
                        "workload.component_values",
                        "workload",
                        "Workload component values",
                        None,
                        workload_prefix,
                        [],
                        "component values scoped to the workload cluster",
                    ),
                ]
            )

        path_checks = [
            (
                "hub.hosted_cluster_defaults",
                "hub",
                "Infra hosted-cluster defaults",
                infra_defaults,
                None,
                [infra_defaults],
                "the default values for hosted clusters on this hub cluster",
            ),
            (
                "hub.component_values",
                "hub",
                "Hub-wide component values",
                None,
                hub_values_prefix,
                [hub_values_prefix + "hcp-config.yaml"],
                "hub-wide HCP and secret-selector values",
            ),
            (
                "hub.local_cluster_values",
                "hub",
                "Infra local-cluster values",
                None,
                local_prefix,
                [
                    local_prefix + name
                    for name in self.registry.required_components(environment.name)
                ],
                "the hub cluster's local operator and shared-service values",
            ),
            (
                "hub.argocd_apps",
                "hub",
                "Infra ArgoCD applications",
                None,
                apps_prefix,
                [apps_prefix + "keycloak-oauth.yaml"],
                "direct ArgoCD applications applied on the hub cluster",
            ),
            *workload_checks,
        ]

        results: list[CheckResult] = []
        for (
            check_id,
            check_scope,
            label,
            exact,
            prefix,
            required_paths,
            purpose,
        ) in path_checks:
            search_path = exact or (prefix or "")
            optional_paths = (
                [
                    local_prefix + name
                    for name in self.registry.optional_components(environment.name)
                ]
                if check_id == "hub.local_cluster_values"
                else []
            )
            expected_paths = required_paths + optional_paths
            found = sorted(
                path
                for path in tree
                if path == search_path or (prefix and path.startswith(prefix))
            )
            if check_id == "hub.component_values":
                found = [
                    path
                    for path in found
                    if not path.startswith(local_prefix)
                    and not any(
                        path.startswith(
                            f"values/{environment.infra_cluster}/"
                            f"{workload_cluster}/"
                        )
                        for workload_cluster in environment.workload_clusters or ()
                    )
                ]

            required_found = [path for path in required_paths if path in tree]
            required_missing = [path for path in required_paths if path not in tree]
            optional_missing = [path for path in optional_paths if path not in tree]
            if expected_paths:
                if not required_missing and not optional_missing:
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
                missing_paths = required_missing + optional_missing
                reason = (
                    f"Some files for {purpose} are present, but expected paths "
                    "are missing: " + ", ".join(missing_paths) + "."
                )
                missing = {"paths": missing_paths}
            else:
                reason = f"No merged main paths were found for {purpose}."
                missing = {"paths": expected_paths or [search_path]}

            severity = "info"
            if state != "declared_in_main":
                if required_missing or not expected_paths:
                    severity = "blocking"
                else:
                    severity = "advisory"

            expected = (
                {
                    "file_count": len(expected_paths),
                    "scope": (exact or prefix or "").rstrip("/"),
                }
                if expected_paths
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
                    id=check_id,
                    stage="GitOps configuration",
                    check=label,
                    scope=check_scope,
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
                        "expected_path_count": len(expected_paths),
                        "expected_paths": expected_paths,
                        "optional_paths": optional_paths,
                        "paths": found,
                    },
                    url=github_url(repository, exact or (prefix or "").rstrip("/")),
                    next_action=_next_action(check_id, state),
                    severity=severity,
                )
            )

        if not self.include_prs:
            return results

        pull_requests = observation.pull_requests

        if not pull_requests:
            results.append(
                CheckResult(
                    id="pull_requests",
                    stage="GitOps configuration",
                    check="Relevant pull requests",
                    scope="shared",
                    repository=repository,
                    path="pulls",
                    ref="all",
                    state="missing",
                    expected="No open PR changing an environment-owned path",
                    actual={"matching_pr_count": 0},
                    reason=(
                        "No open, merged, or closed-unmerged PR changes a file "
                        "under this environment's oac-apps paths."
                    ),
                    present={"matching_pr_count": 0},
                    missing={"matching_pull_requests": 1},
                    evidence={},
                    next_action=_next_action("pull_requests", "missing"),
                    severity="info",
                )
            )
            return results

        open_prs = [
            item for item in pull_requests if item.classification.value == "open"
        ]
        merged_prs = [
            item for item in pull_requests if item.classification.value == "merged"
        ]
        closed_unmerged_prs = [
            item
            for item in pull_requests
            if item.classification.value == "closed_unmerged"
        ]
        repository_counts: dict[str, int] = {}
        for item in pull_requests:
            repository = item.repository.value
            repository_counts[repository] = repository_counts.get(repository, 0) + 1
        state = "pr_open" if open_prs else "declared_in_main"
        evidence = []
        for item in pull_requests:
            pull = item
            evidence.append(
                {
                    "number": pull.number.value,
                    "title": pull.title.to_dict(),
                    "state": pull.state.to_dict(),
                    "merged": pull.merged.to_dict(),
                    "classification": pull.classification.to_dict(),
                    "head_ref": pull.head_ref.to_dict(),
                    "head_sha": pull.head_sha.to_dict(),
                    "html_url": pull.url.to_dict(),
                    "repository": pull.repository.to_dict(),
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
            reason = (
                f"No relevant PRs are open; {len(merged_prs)} merged and "
                f"{len(closed_unmerged_prs)} closed-unmerged PRs are listed "
                "as history."
            )
            missing = None

        results.append(
            CheckResult(
                id="pull_requests",
                stage="GitOps configuration",
                check="Relevant pull requests",
                scope="shared",
                repository=repository,
                path="pulls",
                ref="all",
                state=state,
                expected="No open PR changing an environment-owned path",
                actual={
                    "matching_pr_count": len(pull_requests),
                    "open_count": len(open_prs),
                    "merged_count": len(merged_prs),
                    "closed_unmerged_count": len(closed_unmerged_prs),
                    "repository_counts": dict(sorted(repository_counts.items())),
                },
                reason=reason,
                present={
                    "matching_pr_count": len(pull_requests),
                    "merged_pr_count": len(merged_prs),
                    "open_pr_count": len(open_prs),
                    "closed_unmerged_pr_count": len(closed_unmerged_prs),
                    "repository_counts": dict(sorted(repository_counts.items())),
                },
                missing=missing,
                evidence={"pull_requests": evidence},
                next_action=_next_action("pull_requests", state),
                severity="blocking" if open_prs else "info",
            )
        )
        return results

    def _apply_boot_image_severities(self, checks: list[CheckResult]) -> None:
        """Downgrade generic boot-image gaps when later-stage evidence exists."""

        by_id = {check.id: check for check in checks}
        for check in checks:
            if check.id not in {"hub.boot_image", "workload.boot_image"}:
                continue
            urls = check.actual
            if not isinstance(urls, list) or len(urls) != 1:
                continue
            if urls[0].rsplit("/", 1)[-1] != "discovery.iso":
                continue

            if check.id == "hub.boot_image":
                defaults = by_id.get("hub.hosted_cluster_defaults")
                local_values = by_id.get("hub.local_cluster_values")
                later_evidence = (
                    defaults is not None
                    and defaults.state == "declared_in_main"
                    and local_values is not None
                    and local_values.state == "declared_in_main"
                )
            else:
                workload_values = by_id.get("workload.hosted_cluster_values")
                later_evidence = (
                    workload_values is not None
                    and workload_values.state == "declared_in_main"
                )
            if later_evidence:
                check.severity = "advisory"

    @staticmethod
    def _overall_state(checks: list[CheckResult]) -> str:
        if any(check.severity == "blocking" for check in checks):
            return "CONFIGURATION IN PROGRESS"
        if checks:
            return "DECLARED IN MAIN"
        return "NOT CONFIGURED"
