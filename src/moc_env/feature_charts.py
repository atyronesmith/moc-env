"""Resolve oac-apps feature labels and placements to charts and values.

The application-set files under ``applicationsets/templates/managed`` are Helm
templates, not YAML, so this module extracts only the small set of literals the
status checks need.  Everything here is pure parsing or value merging so it can
be exercised without a GitHub client.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

ALL_MANAGED_PLACEMENT = "all-managed-clusters"

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
_TEMPLATE_COMMENT = re.compile(r"\{\{-?\s*/\*.*?\*/\s*-?\}\}", re.DOTALL)
_ACTION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_REQUIRED = re.compile(
    r'required\s+"([^"]*)"\s+\$?\.Values\.([A-Za-z0-9_.]+)'
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


def parse_application_set(text: str, name: str = "") -> ApplicationSet:
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
    )


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
