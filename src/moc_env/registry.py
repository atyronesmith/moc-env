"""Per-environment configuration for the read-only status checks."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class RegistryError(ValueError):
    """Raised when the environment registry is malformed."""


@dataclass(frozen=True)
class DeferredCheck:
    """One check intentionally deferred for an environment."""

    check: str
    reason: str
    cluster: str | None = None
    until: str | None = None


DEFAULT_REGISTRY_PATH = (
    Path(__file__).parent / "data" / "environments.yaml"
)

_ALLOWED_KEYS = {
    "issue",
    "required_local_cluster_components",
    "optional_local_cluster_components",
    "keycloak_client_name",
    "deferred",
}

_ALLOWED_ROOT_KEYS = {"defaults", "environments", "cluster_scope"}
_ALLOWED_CLUSTER_SCOPE_KEYS = {"deployment_hub_patterns", "test_clusters"}


@dataclass(frozen=True)
class EnvironmentRegistry:
    """Validated per-environment status-check settings."""

    issues: dict[str, int]
    required_local_cluster_components: dict[str, tuple[str, ...]]
    optional_local_cluster_components: dict[str, tuple[str, ...]]
    keycloak_client_names: dict[str, str]
    deferred_checks: dict[str, tuple[DeferredCheck, ...]]
    default_required_components: tuple[str, ...] = ()
    deployment_hub_patterns: tuple[str, ...] = ()
    test_clusters: tuple[str, ...] = ()

    @classmethod
    def load(
        cls, path: Path | str = DEFAULT_REGISTRY_PATH
    ) -> "EnvironmentRegistry":
        try:
            document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise RegistryError(f"could not load environment registry: {exc}") from exc
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document: Any) -> "EnvironmentRegistry":
        if not isinstance(document, dict):
            raise RegistryError("environment registry must be a mapping")

        unknown_root_keys = sorted(set(document) - _ALLOWED_ROOT_KEYS)
        if unknown_root_keys:
            raise RegistryError(
                f"{unknown_root_keys[0]} is not a supported registry key"
            )

        defaults = document.get("defaults", {})
        if not isinstance(defaults, dict):
            raise RegistryError("defaults must be a mapping")
        _validate_section("defaults", defaults)
        for key in (
            "required_local_cluster_components",
            "optional_local_cluster_components",
        ):
            if key not in defaults:
                raise RegistryError(f"defaults.{key} is required")

        environments = document.get("environments", {})
        if not isinstance(environments, dict):
            raise RegistryError("environments must be a mapping")

        deployment_patterns, test_clusters = _cluster_scope(document.get("cluster_scope"))

        issues: dict[str, int] = {}
        required: dict[str, tuple[str, ...]] = {}
        optional: dict[str, tuple[str, ...]] = {}
        keycloak_names: dict[str, str] = {}
        deferred: dict[str, tuple[DeferredCheck, ...]] = {}

        for environment, settings in environments.items():
            if not isinstance(environment, str) or not environment:
                raise RegistryError("environments keys must be non-empty strings")
            section = f"environments.{environment}"
            if not isinstance(settings, dict):
                raise RegistryError(f"{section} must be a mapping")
            _validate_section(section, settings)

            issue = settings.get("issue", defaults.get("issue"))
            if issue is not None:
                issues[environment] = _issue_number(issue, f"{section}.issue")

            required[environment] = _component_list(
                settings.get(
                    "required_local_cluster_components",
                    defaults.get("required_local_cluster_components"),
                ),
                f"{environment}.required_local_cluster_components",
            )
            optional[environment] = _component_list(
                settings.get(
                    "optional_local_cluster_components",
                    defaults.get("optional_local_cluster_components"),
                ),
                f"{environment}.optional_local_cluster_components",
            )
            overlap = set(required[environment]) & set(optional[environment])
            if overlap:
                raise RegistryError(
                    f"{environment}.required_local_cluster_components and "
                    f"{environment}.optional_local_cluster_components both list: "
                    + ", ".join(sorted(overlap))
                )

            keycloak_name = settings.get(
                "keycloak_client_name",
                defaults.get("keycloak_client_name", f"{environment}-infra"),
            )
            if not isinstance(keycloak_name, str) or not keycloak_name:
                raise RegistryError(
                    f"{environment}.keycloak_client_name must be a non-empty string"
                )
            keycloak_names[environment] = keycloak_name

            deferred[environment] = _deferred_list(
                settings.get("deferred", ()),
                f"{section}.deferred",
            )

        return cls(
            issues=issues,
            required_local_cluster_components=required,
            optional_local_cluster_components=optional,
            keycloak_client_names=keycloak_names,
            deferred_checks=deferred,
            default_required_components=_component_list(
                defaults.get("required_local_cluster_components"),
                "defaults.required_local_cluster_components",
            ),
            deployment_hub_patterns=deployment_patterns,
            test_clusters=test_clusters,
        )

    def issue(self, environment: str) -> int | None:
        return self.issues.get(environment)

    def required_components(self, environment: str) -> tuple[str, ...]:
        return self.required_local_cluster_components.get(
            environment, self.default_required_components
        )

    def optional_components(self, environment: str) -> tuple[str, ...]:
        return self.optional_local_cluster_components.get(environment, ())

    def keycloak_client_name(self, environment: str) -> str:
        return self.keycloak_client_names.get(environment, f"{environment}-infra")

    def deferred(self, environment: str) -> tuple[DeferredCheck, ...]:
        return self.deferred_checks.get(environment, ())

    def is_deployment_hub(self, hub: str) -> bool:
        """Return whether a hub name matches a configured deployment pattern."""

        return any(
            fnmatch.fnmatchcase(hub, pattern)
            for pattern in self.deployment_hub_patterns
        )


def _cluster_scope(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if value is None:
        return (), ()
    if not isinstance(value, dict):
        raise RegistryError("cluster_scope must be a mapping")
    unknown = sorted(set(value) - _ALLOWED_CLUSTER_SCOPE_KEYS)
    if unknown:
        raise RegistryError(
            f"cluster_scope.{unknown[0]} is not a supported registry key"
        )
    patterns = value.get("deployment_hub_patterns")
    if (
        not isinstance(patterns, (list, tuple))
        or not patterns
        or not all(isinstance(item, str) and item for item in patterns)
    ):
        raise RegistryError(
            "cluster_scope.deployment_hub_patterns must be a non-empty list "
            "of non-empty strings"
        )
    test_clusters = value.get("test_clusters", [])
    if not isinstance(test_clusters, list) or not all(
        isinstance(item, str) and item for item in test_clusters
    ):
        raise RegistryError(
            "cluster_scope.test_clusters must be a list of non-empty strings"
        )
    return tuple(patterns), tuple(test_clusters)


def _validate_section(path: str, settings: dict[str, Any]) -> None:
    unknown = sorted(set(settings) - _ALLOWED_KEYS)
    if unknown:
        raise RegistryError(f"{path}.{unknown[0]} is not a supported registry key")
    if "issue" in settings:
        _issue_number(settings["issue"], f"{path}.issue")
    if "required_local_cluster_components" in settings:
        _component_list(
            settings["required_local_cluster_components"],
            f"{path}.required_local_cluster_components",
        )
    if "optional_local_cluster_components" in settings:
        _component_list(
            settings["optional_local_cluster_components"],
            f"{path}.optional_local_cluster_components",
        )
    if "keycloak_client_name" in settings:
        value = settings["keycloak_client_name"]
        if not isinstance(value, str) or not value:
            raise RegistryError(
                f"{path}.keycloak_client_name must be a non-empty string"
            )
    if "deferred" in settings:
        _deferred_list(settings["deferred"], f"{path}.deferred")


def _issue_number(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RegistryError(f"{path} must be a positive integer")
    return value


def _component_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise RegistryError(f"{path} must be a list of non-empty file names")
    if len(value) != len(set(value)):
        raise RegistryError(f"{path} must not contain duplicate file names")
    return tuple(value)


def _deferred_list(value: Any, path: str) -> tuple[DeferredCheck, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise RegistryError(f"{path} must be a list")
    entries: list[DeferredCheck] = []
    seen: set[tuple[str, str | None]] = set()
    for index, item in enumerate(value):
        entry_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            raise RegistryError(f"{entry_path} must be a mapping")
        if "date" in item:
            raise RegistryError(
                f"{entry_path}.date is not supported; rename it to until"
            )
        unknown = sorted(
            set(item) - {"check", "check_id", "id", "reason", "cluster", "until"}
        )
        if unknown:
            raise RegistryError(
                f"{entry_path}.{unknown[0]} is not a supported registry key"
            )
        check = item.get("check", item.get("check_id", item.get("id")))
        if not isinstance(check, str) or not check:
            raise RegistryError(f"{entry_path}.check must be a non-empty string")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise RegistryError(f"{entry_path}.reason must be a non-empty string")
        cluster = item.get("cluster")
        if cluster is not None and (not isinstance(cluster, str) or not cluster):
            raise RegistryError(
                f"{entry_path}.cluster must be a non-empty string"
            )
        deferred_until = item.get("until")
        if deferred_until is not None:
            if isinstance(deferred_until, date):
                deferred_until = deferred_until.isoformat()
            if not isinstance(deferred_until, str):
                raise RegistryError(
                    f"{entry_path}.until must be a YYYY-MM-DD string"
                )
            try:
                date.fromisoformat(deferred_until)
            except ValueError as exc:
                raise RegistryError(
                    f"{entry_path}.until must be a YYYY-MM-DD string"
                ) from exc
        key = (check, cluster)
        if key in seen:
            raise RegistryError(
                f"{path} lists {check}"
                + (f" for {cluster}" if cluster else "")
                + " more than once"
            )
        seen.add(key)
        entries.append(
            DeferredCheck(
                check=check,
                reason=reason.strip(),
                cluster=cluster,
                until=deferred_until,
            )
        )
    return tuple(entries)
