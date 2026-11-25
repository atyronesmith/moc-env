"""Normalized observations from CCI-MOC repository configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import re
from typing import Any

import yaml

from .github import GitHubClient, GitHubError
from .model import Environment
from .repositories import (
    MOC_ISSUES_REPOSITORY,
    MOC_KEYCLOAK_REPOSITORY,
    OAC_APPS_REPOSITORY,
    OAC_INFRA_REPOSITORY,
)

INVENTORY_PATH = "infra/inventory/00hosts.yaml"
UPDATE_AGENTS_PATH = "infra/update-agents.yaml"
HARDWARE_NETWORK_DOC_PATH = (
    "docs/hardware-and-network-configuration.md"
)
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
                "bm_management": host.get("bm_management"),
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


def parse_hardware_resource_classes(markdown: str) -> dict[str, str]:
    """Read Node Name and Resource Class columns from hardware documentation."""

    lines = [line.strip() for line in markdown.splitlines()]
    values: dict[str, str] = {}
    for index, header in enumerate(lines[:-1]):
        if not header.startswith("|") or not header.endswith("|"):
            continue
        columns = [cell.strip() for cell in header.strip("|").split("|")]
        try:
            node_index = columns.index("Node Name")
            resource_index = columns.index("Resource Class")
        except ValueError:
            continue
        separator = lines[index + 1]
        if not separator.startswith("|") or not separator.endswith("|"):
            continue
        if not all(
            re.fullmatch(r":?-+:?", cell.strip())
            for cell in separator.strip("|").split("|")
        ):
            continue

        for row in lines[index + 2 :]:
            if not row.startswith("|") or not row.endswith("|"):
                break
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            if node_index >= len(cells) or resource_index >= len(cells):
                continue
            node_name = cells[node_index]
            resource_class = cells[resource_index]
            if node_name and resource_class:
                values[node_name] = resource_class
    return values


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
    near_match_client: KeycloakClientObservation | None
    source_repository: str
    source_path: str


@dataclass(frozen=True)
class PullRequestObservation:
    """A pull request relevant to an environment."""

    number: SourceValue
    title: SourceValue
    state: SourceValue
    head_ref: SourceValue
    head_sha: SourceValue
    url: SourceValue
    repository: SourceValue
    changed_files: SourceValue
    classification: SourceValue


@dataclass(frozen=True)
class AppsObservation:
    """Normalized oac-apps merged-main paths and in-flight pull requests."""

    paths: SourceValue
    pull_requests: tuple[PullRequestObservation, ...]
    source_repository: str
    source_ref: str = "main"
    files: dict[str, str] = field(default_factory=dict)
    pull_requests_unavailable: str | None = None


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
        if not self.environment.workload_clusters:
            raise ValueError("no workload cluster is declared for this hub")
        workload_cluster = self.environment.workload_cluster
        if workload_cluster is None:
            raise ValueError("no workload cluster is declared for this hub")
        return ObservedWorkloadCluster(
            inventory=self.infra.clusters[workload_cluster],
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
    update_agents_present: SourceValue
    hardware_resource_classes: SourceValue
    clusters: dict[str, ClusterInventoryObservation]
    discovered_workload_clusters: tuple[str, ...]
    workload_clusters: tuple[str, ...]
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
    emit(
        "Hardware and inventory",
        "read update-agents inputs required to label and approve agents",
        UPDATE_AGENTS_PATH,
    )
    update_agents_text = (
        client.get_file(OAC_INFRA_REPOSITORY, UPDATE_AGENTS_PATH)
        if UPDATE_AGENTS_PATH in tree
        else None
    )
    update_agents = yaml.safe_load(update_agents_text) if update_agents_text else None
    update_agents_supported = update_agents is None or isinstance(update_agents, dict)
    emit(
        "Hardware and inventory",
        "read hardware documentation for documented resource classes",
        HARDWARE_NETWORK_DOC_PATH,
    )
    hardware_doc_text = (
        client.get_file(OAC_INFRA_REPOSITORY, HARDWARE_NETWORK_DOC_PATH)
        if HARDWARE_NETWORK_DOC_PATH in tree
        else None
    )
    hardware_resource_classes = parse_hardware_resource_classes(
        hardware_doc_text or ""
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
    all_clusters = inventory_clusters(inventory_root)
    discovered_workloads = tuple(
        sorted(
            cluster
            for cluster in all_clusters
            if cluster.startswith(f"{environment.base_name}-")
            and cluster != environment.infra_cluster
        )
    )
    workload_clusters: tuple[str, ...]
    if environment.workload_clusters is None:
        fallback = environment.workload_cluster
        workload_clusters = discovered_workloads or ((fallback,) if fallback else ())
    else:
        workload_clusters = environment.workload_clusters
    cluster_observations: dict[str, ClusterInventoryObservation] = {}
    for cluster in (environment.infra_cluster, *workload_clusters):
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
        update_agents_present=SourceValue(
            update_agents_text is not None,
            OAC_INFRA_REPOSITORY,
            UPDATE_AGENTS_PATH,
            confidence="exact" if update_agents_supported else "unsupported",
        ),
        hardware_resource_classes=SourceValue(
            hardware_resource_classes,
            OAC_INFRA_REPOSITORY,
            HARDWARE_NETWORK_DOC_PATH,
            confidence="exact" if hardware_doc_text is not None else "missing",
        ),
        clusters=cluster_observations,
        discovered_workload_clusters=discovered_workloads,
        workload_clusters=workload_clusters,
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
    # MOC-issues is otherwise read through its issue endpoint. Resolve the ref
    # so report metadata can record the repository SHA without downloading a
    # tree whose paths are never used.
    client.resolve_commit(repository)
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
    client_name: str | None = None,
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
    try:
        client.resolve_commit(repository)
        text = client.get_file(repository, KEYCLOAK_PATH)
    except GitHubError as exc:
        if "(404)" not in str(exc):
            raise
        return KeycloakObservation(
            path_present=SourceValue(False, repository, KEYCLOAK_PATH),
            client=None,
            near_match_client=None,
            source_repository=repository,
            source_path=KEYCLOAK_PATH,
        )

    cluster = client_name or environment.infra_cluster
    pattern = re.compile(
        r'^\s*([A-Za-z0-9_-]+)\s*=\s*\{(.*?)^\s*\}',
        re.MULTILINE | re.DOTALL,
    )
    client_observation: KeycloakClientObservation | None = None
    near_match_observation: KeycloakClientObservation | None = None
    for match in pattern.finditer(text):
        block_name, block = match.groups()
        declared_cluster = _terraform_string(block, "cluster_name")
        observation = KeycloakClientObservation(
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
        if declared_cluster == cluster:
            client_observation = observation
            break
        if declared_cluster == environment.base_name or block_name == environment.base_name:
            near_match_observation = observation
    return KeycloakObservation(
        path_present=SourceValue(True, repository, KEYCLOAK_PATH),
        client=client_observation,
        near_match_client=near_match_observation,
        source_repository=repository,
        source_path=KEYCLOAK_PATH,
    )


def _pull_text(pull: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in (
            pull.get("title"),
            pull.get("body"),
            pull.get("head", {}).get("ref"),
        )
        if value
    )


def _changed_lines(files: tuple[dict[str, Any], ...]) -> str:
    lines: list[str] = []
    for file in files:
        patch = file.get("patch")
        if not isinstance(patch, str):
            continue
        lines.extend(
            line
            for line in patch.splitlines()
            if line.startswith(("+", "-"))
        )
    return "\n".join(lines)


def _body_links_issue(pull: dict[str, Any], environment: Environment) -> bool:
    if environment.issue_number is None:
        return False
    issue_url = (
        f"https://github.com/CCI-MOC/MOC-issues/issues/"
        f"{environment.issue_number}"
    )
    body = pull.get("body")
    return isinstance(body, str) and issue_url in body


def read_apps_observation(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None = None,
    include_pull_requests: bool = True,
    path_scope: str = "environment",
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
    values_files: dict[str, str] = {}
    for path in tree:
        if path.startswith("hosted-clusters/") and path.endswith("/values.yaml"):
            try:
                values_files[path] = client.get_file(repository, path)
            except GitHubError:
                pass
    hub = environment.infra_cluster
    environment_path_prefixes = (
        f"hosted-clusters/{hub}/",
        f"values/{hub}/",
        f"apps/{hub}/",
    )
    workload_path_prefixes = tuple(
        prefix
        for workload in environment.workload_clusters or ()
        for prefix in (
            f"hosted-clusters/{hub}/{workload}/",
            f"values/{hub}/{workload}/",
            f"apps/{hub}/{workload}/",
        )
    )

    def changes_environment_path(path: str) -> bool:
        if path_scope == "workload":
            return path.startswith(workload_path_prefixes)
        if not path.startswith(environment_path_prefixes):
            return False
        return path_scope != "hub" or not path.startswith(workload_path_prefixes)

    pull_requests: list[PullRequestObservation] = []
    pull_request_errors: list[str] = []
    if include_pull_requests:
        pull_repositories = (
            OAC_APPS_REPOSITORY,
            OAC_INFRA_REPOSITORY,
            MOC_KEYCLOAK_REPOSITORY,
        )
        for pull_repository in pull_repositories:
            if progress is not None:
                progress(
                    "GitOps configuration",
                    "inspect pull-request file lists for environment-relevant changes",
                    pull_repository,
                    "pulls?state=open",
                )
            try:
                all_pulls = list(client.pulls(pull_repository, state="open"))
                if any(
                    not isinstance(pull, dict)
                    or type(pull.get("number")) is not int
                    or pull.get("state") not in ("open", "closed")
                    or (pull.get("head") is not None and not isinstance(pull["head"], dict))
                    for pull in all_pulls
                ):
                    raise GitHubError("Malformed pull-request record in GitHub response")
                all_pulls = [
                    {**pull, "head": pull.get("head") or {}}
                    for pull in all_pulls
                ]
            except Exception as exc:
                # PR context is optional: even a malformed payload or client
                # failure must not discard repository configuration evidence.
                pull_request_errors.append(f"{pull_repository}: {exc}")
                continue
            candidates = [
                pull
                for pull in all_pulls
                if pull.get("state") == "open"
            ]
            for pull in candidates:
                try:
                    file_observations = tuple(client.pr_files(pull_repository, pull["number"]))
                    if any(
                        not isinstance(file, dict)
                        or not isinstance(file.get("filename"), str)
                        or not file["filename"]
                        for file in file_observations
                    ):
                        raise GitHubError("Malformed pull-request file record in GitHub response")
                except Exception as exc:
                    pull_request_errors.append(
                        f"{pull_repository}#{pull['number']}: {exc}"
                    )
                    continue
                files = tuple(
                    str(file["filename"]) for file in file_observations
                )
                issue_linked = _body_links_issue(pull, environment)
                matching_files: tuple[str, ...] = ()

                if issue_linked:
                    matching_files = files
                elif pull_repository == OAC_APPS_REPOSITORY:
                    matching_files = tuple(
                        path for path in files if changes_environment_path(path)
                    )
                elif pull_repository == OAC_INFRA_REPOSITORY:
                    infra_paths = tuple(
                        path
                        for path in files
                        if path == INVENTORY_PATH
                        or path == HUB_INVENTORY_PATH
                        or path.startswith(f"hub-images/group_vars/{hub}/")
                    )
                    if not infra_paths:
                        continue
                    cluster_names: tuple[str, ...]
                    if path_scope == "hub":
                        cluster_names = (hub,)
                    elif path_scope == "workload":
                        cluster_names = tuple(environment.workload_clusters or ())
                    else:
                        cluster_names = (
                            hub,
                            *(environment.workload_clusters or ()),
                        )
                    changed_lines = _changed_lines(
                        tuple(
                            file
                            for file in file_observations
                            if file.get("filename") in infra_paths
                        )
                    )
                    metadata_text = _pull_text(pull)
                    if not any(
                        cluster_name in changed_lines
                        or cluster_name in metadata_text
                        for cluster_name in cluster_names
                    ):
                        continue
                    matching_files = infra_paths
                elif pull_repository == MOC_KEYCLOAK_REPOSITORY:
                    if path_scope == "workload":
                        continue
                    keycloak_paths = tuple(
                        path for path in files if path == KEYCLOAK_PATH
                    )
                    if not keycloak_paths:
                        continue
                    changed_lines = _changed_lines(
                        tuple(
                            file
                            for file in file_observations
                            if file.get("filename") == KEYCLOAK_PATH
                        )
                    )
                    metadata_text = _pull_text(pull)
                    if hub not in changed_lines and hub not in metadata_text:
                        continue
                    matching_files = keycloak_paths

                if not matching_files:
                    continue
                source = (pull_repository, f"pulls/{pull['number']}", "open")
                files_source = (
                    pull_repository,
                    f"pulls/{pull['number']}/files",
                    "open",
                )
                pull_requests.append(
                    PullRequestObservation(
                        number=SourceValue(pull["number"], *source),
                        title=SourceValue(pull.get("title"), *source),
                        state=SourceValue(pull.get("state"), *source),
                        head_ref=SourceValue(
                            pull.get("head", {}).get("ref"), *source
                        ),
                        head_sha=SourceValue(
                            pull.get("head", {}).get("sha"), *source
                        ),
                        url=SourceValue(pull.get("html_url"), *source),
                        repository=SourceValue(pull_repository, *source),
                        changed_files=SourceValue(matching_files, *files_source),
                        classification=SourceValue("open", *source),
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
        files=values_files,
        pull_requests_unavailable=(
            "\n".join(pull_request_errors) if pull_request_errors else None
        ),
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
    path_scope: str = "environment",
    keycloak_client_name: str | None = None,
) -> ObservedEnvironment:
    """Read all Phase 1 observations for an environment."""

    issue = read_issue_observation(client, environment, progress)
    infra = read_infra_observation(client, environment, progress)
    if environment.workload_clusters is None:
        environment = replace(
            environment,
            workload_clusters=infra.discovered_workload_clusters,
        )
    else:
        environment = replace(environment, workload_clusters=infra.workload_clusters)
    keycloak = read_keycloak_observation(
        client,
        environment,
        progress,
        client_name=keycloak_client_name,
    )
    apps = read_apps_observation(
        client,
        environment,
        progress,
        include_pull_requests=include_pull_requests,
        path_scope=path_scope,
    )
    return ObservedEnvironment(
        environment=environment,
        issue=issue,
        infra=infra,
        keycloak=keycloak,
        apps=apps,
    )
