"""Resolve oac-apps feature labels and placements to charts and values.

The application-set files under ``applicationsets/templates/managed`` are Helm
templates, not YAML, so this module extracts only the small set of literals the
status checks need.  Everything here is pure parsing or value merging so it can
be exercised without a GitHub client.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml

ALL_MANAGED_PLACEMENT = "all-managed-clusters"

TextReader = Callable[[str], tuple[str | None, str | None]]

_PLACEMENT = re.compile(
    r"cluster\.open-cluster-management\.io/placement:\s*([a-z0-9-]+)"
)
_COMPONENT = re.compile(
    r"^\s*-\s*component:\s*([a-z0-9-]+)\s*$", re.MULTILINE
)
_LITERAL_CHART = re.compile(
    r"^\s*path:\s*[\"']?charts/([a-z0-9-]+)[\"']?\s*$", re.MULTILINE
)
_QUOTED_PATH = re.compile(r"^\s*path:\s*[\"']([^\"']+)[\"']\s*$", re.MULTILINE)
_COMPONENT_SOURCE = re.compile(
    r"^\s*path:\s*[\"']?charts/\{\{.*component.*\}\}[\"']?\s*$",
    re.MULTILINE,
)
_FILES_GENERATOR_PATH = re.compile(
    r"^\s*-\s*path:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", re.MULTILINE
)
_METADATA_NAME = re.compile(
    r"^metadata:\s*\n(?:[ \t].*\n)*?[ \t]+name:\s*[\"']?([A-Za-z0-9._-]+)",
    re.MULTILINE,
)
_TEMPLATE_COMMENT = re.compile(r"\{\{-?\s*/\*.*?\*/\s*-?\}\}", re.DOTALL)
_ACTION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_REQUIRED = re.compile(
    r'required\s+"([^"]*)"\s+\$?\.Values\.([A-Za-z0-9_.]+)'
)

KNOWN_APPLICATION_SET_FILES = frozenset(
    {
        "cluster-apps.yaml",
        "hosted-clusters.yaml",
        "hosted-cluster-compliance.yaml",
        "pure-cosi.yaml",
    }
)


@dataclass(frozen=True)
class Placement:
    """One placement from a hub's acm-placements.yaml."""

    name: str
    match_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplicationSet:
    """The placement and destination charts named by one managed template."""

    name: str
    placement: str | None
    components: tuple[str, ...] = ()
    literal_chart: str | None = None
    kustomize_path: str | None = None
    value_files: tuple[str, ...] = ()
    manifest_path: str = ""


def parse_placements(text: str) -> list[Placement]:
    """Parse an acm-placements.yaml body.

    Raises ``ValueError`` when the file is not a mapping with a placements
    list, which the caller reports as an unknown check result.
    """

    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("placements"), list):
        raise ValueError("acm-placements.yaml does not contain a placements list")
    placements: list[Placement] = []
    for item in data["placements"]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        labels = item.get("matchLabels")
        match_labels = {
            str(key): str(value)
            for key, value in (labels.items() if isinstance(labels, dict) else ())
        }
        placements.append(Placement(name=name, match_labels=match_labels))
    return placements


def merge_placements(
    underneath: list[Placement], override: list[Placement]
) -> list[Placement]:
    """Layer a hub-wide placement list underneath the local-cluster one."""

    merged = list(underneath)
    index = {placement.name: position for position, placement in enumerate(merged)}
    for placement in override:
        if placement.name in index:
            merged[index[placement.name]] = placement
        else:
            index[placement.name] = len(merged)
            merged.append(placement)
    return merged


