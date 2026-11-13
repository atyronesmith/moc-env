"""Discovery and reconciliation for chart-value documentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import yaml

from .chart_values import ManualDocumentation, ManualVariable


@dataclass(frozen=True)
class DiscoveredVariable:
    """One variable discovered from local oac-apps values files."""

    key: str
    charts: tuple[str, ...]
    scopes: tuple[str, ...]
    types: tuple[str, ...]
    file_count: int
    paths: tuple[str, ...]


@dataclass(frozen=True)
class DefaultConflict:
    """A manual default that differs from a chart default."""

    key: str
    chart: str
    manual_default: Any
    chart_default: Any


@dataclass(frozen=True)
class DiscoveryReport:
    """The result of reconciling manual and discovered chart values."""

    repository_root: str
    cache_root: str
    manual_variable_count: int
    discovered_variable_count: int
    matched_variable_count: int
    new_variables: tuple[DiscoveredVariable, ...]
    manual_without_occurrence: tuple[str, ...]
    changed_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    default_conflicts: tuple[DefaultConflict, ...]
    unsupported_yaml_files: tuple[str, ...]


def _scope(path: Path, repository: Path) -> str:
    relative = path.relative_to(repository).as_posix()
    parts = relative.split("/")
    if relative.startswith("values/") and len(parts) >= 3:
        if parts[2] == "local-cluster":
            return "hub-local-cluster"
        if len(parts) > 3:
            return "workload-components"
        return "hub-wide"
    if relative.startswith("hosted-clusters/"):
        if len(parts) == 3:
            return "hosted-cluster-defaults"
        return "hosted-cluster"
    return "other"


def _chart_name(path: Path, repository: Path, scope: str) -> str:
    relative = path.relative_to(repository).as_posix()
    filename = path.stem
    if scope == "hosted-cluster" and filename == "values":
        return "hosted-cluster"
    if scope == "hosted-cluster-defaults" and filename == "values":
        return "hosted-cluster-defaults"
    return filename


def _flatten(
    values: dict[str, Any],
    prefix: str = "",
) -> dict[str, list[Any]]:
    flattened: dict[str, list[Any]] = {}

    def visit(mapping: dict[str, Any], path: str) -> None:
        for key, value in mapping.items():
            key_path = f"{path}.{key}" if path else str(key)
            flattened.setdefault(key_path, []).append(value)
            if isinstance(value, dict):
                visit(value, key_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        visit(item, f"{key_path}[]")
                    else:
                        flattened.setdefault(f"{key_path}[]", []).append(item)

    visit(values, prefix)
    return flattened


def _values_paths(repository: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in ("values", "hosted-clusters"):
        root = repository / directory
        if root.is_dir():
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix in {".yaml", ".yml"}
            )
    return sorted(paths)


def discover_chart_values(repository: Path) -> tuple[
    dict[str, DiscoveredVariable], tuple[str, ...]
]:
    """Discover variables from local oac-apps values files."""

    repository = repository.resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"repository not found: {repository}")

    discovered: dict[str, dict[str, set[Any]]] = {}
    unsupported: list[str] = []
    for path in _values_paths(repository):
        relative = path.relative_to(repository).as_posix()
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            unsupported.append(relative)
            continue
        if parsed is None:
            continue
        if not isinstance(parsed, dict):
            unsupported.append(relative)
            continue

        scope = _scope(path, repository)
        chart = _chart_name(path, repository, scope)
        flattened = _flatten(parsed)
        for key, values in flattened.items():
            aggregate = discovered.setdefault(
                key,
                {
                    "charts": set(),
                    "scopes": set(),
                    "types": set(),
                    "paths": set(),
                },
            )
            aggregate["charts"].add(chart)
            aggregate["scopes"].add(scope)
            aggregate["types"].update(type(value).__name__ for value in values)
            aggregate["paths"].add(relative)

    variables = {
        key: DiscoveredVariable(
            key=key,
            charts=tuple(sorted(aggregate["charts"])),
            scopes=tuple(sorted(aggregate["scopes"])),
            types=tuple(sorted(aggregate["types"])),
            file_count=len(aggregate["paths"]),
            paths=tuple(sorted(aggregate["paths"])),
        )
        for key, aggregate in discovered.items()
    }
    return variables, tuple(sorted(unsupported))


def _chart_defaults(repository: Path, chart: str) -> dict[str, Any]:
    path = repository / "charts" / chart / "values.yaml"
    if not path.is_file():
        return {}
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _default_conflicts(
    manual_variables: dict[str, ManualVariable],
    discovered: dict[str, DiscoveredVariable],
    repository: Path,
) -> tuple[DefaultConflict, ...]:
    conflicts: list[DefaultConflict] = []
    for key, variable in manual_variables.items():
        if variable.default is None:
            continue
        observed = discovered.get(key)
        if observed is None:
            continue
        for chart in observed.charts:
            defaults = _flatten(_chart_defaults(repository, chart))
            if key not in defaults:
                continue
            chart_default = defaults[key][0]
            if chart_default != variable.default:
                conflicts.append(
                    DefaultConflict(
                        key=key,
                        chart=chart,
                        manual_default=variable.default,
                        chart_default=chart_default,
                    )
                )
    return tuple(conflicts)


def _load_manifest(cache_root: Path) -> dict[str, Any]:
    path = cache_root / "manifest.json"
    if not path.is_file():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def build_discovery_report(
    manual: ManualDocumentation,
    repository: Path,
    cache_root: Path,
) -> DiscoveryReport:
    """Reconcile manual definitions with local repository discovery."""

    repository = repository.resolve()
    cache_root = cache_root.resolve()
    discovered, unsupported = discover_chart_values(repository)
    manifest = _load_manifest(cache_root)
    manifest_sources = manifest.get("sources", {})
    if not isinstance(manifest_sources, dict):
        manifest_sources = {}

    manual_variables = {
        variable.key: variable
        for topic in manual.topics
        for variable in topic.variables
    }
    new_keys = sorted(set(discovered) - set(manual_variables))
    manual_without_occurrence = sorted(set(manual_variables) - set(discovered))
    matched = set(manual_variables) & set(discovered)

    changed_evidence: set[str] = set()
    missing_evidence: set[str] = set()
    for variable in manual_variables.values():
        for evidence in variable.evidence:
            entry = manifest_sources.get(evidence.source)
            if not isinstance(entry, dict):
                missing_evidence.add(evidence.source)
                continue
            document_path = entry.get("documentPath")
            if not isinstance(document_path, str) or not (
                cache_root / document_path
            ).is_file():
                missing_evidence.add(evidence.source)
            elif entry.get("status") != "current":
                changed_evidence.add(evidence.source)

    default_conflicts = _default_conflicts(
        manual_variables,
        discovered,
        repository,
    )

    return DiscoveryReport(
        repository_root=str(repository),
        cache_root=str(cache_root),
        manual_variable_count=len(manual_variables),
        discovered_variable_count=len(discovered),
        matched_variable_count=len(matched),
        new_variables=tuple(discovered[key] for key in new_keys),
        manual_without_occurrence=tuple(manual_without_occurrence),
        changed_evidence=tuple(sorted(changed_evidence)),
        missing_evidence=tuple(sorted(missing_evidence)),
        default_conflicts=default_conflicts,
        unsupported_yaml_files=unsupported,
    )


def render_discovery_markdown(report: DiscoveryReport) -> str:
    """Render a human-readable discovery report."""

    lines = [
        "# 🔍 Chart Values Discovery Report",
        "",
        "This report reconciles manual variable definitions with variables found in the local `oac-apps` clone. It does not modify manual documentation.",
        "",
        "| Measure | Count |",
        "|---|---:|",
        f"| Manual variables | {report.manual_variable_count} |",
        f"| Discovered variables | {report.discovered_variable_count} |",
        f"| Matched variables | {report.matched_variable_count} |",
        f"| New variables needing definitions | {len(report.new_variables)} |",
        f"| Manual variables without current occurrences | {len(report.manual_without_occurrence)} |",
        f"| Changed evidence sources | {len(report.changed_evidence)} |",
        f"| Missing evidence sources | {len(report.missing_evidence)} |",
        f"| Default conflicts | {len(report.default_conflicts)} |",
        f"| Unsupported YAML files | {len(report.unsupported_yaml_files)} |",
        "",
        "## New variables needing definitions",
        "",
        "| Key | Charts | Scopes | Files |",
        "|---|---|---|---:|",
    ]
    if report.new_variables:
        for variable in report.new_variables:
            lines.append(
                f"| `{variable.key}` | `{', '.join(variable.charts)}` | "
                f"`{', '.join(variable.scopes)}` | {variable.file_count} |"
            )
    else:
        lines.append("| — | — | — | 0 |")

    lines.extend(
        [
            "",
            "## Manual variables without current occurrences",
            "",
        ]
    )
    if report.manual_without_occurrence:
        lines.extend(
            f"- `{key}`" for key in report.manual_without_occurrence
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Changed evidence",
            "",
        ]
    )
    if report.changed_evidence:
        lines.extend(f"- `{source}`" for source in report.changed_evidence)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Missing evidence",
            "",
        ]
    )
    if report.missing_evidence:
        lines.extend(f"- `{source}`" for source in report.missing_evidence)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Default conflicts",
            "",
            "| Key | Chart | Manual default | Chart default |",
            "|---|---|---|---|",
        ]
    )
    if report.default_conflicts:
        for conflict in report.default_conflicts:
            lines.append(
                f"| `{conflict.key}` | `{conflict.chart}` | "
                f"`{conflict.manual_default}` | `{conflict.chart_default}` |"
            )
    else:
        lines.append("| — | — | — | — |")

    lines.extend(
        [
            "",
            "## Unsupported YAML files",
            "",
        ]
    )
    if report.unsupported_yaml_files:
        lines.extend(f"- `{path}`" for path in report.unsupported_yaml_files)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def render_discovery_text(report: DiscoveryReport) -> str:
    """Render a compact discovery report."""

    return (
        "Chart values discovery: "
        f"{report.manual_variable_count} manual, "
        f"{report.discovered_variable_count} discovered, "
        f"{report.matched_variable_count} matched, "
        f"{len(report.new_variables)} new, "
        f"{len(report.manual_without_occurrence)} without occurrence, "
        f"{len(report.changed_evidence)} changed evidence, "
        f"{len(report.missing_evidence)} missing evidence, "
        f"{len(report.default_conflicts)} default conflicts.\n"
    )


def render_discovery_json(report: DiscoveryReport) -> str:
    """Render the discovery report as JSON."""

    return json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
