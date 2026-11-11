"""Normalized observations from CCI-MOC repository configuration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import yaml

from .github import GitHubClient
from .model import Environment

OAC_INFRA_REPOSITORY = "CCI-MOC/oac-infra"
INVENTORY_PATH = "infra/inventory/00hosts.yaml"
HUB_INVENTORY_PATH = "hub-images/inventory.yml"
ProgressCallback = Callable[[str, str, str, str], None]


def flatten_host(
    group: dict[str, Any], inherited: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Flatten an Ansible inventory group into effective host records."""

    values = dict(inherited or {})
    values.update(group.get("vars", {}))
    hosts: list[dict[str, Any]] = []

    for name, details in group.get("hosts", {}).items():
        if not isinstance(details, dict):
            continue
        hosts.append({"name": name, **values, **details})

    for child in group.get("children", {}).values():
        if isinstance(child, dict):
            hosts.extend(flatten_host(child, values))
    return hosts


def find_cluster_group(node: Any, cluster: str) -> dict[str, Any] | None:
    """Find an inventory group whose vars.cluster matches ``cluster``."""

    if not isinstance(node, dict):
        return None
    variables = node.get("vars")
    if isinstance(variables, dict) and variables.get("cluster") == cluster:
        return node
    for child in node.get("children", {}).values():
        found = find_cluster_group(child, cluster)
        if found is not None:
            return found
    return None


def inventory_clusters(node: Any) -> list[str]:
    """Return all values of vars.cluster in an Ansible inventory."""

    clusters: list[str] = []
    if not isinstance(node, dict):
        return clusters
    variables = node.get("vars")
    if isinstance(variables, dict) and isinstance(variables.get("cluster"), str):
        clusters.append(variables["cluster"])
    for child in node.get("children", {}).values():
        clusters.extend(inventory_clusters(child))
    return sorted(set(clusters))


@dataclass(frozen=True)
class ClusterInventoryObservation:
    """Normalized inventory observation for one infra or workload cluster."""

    cluster: str
    group_found: bool
    hosts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def boot_image_urls(self) -> list[str]:
        return sorted(
            {
                host["boot_image_url"]
                for host in self.hosts
                if host.get("boot_image_url")
            }
        )

    def host_summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "name": host.get("name"),
                "node_name": host.get("node_name"),
                "bmc_addr": host.get("bmc_addr"),
                "boot_image_url": host.get("boot_image_url"),
            }
            for host in self.hosts
        ]


@dataclass(frozen=True)
class HubInventoryObservation:
    """Normalized hub-image inventory observation."""

    path_present: bool
    inventory_present: bool
    cluster_key_present: bool


@dataclass(frozen=True)
class HubVariablesObservation:
    """Normalized hub-image group-variable observation."""

    path_present: bool
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InfraObservation:
    """Repository-declared inputs for one infra cluster and its workload."""

    repository: str
    inventory_path: str
    hub_inventory_path: str
    variables_path: str
    inventory_present: bool
    clusters: dict[str, ClusterInventoryObservation]
    hub_inventory: HubInventoryObservation
    hub_variables: HubVariablesObservation


def read_infra_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
) -> InfraObservation:
    """Read and normalize the current oac-infra repository state."""

    def emit(stage: str, action: str, path: str) -> None:
        if progress is not None:
            progress(stage, action, OAC_INFRA_REPOSITORY, path)

    emit(
        "Hardware and inventory",
        "read the Ansible inventory to find infra and workload host groups",
        INVENTORY_PATH,
    )
    tree = client.get_tree(OAC_INFRA_REPOSITORY)
    inventory_text = (
        client.get_file(OAC_INFRA_REPOSITORY, INVENTORY_PATH)
        if INVENTORY_PATH in tree
        else None
    )
    inventory = yaml.safe_load(inventory_text) if inventory_text else None
    inventory_root = (
        inventory.get("all", inventory) if isinstance(inventory, dict) else inventory
    )
    cluster_observations: dict[str, ClusterInventoryObservation] = {}
    for cluster in (environment.infra_cluster, environment.workload_cluster):
        group = find_cluster_group(inventory_root, cluster)
        hosts = flatten_host(group) if group else []
        cluster_observations[cluster] = ClusterInventoryObservation(
            cluster=cluster,
            group_found=group is not None,
            hosts=hosts,
        )

    emit(
        "Cluster build",
        "read the hub-image inventory to confirm the infra cluster can generate a hub image",
        HUB_INVENTORY_PATH,
    )
    hub_text = (
        client.get_file(OAC_INFRA_REPOSITORY, HUB_INVENTORY_PATH)
        if HUB_INVENTORY_PATH in tree
        else None
    )
    hub_inventory = yaml.safe_load(hub_text) if hub_text else {}
    hub_children = (
        hub_inventory.get("all", {}).get("children", {}) or {}
        if isinstance(hub_inventory, dict)
        else {}
    )
    hub_observation = HubInventoryObservation(
        path_present=HUB_INVENTORY_PATH in tree,
        inventory_present=bool(hub_inventory),
        cluster_key_present=environment.infra_cluster in hub_children,
    )

    variables_path = (
        f"hub-images/group_vars/{environment.infra_cluster}/vars.yml"
    )
    emit(
        "Cluster build",
        "read hub-image variables to verify domain, network, API, ingress, and DNS inputs",
        variables_path,
    )
    variables_text = (
        client.get_file(OAC_INFRA_REPOSITORY, variables_path)
        if variables_path in tree
        else None
    )
    parsed_values = yaml.safe_load(variables_text) if variables_text else {}
    values = parsed_values if isinstance(parsed_values, dict) else {}
    variables_observation = HubVariablesObservation(
        path_present=variables_path in tree,
        values=values,
    )

    return InfraObservation(
        repository=OAC_INFRA_REPOSITORY,
        inventory_path=INVENTORY_PATH,
        hub_inventory_path=HUB_INVENTORY_PATH,
        variables_path=variables_path,
        inventory_present=bool(inventory),
        clusters=cluster_observations,
        hub_inventory=hub_observation,
        hub_variables=variables_observation,
    )
