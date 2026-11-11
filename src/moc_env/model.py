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
