"""Per-environment configuration for the read-only status checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RegistryError(ValueError):
    """Raised when the environment registry is malformed."""


DEFAULT_REGISTRY_PATH = (
    Path(__file__).parent / "data" / "environments.yaml"
)

_ALLOWED_KEYS = {
    "issue",
    "required_local_cluster_components",
    "optional_local_cluster_components",
    "keycloak_client_name",
}

_ALLOWED_ROOT_KEYS = {"defaults", "environments"}


@dataclass(frozen=True)
class EnvironmentRegistry:
    """Validated per-environment status-check settings."""

    issues: dict[str, int]
    required_local_cluster_components: dict[str, tuple[str, ...]]
    optional_local_cluster_components: dict[str, tuple[str, ...]]
    keycloak_client_names: dict[str, str]

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

        issues: dict[str, int] = {}
        required: dict[str, tuple[str, ...]] = {}
        optional: dict[str, tuple[str, ...]] = {}
        keycloak_names: dict[str, str] = {}

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

        return cls(
            issues=issues,
            required_local_cluster_components=required,
            optional_local_cluster_components=optional,
            keycloak_client_names=keycloak_names,
        )

    def issue(self, environment: str) -> int | None:
        return self.issues.get(environment)

    def required_components(self, environment: str) -> tuple[str, ...]:
        return self.required_local_cluster_components.get(environment, ())

    def optional_components(self, environment: str) -> tuple[str, ...]:
        return self.optional_local_cluster_components.get(environment, ())

    def keycloak_client_name(self, environment: str) -> str:
        return self.keycloak_client_names.get(environment, f"{environment}-infra")


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
