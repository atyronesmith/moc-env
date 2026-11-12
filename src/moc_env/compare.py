"""Compare reviewed desired state with current repository state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .model import Environment
from .observed import (
    AppsObservation,
    InfraObservation,
    IssueObservation,
)

COMPARISON_STATES = (
    "matches_main",
    "missing_from_main",
    "value_mismatch",
    "unexpected_in_main",
    "unsupported_check",
    "ambiguous",
    "pr_open",
)

_MISSING = object()


@dataclass(frozen=True)
class ComparisonCheck:
    """One desired-state field comparison."""

    category: str
    field: str
    desired: Any
    current: Any
    state: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "field": self.field,
            "desired": self.desired,
            "current": self.current,
            "state": self.state,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ComparisonReport:
    """The complete desired-state versus merged-main comparison."""

    environment: Environment
    kind: str = "Infra"
    checks: list[ComparisonCheck] = field(default_factory=list)

    @property
    def overall_state(self) -> str:
        states = {check.state for check in self.checks}
        hard_differences = states & {
            "missing_from_main",
            "value_mismatch",
            "unexpected_in_main",
            "unsupported_check",
            "ambiguous",
        }
        if hard_differences:
            return "DIFFERENCES FOUND"
        if "pr_open" in states:
            return "CONFIGURATION IN PROGRESS"
        return "MATCHES MAIN"

    def to_dict(self) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        for check in self.checks:
            state_counts[check.state] = state_counts.get(check.state, 0) + 1
        return {
            "kind": self.kind,
            "environment": self.environment.to_dict(),
            "overall_state": self.overall_state,
            "summary": {
                "check_count": len(self.checks),
                "state_counts": dict(sorted(state_counts.items())),
            },
            "checks": [check.to_dict() for check in self.checks],
        }


def _desired_source(parent: Any, key: str) -> Any:
    if not isinstance(parent, dict):
        return _MISSING
    source = parent.get(key)
    if not isinstance(source, dict) or "value" not in source:
        return _MISSING
    return source["value"]


def _current_source(source: Any) -> Any:
    if not hasattr(source, "value"):
        return _MISSING
    return source.value


def _normal(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_normal(item) for item in value]
    if isinstance(value, list):
        return [_normal(item) for item in value]
    return value


def _compare(
    checks: list[ComparisonCheck],
    category: str,
    field_name: str,
    desired: Any,
    current: Any,
) -> None:
    if desired is _MISSING:
        checks.append(
            ComparisonCheck(
                category=category,
                field=field_name,
                desired=None,
                current=None if current is _MISSING else _normal(current),
                state="unsupported_check",
                reason="The desired-state document does not provide a supported value.",
            )
        )
        return
    if current is _MISSING:
        checks.append(
            ComparisonCheck(
                category=category,
                field=field_name,
                desired=_normal(desired),
                current=None,
                state="unsupported_check",
                reason="The current repository observation does not provide a supported value.",
            )
        )
        return
    desired_value = _normal(desired)
    current_value = _normal(current)
    if desired_value == current_value:
        state = "matches_main"
        reason = "The reviewed desired value matches merged main."
    else:
        state = "value_mismatch"
        reason = "The reviewed desired value differs from merged main."
    checks.append(
        ComparisonCheck(
            category=category,
            field=field_name,
            desired=desired_value,
            current=current_value,
            state=state,
            reason=reason,
        )
    )


def _mapping(document: Any, *path: str) -> Any:
    value: Any = document
    for part in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(part, {})
    return value


def desired_environment(document: Any) -> Environment:
    """Derive the Environment represented by a desired-state document."""

    if document.get("kind") == "Environment":
        environment_name = _desired_source(_mapping(document, "metadata"), "name")
        issue_url = _desired_source(_mapping(document, "spec"), "issue")
        issue_number = None
        if isinstance(issue_url, str) and issue_url.rsplit("/", 1)[-1].isdigit():
            issue_number = int(issue_url.rsplit("/", 1)[-1])
        return Environment(
            name=environment_name if isinstance(environment_name, str) else "",
            issue_number=issue_number,
        )

    environment_name = _desired_source(_mapping(document, "metadata"), "environment")
    if not isinstance(environment_name, str):
        infra_name = _desired_source(_mapping(document, "metadata"), "name")
        if isinstance(infra_name, str) and infra_name.endswith("-infra"):
            environment_name = infra_name[: -len("-infra")]
        else:
            environment_name = ""
    return Environment(name=environment_name)


def compare_environment(
    document: Any,
    environment: Environment,
    issue: IssueObservation,
    infra: InfraObservation,
    apps: AppsObservation,
) -> ComparisonReport:
    """Compare an Environment bundle with current merged main."""

    checks: list[ComparisonCheck] = []
    metadata = _mapping(document, "metadata")
    spec = _mapping(document, "spec")
    network = _mapping(document, "spec", "network")

    _compare(
        checks,
        "Metadata",
        "metadata.name.value",
        _desired_source(metadata, "name"),
        environment.name,
    )
    _compare(
        checks,
        "Bundle",
        "spec.issue.value",
        _desired_source(spec, "issue"),
        issue.url.value,
    )
    _compare(
        checks,
        "References",
        "spec.hubCluster.value",
        _desired_source(spec, "hubCluster"),
        environment.infra_cluster,
    )
    _compare(
        checks,
        "References",
        "spec.hubCluster.inventoryPresent",
        True,
        environment.infra_cluster in infra.clusters,
    )
    _compare(
        checks,
        "Network and domain",
        "spec.network.machineNetwork.value",
        _desired_source(network, "machineNetwork"),
        infra.hub_variables.values.value.get("machine_network")
        if isinstance(infra.hub_variables.values.value, dict)
        else _MISSING,
    )

    values = infra.hub_variables.values.value
    current_domain = (
        f"{values['cluster_domain_name']}.{values['base_domain']}"
        if isinstance(values, dict)
        and isinstance(values.get("cluster_domain_name"), str)
        and isinstance(values.get("base_domain"), str)
        else _MISSING
    )
    _compare(
        checks,
        "Network and domain",
        "spec.domain.value",
        _desired_source(spec, "domain"),
        current_domain,
    )

    workloads = spec.get("workloadClusters")
    workloads = workloads if isinstance(workloads, list) else []
    paths = set(apps.paths.value)
    for index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            continue
        workload_name = _desired_source(workload, "name")
        parent_hub = _desired_source(workload, "parentHubCluster")
        _compare(
            checks,
            "References",
            f"spec.workloadClusters[{index}].name.value",
            workload_name,
            environment.workload_cluster,
        )
        _compare(
            checks,
            "References",
            f"spec.workloadClusters[{index}].parentHubCluster.value",
            parent_hub,
            environment.infra_cluster,
        )
        _compare(
            checks,
            "References",
            f"spec.workloadClusters[{index}].inventoryPresent",
            True,
            workload_name in infra.clusters,
        )

        hosted_path = (
            f"hosted-clusters/{environment.infra_cluster}/{workload_name}/values.yaml"
            if isinstance(workload_name, str)
            else None
        )
        component_prefix = (
            f"values/{environment.infra_cluster}/{workload_name}/"
            if isinstance(workload_name, str)
            else None
        )
        application_prefix = (
            f"apps/{environment.infra_cluster}/{workload_name}/"
            if isinstance(workload_name, str)
            else None
        )
        for field_name, expected, current in (
            (
                f"spec.workloadClusters[{index}].gitOps.hostedClusterValues",
                hosted_path,
                hosted_path in paths if hosted_path is not None else _MISSING,
            ),
            (
                f"spec.workloadClusters[{index}].gitOps.componentValues",
                component_prefix,
                bool(
                    component_prefix
                    and any(path.startswith(component_prefix) for path in paths)
                ),
            ),
            (
                f"spec.workloadClusters[{index}].gitOps.applications",
                application_prefix,
                bool(
                    application_prefix
                    and any(path.startswith(application_prefix) for path in paths)
                ),
            ),
        ):
            if current is True:
                state = "matches_main"
                reason = "The expected GitOps path is present in merged main."
            else:
                state = "missing_from_main"
                reason = "The expected GitOps path is absent from merged main."
            checks.append(
                ComparisonCheck(
                    category="GitOps",
                    field=field_name,
                    desired=expected,
                    current=current,
                    state=state,
                    reason=reason,
                )
            )

    _compare(
        checks,
        "GitOps",
        "spec.gitOps.sourceRepository.value",
        _desired_source(_mapping(document, "spec", "gitOps"), "sourceRepository"),
        apps.source_repository,
    )

    open_prs = [pull for pull in apps.pull_requests if pull.state.value == "open"]
    checks.append(
        ComparisonCheck(
            category="Pull requests",
            field="relevant_pull_requests",
            desired="No relevant open pull requests",
            current={
                "matching_pr_count": len(apps.pull_requests),
                "open_pr_count": len(open_prs),
            },
            state="pr_open" if open_prs else "matches_main",
            reason=(
                f"{len(open_prs)} relevant pull request(s) are open."
                if open_prs
                else "No relevant pull requests are open."
            ),
        )
    )

    return ComparisonReport(
        environment=environment,
        kind="Environment",
        checks=checks,
    )


def compare_infra(
    document: Any,
    environment: Environment,
    observation: InfraObservation,
    apps: AppsObservation | None = None,
) -> ComparisonReport:
    """Compare an InfraCluster desired-state document with current main."""

    checks: list[ComparisonCheck] = []
    metadata = _mapping(document, "metadata")
    spec = _mapping(document, "spec")
    inventory = _mapping(document, "spec", "inventory")
    hub_inventory = _mapping(document, "spec", "hubInventory")
    variables = _mapping(document, "spec", "variables")
    variable_fields = _mapping(document, "spec", "variables", "fields")

    _compare(
        checks,
        "Metadata",
        "metadata.environment.value",
        _desired_source(metadata, "environment"),
        environment.name,
    )
    _compare(
        checks,
        "Metadata",
        "metadata.name.value",
        _desired_source(metadata, "name"),
        environment.infra_cluster,
    )
    _compare(
        checks,
        "Inventory",
        "spec.inventory.present.value",
        _desired_source(inventory, "present"),
        observation.inventory_present.value,
    )

    _compare(
        checks,
        "Hub inventory",
        "spec.hubInventory.present.value",
        _desired_source(hub_inventory, "present"),
        observation.hub_inventory.path_present.value,
    )
    _compare(
        checks,
        "Hub inventory",
        "spec.hubInventory.inventoryPresent.value",
        _desired_source(hub_inventory, "inventoryPresent"),
        observation.hub_inventory.inventory_present.value,
    )
    _compare(
        checks,
        "Hub inventory",
        "spec.hubInventory.clusterKeyPresent.value",
        _desired_source(hub_inventory, "clusterKeyPresent"),
        observation.hub_inventory.cluster_key_present.value,
    )

    _compare(
        checks,
        "Variables",
        "spec.variables.present.value",
        _desired_source(variables, "present"),
        observation.hub_variables.path_present.value,
    )
    for variable_name in (
        "cluster_domain_name",
        "base_domain",
        "machine_network",
        "api_ip",
        "ingress_ip",
        "dns_ip",
    ):
        desired_value = _desired_source(variable_fields, variable_name)
        current_value = (
            observation.hub_variables.values.value.get(variable_name)
            if isinstance(observation.hub_variables.values.value, dict)
            else _MISSING
        )
        _compare(
            checks,
            "Variables",
            f"spec.variables.fields.{variable_name}.value",
            desired_value,
            current_value,
        )

    desired_domain = _desired_source(spec, "domain")
    current_values = observation.hub_variables.values.value
    current_domain = (
        f"{current_values['cluster_domain_name']}.{current_values['base_domain']}"
        if isinstance(current_values, dict)
        and isinstance(current_values.get("cluster_domain_name"), str)
        and isinstance(current_values.get("base_domain"), str)
        else _MISSING
    )
    _compare(checks, "Domain", "spec.domain.value", desired_domain, current_domain)

    desired_clusters = inventory.get("clusters")
    desired_clusters = desired_clusters if isinstance(desired_clusters, dict) else {}
    current_clusters = observation.clusters
    for cluster_name, desired_cluster in desired_clusters.items():
        if cluster_name not in current_clusters:
            checks.append(
                ComparisonCheck(
                    category="Inventory",
                    field=f"spec.inventory.clusters.{cluster_name}",
                    desired="present",
                    current="missing",
                    state="missing_from_main",
                    reason="The desired-state cluster is absent from merged main.",
                )
            )
            continue
        current_cluster = current_clusters[cluster_name]
        _compare(
            checks,
            "Inventory",
            f"spec.inventory.clusters.{cluster_name}.name.value",
            _desired_source(desired_cluster, "name"),
            _current_source(current_cluster.cluster),
        )
        _compare(
            checks,
            "Inventory",
            f"spec.inventory.clusters.{cluster_name}.groupPresent.value",
            _desired_source(desired_cluster, "groupPresent"),
            _current_source(current_cluster.group_found),
        )
        _compare(
            checks,
            "Inventory",
            f"spec.inventory.clusters.{cluster_name}.hosts.value",
            _desired_source(desired_cluster, "hosts"),
            _current_source(current_cluster.hosts),
        )
        if "bootImage" in desired_cluster:
            desired_boot = _mapping(desired_cluster, "bootImage")
            desired_selected = _desired_source(desired_boot, "selected")
            boot_urls = current_cluster.boot_image_urls
            if len(boot_urls) > 1:
                checks.append(
                    ComparisonCheck(
                        category="Inventory",
                        field=f"spec.inventory.clusters.{cluster_name}.bootImage.selected.value",
                        desired=None if desired_selected is _MISSING else desired_selected,
                        current=None,
                        state="ambiguous",
                        reason="Merged main declares multiple boot image URLs.",
                    )
                )
            else:
                current_selected = boot_urls[0] if len(boot_urls) == 1 else None
                _compare(
                    checks,
                    "Inventory",
                    f"spec.inventory.clusters.{cluster_name}.bootImage.selected.value",
                    desired_selected,
                    current_selected,
                )

    for cluster_name in sorted(set(current_clusters) - set(desired_clusters)):
        checks.append(
            ComparisonCheck(
                category="Inventory",
                field=f"spec.inventory.clusters.{cluster_name}",
                desired="absent",
                current="present",
                state="unexpected_in_main",
                reason="Merged main contains a cluster absent from desired state.",
            )
        )

    if apps is not None:
        open_prs = [
            pull for pull in apps.pull_requests if pull.state.value == "open"
        ]
        if open_prs:
            state = "pr_open"
            reason = (
                f"{len(open_prs)} relevant pull request(s) are open; "
                "their changes are not in merged main."
            )
        else:
            state = "matches_main"
            reason = "No relevant pull requests are open."
        checks.append(
            ComparisonCheck(
                category="Pull requests",
                field="relevant_pull_requests",
                desired="No relevant open pull requests",
                current={
                    "matching_pr_count": len(apps.pull_requests),
                    "open_pr_count": len(open_prs),
                },
                state=state,
                reason=reason,
            )
        )

    return ComparisonReport(environment=environment, kind="Hub", checks=checks)


def _workload_boot_image_is_specific(url: Any, workload_cluster: str) -> bool:
    if not isinstance(url, str):
        return False
    image_name = url.rsplit("/", 1)[-1]
    aliases = [workload_cluster]
    if workload_cluster.startswith("oac-"):
        aliases.append(workload_cluster.removeprefix("oac-"))
    return any(alias in image_name for alias in aliases)


def compare_workload(
    document: Any,
    infra_observation: InfraObservation,
    apps_observation: AppsObservation | None = None,
) -> ComparisonReport:
    """Compare a WorkloadCluster desired-state document with current main."""

    environment = desired_environment(document)
    checks: list[ComparisonCheck] = []
    metadata = _mapping(document, "metadata")
    spec = _mapping(document, "spec")
    inventory = _mapping(document, "spec", "inventory")
    parent = _mapping(document, "spec", "parent")
    gitops = _mapping(document, "spec", "gitOps")

    workload_name = _desired_source(metadata, "name")
    parent_name = _desired_source(metadata, "parentInfraCluster")
    environment_name = _desired_source(metadata, "environment")

    _compare(
        checks,
        "Metadata",
        "metadata.environment.value",
        environment_name,
        environment.name,
    )
    _compare(
        checks,
        "Metadata",
        "metadata.name.value",
        workload_name,
        environment.workload_cluster,
    )
    _compare(
        checks,
        "Metadata",
        "metadata.parentInfraCluster.value",
        parent_name,
        environment.infra_cluster,
    )

    referenced_infra_present = (
        isinstance(parent_name, str) and parent_name in infra_observation.clusters
    )
    checks.append(
        ComparisonCheck(
            category="Parent references",
            field="metadata.parentInfraCluster",
            desired=parent_name,
            current=(
                "present"
                if referenced_infra_present
                else f"expected {environment.infra_cluster}"
            ),
            state="matches_main" if referenced_infra_present else "missing_from_main",
            reason=(
                "The referenced parent hub cluster exists in merged main."
                if referenced_infra_present
                else "The referenced parent hub cluster is absent from merged main."
            ),
        )
    )

    current_values = infra_observation.hub_variables.values.value
    current_domain = (
        f"{current_values['cluster_domain_name']}.{current_values['base_domain']}"
        if isinstance(current_values, dict)
        and isinstance(current_values.get("cluster_domain_name"), str)
        and isinstance(current_values.get("base_domain"), str)
        else _MISSING
    )
    _compare(
        checks,
        "Parent references",
        "spec.parent.domain.value",
        _desired_source(parent, "domain"),
        current_domain,
    )
    _compare(
        checks,
        "Parent references",
        "spec.parent.network.machineNetwork.value",
        _desired_source(_mapping(parent, "network"), "machineNetwork"),
        (
            current_values.get("machine_network")
            if isinstance(current_values, dict)
            else _MISSING
        ),
    )

    workload_exists = (
        isinstance(workload_name, str) and workload_name in infra_observation.clusters
    )
    checks.append(
        ComparisonCheck(
            category="Inventory",
            field="metadata.name",
            desired=workload_name,
            current="present" if workload_exists else "missing",
            state="matches_main" if workload_exists else "missing_from_main",
            reason=(
                "The workload cluster exists in the current inventory."
                if workload_exists
                else "The workload cluster is absent from the current inventory."
            ),
        )
    )
    if workload_exists:
        current_cluster = infra_observation.clusters[workload_name]
        _compare(
            checks,
            "Inventory",
            "spec.inventory.groupPresent.value",
            _desired_source(inventory, "groupPresent"),
            _current_source(current_cluster.group_found),
        )
        _compare(
            checks,
            "Inventory",
            "spec.inventory.hostCount.value",
            _desired_source(inventory, "hostCount"),
            len(current_cluster.hosts.value),
        )
        _compare(
            checks,
            "Inventory",
            "spec.inventory.hosts.value",
            _desired_source(inventory, "hosts"),
            _current_source(current_cluster.hosts),
        )

        desired_boot = _desired_source(_mapping(inventory, "bootImage"), "selected")
        boot_urls = current_cluster.boot_image_urls
        if len(boot_urls) > 1:
            checks.append(
                ComparisonCheck(
                    category="Inventory",
                    field="spec.inventory.bootImage.selected.value",
                    desired=None if desired_boot is _MISSING else desired_boot,
                    current=None,
                    state="ambiguous",
                    reason="Merged main declares multiple boot image URLs.",
                )
            )
        else:
            current_boot = boot_urls[0] if len(boot_urls) == 1 else None
            _compare(
                checks,
                "Inventory",
                "spec.inventory.bootImage.selected.value",
                desired_boot,
                current_boot,
            )
        boot_is_specific = _workload_boot_image_is_specific(
            desired_boot,
            workload_name,
        )
        checks.append(
            ComparisonCheck(
                category="Inventory",
                field="spec.inventory.bootImage.selected.clusterSpecific",
                desired=True,
                current=boot_is_specific,
                state="matches_main" if boot_is_specific else "value_mismatch",
                reason=(
                    "The selected boot image identifies the workload cluster."
                    if boot_is_specific
                    else "The selected boot image does not identify the workload cluster."
                ),
            )
        )

    if apps_observation is not None:
        paths = set(apps_observation.paths.value)
        hosted = _mapping(gitops, "hostedClusterValues")
        components = _mapping(gitops, "componentValues")
        applications = _mapping(gitops, "applications")
        expected_hosted_path = (
            f"hosted-clusters/{environment.infra_cluster}/"
            f"{environment.workload_cluster}/values.yaml"
        )
        expected_component_prefix = (
            f"values/{environment.infra_cluster}/{environment.workload_cluster}/"
        )
        expected_application_prefix = (
            f"apps/{environment.infra_cluster}/{environment.workload_cluster}/"
        )

        desired_hosted_path = _desired_source(hosted, "path")
        hosted_path_correct = desired_hosted_path == expected_hosted_path
        checks.append(
            ComparisonCheck(
                category="GitOps references",
                field="spec.gitOps.hostedClusterValues.path.value",
                desired=desired_hosted_path,
                current=expected_hosted_path,
                state="matches_main" if hosted_path_correct else "value_mismatch",
                reason=(
                    "The hosted-cluster path references the correct infra and workload clusters."
                    if hosted_path_correct
                    else "The hosted-cluster path does not reference the correct clusters."
                ),
            )
        )
        hosted_present = expected_hosted_path in paths
        checks.append(
            ComparisonCheck(
                category="GitOps presence",
                field="spec.gitOps.hostedClusterValues.present",
                desired=True,
                current=hosted_present,
                state="matches_main" if hosted_present else "missing_from_main",
                reason=(
                    "The hosted-cluster values file exists in merged main."
                    if hosted_present
                    else "The hosted-cluster values file is absent from merged main."
                ),
            )
        )

        desired_component_prefix = _desired_source(components, "prefix")
        component_prefix_correct = (
            desired_component_prefix == expected_component_prefix
        )
        checks.append(
            ComparisonCheck(
                category="GitOps references",
                field="spec.gitOps.componentValues.prefix.value",
                desired=desired_component_prefix,
                current=expected_component_prefix,
                state="matches_main" if component_prefix_correct else "value_mismatch",
                reason=(
                    "The component-value prefix references the correct clusters."
                    if component_prefix_correct
                    else "The component-value prefix does not reference the correct clusters."
                ),
            )
        )
        current_component_paths = sorted(
            path for path in paths if path.startswith(expected_component_prefix)
        )
        _compare(
            checks,
            "GitOps presence",
            "spec.gitOps.componentValues.paths.value",
            _desired_source(components, "paths"),
            current_component_paths,
        )
        checks.append(
            ComparisonCheck(
                category="GitOps presence",
                field="spec.gitOps.componentValues.present",
                desired=True,
                current=bool(current_component_paths),
                state=(
                    "matches_main" if current_component_paths else "missing_from_main"
                ),
                reason=(
                    "Workload component values exist in merged main."
                    if current_component_paths
                    else "No workload component values exist in merged main."
                ),
            )
        )

        desired_application_prefix = _desired_source(applications, "prefix")
        application_prefix_correct = (
            desired_application_prefix == expected_application_prefix
        )
        checks.append(
            ComparisonCheck(
                category="GitOps references",
                field="spec.gitOps.applications.prefix.value",
                desired=desired_application_prefix,
                current=expected_application_prefix,
                state=(
                    "matches_main" if application_prefix_correct else "value_mismatch"
                ),
                reason=(
                    "The application prefix references the correct clusters."
                    if application_prefix_correct
                    else "The application prefix does not reference the correct clusters."
                ),
            )
        )
        current_application_paths = sorted(
            path for path in paths if path.startswith(expected_application_prefix)
        )
        _compare(
            checks,
            "GitOps presence",
            "spec.gitOps.applications.paths.value",
            _desired_source(applications, "paths"),
            current_application_paths,
        )
        _compare(
            checks,
            "GitOps presence",
            "spec.gitOps.applications.present",
            _desired_source(applications, "present"),
            bool(current_application_paths),
        )

        open_prs = [
            pull for pull in apps_observation.pull_requests if pull.state.value == "open"
        ]
        checks.append(
            ComparisonCheck(
                category="Pull requests",
                field="relevant_pull_requests",
                desired="No relevant open pull requests",
                current={
                    "matching_pr_count": len(apps_observation.pull_requests),
                    "open_pr_count": len(open_prs),
                },
                state="pr_open" if open_prs else "matches_main",
                reason=(
                    f"{len(open_prs)} relevant pull request(s) are open."
                    if open_prs
                    else "No relevant pull requests are open."
                ),
            )
        )

    return ComparisonReport(
        environment=environment,
        kind="Workload",
        checks=checks,
    )


def render_comparison_text(report: ComparisonReport) -> str:
    data = report.to_dict()
    lines = [
        "=" * 78,
        f"MOC {report.kind.lower()} comparison: {data['environment']['name']}",
        "=" * 78,
        f"Hub cluster: {data['environment']['infra_cluster']}",
        f"Overall:       {data['overall_state']}",
        "",
        "State summary:",
    ]
    for state, count in data["summary"]["state_counts"].items():
        lines.append(f"  {state:<22} {count}")
    lines.extend(["", "Detailed comparison:"])
    for check in report.checks:
        lines.extend(
            [
                "-" * 78,
                f"[{check.state}] {check.category} / {check.field}",
                f"  Reason:   {check.reason}",
                f"  Desired:  {json.dumps(check.desired, sort_keys=True, default=str)}",
                f"  Current:  {json.dumps(check.current, sort_keys=True, default=str)}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_comparison_json(report: ComparisonReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _markdown_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, sort_keys=True, default=str)
    else:
        rendered = str(value)
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def render_comparison_markdown(report: ComparisonReport) -> str:
    data = report.to_dict()
    state_symbols = {
        "matches_main": "✅",
        "missing_from_main": "❌",
        "value_mismatch": "🟡",
        "unexpected_in_main": "⚠️",
        "unsupported_check": "❓",
        "ambiguous": "❓",
        "pr_open": "🚧",
    }
    lines = [
        f"# 🔍 {report.kind} Desired-State Comparison",
        "",
        f"## `{data['environment']['name']}` — {data['overall_state']}",
        "",
        "This report compares reviewed desired state with merged repository `main`. It does not claim live cluster health.",
        "",
        "## Summary",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state, count in data["summary"]["state_counts"].items():
        lines.append(
            f"| {state_symbols.get(state, '•')} `{state}` | {count} |"
        )
    lines.extend(
        [
            "",
            "## Detailed comparison",
            "",
            "| Category | Field | Desired | Current | State | Reason |",
            "|---|---|---|---|---|---|",
        ]
    )
    for check in report.checks:
        lines.append(
            "| "
            f"{_markdown_value(check.category)} | "
            f"`{_markdown_value(check.field)}` | "
            f"`{_markdown_value(check.desired)}` | "
            f"`{_markdown_value(check.current)}` | "
            f"{state_symbols.get(check.state, '•')} `{check.state}` | "
            f"{_markdown_value(check.reason)} |"
        )
    return "\n".join(lines).rstrip() + "\n"
