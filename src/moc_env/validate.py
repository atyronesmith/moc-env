"""Validation for desired-state YAML documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import ipaddress
import json
import re
from typing import Any

import yaml

from .export import EXPORT_API_VERSION, INFRA_EXPORT_KIND, INFRA_EXPORT_SCHEMA_VERSION

REQUIRED_VARIABLE_FIELDS = (
    "cluster_domain_name",
    "base_domain",
    "machine_network",
    "api_ip",
    "ingress_ip",
    "dns_ip",
)

_DOMAIN_LABEL = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)
_SECRET_KEY_TOKENS = ("secret", "token", "password", "credential")

_SOURCE_SCHEMA: dict[str, Any] = {
    "value": None,
    "provenance": {
        "repository": None,
        "path": None,
        "ref": None,
    },
    "confidence": None,
}
_DOCUMENT_SCHEMA: dict[str, Any] = {
    "apiVersion": None,
    "kind": None,
    "schemaVersion": None,
    "metadata": {
        "name": _SOURCE_SCHEMA,
        "environment": _SOURCE_SCHEMA,
    },
    "spec": {
        "inventory": {
            "path": _SOURCE_SCHEMA,
            "present": _SOURCE_SCHEMA,
            "clusters": "dynamic-clusters",
        },
        "hubInventory": {
            "path": _SOURCE_SCHEMA,
            "present": _SOURCE_SCHEMA,
            "inventoryPresent": _SOURCE_SCHEMA,
            "clusterKeyPresent": _SOURCE_SCHEMA,
        },
        "variables": {
            "path": _SOURCE_SCHEMA,
            "present": _SOURCE_SCHEMA,
            "fields": "dynamic-fields",
        },
        "domain": _SOURCE_SCHEMA,
    },
}
_CLUSTER_SCHEMA: dict[str, Any] = {
    "name": _SOURCE_SCHEMA,
    "groupPresent": _SOURCE_SCHEMA,
    "hosts": _SOURCE_SCHEMA,
    "bootImage": {
        "urls": "source-list",
        "selected": _SOURCE_SCHEMA,
        "ambiguous": None,
    },
}


@dataclass(frozen=True)
class ValidationCheck:
    """One discrete desired-state validation check."""

    category: str
    name: str
    path: str
    expected: str
    actual: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "name": self.name,
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one desired-state document."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[ValidationCheck] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": [check.to_dict() for check in self.checks],
        }


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.Node, deep: bool = False):
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _source_value(
    parent: Any,
    field_name: str,
    path: str,
    errors: list[str],
) -> Any:
    if not isinstance(parent, dict):
        return None
    source = parent.get(field_name)
    if not isinstance(source, dict):
        errors.append(f"{path}: expected a source value object")
        return None
    if "value" not in source:
        errors.append(f"{path}: missing required 'value'")
    confidence = source.get("confidence")
    if confidence not in {"exact", "inferred", "unsupported"}:
        errors.append(f"{path}: confidence must be exact, inferred, or unsupported")
    provenance = source.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(f"{path}: missing required provenance")
    else:
        for provenance_field in ("repository", "path", "ref"):
            if not isinstance(provenance.get(provenance_field), str):
                errors.append(
                    f"{path}.provenance.{provenance_field}: expected a string"
                )
    if confidence == "unsupported":
        errors.append(f"{path}: unsupported values cannot be reviewed desired state")
    return source.get("value")


def _required_source(
    parent: Any,
    field_name: str,
    path: str,
    errors: list[str],
) -> Any:
    if not isinstance(parent, dict) or field_name not in parent:
        errors.append(f"{path}: missing required field")
        return None
    return _source_value(parent, field_name, path, errors)


def _is_domain(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 253:
        return False
    return all(_DOMAIN_LABEL.fullmatch(label) for label in value.split("."))


def _walk_unknown_fields(
    node: Any,
    schema: Any,
    path: tuple[str, ...],
    warnings: list[str],
) -> None:
    if schema == "dynamic-clusters":
        if not isinstance(node, dict):
            return
        for cluster_name, cluster in node.items():
            _walk_unknown_fields(
                cluster,
                _CLUSTER_SCHEMA,
                (*path, str(cluster_name)),
                warnings,
            )
        return
    if schema == "dynamic-fields":
        if not isinstance(node, dict):
            return
        for field_name, source in node.items():
            if field_name not in REQUIRED_VARIABLE_FIELDS:
                warnings.append(
                    f"spec.variables.fields.{field_name}: unknown field (warning)"
                )
            _walk_unknown_fields(
                source,
                _SOURCE_SCHEMA,
                (*path, str(field_name)),
                warnings,
            )
        return
    if schema == "source-list":
        if not isinstance(node, list):
            return
        for index, source in enumerate(node):
            _walk_unknown_fields(source, _SOURCE_SCHEMA, (*path, str(index)), warnings)
        return
    if not isinstance(schema, dict) or not isinstance(node, dict):
        return

    for key, value in node.items():
        if key not in schema:
            warnings.append(f"{'.'.join((*path, str(key)))}: unknown field (warning)")
            continue
        _walk_unknown_fields(value, schema[key], (*path, str(key)), warnings)


def _find_secret_fields(node: Any, path: tuple[str, ...], errors: list[str]) -> None:
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        key_name = str(key).lower()
        if any(token in key_name for token in _SECRET_KEY_TOKENS):
            errors.append(
                f"{'.'.join((*path, str(key)))}: secret-like fields are not allowed"
            )
        _find_secret_fields(value, (*path, str(key)), errors)


def _has_error(errors: list[str], prefix: str) -> bool:
    return any(error == prefix or error.startswith(f"{prefix}:") for error in errors)


def _source_actual(parent: Any, field_name: str) -> str:
    if not isinstance(parent, dict):
        return "missing parent mapping"
    source = parent.get(field_name)
    if not isinstance(source, dict):
        return "missing source object"
    value = source.get("value")
    confidence = source.get("confidence", "missing")
    return f"{value!r} ({confidence})"


def _validation_checks(
    document: Any,
    errors: list[str],
    warnings: list[str],
) -> list[ValidationCheck]:
    """Build a detailed ledger from the validator's errors and warnings."""

    checks: list[ValidationCheck] = []

    def record(
        category: str,
        name: str,
        path: str,
        expected: str,
        actual: str,
        passed: bool,
        detail: str = "",
    ) -> None:
        checks.append(
            ValidationCheck(
                category=category,
                name=name,
                path=path,
                expected=expected,
                actual=actual,
                status="pass" if passed else "fail",
                detail=detail,
            )
        )

    if not isinstance(document, dict):
        record(
            "Document",
            "YAML document shape",
            "document",
            "Mapping",
            type(document).__name__,
            False,
            "The document must be a YAML mapping.",
        )
        return checks

    record(
        "Document",
        "YAML document shape",
        "document",
        "Mapping",
        "Mapping",
        True,
    )
    record(
        "Document",
        "API version",
        "apiVersion",
        EXPORT_API_VERSION,
        repr(document.get("apiVersion")),
        document.get("apiVersion") == EXPORT_API_VERSION,
    )
    record(
        "Document",
        "Resource kind",
        "kind",
        INFRA_EXPORT_KIND,
        repr(document.get("kind")),
        document.get("kind") == INFRA_EXPORT_KIND,
    )
    record(
        "Document",
        "Schema version",
        "schemaVersion",
        INFRA_EXPORT_SCHEMA_VERSION,
        repr(document.get("schemaVersion")),
        str(document.get("schemaVersion")) == INFRA_EXPORT_SCHEMA_VERSION,
    )

    metadata = document.get("metadata")
    metadata_mapping = isinstance(metadata, dict)
    record(
        "Metadata",
        "Metadata mapping",
        "metadata",
        "Mapping",
        "Mapping" if metadata_mapping else type(metadata).__name__,
        metadata_mapping,
    )
    metadata = metadata if metadata_mapping else {}
    infra_name = (
        metadata.get("name", {}).get("value")
        if isinstance(metadata.get("name"), dict)
        else None
    )
    environment_name = (
        metadata.get("environment", {}).get("value")
        if isinstance(metadata.get("environment"), dict)
        else None
    )
    record(
        "Metadata",
        "Infra-cluster metadata",
        "metadata.name",
        "Source object with cluster name",
        _source_actual(metadata, "name"),
        not _has_error(errors, "metadata.name"),
    )
    record(
        "Metadata",
        "Environment metadata",
        "metadata.environment",
        "Source object with environment name",
        _source_actual(metadata, "environment"),
        not _has_error(errors, "metadata.environment"),
    )
    record(
        "Metadata",
        "Infra-cluster name format",
        "metadata.name.value",
        "Valid DNS-like cluster name",
        repr(infra_name),
        not _has_error(errors, "metadata.name.value"),
    )
    record(
        "Metadata",
        "Environment name format",
        "metadata.environment.value",
        "Valid DNS-like environment name",
        repr(environment_name),
        not _has_error(errors, "metadata.environment.value"),
    )
    expected_infra_name = (
        f"{environment_name}-infra"
        if isinstance(environment_name, str)
        else None
    )
    record(
        "Metadata",
        "Environment and infra naming",
        "metadata",
        f"ENVIRONMENT-infra ({expected_infra_name!r})",
        repr(infra_name),
        not _has_error(errors, "metadata: infra-cluster name"),
    )

    spec = document.get("spec")
    spec_mapping = isinstance(spec, dict)
    record(
        "Specification",
        "Specification mapping",
        "spec",
        "Mapping",
        "Mapping" if spec_mapping else type(spec).__name__,
        spec_mapping,
    )
    spec = spec if spec_mapping else {}
    inventory = spec.get("inventory")
    inventory_mapping = isinstance(inventory, dict)
    record(
        "Inventory",
        "Inventory mapping",
        "spec.inventory",
        "Mapping",
        "Mapping" if inventory_mapping else type(inventory).__name__,
        inventory_mapping,
    )
    inventory = inventory if inventory_mapping else {}
    clusters = inventory.get("clusters")
    clusters_mapping = isinstance(clusters, dict)
    record(
        "Inventory",
        "Inventory cluster mapping",
        "spec.inventory.clusters",
        "Mapping of cluster names",
        "Mapping" if clusters_mapping else type(clusters).__name__,
        clusters_mapping,
    )
    clusters = clusters if clusters_mapping else {}
    expected_cluster_present = isinstance(infra_name, str) and infra_name in clusters
    record(
        "Inventory",
        "Expected inventory cluster",
        "spec.inventory.clusters",
        repr(infra_name),
        "present" if expected_cluster_present else "missing",
        expected_cluster_present,
    )
    cluster = clusters.get(infra_name, {}) if isinstance(infra_name, str) else {}
    cluster_name = (
        cluster.get("name", {}).get("value")
        if isinstance(cluster, dict) and isinstance(cluster.get("name"), dict)
        else None
    )
    record(
        "Inventory",
        "Inventory cluster name",
        f"spec.inventory.clusters.{infra_name}.name.value"
        if isinstance(infra_name, str)
        else "spec.inventory.clusters",
        repr(infra_name),
        repr(cluster_name),
        cluster_name == infra_name and isinstance(infra_name, str),
    )

    variables = spec.get("variables")
    variables_mapping = isinstance(variables, dict)
    record(
        "Network and domain",
        "Variables mapping",
        "spec.variables",
        "Mapping",
        "Mapping" if variables_mapping else type(variables).__name__,
        variables_mapping,
    )
    variables = variables if variables_mapping else {}
    variable_fields = variables.get("fields")
    fields_mapping = isinstance(variable_fields, dict)
    record(
        "Network and domain",
        "Variable fields mapping",
        "spec.variables.fields",
        "Mapping of required fields",
        "Mapping" if fields_mapping else type(variable_fields).__name__,
        fields_mapping,
    )
    variable_fields = variable_fields if fields_mapping else {}
    values: dict[str, Any] = {}
    for variable_name in REQUIRED_VARIABLE_FIELDS:
        path = f"spec.variables.fields.{variable_name}"
        values[variable_name] = (
            variable_fields.get(variable_name, {}).get("value")
            if isinstance(variable_fields.get(variable_name), dict)
            else None
        )
        record(
            "Network and domain",
            f"Required field: {variable_name}",
            path,
            "Source object with value, provenance, and confidence",
            _source_actual(variable_fields, variable_name),
            not _has_error(errors, path),
        )

    record(
        "Network and domain",
        "Machine network CIDR syntax",
        "spec.variables.fields.machine_network.value",
        "Valid IPv4 or IPv6 CIDR",
        repr(values.get("machine_network")),
        not _has_error(errors, "spec.variables.fields.machine_network.value"),
    )
    for ip_field in ("api_ip", "ingress_ip", "dns_ip"):
        path = f"spec.variables.fields.{ip_field}.value"
        record(
            "Network and domain",
            f"{ip_field} syntax",
            path,
            "Valid IPv4 or IPv6 address",
            repr(values.get(ip_field)),
            not _has_error(errors, path),
        )
    for domain_field in ("cluster_domain_name", "base_domain"):
        path = f"spec.variables.fields.{domain_field}.value"
        record(
            "Network and domain",
            f"{domain_field} syntax",
            path,
            "Valid DNS name",
            repr(values.get(domain_field)),
            not _has_error(errors, path),
        )

    domain = (
        spec.get("domain", {}).get("value")
        if isinstance(spec.get("domain"), dict)
        else None
    )
    expected_domain = (
        f"{values.get('cluster_domain_name')}.{values.get('base_domain')}"
        if isinstance(values.get("cluster_domain_name"), str)
        and isinstance(values.get("base_domain"), str)
        else None
    )
    record(
        "Network and domain",
        "Domain consistency",
        "spec.domain.value",
        "cluster_domain_name.base_domain "
        f"({expected_domain!r})",
        repr(domain),
        not _has_error(errors, "spec.domain.value"),
    )

    secret_errors = [
        error for error in errors if "secret-like fields are not allowed" in error
    ]
    record(
        "Security",
        "Secret-like field names",
        "document",
        "No fields named secret, token, password, or credential",
        f"{len(secret_errors)} prohibited field(s)",
        not secret_errors,
        "; ".join(secret_errors),
    )

    unknown_warnings = [
        warning for warning in warnings if warning.endswith("unknown field (warning)")
    ]
    checks.append(
        ValidationCheck(
            category="Schema compatibility",
            name="Unknown fields",
            path="document",
            expected="Only fields defined by schema version 1",
            actual=f"{len(unknown_warnings)} unknown field(s)",
            status="warning" if unknown_warnings else "pass",
            detail="; ".join(unknown_warnings),
        )
    )
    return checks


