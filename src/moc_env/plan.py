"""Build read-only Phase 8 change plans from comparison reports."""

from __future__ import annotations

import json
import re
from typing import Any

from .compare import ComparisonReport
from .model import ChangePlan, Environment, PlannedChange

_OPERATIONS_BY_STATE = {
    "missing_from_main": "create",
    "value_mismatch": "update",
    "unexpected_in_main": "delete",
    "unsupported_check": "manual_review",
    "ambiguous": "manual_review",
}


def _walk(document: Any, parts: list[str]) -> Any:
    value: Any = document
    for part in parts:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _first_source(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("provenance"), dict):
        return value
    for child in value.values():
        source = _first_source(child)
        if source is not None:
            return source
    return None


def _source_for_field(document: Any, field: str) -> dict[str, Any] | None:
    """Resolve a comparison field to its desired-state source metadata."""

    parts = field.split(".")
    if parts[-1] == "value":
        parent = _walk(document, parts[:-1])
        if isinstance(parent, dict):
            source = parent.get(parts[-1])
            if isinstance(source, dict) and isinstance(
                source.get("provenance"), dict
            ):
                return source
            nested = _first_source(parent)
            if nested is not None:
                return nested
        return None
    source = _first_source(_walk(document, parts))
    if source is None and field.startswith("spec.inventory.clusters."):
        source = _first_source(
            _walk(document, ["spec", "inventory", "clusters"])
        )
    if source is None and field.startswith("spec.inventory.clusters."):
        source = _source_for_field(document, "metadata.environment.value")
    return source


def _repository_name(repository: str) -> str:
    name = repository.rsplit("/", 1)[-1]
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-").lower()


def _branch_name(environment: Environment, repository: str) -> str:
    return f"moc-env/{environment.base_name}-infra-{_repository_name(repository)}"


def build_infra_change_plan(
    document: Any,
    report: ComparisonReport,
) -> ChangePlan:
    """Convert an InfraCluster comparison into a read-only change plan.

    Matches and open pull requests do not create repository operations. Open
    PRs are already in flight and must be reviewed separately; this function
    does not assume that their changes satisfy the desired state.
    """

    if report.kind != "Hub":
        raise ValueError(f"unsupported comparison kind for infra planning: {report.kind}")

    changes: list[PlannedChange] = []
    for check in report.checks:
        operation = _OPERATIONS_BY_STATE.get(check.state)
        if operation is None:
            continue

        source = _source_for_field(document, check.field)
        provenance = source.get("provenance", {}) if source else {}
        repository = provenance.get("repository")
        path = provenance.get("path")
        if not isinstance(repository, str) or not isinstance(path, str):
            raise ValueError(
                f"cannot determine repository provenance for field: {check.field}"
            )

        changes.append(
            PlannedChange(
                repository=repository,
                base_ref=provenance.get("ref", "main"),
                branch=_branch_name(report.environment, repository),
                path=path,
                field=check.field,
                operation=operation,
                desired=check.desired,
                current=check.current,
                reason=check.reason,
            )
        )

    return ChangePlan(
        environment=report.environment,
        kind="Infra",
        changes=changes,
    )


def render_change_plan_text(plan: ChangePlan) -> str:
    """Render a compact, deterministic human-readable change plan."""

    lines = [
        "=" * 78,
        f"MOC infra change plan: {plan.environment.name}",
        "=" * 78,
        f"Hub cluster:    {plan.environment.infra_cluster}",
        f"Overall:        {plan.overall_state}",
        "",
    ]
    if not plan.changes:
        lines.extend(
            [
                "No repository changes are required by the reviewed desired state.",
                "Open pull requests, if any, still require separate review.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(["Branches:"])
    branches: dict[tuple[str, str, str], int] = {}
    for change in plan.changes:
        key = (change.repository, change.base_ref, change.branch)
        branches[key] = branches.get(key, 0) + 1
    for (repository, base_ref, branch), count in branches.items():
        lines.append(
            f"  {repository}: {base_ref} -> {branch} ({count} change(s))"
        )

    lines.extend(["", "Planned changes:"])
    for index, change in enumerate(plan.changes, start=1):
        dependencies = ", ".join(change.depends_on) if change.depends_on else "none"
        lines.extend(
            [
                "-" * 78,
                f"[{index}] {change.operation}: {change.field}",
                f"  Repository: {change.repository}",
                f"  Branch:     {change.branch} (from {change.base_ref})",
                f"  Path:       {change.path}",
                f"  Desired:    {json.dumps(change.desired, sort_keys=True, default=str)}",
                f"  Current:    {json.dumps(change.current, sort_keys=True, default=str)}",
                f"  Depends on: {dependencies}",
                f"  Reason:     {change.reason}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_change_plan_json(plan: ChangePlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n"


def _markdown_value(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, default=str)
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def render_change_plan_markdown(plan: ChangePlan) -> str:
    """Render a Phase 8 plan as review-friendly Markdown."""

    lines = [
        "# 🗺️ Infra Change Plan",
        "",
        f"## `{plan.environment.name}` — {plan.overall_state}",
        "",
        (
            "This plan is read-only. It does not create branches, commits, "
            "pull requests, or repository changes."
        ),
        "",
        "## Summary",
        "",
        "| Measure | Value |",
        "|---|---:|",
        f"| Planned changes | {len(plan.changes)} |",
    ]
    for operation, count in plan.to_dict()["summary"]["operation_counts"].items():
        lines.append(f"| `{operation}` | {count} |")

    if not plan.changes:
        lines.extend(
            [
                "",
                (
                    "No repository changes are required by the reviewed desired state. "
                    "Open pull requests, if any, still require separate review."
                ),
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "",
            "## Planned changes",
            "",
            (
                "| # | Operation | Repository | Branch | Path | Field | "
                "Desired | Current | Depends on | Reason |"
            ),
            "|---:|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for index, change in enumerate(plan.changes, start=1):
        dependencies = ", ".join(change.depends_on) if change.depends_on else "—"
        lines.append(
            "| "
            f"{index} | "
            f"`{change.operation}` | "
            f"`{change.repository}` | "
            f"`{change.branch}` | "
            f"`{change.path}` | "
            f"`{change.field}` | "
            f"`{_markdown_value(change.desired)}` | "
            f"`{_markdown_value(change.current)}` | "
            f"{dependencies} | "
            f"{change.reason} |"
        )
    return "\n".join(lines).rstrip() + "\n"
