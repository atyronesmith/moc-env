"""Normalized observations from CCI-MOC repository configuration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import re
from typing import Any

import yaml

from .github import GitHubClient
from .model import Environment

OAC_INFRA_REPOSITORY = "CCI-MOC/oac-infra"
MOC_ISSUES_REPOSITORY = "CCI-MOC/MOC-issues"
MOC_KEYCLOAK_REPOSITORY = "CCI-MOC/moc-keycloak"
OAC_APPS_REPOSITORY = "CCI-MOC/oac-apps"
INVENTORY_PATH = "infra/inventory/00hosts.yaml"
HUB_INVENTORY_PATH = "hub-images/inventory.yml"
KEYCLOAK_PATH = "main.tf"
ProgressCallback = Callable[[str, str, str, str], None]


@dataclass(frozen=True)
class SourceValue:
    """One extracted value with its source and extraction confidence."""

    value: Any
    repository: str
    path: str
    ref: str = "main"
    confidence: str = "exact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "provenance": {
                "repository": self.repository,
                "path": self.path,
                "ref": self.ref,
            },
            "confidence": self.confidence,
        }


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
    children = node.get("children", {})
    child_nodes = children.values() if isinstance(children, dict) else []
    child_nodes = [
        *child_nodes,
        *(
            value
            for key, value in node.items()
            if key not in {"children", "hosts", "vars"} and isinstance(value, dict)
        ),
    ]
    for child in child_nodes:
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
    children = node.get("children", {})
    child_nodes = children.values() if isinstance(children, dict) else []
    child_nodes = [
        *child_nodes,
        *(
            value
            for key, value in node.items()
            if key not in {"children", "hosts", "vars"} and isinstance(value, dict)
        ),
    ]
    for child in child_nodes:
        clusters.extend(inventory_clusters(child))
    return sorted(set(clusters))


@dataclass(frozen=True)
class ClusterInventoryObservation:
    """Normalized inventory observation for one infra or workload cluster."""

    cluster: SourceValue
    group_found: SourceValue
    hosts: SourceValue

    @property
    def boot_image_urls(self) -> list[str]:
        return sorted(
            {
                host["boot_image_url"]
                for host in self.hosts.value
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
            for host in self.hosts.value
        ]


@dataclass(frozen=True)
class HubInventoryObservation:
    """Normalized hub-image inventory observation."""

    path_present: SourceValue
    inventory_present: SourceValue
    cluster_key_present: SourceValue


@dataclass(frozen=True)
class HubVariablesObservation:
    """Normalized hub-image group-variable observation."""

    path_present: SourceValue
    values: SourceValue


@dataclass(frozen=True)
class IssueObservation:
    """Normalized MOC issue intent."""

    issue_number: int
    state: SourceValue
    title: SourceValue
    url: SourceValue


@dataclass(frozen=True)
class KeycloakClientObservation:
    """Normalized Keycloak OIDC declaration for one hub cluster."""

    block_name: SourceValue
    cluster_name: SourceValue
    redirect_uri: SourceValue
    secret_name: SourceValue


@dataclass(frozen=True)
class KeycloakObservation:
    """Normalized moc-keycloak state."""

    path_present: SourceValue
    client: KeycloakClientObservation | None
    source_repository: str
    source_path: str


@dataclass(frozen=True)
class PullRequestObservation:
    """A pull request relevant to an environment."""

    number: SourceValue
    title: SourceValue
    state: SourceValue
    merged: SourceValue
    head_ref: SourceValue
    head_sha: SourceValue
    url: SourceValue
    changed_files: SourceValue


@dataclass(frozen=True)
class AppsObservation:
    """Normalized oac-apps merged-main paths and in-flight pull requests."""

    paths: SourceValue
    pull_requests: tuple[PullRequestObservation, ...]
    source_repository: str
    source_ref: str = "main"


@dataclass(frozen=True)
class ChartValueObservation:
    """One leaf value from an oac-apps values file."""

    key: SourceValue
    value: SourceValue


@dataclass(frozen=True)
class ChartValuesFileObservation:
    """One parsed oac-apps values file."""

    path: SourceValue
    present: SourceValue
    scope: SourceValue
    chart: SourceValue
    values: SourceValue
    entries: tuple[ChartValueObservation, ...]


@dataclass(frozen=True)
class ChartValuesScopeObservation:
    """All values files in one hub or workload scope."""

    scope: SourceValue
    prefix: SourceValue
    present: SourceValue
    files: tuple[ChartValuesFileObservation, ...]


@dataclass(frozen=True)
class ChartValuesObservation:
    """Normalized oac-apps chart-values documentation inputs."""

    scopes: tuple[ChartValuesScopeObservation, ...]
    source_repository: str
    source_ref: str = "main"


@dataclass(frozen=True)
class ChartValuesKeyObservation:
    """One configuration key aggregated across oac-apps values files."""

    key: SourceValue
    scopes: SourceValue
    charts: SourceValue
    types: SourceValue
    file_count: SourceValue
    paths: SourceValue


@dataclass(frozen=True)
class ChartValuesReferenceObservation:
    """A repository-wide, environment-independent chart-values reference."""

    files: tuple[ChartValuesFileObservation, ...]
    keys: tuple[ChartValuesKeyObservation, ...]
    source_repository: str
    source_ref: str = "main"


@dataclass(frozen=True)
class ObservedWorkloadCluster:
    """Observed inputs for one workload cluster."""

    inventory: ClusterInventoryObservation
    apps: AppsObservation


@dataclass(frozen=True)
class ObservedEnvironment:
    """Combined repository observations for one environment."""

    environment: Environment
    issue: IssueObservation | None
    infra: InfraObservation
    keycloak: KeycloakObservation
    apps: AppsObservation

    @property
    def infra_cluster(self) -> ClusterInventoryObservation:
        return self.infra.clusters[self.environment.infra_cluster]

    @property
    def workload_cluster(self) -> ObservedWorkloadCluster:
        return ObservedWorkloadCluster(
            inventory=self.infra.clusters[self.environment.workload_cluster],
            apps=self.apps,
        )


@dataclass(frozen=True)
class InfraObservation:
    """Repository-declared inputs for one hub cluster and its workload."""

    repository: str
    inventory_path: str
    hub_inventory_path: str
    variables_path: str
    inventory_present: SourceValue
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
    inventory_supported = inventory is None or isinstance(inventory, dict)
    inventory_present = SourceValue(
        inventory is not None,
        OAC_INFRA_REPOSITORY,
        INVENTORY_PATH,
        confidence="exact" if inventory_supported else "unsupported",
    )
    cluster_observations: dict[str, ClusterInventoryObservation] = {}
    for cluster in (environment.infra_cluster, environment.workload_cluster):
        group = find_cluster_group(inventory_root, cluster)
        hosts = flatten_host(group) if group else []
        cluster_observations[cluster] = ClusterInventoryObservation(
            cluster=SourceValue(
                cluster,
                OAC_INFRA_REPOSITORY,
                INVENTORY_PATH,
                confidence="inferred",
            ),
            group_found=SourceValue(
                group is not None,
                OAC_INFRA_REPOSITORY,
                INVENTORY_PATH,
            ),
            hosts=SourceValue(
                tuple(hosts),
                OAC_INFRA_REPOSITORY,
                INVENTORY_PATH,
            ),
        )

    emit(
        "Cluster build",
        "read the hub-image inventory to confirm the hub cluster can generate a hub image",
        HUB_INVENTORY_PATH,
    )
    hub_text = (
        client.get_file(OAC_INFRA_REPOSITORY, HUB_INVENTORY_PATH)
        if HUB_INVENTORY_PATH in tree
        else None
    )
    hub_inventory = yaml.safe_load(hub_text) if hub_text else {}
    hub_inventory_supported = hub_inventory is None or isinstance(hub_inventory, dict)
    hub_children = (
        hub_inventory.get("all", {}).get("children", {}) or {}
        if isinstance(hub_inventory, dict)
        else {}
    )
    hub_observation = HubInventoryObservation(
        path_present=SourceValue(
            HUB_INVENTORY_PATH in tree,
            OAC_INFRA_REPOSITORY,
            HUB_INVENTORY_PATH,
        ),
        inventory_present=SourceValue(
            bool(hub_inventory),
            OAC_INFRA_REPOSITORY,
            HUB_INVENTORY_PATH,
            confidence="exact" if hub_inventory_supported else "unsupported",
        ),
        cluster_key_present=SourceValue(
            environment.infra_cluster in hub_children,
            OAC_INFRA_REPOSITORY,
            HUB_INVENTORY_PATH,
        ),
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
    values_supported = parsed_values is None or isinstance(parsed_values, dict)
    values = parsed_values if isinstance(parsed_values, dict) else {}
    variables_observation = HubVariablesObservation(
        path_present=SourceValue(
            variables_path in tree,
            OAC_INFRA_REPOSITORY,
            variables_path,
        ),
        values=SourceValue(
            values,
            OAC_INFRA_REPOSITORY,
            variables_path,
            confidence="exact" if values_supported else "unsupported",
        ),
    )

    return InfraObservation(
        repository=OAC_INFRA_REPOSITORY,
        inventory_path=INVENTORY_PATH,
        hub_inventory_path=HUB_INVENTORY_PATH,
        variables_path=variables_path,
        inventory_present=inventory_present,
        clusters=cluster_observations,
        hub_inventory=hub_observation,
        hub_variables=variables_observation,
    )


def read_issue_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
) -> IssueObservation | None:
    """Read and normalize the requested MOC issue."""

    if environment.issue_number is None:
        return None
    repository = MOC_ISSUES_REPOSITORY
    path = f"issues/{environment.issue_number}"
    if progress is not None:
        progress(
            "Request",
            f"read MOC issue #{environment.issue_number} to establish requested intent",
            repository,
            path,
        )
    issue = client.get_json(f"/repos/{repository}/{path}")
    source = (repository, path)
    return IssueObservation(
        issue_number=environment.issue_number,
        state=SourceValue(issue.get("state"), *source),
        title=SourceValue(issue.get("title"), *source),
        url=SourceValue(issue.get("html_url"), *source),
    )


def _terraform_string(text: str, key: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def read_keycloak_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
) -> KeycloakObservation:
    """Read and normalize the hub cluster's Keycloak OIDC client."""

    repository = MOC_KEYCLOAK_REPOSITORY
    if progress is not None:
        progress(
            "Identity",
            "read Terraform configuration to verify the hub cluster's Keycloak OIDC client",
            repository,
            KEYCLOAK_PATH,
        )
    tree = client.get_tree(repository)
    if KEYCLOAK_PATH not in tree:
        return KeycloakObservation(
            path_present=SourceValue(False, repository, KEYCLOAK_PATH),
            client=None,
            source_repository=repository,
            source_path=KEYCLOAK_PATH,
        )

    text = client.get_file(repository, KEYCLOAK_PATH)

    cluster = environment.infra_cluster
    pattern = re.compile(
        rf'^\s*([A-Za-z0-9_-]+)\s*=\s*\{{(.*?)^\s*\}}',
        re.MULTILINE | re.DOTALL,
    )
    client_observation: KeycloakClientObservation | None = None
    for match in pattern.finditer(text):
        block_name, block = match.groups()
        declared_cluster = _terraform_string(block, "cluster_name")
        if declared_cluster != cluster:
            continue
        client_observation = KeycloakClientObservation(
            block_name=SourceValue(block_name, repository, KEYCLOAK_PATH),
            cluster_name=SourceValue(declared_cluster, repository, KEYCLOAK_PATH),
            redirect_uri=SourceValue(
                _terraform_string(block, "openshift_redirect_uri"),
                repository,
                KEYCLOAK_PATH,
            ),
            secret_name=SourceValue(
                _terraform_string(block, "client_secret_name"),
                repository,
                KEYCLOAK_PATH,
            ),
        )
        break
    return KeycloakObservation(
        path_present=SourceValue(True, repository, KEYCLOAK_PATH),
        client=client_observation,
        source_repository=repository,
        source_path=KEYCLOAK_PATH,
    )


