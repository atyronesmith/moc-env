"""Compare reviewed desired state with current repository state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .model import Environment
from .observed import AppsObservation, InfraObservation

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

    environment_name = _desired_source(_mapping(document, "metadata"), "environment")
    if not isinstance(environment_name, str):
        infra_name = _desired_source(_mapping(document, "metadata"), "name")
        if isinstance(infra_name, str) and infra_name.endswith("-infra"):
            environment_name = infra_name[: -len("-infra")]
        else:
            environment_name = ""
    return Environment(name=environment_name)


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

    return ComparisonReport(environment=environment, checks=checks)


def render_comparison_text(report: ComparisonReport) -> str:
    data = report.to_dict()
    lines = [
        "=" * 78,
        f"MOC infra comparison: {data['environment']['name']}",
        "=" * 78,
        f"Infra cluster: {data['environment']['infra_cluster']}",
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
        "# 🔍 Infra Desired-State Comparison",
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