def validate_infra_cluster(document: Any) -> ValidationResult:
    """Validate an InfraCluster desired-state document."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(document, dict):
        return ValidationResult(
            errors=["document: expected a YAML mapping"],
            checks=_validation_checks(document, ["document: expected a YAML mapping"], []),
        )

    if document.get("apiVersion") != EXPORT_API_VERSION:
        errors.append(f"apiVersion: expected {EXPORT_API_VERSION}")
    if document.get("kind") != INFRA_EXPORT_KIND:
        errors.append(f"kind: expected {INFRA_EXPORT_KIND}")
    if str(document.get("schemaVersion")) != INFRA_EXPORT_SCHEMA_VERSION:
        errors.append(f"schemaVersion: expected {INFRA_EXPORT_SCHEMA_VERSION}")

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata: expected a mapping")
        metadata = {}
    infra_name = _required_source(metadata, "name", "metadata.name", errors)
    environment_name = _required_source(
        metadata,
        "environment",
        "metadata.environment",
        errors,
    )
    if not isinstance(infra_name, str) or not _is_domain(infra_name):
        errors.append("metadata.name.value: expected a valid cluster name")
    if not isinstance(environment_name, str) or not _is_domain(environment_name):
        errors.append("metadata.environment.value: expected a valid environment name")
    if (
        isinstance(infra_name, str)
        and isinstance(environment_name, str)
        and infra_name != f"{environment_name}-infra"
    ):
        errors.append(
            "metadata: infra-cluster name must be ENVIRONMENT-infra; "
            f"expected {environment_name}-infra, got {infra_name}"
        )

    spec = document.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec: expected a mapping")
        spec = {}

    inventory = spec.get("inventory")
    if not isinstance(inventory, dict):
        errors.append("spec.inventory: expected a mapping")
        inventory = {}
    clusters = inventory.get("clusters")
    if not isinstance(clusters, dict):
        errors.append("spec.inventory.clusters: expected a mapping")
        clusters = {}
    if isinstance(infra_name, str) and infra_name in clusters:
        cluster = clusters[infra_name]
        cluster_name = (
            _source_value(cluster, "name", f"spec.inventory.clusters.{infra_name}.name", errors)
            if isinstance(cluster, dict)
            else None
        )
        if cluster_name != infra_name:
            errors.append(
                f"spec.inventory.clusters.{infra_name}.name.value: expected "
                f"{infra_name!r}, got {cluster_name!r}"
            )
    else:
        errors.append(f"spec.inventory.clusters: missing required cluster {infra_name!r}")

    variables = spec.get("variables")
    if not isinstance(variables, dict):
        errors.append("spec.variables: expected a mapping")
        variables = {}
    variable_fields = variables.get("fields")
    if not isinstance(variable_fields, dict):
        errors.append("spec.variables.fields: expected a mapping")
        variable_fields = {}

    values: dict[str, Any] = {}
    for variable_name in REQUIRED_VARIABLE_FIELDS:
        values[variable_name] = _required_source(
            variable_fields,
            variable_name,
            f"spec.variables.fields.{variable_name}",
            errors,
        )

    try:
        ipaddress.ip_network(values["machine_network"], strict=False)
    except (TypeError, ValueError):
        errors.append("spec.variables.fields.machine_network.value: invalid CIDR")
    for ip_field in ("api_ip", "ingress_ip", "dns_ip"):
        try:
            ipaddress.ip_address(values[ip_field])
        except (TypeError, ValueError):
            errors.append(f"spec.variables.fields.{ip_field}.value: invalid IP address")

    if not _is_domain(values["cluster_domain_name"]):
        errors.append(
            "spec.variables.fields.cluster_domain_name.value: invalid domain"
        )
    if not _is_domain(values["base_domain"]):
        errors.append("spec.variables.fields.base_domain.value: invalid domain")
    domain = _required_source(spec, "domain", "spec.domain", errors)
    expected_domain = (
        f"{values['cluster_domain_name']}.{values['base_domain']}"
        if isinstance(values["cluster_domain_name"], str)
        and isinstance(values["base_domain"], str)
        else None
    )
    if domain != expected_domain:
        errors.append(
            "spec.domain.value: expected "
            f"{expected_domain!r}, got {domain!r}"
        )

    _walk_unknown_fields(document, _DOCUMENT_SCHEMA, (), warnings)
    _find_secret_fields(document, (), errors)
    return ValidationResult(
        errors=errors,
        warnings=warnings,
        checks=_validation_checks(document, errors, warnings),
    )


def load_validation_result(path: Path) -> ValidationResult:
    """Load and validate a desired-state YAML file."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(errors=[f"could not read {path}: {exc}"])
    try:
        document = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        error = f"invalid YAML: {exc}"
        return ValidationResult(
            errors=[error],
            checks=[
                ValidationCheck(
                    category="Document",
                    name="YAML parsing and duplicate keys",
                    path="document",
                    expected="Parseable YAML without duplicate mapping keys",
                    actual="Invalid YAML",
                    status="fail",
                    detail=error,
                )
            ],
        )
    result = validate_infra_cluster(document)
    return ValidationResult(
        errors=result.errors,
        warnings=result.warnings,
        checks=[
            ValidationCheck(
                category="Document",
                name="YAML parsing and duplicate keys",
                path="document",
                expected="Parseable YAML without duplicate mapping keys",
                actual="Valid",
                status="pass",
            ),
            *result.checks,
        ],
    )