def read_apps_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
    include_pull_requests: bool = True,
) -> AppsObservation:
    """Read merged oac-apps paths and environment-relevant pull requests."""

    repository = OAC_APPS_REPOSITORY
    if progress is not None:
        progress(
            "GitOps configuration",
            "read the repository tree to locate merged infra and workload GitOps paths",
            repository,
            "git/trees/main?recursive=1",
        )
    tree = client.get_tree(repository)
    terms = (
        environment.name,
        environment.infra_cluster,
        environment.workload_cluster,
    )
    pull_requests: list[PullRequestObservation] = []
    if include_pull_requests:
        if progress is not None:
            progress(
                "GitOps configuration",
                "search pull requests for in-flight changes that reference the environment",
                repository,
                "pulls?state=all",
            )
        for pull in client.pulls(repository):
            searchable = " ".join(
                [
                    str(pull.get("title") or ""),
                    str(pull.get("body") or ""),
                    str(pull.get("head", {}).get("ref") or ""),
                ]
            )
            if not any(term in searchable for term in terms):
                continue
            files = tuple(
                file.get("filename")
                for file in client.pr_files(repository, pull["number"])
                if file.get("filename") is not None
            )
            source = (repository, f"pulls/{pull['number']}", "all")
            files_source = (
                repository,
                f"pulls/{pull['number']}/files",
                "all",
            )
            pull_requests.append(
                PullRequestObservation(
                    number=SourceValue(pull["number"], *source),
                    title=SourceValue(pull.get("title"), *source),
                    state=SourceValue(pull.get("state"), *source),
                    merged=SourceValue(bool(pull.get("merged_at")), *source),
                    head_ref=SourceValue(
                        pull.get("head", {}).get("ref"), *source
                    ),
                    head_sha=SourceValue(
                        pull.get("head", {}).get("sha"), *source
                    ),
                    url=SourceValue(pull.get("html_url"), *source),
                    changed_files=SourceValue(files, *files_source),
                )
            )
    return AppsObservation(
        paths=SourceValue(
            tuple(sorted(tree)),
            repository,
            "git/trees/main?recursive=1",
        ),
        pull_requests=tuple(pull_requests),
        source_repository=repository,
    )


