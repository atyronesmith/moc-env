"""Configuration-state checks across CCI-MOC repositories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any

import yaml

from . import __version__
from .boot_image import image_is_specific

from .check_descriptions import DescriptionContext, apply_descriptions
from .github import GitHubClient, GitHubError, RateLimitError, github_url
from .report_fields import field_rows, failing_field_rows, plain
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
    read_infra_observation,
    read_keycloak_observation,
    read_environment_observation,
)
from .phases import annotate_and_sort_checks
from .registry import DEFAULT_REGISTRY_PATH, EnvironmentRegistry, RegistryError
from .suggestions import attach_suggestions

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
        "hosted-clusters/<hub>/values.yaml in CCI-MOC/oac-apps."
    ),
    "hub.component_values": (
        "Create or complete values/<hub>/hcp-config.yaml in CCI-MOC/oac-apps "
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
}


def _next_action(check_id: str, state: str) -> str | None:
    if state in {"declared_in_main", "requested", "pr_merged"}:
        return None
    return _NEXT_ACTIONS[check_id]


def _package_version() -> str:
    return __version__


def _safe_yaml_value(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


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
    if image_is_specific(url, cluster, hub_cluster):
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
        *,
        evaluate_prs: bool = True,
    ) -> StatusReport:
        try:
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
                checks.extend(
                    self._issue_checks(environment, observation.issue)
                )
            infra_checks, environment = self._infra_checks(
                environment, observation.infra
            )
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
        except RateLimitError:
            checks = annotate_and_sort_checks(
                self._rate_limited_checks(environment, path_scope)
            )
            self._apply_source_refs(checks)
            apply_descriptions(
                checks, self._description_context(environment, None)
            )
            checks = self._apply_deferred(checks, environment)
            return StatusReport(
                environment=environment,
                checks=checks,
                overall_state="UNKNOWN",
                metadata=self._metadata(),
                rate_limited=True,
            )
        checks = annotate_and_sort_checks(checks)
        self._apply_source_refs(checks)
        apply_descriptions(
            checks, self._description_context(environment, observation)
        )
        checks = self._apply_blocked_states(checks, environment)
        checks = self._apply_deferred(checks, environment)
        pulls = self._pull_request_evidence(observation.apps.pull_requests)
        if evaluate_prs and self.include_prs:
            self._evaluate_pr_candidates(
                environment,
                path_scope,
                checks,
                pulls,
                observation=observation,
            )
        attach_suggestions(
            self.client, environment, checks,
            lambda client: cross_repository_checks(
                client, environment, observation.infra, observation.apps
            ),
        )
        return StatusReport(
            environment=environment,
            checks=checks,
            overall_state=self._overall_state(checks),
            metadata=self._metadata(),
            pull_requests=pulls,
            pull_requests_unavailable=observation.apps.pull_requests_unavailable,
            pull_requests_skipped=not self.include_prs,
            pull_requests_skip_reason=(
                "skipped (--no-prs)" if not self.include_prs else None
            ),
        )

    @staticmethod
    def _path_matches(changed: str, expected: str) -> bool:
        return changed == expected or changed.startswith(expected.rstrip("/") + "/")

    def _candidate_input_paths(
        self, check: CheckResult, environment: Environment
    ) -> tuple[tuple[str, str], ...]:
        """Return all repository paths that can change this check's inputs.

        ``CheckResult.repository`` is the repository used for the primary
        evidence, but several cross-repository checks consume values from more
        than one repository.  Keeping this map here makes PR candidacy follow
        the actual data flow instead of the display path alone.
        """

        paths: list[tuple[str, str]] = []

        def add(repository: str, path: str | None) -> None:
            if path:
                item = (repository, path)
                if item not in paths:
                    paths.append(item)

        add(check.repository, check.path)
        for path in check.evidence.get("expected_paths", []):
            if isinstance(path, str):
                add(check.repository, path)

        infra = OAC_INFRA_REPOSITORY
        apps = "CCI-MOC/oac-apps"
        switches = "CCI-MOC/ansible-switches"
        hub = environment.infra_cluster
        workloads = environment.workload_clusters or ()
        workload_values = [
            f"hosted-clusters/{hub}/{workload}/values.yaml"
            for workload in workloads
        ]
        hub_defaults = f"hosted-clusters/{hub}/values.yaml"

        if check.id == "workload.agent_labels_inputs":
            add(infra, "infra/inventory/00hosts.yaml")
            add(infra, UPDATE_AGENTS_PATH)
            add(infra, HARDWARE_NETWORK_DOC_PATH)
        elif check.id in {
            "workload.api_address_network",
            "workload.ingress_address_network",
            "workload.dns_base_domain",
            "workload.node_pool_hosts",
            "workload.gpu_without_hosts",
            "workload.keycloak_oidc_client",
            "workload.identity_provider",
        }:
            for path in workload_values:
                add(apps, path)

            if check.id in {
                "workload.api_address_network",
                "workload.ingress_address_network",
            }:
                add(infra, f"hub-images/group_vars/{hub}/vars.yml")
            if check.id == "workload.ingress_address_network":
                add(switches, "group_vars/all/vlans.yaml")
            if check.id in {
                "workload.dns_base_domain",
                "workload.keycloak_oidc_client",
                "workload.identity_provider",
            }:
                add(apps, hub_defaults)
            if check.id in {
                "workload.node_pool_hosts",
                "workload.gpu_without_hosts",
            }:
                add(infra, "infra/inventory/00hosts.yaml")
                add(infra, HARDWARE_NETWORK_DOC_PATH)
            if check.id in {
                "workload.keycloak_oidc_client",
                "workload.identity_provider",
            }:
                add("CCI-MOC/moc-keycloak", "main.tf")
        elif check.id in {
            "workload.address_uniqueness",
            "workload.address_internal_duplicates",
        }:
            # The check compares every hosted-cluster values file to detect
            # duplicate addresses, not only the current workload file.
            add(apps, "hosted-clusters/")
        elif check.id == "hub.moc_dns_records":
            add(infra, f"hub-images/group_vars/{hub}/vars.yml")

        return tuple(paths)

    @staticmethod
    def _candidate_field_rows(check: CheckResult) -> list[list[Any]]:
        """Project comparison rows to fields consumed by this check.

        Some checks expose useful context in ``actual`` that is not an input
        to the check.  In particular, moc-aws OIDC checks include secret-prefix
        context while validating only ``cluster_name``; a PR changing that
        context must not produce a misleading annotation.
        """

        if check.id.endswith(".moc_aws_oidc_cluster"):
            expected = check.expected if isinstance(check.expected, dict) else {}
            actual = check.actual if isinstance(check.actual, dict) else {}
            return [["cluster_name", expected.get("cluster_name"), actual.get("cluster_name")]]
        return field_rows(check.to_dict())

    def _candidate_check_results(
        self,
        environment,
        path_scope,
        repository: str,
        affected_ids: set[str],
        changed_files: list[str],
        observation,
    ) -> list[CheckResult]:
        """Evaluate only checks affected by one candidate repository.

        The baseline observations are reused for unchanged repositories.  A
        candidate ref is read only for the repository under review, then the
        relevant check families are recomputed from the mixed observation.
        """

        refs = self.client.refs
        snapshots = self.client.source_snapshots.copy()
        try:
            # The caller installs the pull/<n>/head ref around this method.
            infra = observation.infra
            apps = observation.apps
            candidate_environment = environment
            results: list[CheckResult] = []

            if repository == OAC_INFRA_REPOSITORY:
                infra = read_infra_observation(
                    self.client, environment, progress=self._emit_progress
                )
                infra_results, candidate_environment = self._infra_checks(
                    environment, infra
                )
                if any(item.id in affected_ids for item in infra_results):
                    results.extend(
                        item for item in infra_results if item.id in affected_ids
                    )

            if repository == "CCI-MOC/oac-apps":
                apps = self._candidate_apps_observation(
                    candidate_environment,
                    observation.apps,
                    affected_ids,
                    changed_files,
                )
                app_results = self._apps_checks(candidate_environment, apps)
                results.extend(
                    item for item in app_results if item.id in affected_ids
                )

            if repository == "CCI-MOC/moc-keycloak":
                candidate_keycloak = read_keycloak_observation(
                    self.client,
                    candidate_environment,
                    progress=self._emit_progress,
                    client_name=self.registry.keycloak_client_name(
                        candidate_environment.name
                    ),
                )
                keycloak_results = self._keycloak_checks(
                    candidate_environment, candidate_keycloak
                )
                results.extend(
                    item for item in keycloak_results if item.id in affected_ids
                )

            cross_ids = {
                item
                for item in affected_ids
                if item.startswith(("hub.", "workload."))
                and item
                not in {
                    "hub.inventory",
                    "hub.boot_image",
                    "workload.inventory",
                    "workload.boot_image",
                    "workload.agent_labels_inputs",
                    "hub.image_inventory",
                    "hub.image_vars",
                    "hub.hosted_cluster_defaults",
                    "hub.component_values",
                    "hub.local_cluster_values",
                    "hub.argocd_apps",
                    "workload.hosted_cluster_values",
                    "workload.component_values",
                    "hub.oidc_client",
                }
            }
            if cross_ids:
                cross_results = cross_repository_checks(
                    self.client,
                    candidate_environment,
                    infra,
                    apps,
                    self._emit_progress,
                )
                results.extend(item for item in cross_results if item.id in cross_ids)

            return results
        finally:
            # Candidate snapshots are evidence for the annotation only; never
            # leak them into the report's selected source set.
            self.client.refs = refs
            self.client.source_snapshots = snapshots

    def _candidate_apps_observation(
        self,
        environment: Environment,
        baseline,
        affected_ids: set[str],
        changed_files: list[str],
    ):
        """Overlay only candidate values files needed by affected checks.

        ``read_apps_observation`` intentionally loads every hosted-cluster
        values file for the normal report because address uniqueness is a
        repository-wide check.  A PR touching only paths/checks that do not
        need that comparison should not trigger those extra raw downloads.
        """

        repository = "CCI-MOC/oac-apps"
        tree = self.client.get_tree(repository)
        hub = environment.infra_cluster
        wanted = {
            path
            for path in changed_files
            if path.startswith("hosted-clusters/") and path.endswith("/values.yaml")
        }
        if affected_ids & {
            "workload.address_uniqueness",
        }:
            wanted.update(
                path
                for path in tree
                if path.startswith("hosted-clusters/")
                and path.endswith("/values.yaml")
            )
        if affected_ids & {
            "hub.hosted_cluster_defaults",
            "workload.dns_base_domain",
            "workload.keycloak_oidc_client",
        }:
            wanted.add(f"hosted-clusters/{hub}/values.yaml")
        for workload in environment.workload_clusters or ():
            if affected_ids & {
                "workload.address_internal_duplicates",
                "workload.hosted_cluster_values",
                "workload.api_address_network",
                "workload.ingress_address_network",
                "workload.dns_base_domain",
                "workload.node_pool_hosts",
                "workload.gpu_without_hosts",
                "workload.keycloak_oidc_client",
            }:
                wanted.add(
                    f"hosted-clusters/{hub}/{workload}/values.yaml"
                )

        files = dict(baseline.files)
        # A candidate deletion must hide the baseline file; changed files that
        # remain in the tree are fetched at the candidate ref below.
        for path in list(files):
            if path not in tree and path.startswith("hosted-clusters/"):
                files.pop(path, None)
        for path in sorted(wanted):
            if path not in tree:
                files.pop(path, None)
                continue
            try:
                files[path] = self.client.get_file(repository, path)
            except GitHubError:
                files.pop(path, None)

        return replace(
            baseline,
            paths=SourceValue(
                tuple(sorted(tree)),
                repository,
                "git/trees/main?recursive=1",
                ref=self.client.ref_for(repository),
            ),
            files=files,
            pull_requests=(),
            pull_requests_unavailable=None,
        )

    def _evaluate_pr_candidates(
        self, environment, path_scope, checks, pulls, *, observation
    ) -> None:
        """A changed file is only a candidate: compare the check's observed fields.

        Reuse the client's immutable response cache for unchanged repositories,
        but resolve each candidate repository at its PR head. Candidate snapshots
        must not replace the sources of the report being annotated.
        """
        passing = {"declared_in_main", "requested", "pr_merged"}
        candidates: dict[tuple[str, int], list[CheckResult]] = {}
        for check in checks:
            if check.state in passing and check.severity == "info":
                continue
            for pull in pulls:
                repository = pull["repository"]["value"]
                number = pull["number"]
                ref = f"pull/{number}/head"
                selected_ref = self.client.ref_for(repository)
                selected_refs = {
                    pull.get("head_sha", {}).get("value"),
                    ref,
                }
                if (
                    pull["classification"]["value"] != "open"
                    or selected_ref in selected_refs - {None}
                ):
                    continue
                dependencies = self._candidate_input_paths(check, environment)
                if not any(
                    repo == repository
                    and self._path_matches(changed, path)
                    for repo, path in dependencies
                    for changed in pull["changed_files"]
                ):
                    continue
                key = (repository, number)
                if key not in candidates:
                    refs = self.client.refs
                    try:
                        self.client.refs = {**refs, repository: ref}
                        candidates[key] = self._candidate_check_results(
                            environment,
                            path_scope,
                            repository,
                            {
                                item.id
                                for item in checks
                                if any(
                                    repo == repository
                                    and self._path_matches(changed, path)
                                    for repo, path in self._candidate_input_paths(
                                        item, environment
                                    )
                                    for changed in pull["changed_files"]
                                )
                            },
                            pull["changed_files"],
                            observation,
                        )
                    except GitHubError:
                        candidates[key] = []
                    finally:
                        self.client.refs = refs
                candidate = next((item for item in candidates[key]
                                if item.id == check.id and item.check == check.check), None)
                if candidate is None or candidate.state in {"unknown", "blocked"}:
                    continue
                before = self._candidate_field_rows(check)
                after = self._candidate_field_rows(candidate)
                if before == after:
                    continue
                label = f"{repository.removeprefix('CCI-MOC/')}#{number}"
                if candidate.state in passing and candidate.severity == "info":
                    annotation = f"fixed by open PR {label}"
                else:
                    failures = "; ".join(
                        f"{name} is {plain(observed)}; expected {plain(expected)}"
                        for name, expected, observed in failing_field_rows(candidate.to_dict())
                    )
                    annotation = f"open PR {label} touches this but the check still fails there: {failures}"
                check.evidence.setdefault("pr_evaluations", []).append(annotation)

    def _apply_source_refs(self, checks: list[CheckResult]) -> None:
        """Use the actual selected ref for checks and source links."""

        for check in checks:
            ref = self.client.ref_for(check.repository)
            check.ref = ref
            if check.url and "/blob/" in check.url:
                check.url = github_url(check.repository, check.path, ref)
            if check.source is not None:
                repository = check.source.get("repository", check.repository)
                check.source = {
                    **check.source,
                    "ref": self.client.ref_for(repository),
                }

    @staticmethod
    def _apply_blocked_states(
        checks: list[CheckResult], environment: Environment
    ) -> list[CheckResult]:
        by_key = {
            (check.id, check.cluster): check for check in checks
        }
        hub_cluster = environment.infra_cluster
        results = []
        for check in checks:
            blockers = []
            for item in check.blocked_by:
                blocker = by_key.get((item, check.cluster))
                if blocker is None:
                    blocker = by_key.get((item, hub_cluster))
                if blocker is not None and blocker.state == "missing":
                    blockers.append(blocker)
            if blockers and check.state == "unknown":
                blocker_names = ", ".join(blocker.check for blocker in blockers)
                results.append(
                    replace(
                        check,
                        state="blocked",
                        severity="advisory",
                        next_action=None,
                        reason=f"Blocked until {blocker_names} is complete.",
                    )
                )
            else:
                results.append(check)
        return results

    def _apply_deferred(
        self, checks: list[CheckResult], environment: Environment
    ) -> list[CheckResult]:
        """Mark registry-deferred gaps and report deferred items that now pass."""

        deferred = self.registry.deferred(environment.name)
        if not deferred:
            return checks
        today = self.clock().date()
        workload_count = len(environment.workload_clusters or ())
        passing = {"declared_in_main", "requested", "pr_merged"}
        results = list(checks)
        for entry in deferred:
            if (
                entry.check.startswith("workload.")
                and workload_count > 1
                and not entry.cluster
            ):
                raise RegistryError(
                    f"deferred entry for {entry.check} must name a cluster "
                    f"because {environment.name} has {workload_count} workloads"
                )
            expired = bool(
                entry.until and today > date.fromisoformat(entry.until)
            )
            for index, check in enumerate(results):
                if check.id != entry.check:
                    continue
                if entry.cluster and check.cluster != entry.cluster:
                    continue
                check = results[index]
                if check.state in passing:
                    results[index] = replace(check, deferred_resolved=True)
                elif expired:
                    results[index] = replace(
                        check,
                        deferred=False,
                        deferred_expired=True,
                        defer_reason=entry.reason,
                        defer_until=entry.until,
                    )
                elif check.state != "unknown":
                    results[index] = replace(
                        check,
                        deferred=True,
                        defer_reason=entry.reason,
                        defer_until=entry.until,
                    )
        return results

    def _rate_limited_checks(
        self, environment: Environment, path_scope: str
    ) -> list[CheckResult]:
        definitions = {
            "shared": (
                ("request.issue", "MOC issue", "CCI-MOC/MOC-issues", "issues"),
            ),
            "hub": (
                ("hub.inventory", "Hub host inventory", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"),
                ("hub.image_inventory", "Hub image inventory", "CCI-MOC/oac-infra", "hub-images/inventory.yml"),
                ("hub.image_vars", "Hub image variables", "CCI-MOC/oac-infra", "hub-images/group_vars"),
                ("hub.boot_image", "Hub discovery image", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"),
                ("hub.oidc_client", "Hub OIDC client", "CCI-MOC/moc-keycloak", "main.tf"),
                ("hub.hosted_cluster_defaults", "Hub hosted-cluster defaults", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("hub.component_values", "Hub-wide component values", "CCI-MOC/oac-apps", "values"),
                ("hub.local_cluster_values", "Hub local-cluster values", "CCI-MOC/oac-apps", "values"),
                ("hub.argocd_apps", "Hub ArgoCD applications", "CCI-MOC/oac-apps", "apps"),
                ("hub.pure_storage_realm", "Hub Pure storage realm", "CCI-MOC/everpure-moc", "ansible/group_vars/all/realms.yaml"),
                ("hub.moc_aws_oidc_cluster", "Hub moc-aws OIDC cluster", "CCI-MOC/moc-aws", "main.tf"),
                ("hub.moc_aws_cert_manager_policy", "Hub moc-aws cert-manager policy", "CCI-MOC/moc-aws", "cert-manager-policies.tf"),
                ("hub.moc_aws_hosted_secret_prefix", "Hub hosted-cluster secret prefix", "CCI-MOC/moc-aws", "main.tf"),
                ("hub.moc_dns_records", "Hub moc-dns records", "CCI-MOC/moc-dns", "zonefiles"),
            ),
            "workload": (
                ("workload.inventory", "Workload host inventory", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"),
                ("workload.boot_image", "Workload discovery image", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"),
                ("workload.agent_labels_inputs", "Workload agent-label inputs", "CCI-MOC/oac-infra", "infra/update-agents.yaml"),
                ("workload.hosted_cluster_values", "Workload hosted-cluster values", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.component_values", "Workload component values", "CCI-MOC/oac-apps", "values"),
                ("workload.pure_storage_realm", "Workload Pure storage realm", "CCI-MOC/everpure-moc", "ansible/group_vars/all/realms.yaml"),
                ("workload.moc_aws_oidc_cluster", "Workload moc-aws OIDC cluster", "CCI-MOC/moc-aws", "main.tf"),
                ("workload.moc_aws_cert_manager_policy", "Workload moc-aws cert-manager policy", "CCI-MOC/moc-aws", "cert-manager-policies.tf"),
                ("workload.keycloak_oidc_client", "Workload Keycloak OIDC client", "CCI-MOC/moc-keycloak", "main.tf"),
                ("workload.identity_provider", "Workload identity provider", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.api_address_network", "Workload API address network", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.ingress_address_network", "Workload ingress address network", "CCI-MOC/ansible-switches", "group_vars/all/vlans.yaml"),
                ("workload.address_uniqueness", "Workload address uniqueness", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.address_internal_duplicates", "Workload internal address duplicates", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.dns_base_domain", "Workload DNS base domain", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.node_pool_hosts", "Workload node-pool host capacity", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"),
                ("workload.gpu_without_hosts", "Workload GPU feature support", "CCI-MOC/oac-apps", "hosted-clusters"),
                ("workload.feature_placements", "Workload feature placements", "CCI-MOC/oac-apps", "applicationsets"),
                ("workload.feature_chart_values", "Workload feature chart values", "CCI-MOC/oac-apps", "applicationsets"),
            ),
        }
        scopes = ("shared", "hub") if path_scope == "hub" else (
            ("shared", "workload") if path_scope == "workload" else definitions
        )
        results = []
        hub_cluster = environment.infra_cluster
        for scope in scopes:
            clusters = (
                tuple(environment.workload_clusters or ())
                if scope == "workload"
                else (hub_cluster,)
            )
            for cluster in clusters:
                for check_id, name, repository, path in definitions[scope]:
                    results.append(
                        CheckResult(
                            id=check_id,
                            stage="Rate limited",
                            check=name,
                            scope=scope,
                            cluster=cluster,
                            repository=repository,
                            path=path,
                            ref="main",
                            state="unknown",
                            severity="advisory",
                            expected=None,
                            actual=None,
                            reason="unknown (rate limited)",
                        )
                    )
        return results

    def _description_context(
        self,
        environment: Environment,
        observation: Any = None,
    ) -> DescriptionContext:
        """Collect the values that check descriptions substitute."""

        hub_values: dict[str, Any] = {}
        hub_defaults: dict[str, Any] = {}
        if observation is not None:
            values = observation.infra.hub_variables.values.value
            if isinstance(values, dict):
                hub_values = values
            files = getattr(observation.apps, "files", {}) or {}
            try:
                parsed = yaml.safe_load(
                    files.get(
                        f"hosted-clusters/{environment.infra_cluster}/values.yaml",
                        "",
                    )
                )
            except yaml.YAMLError:
                parsed = None
            if isinstance(parsed, dict):
                hub_defaults = parsed

        def text(value: Any) -> str | None:
            return value if isinstance(value, str) and value else None

        return DescriptionContext(
            hub=environment.infra_cluster,
            workload=environment.workload_cluster,
            workloads=tuple(environment.workload_clusters or ()),
            issue=environment.issue_number,
            domain=environment.domain,
            machine_network=text(hub_values.get("machine_network")),
            base_domain=text(hub_defaults.get("baseDomain")),
            hcp_external_domain=text(hub_defaults.get("hcpExternalDomain")),
            required_components=self.registry.required_components(environment.name),
            optional_components=self.registry.optional_components(environment.name),
            keycloak_client=self.registry.keycloak_client_name(environment.name),
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
            workload_clusters = environment.workload_clusters
            if workload_clusters is None:
                fallback = environment.workload_cluster
                if fallback is None:
                    raise ValueError("no workload cluster is declared for this hub")
                workload_clusters = (fallback,)
                environment = replace(
                    environment,
                    workload_clusters=workload_clusters,
                )
            if workload not in workload_clusters:
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

    @staticmethod
    def _pull_request_evidence(
        pull_requests: tuple[Any, ...]
    ) -> tuple[dict[str, Any], ...]:
        evidence = []
        for item in pull_requests:
            evidence.append(
                {
                    "number": item.number.value,
                    "title": item.title.to_dict(),
                    "state": item.state.to_dict(),
                    "classification": item.classification.to_dict(),
                    "head_ref": item.head_ref.to_dict(),
                    "head_sha": item.head_sha.to_dict(),
                    "html_url": item.url.to_dict(),
                    "repository": item.repository.to_dict(),
                    "changed_files": list(item.changed_files.value),
                }
            )
        return tuple(evidence)

    def _issue_checks(
        self, environment: Environment, observation: IssueObservation
    ) -> list[CheckResult]:
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
                cluster=environment.infra_cluster,
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
        ref = self.client.ref_for(repository)

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
                    f"The inventory file is present in {ref}, but no group has "
                    f"vars.cluster == {cluster!r}."
                )
                present = {"inventory_file": inventory_path}
                missing = {"cluster_group": cluster}
            else:
                state = "missing"
                reason = f"The Ansible inventory file is absent from {ref}."
                present = {"inventory_file": None}
                missing = {"inventory_file": inventory_path, "cluster_group": cluster}

            results.append(
                CheckResult(
                    id=inventory_id,
                    stage="Hardware and inventory",
                    check=f"{cluster} host inventory",
                    scope=inventory_scope,
                    cluster=cluster,
                    repository=repository,
                    path=inventory_path,
                    ref="main",
                    state=state,
                    severity=(
                        "info" if state == "declared_in_main" else "blocking"
                    ),
                    expected=f"Inventory group for {cluster}",
                    actual={"cluster_group": cluster if group else None, "host_count": len(hosts)},
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
            boot_present: dict[str, Any]
            boot_missing: dict[str, Any] | None
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
                    cluster=cluster,
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
        hub_present: dict[str, Any]
        hub_missing: dict[str, Any] | None
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
            hub_reason = f"The hub-image inventory file is absent from {ref}."
            hub_present = {"inventory_file": None}
            hub_missing = {"inventory_file": hub_inventory_path}

        results.append(
            CheckResult(
                id="hub.image_inventory",
                stage="Cluster build",
                check="Hub image inventory",
                scope="hub",
                cluster=environment.infra_cluster,
                repository=repository,
                path=hub_inventory_path,
                ref="main",
                state=hub_state,
                severity="info" if hub_state == "declared_in_main" else "blocking",
                expected=f"Hub-image inventory entry for {environment.infra_cluster}",
                actual={
                    "inventory_key": environment.infra_cluster if hub_found else None
                },
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
            reason = (
                f"All six required hub-image variables are present in {ref}; "
                "their values are not validated."
            )
        elif observation.hub_variables.path_present.value:
            state = "partial"
            reason = (
                "The hub-image variable file is present, but required fields are "
                "absent: " + ", ".join(missing_fields) + "."
            )
        else:
            state = "missing"
            reason = f"The hub-image variable file is absent from {ref}."

        results.append(
            CheckResult(
                id="hub.image_vars",
                stage="Cluster build",
                check="Hub image variables",
                scope="hub",
                cluster=environment.infra_cluster,
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
        ref = self.client.ref_for(repository)
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
            reason = (
                f"The infra/update-agents.yaml playbook is absent from {ref}."
            )
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
            cluster=cluster,
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
            "openshift_redirect_uri": (
                f"https://oauth-openshift.apps.{environment.domain}"
                "/oauth2callback/mocsso"
            ),
            "client_secret_name": (
                f"cluster/{environment.infra_cluster}/keycloak-oidc"
            ),
        }
        client = observation.client
        near_match = observation.near_match_client
        selected_client = client or near_match
        observed = {
            "client": selected_client.cluster_name.value if selected_client else None,
            "openshift_redirect_uri": (
                selected_client.redirect_uri.value if selected_client else None
            ),
            "client_secret_name": (
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
                f"`{expected['openshift_redirect_uri']}`, and client_secret_name = "
                f"`{expected['client_secret_name']}`."
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
                check="Hub OIDC client",
                scope="hub",
                cluster=environment.infra_cluster,
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
        ref = self.client.ref_for(repository)
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
                        workload_cluster,
                        "workload",
                        "Workload hosted-cluster values",
                        workload_values,
                        None,
                        [workload_values],
                        "the hosted workload cluster definition",
                    ),
                    (
                        "workload.component_values",
                        workload_cluster,
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
                environment.infra_cluster,
                "hub",
                "Hub hosted-cluster defaults",
                infra_defaults,
                None,
                [infra_defaults],
                "the default values for hosted clusters on this hub cluster",
            ),
            (
                "hub.component_values",
                environment.infra_cluster,
                "hub",
                "Hub-wide component values",
                None,
                hub_values_prefix,
                [hub_values_prefix + "hcp-config.yaml"],
                "hub-wide HCP and secret-selector values",
            ),
            (
                "hub.local_cluster_values",
                environment.infra_cluster,
                "hub",
                "Hub local-cluster values",
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
                environment.infra_cluster,
                "hub",
                "Hub ArgoCD applications",
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
            cluster,
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
            missing: dict[str, Any] | None
            if expected_paths:
                if not required_missing and not optional_missing:
                    state = "declared_in_main"
                elif required_found or found:
                    state = "partial"
                else:
                    state = "missing"
            else:
                state = "declared_in_main" if found else "missing"

            scope_label = (
                (prefix or "").rstrip("/")
                or (exact or "").rsplit("/", 1)[0]
                or (exact or "")
            )
            required_total = len(required_paths)
            required_names = ", ".join(
                path.rsplit("/", 1)[-1] for path in required_paths
            )
            required_verb = "exists" if required_total == 1 else "exist"
            if state == "declared_in_main":
                if required_paths:
                    reason = (
                        f"{len(required_found)} of {required_total} required "
                        f"{'file' if required_total == 1 else 'files'} "
                        f"{required_verb} in "
                        f"{ref} under {scope_label} ({required_names}). "
                        "File contents are not read."
                    )
                else:
                    found_verb = "file exists" if len(found) == 1 else "files exist"
                    reason = (
                        f"{len(found)} {found_verb} in {ref} under {scope_label}; "
                        "at least 1 is required. File contents are not read."
                    )
                missing = None
            elif state == "partial":
                missing_paths = required_missing + optional_missing
                reason = (
                    f"{len(required_found)} of {required_total} required "
                    f"{'file' if required_total == 1 else 'files'} "
                    f"{required_verb} in "
                    f"{ref} under {scope_label}; missing: "
                    + ", ".join(missing_paths)
                    + ". File contents are not read."
                )
                missing = {"paths": missing_paths}
            elif required_paths:
                reason = (
                    f"None of the {required_total} required "
                    f"{'file' if required_total == 1 else 'files'} exist in {ref} "
                    f"under {scope_label}. Missing: "
                    + ", ".join(expected_paths or [search_path])
                    + ". File contents are not read."
                )
                missing = {"paths": expected_paths or [search_path]}
            else:
                reason = (
                    f"No files exist in {ref} under {scope_label}; at least 1 is "
                    "required. File contents are not read."
                )
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
                    "scope": scope_label,
                }
                if expected_paths
                else "At least one matching path"
            )
            present: dict[str, Any] = {"file_count": len(found)}
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
                    cluster=cluster,
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
                        **(
                            {"values": _safe_yaml_value(
                                observation.files.get(exact, "")
                            )}
                            if check_id == "hub.hosted_cluster_defaults"
                            and exact in observation.files
                            else {}
                        ),
                    },
                    url=github_url(repository, exact or (prefix or "").rstrip("/")),
                    next_action=_next_action(check_id, state),
                    severity=severity,
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
        if any(
            check.severity == "blocking" and not check.deferred
            for check in checks
        ):
            return "CONFIGURATION IN PROGRESS"
        if checks:
            return "DECLARED IN MAIN"
        return "NOT CONFIGURED"