def render_validation_text(result: ValidationResult) -> str:
    status = "VALID" if result.valid else "INVALID"
    lines = [f"Desired-state validation: {status}"]
    if result.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in result.errors)
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in result.warnings)
    if not result.errors and not result.warnings:
        lines.append("No validation errors or warnings.")
    return "\n".join(lines) + "\n"


def render_validation_json(result: ValidationResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_validation_markdown(
    result: ValidationResult,
    path: Path | None = None,
) -> str:
    """Render a standalone human-readable validation report."""

    status = "✅ VALID" if result.valid else "❌ INVALID"
    document = str(path) if path is not None else "—"
    passed_count = sum(check.status == "pass" for check in result.checks)
    failed_count = sum(check.status == "fail" for check in result.checks)
    warning_count = sum(check.status == "warning" for check in result.checks)
    status_symbols = {
        "pass": "✅ Pass",
        "fail": "❌ Fail",
        "warning": "⚠️ Warning",
    }
    lines = [
        "# 🧪 Desired-State Validation",
        "",
        f"**Result:** {status}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Document | `{_markdown_cell(document)}` |",
        f"| Error count | {len(result.errors)} |",
        f"| Warning count | {len(result.warnings)} |",
        f"| Checks passed | {passed_count} |",
        f"| Checks failed | {failed_count} |",
        f"| Checks with warnings | {warning_count} |",
        f"| Total checks | {len(result.checks)} |",
    ]

    if result.checks:
        categories: list[str] = []
        for check in result.checks:
            if check.category not in categories:
                categories.append(check.category)

        lines.extend(
            [
                "",
                "## Check summary by category",
                "",
                "| Category | Passed | Failed | Warnings | Total |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for category in categories:
            category_checks = [
                check for check in result.checks if check.category == category
            ]
            lines.append(
                f"| {category} | "
                f"{sum(check.status == 'pass' for check in category_checks)} | "
                f"{sum(check.status == 'fail' for check in category_checks)} | "
                f"{sum(check.status == 'warning' for check in category_checks)} | "
                f"{len(category_checks)} |"
            )

        lines.extend(
            [
                "",
                "## Detailed checks",
                "",
            ]
        )
        for category in categories:
            category_checks = [
                check for check in result.checks if check.category == category
            ]
            category_pass = sum(check.status == "pass" for check in category_checks)
            lines.extend(
                [
                    f"### {category}",
                    "",
                    f"{category_pass} of {len(category_checks)} checks passed.",
                    "",
                    "| Check | Path | Expected | Actual | Result | Detail |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for check in category_checks:
                lines.append(
                    "| "
                    f"{_markdown_cell(check.name)} | "
                    f"`{_markdown_cell(check.path)}` | "
                    f"{_markdown_cell(check.expected)} | "
                    f"{_markdown_cell(check.actual)} | "
                    f"{status_symbols.get(check.status, check.status)} | "
                    f"{_markdown_cell(check.detail or '—')} |"
                )
            lines.append("")

    if result.errors:
        lines.extend(
            [
                "",
                "## Errors",
                "",
                "| # | Issue |",
                "|---:|---|",
            ]
        )
        lines.extend(
            f"| {number} | {_markdown_cell(error)} |"
            for number, error in enumerate(result.errors, start=1)
        )

    if result.warnings:
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                "| # | Issue |",
                "|---:|---|",
            ]
        )
        lines.extend(
            f"| {number} | {_markdown_cell(warning)} |"
            for number, warning in enumerate(result.warnings, start=1)
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- **VALID** means the document satisfies the current desired-state schema and validation rules.",
            "- **INVALID** means at least one error must be corrected before the document is reviewed as desired state.",
            "- Warnings identify unknown fields or unusual content; they do not fail validation.",
            "- This report validates repository-derived desired state only. It does not prove live cluster health or synchronization.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