def _flatten_chart_values(
    repository: str,
    path: str,
    values: dict[str, Any],
) -> tuple[ChartValueObservation, ...]:
    entries: list[ChartValueObservation] = []

    def visit(prefix: str, mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            entries.append(
                ChartValueObservation(
                    key=SourceValue(key_path, repository, path),
                    value=SourceValue(value, repository, path),
                )
            )
            if isinstance(value, dict):
                visit(key_path, value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        visit(f"{key_path}[]", item)
                    else:
                        entries.append(
                            ChartValueObservation(
                                key=SourceValue(f"{key_path}[]", repository, path),
                                value=SourceValue(item, repository, path),
                            )
                        )

    visit("", values)
    return tuple(entries)


def _chart_values_scope(path: str) -> str | None:
    """Classify an oac-apps values path into its deployment scope."""

    parts = path.split("/")
    if path.startswith("values/") and len(parts) >= 3:
        if parts[2] == "local-cluster":
            return "hub-local-cluster"
        if len(parts) > 3:
            return "workload-components"
        return "hub-wide"
    if path.startswith("hosted-clusters/"):
        if len(parts) == 3:
            return "hosted-cluster-defaults"
        return "hosted-cluster"
    return None


def read_chart_values_reference_observation(
    client: GitHubClient,
    progress: ProgressCallback | None = None,
) -> ChartValuesReferenceObservation:
    """Read a repository-wide, environment-independent values reference."""

    repository = OAC_APPS_REPOSITORY
    tree_source = "git/trees/main?recursive=1"
    if progress is not None:
        progress(
            "Chart values",
            "read all hub and hosted-cluster values files to build a general reference",
            repository,
            tree_source,
        )

    paths = sorted(
        path
        for path in client.get_tree(repository)
        if path.endswith((".yaml", ".yml"))
        and (path.startswith("values/") or path.startswith("hosted-clusters/"))
        and _chart_values_scope(path) is not None
    )
    files: list[ChartValuesFileObservation] = []
    aggregated: dict[str, dict[str, set[Any]]] = {}

    for path in paths:
        text = client.get_file(repository, path)
        parsed = yaml.safe_load(text) if text else None
        supported = parsed is None or isinstance(parsed, dict)
        values = parsed if isinstance(parsed, dict) else {}
        scope_name = _chart_values_scope(path)
        if scope_name is None:
            continue
        filename = path.rsplit("/", 1)[-1]
        if scope_name == "hosted-cluster" and filename == "values.yaml":
            chart_name = "hosted-cluster"
        elif scope_name == "hosted-cluster-defaults" and filename == "values.yaml":
            chart_name = "hosted-cluster-defaults"
        else:
            chart_name = filename.removesuffix(".yaml").removesuffix(".yml")

        entries = (
            _flatten_chart_values(repository, path, values) if supported else ()
        )
        files.append(
            ChartValuesFileObservation(
                path=SourceValue(path, repository, tree_source, confidence="inferred"),
                present=SourceValue(True, repository, path),
                scope=SourceValue(
                    scope_name,
                    repository,
                    path,
                    confidence="inferred",
                ),
                chart=SourceValue(
                    chart_name,
                    repository,
                    path,
                    confidence="inferred",
                ),
                values=SourceValue(
                    values,
                    repository,
                    path,
                    confidence="exact" if supported else "unsupported",
                ),
                entries=entries,
            )
        )

        for entry in entries:
            key = entry.key.value
            aggregate = aggregated.setdefault(
                key,
                {"scopes": set(), "charts": set(), "types": set(), "paths": set()},
            )
            aggregate["scopes"].add(scope_name)
            aggregate["charts"].add(chart_name)
            aggregate["types"].add(type(entry.value.value).__name__)
            aggregate["paths"].add(path)

    keys: list[ChartValuesKeyObservation] = []
    for key in sorted(aggregated):
        aggregate = aggregated[key]
        paths_for_key = sorted(aggregate["paths"])
        keys.append(
            ChartValuesKeyObservation(
                key=SourceValue(key, repository, paths_for_key[0]),
                scopes=SourceValue(
                    tuple(sorted(aggregate["scopes"])),
                    repository,
                    tree_source,
                    confidence="inferred",
                ),
                charts=SourceValue(
                    tuple(sorted(aggregate["charts"])),
                    repository,
                    tree_source,
                    confidence="inferred",
                ),
                types=SourceValue(
                    tuple(sorted(aggregate["types"])),
                    repository,
                    tree_source,
                    confidence="inferred",
                ),
                file_count=SourceValue(
                    len(paths_for_key),
                    repository,
                    tree_source,
                    confidence="inferred",
                ),
                paths=SourceValue(tuple(paths_for_key), repository, tree_source),
            )
        )

    return ChartValuesReferenceObservation(
        files=tuple(files),
        keys=tuple(keys),
        source_repository=repository,
    )


def read_environment_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
    include_pull_requests: bool = True,
) -> ObservedEnvironment:
    """Read all Phase 1 observations for an environment."""

    issue = read_issue_observation(client, environment, progress)
    infra = read_infra_observation(client, environment, progress)
    keycloak = read_keycloak_observation(client, environment, progress)
    apps = read_apps_observation(
        client,
        environment,
        progress,
        include_pull_requests=include_pull_requests,
    )
    return ObservedEnvironment(
        environment=environment,
        issue=issue,
        infra=infra,
        keycloak=keycloak,
        apps=apps,
    )
