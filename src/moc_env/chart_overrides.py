"""Compare per-cluster chart value layers with a chart's declared defaults.

The functions here are pure: callers read chart and values files and pass the
parsed mappings in.  They are shared by the ``charts --view overrides`` report.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from . import feature_charts

ADDED = "added"
CHANGED = "changed"
RESTATED = "restated"

_MISSING = object()


def _lookup(mapping: Mapping[Any, Any], parts: Sequence[str]) -> Any:
    """Return the dotted value, or a private sentinel when any part is absent."""

    current: Any = mapping
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _source(parts: Sequence[str], layers: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """Return the path of the last layer that contains the dotted key."""

    for path, layer in reversed(layers):
        if _lookup(layer, parts) is not _MISSING:
            return path
    return ""


def _leaf_rows(
    value: Any,
    parts: tuple[str, ...],
    defaults: Mapping[str, Any],
    layers: Sequence[tuple[str, Mapping[str, Any]]],
    rows: list[dict[str, Any]],
) -> None:
    if isinstance(value, Mapping) and value:
        for key, child in value.items():
            _leaf_rows(
                child,
                (*parts, str(key)),
                defaults,
                layers,
                rows,
            )
        return

    key = ".".join(parts)
    default = _lookup(defaults, parts)
    if default is _MISSING:
        status = ADDED
    elif default == value:
        status = RESTATED
    else:
        status = CHANGED

    row: dict[str, Any] = {
        "key": key,
        "status": status,
        "value": copy.deepcopy(value),
        "source": _source(parts, layers),
    }
    if status != ADDED:
        row["default"] = copy.deepcopy(default)
    rows.append(row)


def override_rows(
    defaults: Mapping[str, Any],
    layers: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Compare ordered value layers with chart defaults.

    Layers are merged in order with :func:`feature_charts.deep_merge`; the
    defaults are consulted only for comparison, never merged.  Every leaf in
    the merged result becomes a row whose ``source`` is the last layer that
    contains that dotted key.  Rows are sorted by key.
    """

    merged: Any = {}
    for _path, layer in layers:
        merged = feature_charts.deep_merge(merged, dict(layer))
    if not isinstance(merged, Mapping) or not merged:
        return []

    rows: list[dict[str, Any]] = []
    for key, value in merged.items():
        _leaf_rows(value, (str(key),), defaults, layers, rows)
    return sorted(rows, key=lambda row: row["key"])


# A descriptive alias for callers that prefer the module's noun.
chart_overrides = override_rows

