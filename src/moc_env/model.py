"""Core data models for moc-env."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Environment:
    """Derived identifiers for a MOC environment."""

    name: str
    issue_number: int | None = None
    domain_override: str | None = None

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
    def workload_cluster(self) -> str:
        return f"{self.base_name}-workload0"

    @property
    def domain(self) -> str:
        if self.domain_override:
            return self.domain_override
        return f"{self.base_name}.int.massopen.cloud"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "issue_number": self.issue_number,
            "infra_cluster": self.infra_cluster,
            "workload_cluster": self.workload_cluster,
            "domain": self.domain,
            "domain_source": "repository" if self.domain_override else "derived",
        }


@dataclass
class CheckResult:
    """One normalized configuration-state check."""

    stage: str
    check: str
    repository: str
    path: str
    ref: str
    state: str
    expected: Any
    actual: Any
    reason: str
    present: Any = None
    missing: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class StatusReport:
    """The complete configuration-state report for one environment."""

    environment: Environment
    checks: list[CheckResult]
    overall_state: str

    def to_dict(self) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        for check in self.checks:
            state_counts[check.state] = state_counts.get(check.state, 0) + 1

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
            "environment": self.environment.to_dict(),
            "overall_state": self.overall_state,
            "summary": {
                "check_count": len(self.checks),
                "state_counts": dict(sorted(state_counts.items())),
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
        }


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