def _value_file_scalar(raw: str) -> str:
    """Return one valueFiles list item without its YAML quoting or comment."""

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, str):
        return parsed
    text = raw.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_value_files(text: str) -> tuple[str, ...]:
    """Read the entries under the first ``valueFiles:`` block, in order.

    The ApplicationSet files are Helm templates, so this walks the YAML text
    by indentation instead of parsing the whole document with ``yaml``.
    """

    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^([ \t]*)valueFiles:\s*(.*)$", line)
        if match is None:
            continue
        indent = len(match.group(1))
        remainder = match.group(2).strip()
        if remainder:
            if remainder.startswith("["):
                try:
                    parsed = yaml.safe_load(remainder)
                except yaml.YAMLError:
                    parsed = None
                if isinstance(parsed, list):
                    return tuple(
                        str(item) for item in parsed if isinstance(item, str)
                    )
            return (_value_file_scalar(remainder),)
        entries: list[str] = []
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if not stripped:
                continue
            following_indent = len(following) - len(following.lstrip(" \t"))
            if following_indent <= indent:
                break
            if stripped.startswith("#"):
                continue
            if not stripped.startswith("-"):
                break
            value = stripped[1:].strip()
            if value:
                entries.append(_value_file_scalar(value))
        return tuple(entries)
    return ()


def resolve_value_file(
    entry: str, hub: str, cluster: str, chart: str
) -> str | None:
    """Resolve one manifest valueFiles entry for a cluster and chart."""

    value = gated_path_for_hub(entry, hub)
    value = value.replace("{{`{{name}}`}}", cluster)
    value = value.replace("{{`{{component}}`}}", chart)
    if "{{" in value:
        return None
    return value.lstrip("/")


def parse_application_set(
    text: str, name: str = "", manifest_path: str = ""
) -> ApplicationSet:
    """Extract the placement, components and source path from a Helm template."""

    placement_match = _PLACEMENT.search(text)
    components = tuple(dict.fromkeys(_COMPONENT.findall(text)))
    literal = _LITERAL_CHART.search(text)
    literal_chart = literal.group(1) if literal and not components else None
    kustomize_path = next(
        (
            path
            for path in _QUOTED_PATH.findall(text)
            if path.startswith("kustomize/") and "{{" in path and "name" in path
        ),
        None,
    )
    return ApplicationSet(
        name=name,
        placement=placement_match.group(1) if placement_match else None,
        components=components,
        literal_chart=literal_chart,
        kustomize_path=kustomize_path,
        value_files=parse_value_files(text),
        manifest_path=manifest_path,
    )


def application_set_name(text: str, fallback: str = "") -> str:
    """Return the ApplicationSet metadata name, or the file stem fallback."""

    match = _METADATA_NAME.search(text)
    return match.group(1) if match else fallback


def has_component_source(text: str) -> bool:
    """Whether a template reads its chart from ``charts/{{component}}``."""

    return _COMPONENT_SOURCE.search(text) is not None


def hub_gate_path(text: str) -> str | None:
    """Return a git files-generator path that depends on ``$hub``, if any."""

    for value in _FILES_GENERATOR_PATH.findall(text):
        if "{{ $hub }}" in value or "{{$hub}}" in value:
            return value
    return None


def gated_path_for_hub(path: str, hub: str) -> str:
    """Substitute a hub name into a git files-generator path."""

    return (
        path.replace("{{ $hub }}", hub)
        .replace("{{$hub}}", hub)
        .replace("{{ $hub}}", hub)
        .replace("{{$hub }}", hub)
        .strip()
    )


