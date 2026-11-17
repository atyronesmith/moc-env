"""Core data models for moc-env."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .phases import not_checked_entries, phase_definitions


@dataclass(frozen=True)
class Environment:
    """Derived identifiers for a MOC environment."""

    name: str
    issue_number: int | None = None
    domain_override: str | None = None
    workload_clusters: tuple[str, ...] | None = None

    @property
    def base_name(self) -> str:
        """Return the environment base name without an infra-cluster suffix."""

        suffix = "-infra"
        if self.name.endswith(suffix):
            return self.name[: -len(suffix)]
        return self.name

    @property
    def infra_cluster(self) -> str:
        return f"{self.base_name}-infra"

    @property
    def workload_cluster(self) -> str | None:
        """Return the first workload, retained for old JSON consumers."""

        # Deprecated: use workload_clusters for environments with multiple clusters.
        if self.workload_clusters is None:
            return f"{self.base_name}-workload0"
        return self.workload_clusters[0] if self.workload_clusters else None

    @property
    def domain(self) -> str:
        if self.domain_override:
            return self.domain_override
        return f"{self.base_name}.int.massopen.cloud"

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "issue_number": self.issue_number,
            "infra_cluster": self.infra_cluster,
            "workload_clusters": (
                list(self.workload_clusters)
                if self.workload_clusters is not None
                else [self.workload_cluster]
            ),
            "workload_cluster": self.workload_cluster,
            "domain": self.domain,
            "domain_source": "repository" if self.domain_override else "derived",
        }
        if self.workload_clusters is not None and not self.workload_clusters:
            data["workload_notice"] = "No workload cluster is declared for this hub."
        return data


@dataclass
class CheckResult:
    """One normalized configuration-state check."""

    id: str
    stage: str
    check: str
    scope: str
    repository: str
    path: str
    ref: str
    state: str
    severity: str
    expected: Any
    actual: Any
    reason: str
    present: Any = None
    missing: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] | None = None
    url: str | None = None
    next_action: str | None = None
    phase: int | None = None
    phase_title: str | None = None
    blocked_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # expected / present / missing / actual are deprecated compatibility
        # payloads. Remove them in the next report-schema release.
        normalized = {
            "expected": _payload_items(data["expected"]),
            "observed": _payload_items(data["actual"]),
            "gaps": _gap_items(data["expected"], data["actual"], data["missing"]),
        }
        return {
            "id": data["id"],
            "scope": data["scope"],
            "next_action": data["next_action"],
            **normalized,
            **{
                key: value
                for key, value in data.items()
                if value is not None and key not in {"id", "scope", "next_action"}
            },
        }


@dataclass(frozen=True)
class SourceSnapshot:
    """One repository ref read while producing a report."""

    repository: str
    ref: str
    sha: str
    from_cache: bool = False
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "sha": self.sha,
            **(
                {"from_cache": True, "fetched_at": self.fetched_at or "unknown"}
                if self.from_cache
                else {}
            ),
        }


@dataclass(frozen=True)
class ReportMetadata:
    """Reproduction and ordering metadata for a status report."""

    schema_version: int
    generated_at: str
    tool_version: str
    command: tuple[str, ...]
    sources: tuple[SourceSnapshot, ...]
    authenticated: bool
    rate_limit_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "tool_version": self.tool_version,
            "command": list(self.command),
            "sources": [source.to_dict() for source in self.sources],
            "authenticated": self.authenticated,
            "rate_limit_remaining": self.rate_limit_remaining,
        }


@dataclass
class StatusReport:
    """The complete configuration-state report for one environment."""

    environment: Environment
    checks: list[CheckResult]
    overall_state: str
    scope: str = "environment"
    metadata: ReportMetadata | None = None
    pull_requests: tuple[dict[str, Any], ...] = ()
    pull_requests_skipped: bool = False
    pull_requests_skip_reason: str | None = None
    pull_requests_unavailable: str | None = None
    rate_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        for check in self.checks:
            state_counts[check.state] = state_counts.get(check.state, 0) + 1
            severity_counts[check.severity] = (
                severity_counts.get(check.severity, 0) + 1
            )

        stages: list[str] = []
        stage_counts: dict[str, dict[str, int]] = {}
        for check in self.checks:
            if check.stage not in stage_counts:
                stages.append(check.stage)
                stage_counts[check.stage] = {}
            stage_counts[check.stage][check.state] = (
                stage_counts[check.stage].get(check.state, 0) + 1
            )

        return {
            "scope": self.scope,
            "current_phase": self._current_phase(),
            "phases": self._phase_definitions(),
            **({"metadata": self.metadata.to_dict()} if self.metadata else {}),
            "environment": self.environment.to_dict(),
            "overall_state": self.overall_state,
            "not_checked": self._not_checked(),
            "summary": {
                "check_count": len(self.checks),
                "state_counts": dict(sorted(state_counts.items())),
                "severity_counts": dict(sorted(severity_counts.items())),
                "advisory_count": severity_counts.get("advisory", 0),
                "stages": [
                    {
                        "stage": stage,
                        "state_counts": dict(sorted(states.items())),
                        "check_count": sum(states.values()),
                    }
                    for stage, states in stage_counts.items()
                ],
            },
            "checks": [check.to_dict() for check in self.checks],
            "pull_requests": list(self.pull_requests),
            "pull_requests_skipped": self.pull_requests_skipped,
            **(
                {"pull_requests_skip_reason": self.pull_requests_skip_reason}
                if self.pull_requests_skip_reason
                else {}
            ),
            **(
                {"pull_requests_unavailable": self.pull_requests_unavailable}
                if self.pull_requests_unavailable
                else {}
            ),
            "rate_limited": self.rate_limited,
        }

    def _current_phase(self) -> int | str | dict[str, int | str]:
        """Return the lowest phase with a blocking gap for each report scope."""

        if self.scope == "environment":
            return {
                scope: self._scope_current_phase(scope)
                for scope in ("hub", "workload")
            }
        return self._scope_current_phase(self.scope)

    def _phase_definitions(self) -> Any:
        if self.scope == "environment":
            return {
                scope: [phase.to_dict() for phase in phase_definitions(scope)]
                for scope in ("hub", "workload")
            }
        return [phase.to_dict() for phase in phase_definitions(self.scope)]

    def _not_checked(self) -> list[dict[str, object]]:
        if self.scope == "environment":
            entries = [
                entry
                for scope in ("hub", "workload")
                for entry in not_checked_entries(
                    scope,
                    (
                        self.environment.workload_cluster
                        if scope == "workload"
                        else self.environment.infra_cluster
                    )
                    or "",
                )
            ]
        else:
            cluster = (
                self.environment.workload_cluster
                if self.scope == "workload"
                else self.environment.infra_cluster
            )
            entries = not_checked_entries(self.scope, cluster or "")
        return [entry.to_dict() for entry in entries]

    def _scope_current_phase(self, scope: str) -> int | str:
        phases = [
            check.phase
            for check in self.checks
            if check.scope == scope
            and check.severity == "blocking"
            and check.phase is not None
            and check.state != "declared_in_main"
        ]
        return min(phases) if phases else "complete"


def _payload_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [{"name": str(key), "value": item} for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        items = []
        for index, item in enumerate(value):
            if isinstance(item, dict) and "name" in item:
                normalized = dict(item)
                normalized.setdefault("value", None)
                items.append(normalized)
            else:
                items.append({"name": str(index), "value": item})
        return items
    return [{"name": "value", "value": value}]


def _gap_items(expected: Any, observed: Any, missing: Any) -> list[dict[str, Any]]:
    if missing is None:
        return []

    expected_mapping = expected if isinstance(expected, dict) else {}
    observed_mapping = observed if isinstance(observed, dict) else {}
    if isinstance(missing, dict):
        gaps = []
        for name, value in missing.items():
            key = str(name)
            gaps.append(
                {
                    "name": key,
                    "expected": expected_mapping.get(key, value),
                    "observed": observed_mapping.get(key),
                }
            )
        return gaps
    if isinstance(missing, (list, tuple)):
        expected_items = expected if isinstance(expected, (list, tuple)) else []
        observed_items = observed if isinstance(observed, (list, tuple)) else []
        return [
            {
                "name": str(index),
                "expected": (
                    expected_items[index]
                    if index < len(expected_items)
                    else item
                ),
                "observed": (
                    observed_items[index]
                    if index < len(observed_items)
                    else None
                ),
            }
            for index, item in enumerate(missing)
        ]
    return [
        {
            "name": "value",
            "expected": expected,
            "observed": observed,
        }
    ]


@dataclass(frozen=True)
class PlannedChange:
    """One read-only repository change proposed by a Phase 8 plan."""

    repository: str
    base_ref: str
    branch: str
    path: str
    field: str
    operation: str
    desired: Any
    current: Any
    reason: str
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "base_ref": self.base_ref,
            "branch": self.branch,
            "path": self.path,
            "field": self.field,
            "operation": self.operation,
            "desired": self.desired,
            "current": self.current,
            "reason": self.reason,
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class ChangePlan:
    """A deterministic, read-only plan derived from a comparison report."""

    environment: Environment
    kind: str
    changes: list[PlannedChange] = field(default_factory=list)

    @property
    def overall_state(self) -> str:
        if self.changes:
            return "CHANGES PLANNED"
        return "NO CHANGES REQUIRED"

    def to_dict(self) -> dict[str, Any]:
        operation_counts: dict[str, int] = {}
        repository_counts: dict[str, int] = {}
        for change in self.changes:
            operation_counts[change.operation] = (
                operation_counts.get(change.operation, 0) + 1
            )
            repository_counts[change.repository] = (
                repository_counts.get(change.repository, 0) + 1
            )
        return {
            "kind": self.kind,
            "environment": self.environment.to_dict(),
            "overall_state": self.overall_state,
            "summary": {
                "change_count": len(self.changes),
                "operation_counts": dict(sorted(operation_counts.items())),
                "repository_counts": dict(sorted(repository_counts.items())),
            },
            "changes": [change.to_dict() for change in self.changes],
        }
