"""Build read-only Phase 8 change plans from comparison reports."""

from __future__ import annotations

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