def classify_application_set(text: str, path: str) -> str:
    """Classify one template file as known, component, literal, or kustomize.

    Returns ``"unknown"`` when the file has none of the recognized shapes.  A
    component list is any template with ``- component:`` entries; hub chart
    discovery additionally requires the ``charts/{{component}}`` source path.
    """

    if path.rsplit("/", 1)[-1] in KNOWN_APPLICATION_SET_FILES:
        return "known"
    parsed = parse_application_set(text, path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    if parsed.components:
        return "component"
    if parsed.literal_chart:
        return "literal"
    if parsed.kustomize_path:
        return "kustomize"
    return "unknown"


def feature_labels(labels: Any) -> dict[str, str]:
    """Return the true feature labels from a clusterLabels mapping."""

    if not isinstance(labels, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in labels.items()
        if "/feature-" in str(key) and str(value).strip().lower() == "true"
    }


def labels_match(match_labels: dict[str, str], cluster_labels: Any) -> bool:
    """Whether every placement label equals the cluster label, ignoring case."""

    if not isinstance(cluster_labels, dict):
        return not match_labels
    for key, wanted in match_labels.items():
        found = cluster_labels.get(key)
        if found is None:
            return False
        if str(found).strip().lower() != str(wanted).strip().lower():
            return False
    return True


def matched_placement_names(
    placements: list[Placement], cluster_labels: Any
) -> list[str]:
    """Placements that select this cluster, including the baseline placement."""

    names = [ALL_MANAGED_PLACEMENT]
    for placement in placements:
        if placement.name not in names and labels_match(
            placement.match_labels, cluster_labels
        ):
            names.append(placement.name)
    return sorted(names)


def placement_feature_label(placement: Placement | None) -> str:
    """Name the feature label that drives a placement, or ``baseline``."""

    if placement is None:
        return "baseline"
    keys = [
        key for key in placement.match_labels if "/feature-" in key
    ]
    return ", ".join(keys) if keys else "baseline"


def deep_merge(base: Any, overlay: Any) -> Any:
    """Merge mappings recursively; any non-mapping overlay value wins."""

    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return copy.deepcopy(overlay)
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_value_layers(*layers: Any) -> dict[str, Any]:
    """Layer chart values in order, later mappings winning."""

    merged: dict[str, Any] = {}
    for layer in layers:
        if isinstance(layer, dict):
            merged = deep_merge(merged, layer)
    return merged


def lookup(values: dict[str, Any], dotted: str) -> Any:
    """Look up a dotted Helm value path, returning None when any part is absent."""

    current: Any = values
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _action_keyword(action: str) -> str:
    text = action.strip().strip("-").strip()
    return text.split(None, 1)[0] if text else ""


def required_value_paths(template: str) -> list[str]:
    """Return required ``.Values`` paths that are not inside a template block.

    Helm comments are removed first.  Actions are walked in order with a stack
    of open ``if``/``with``/``range`` blocks.  ``define`` does not open a block,
    but its matching ``end`` is still consumed.  Required calls found while a
    block is open are ignored because they may only run conditionally.
    """

    stripped = _TEMPLATE_COMMENT.sub("", template)
    stack: list[str] = []
    paths: list[str] = []
    for match in _ACTION.finditer(stripped):
        action = match.group(1)
        keyword = _action_keyword(action)
        if keyword == "end":
            if stack:
                stack.pop()
            continue
        if not any(kind != "define" for kind in stack):
            paths.extend(path for _, path in _REQUIRED.findall(action))
        if keyword in {"if", "with", "range", "define"}:
            stack.append(keyword)
    return list(dict.fromkeys(paths))


def unmet_required(paths: list[str], values: dict[str, Any]) -> list[str]:
    """Return required paths whose merged value is None or an empty string."""

    unmet: list[str] = []
    for path in paths:
        value = lookup(values, path)
        if value is None or (isinstance(value, str) and value == ""):
            unmet.append(path)
    return list(dict.fromkeys(unmet))


def kustomize_overlay_prefix(path: str, cluster: str) -> str:
    """Turn a templated kustomize source path into the cluster's directory."""

    prefix = path.split("{{", 1)[0]
    return f"{prefix}{cluster}/"


def placement_file_paths(tree: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Map each hub with placements files to its local and hub-wide paths."""

    hubs: dict[str, dict[str, str]] = {}
    for path in tree:
        parts = path.split("/")
        if (
            len(parts) == 4
            and parts[0] == "values"
            and parts[2] == "local-cluster"
            and parts[3] == "acm-placements.yaml"
        ):
            hubs.setdefault(parts[1], {})["local"] = path
        elif (
            len(parts) == 3
            and parts[0] == "values"
            and parts[2] == "acm-placements.yaml"
        ):
            hubs.setdefault(parts[1], {})["hub"] = path
    return hubs


def load_placements(
    paths: dict[str, str], read_text: TextReader
) -> tuple[list[Placement] | None, str | None]:
    """Load local-cluster placements over any hub-wide placements file."""

    local_path = paths.get("local")
    hub_path = paths.get("hub")
    if local_path is None and hub_path is None:
        return None, "no acm-placements.yaml exists for this hub"
    underneath: list[Placement] = []
    if hub_path is not None:
        text, error = read_text(hub_path)
        if text is None:
            return None, error or f"{hub_path} is unavailable."
        try:
            underneath = parse_placements(text)
        except (ValueError, yaml.YAMLError) as exc:
            return None, f"{hub_path} is not a placements list: {exc}"
    if local_path is None:
        return underneath, None
    text, error = read_text(local_path)
    if text is None:
        return None, error or f"{local_path} is unavailable."
    try:
        override = parse_placements(text)
    except (ValueError, yaml.YAMLError) as exc:
        return None, f"{local_path} is not a placements list: {exc}"
    return merge_placements(underneath, override), None


def load_application_sets(
    tree: dict[str, Any], read_text: TextReader
) -> tuple[list[ApplicationSet], list[str]]:
    """Read every managed ApplicationSet Helm template in the tree."""

    application_sets: list[ApplicationSet] = []
    errors: list[str] = []
    for path in sorted(
        path
        for path in tree
        if path.startswith("applicationsets/templates/managed/")
        and path.endswith((".yaml", ".yml"))
    ):
        text, error = read_text(path)
        if text is None:
            errors.append(error or f"{path} is unavailable.")
            continue
        if classify_application_set(text, path) == "unknown":
            errors.append(f"Unrecognized ApplicationSet template: {path}.")
            continue
        name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        application_sets.append(parse_application_set(text, name, path))
    return application_sets, errors


def read_values_file(
    tree: dict[str, Any], path: str, read_text: TextReader
) -> dict[str, Any]:
    """Read a chart values file when the tree contains it."""

    if path not in tree:
        return {}
    text, _ = read_text(path)
    if text is None:
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def workload_chart_rows(
    tree: dict[str, Any],
    hub: str,
    workload: str,
    labels: Any,
    placements: list[Placement],
    application_sets: list[ApplicationSet],
    read_text: TextReader,
) -> list[dict[str, Any]]:
    """Build the received-chart rows shared by status and ``charts``.

    Each row names a chart selected by a placement matching this workload's
    labels, the ApplicationSet and placement that selected it, the feature
    label that drives the placement, whether hub and cluster values files
    exist, and any required values still unmet after merging those files.
    """

    matched = matched_placement_names(placements, labels)
    by_name = {placement.name: placement for placement in placements}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for application_set in application_sets:
        if application_set.placement not in matched:
            continue
        placement = by_name.get(application_set.placement or "")
        feature_label = placement_feature_label(placement)
        for chart, is_component in (
            *((component, True) for component in application_set.components),
            *(
                ((application_set.literal_chart, False),)
                if application_set.literal_chart
                else ()
            ),
        ):
            if chart in seen:
                continue
            seen.add(chart)
            hub_path = f"values/{hub}/{chart}.yaml"
            cluster_path = f"values/{hub}/{workload}/{chart}.yaml"
            unmet: list[str] = []
            if is_component:
                defaults = read_values_file(
                    tree, f"charts/{chart}/values.yaml", read_text
                )
                hub_values = read_values_file(tree, hub_path, read_text)
                cluster_values = read_values_file(
                    tree, cluster_path, read_text
                )
                merged = merge_value_layers(
                    defaults, hub_values, cluster_values
                )
                required: list[str] = []
                for template_path in sorted(
                    path
                    for path in tree
                    if path.startswith(f"charts/{chart}/templates/")
                ):
                    text, _ = read_text(template_path)
                    if text is not None:
                        required.extend(required_value_paths(text))
                unmet = unmet_required(required, merged)
            rows.append(
                {
                    "chart": chart,
                    "application_set": application_set.name,
                    "placement": application_set.placement,
                    "feature_label": feature_label,
                    "hub_values_file": hub_path in tree,
                    "cluster_values_file": cluster_path in tree,
                    "unmet_required_values": unmet,
                    "component": is_component,
                }
            )
    return rows
