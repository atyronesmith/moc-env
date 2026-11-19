"""Read-only chart-to-cluster inventory for CCI-MOC/oac-apps."""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from typing import Any, Sequence

import yaml

from . import chart_reference, feature_charts
from .github import GitHubClient, GitHubError
from .repositories import OAC_APPS_REPOSITORY

HUB_TEMPLATES_PREFIX = "applicationsets/templates/hub/"
MANAGED_TEMPLATES_PREFIX = "applicationsets/templates/managed/"
APPLICATIONSET_PREFIX = "applicationsets/templates/"
FOOTER_PREFIX = (
    "Not shown in the cluster tables: the hosted-cluster chart that creates\n"
    "each workload cluster on the hub, and kustomize overlays.\n"
)
FOOTER_SUFFIX = " Declared configuration,\nnot live cluster state."
UNDEPLOYED_NOTE = (
    "These charts are not installed by any ApplicationSet or drop-in. Some\n"
    "may be applied by hand."
)


class ChartInventoryError(RuntimeError):
    """The inventory cannot be assembled from the requested source."""


@dataclass(frozen=True)
class ChartCluster:
    """One hub or workload cluster and the charts it receives."""

    name: str
    kind: str
    environment: str
    rows: tuple[dict[str, Any], ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class HubChartList:
    """One ApplicationSet that installs hub components."""

    name: str
    components: tuple[str, ...]
    gate_path: str | None = None


@dataclass(frozen=True)
class ChartInventory:
    """A resolved oac-apps snapshot and the selected clusters."""

    ref: str
    sha: str
    clusters: tuple[ChartCluster, ...]
    workload_counts: tuple[tuple[str, int], ...] = ()
    compliance_hubs: tuple[str, ...] = ()
    unrecognized: tuple[str, ...] = ()
    undeployed_charts: tuple[dict[str, Any], ...] = ()
    library_charts: tuple[str, ...] = ()
    reference: chart_reference.ChartReference | None = None

    @property
    def has_errors(self) -> bool:
        return any(cluster.error for cluster in self.clusters)


@dataclass(frozen=True)
class SummaryTable:
    """One presentation table derived entirely from collected chart rows."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


def footer(ref: str, sha: str) -> str:
    """Render the fixed explanatory footer for one source snapshot."""

    return (
        FOOTER_PREFIX
        + f"Source: {OAC_APPS_REPOSITORY} @ {ref} ({sha[:7]})."
        + FOOTER_SUFFIX
    )


def environment_name(hub: str) -> str:
    """Strip the infra suffix that distinguishes a hub directory name."""

    return hub[: -len("-infra")] if hub.endswith("-infra") else hub


def hub_directories(tree: dict[str, Any]) -> list[str]:
    """Return every hub directory named under values/."""

    return sorted(
        {
            path.split("/")[1]
            for path in tree
            if path.startswith("values/") and len(path.split("/")) >= 3
        }
    )


def workload_directories(tree: dict[str, Any]) -> dict[str, list[str]]:
    """Map each hub to the directories under hosted-clusters/ with values.yaml."""

    workloads: dict[str, list[str]] = {}
    for path in tree:
        parts = path.split("/")
        if (
            len(parts) == 4
            and parts[0] == "hosted-clusters"
            and parts[3] == "values.yaml"
        ):
            workloads.setdefault(parts[1], []).append(parts[2])
    return {hub: sorted(names) for hub, names in workloads.items()}


def _github_reader(client: GitHubClient, progress: Any) -> feature_charts.TextReader:
    cache: dict[str, str | None] = {}

    def read(path: str) -> tuple[str | None, str | None]:
        if path in cache:
            text = cache[path]
            return text, None if text is not None else f"{path} is unavailable."
        if progress is not None:
            progress("oac-apps charts", f"read {path}", OAC_APPS_REPOSITORY, path)
        try:
            client.resolve_commit(OAC_APPS_REPOSITORY)
            text, error = client.get_file(OAC_APPS_REPOSITORY, path), None
        except (GitHubError, AssertionError) as exc:
            if "(404)" in str(exc):
                error = f"{OAC_APPS_REPOSITORY}/{path} is absent or unavailable."
            else:
                error = f"{path} could not be read: {exc}"
            text = None
        cache[path] = text
        return text, error

    return read


def _application_set_files(tree: dict[str, Any], prefix: str) -> list[str]:
    return sorted(
        path
        for path in tree
        if path.startswith(prefix) and path.endswith((".yaml", ".yml"))
    )


def _hub_chart_lists(
    tree: dict[str, Any], read: feature_charts.TextReader
) -> tuple[list[HubChartList], list[str]]:
    """Discover every hub ApplicationSet that installs component charts."""

    lists: list[HubChartList] = []
    unrecognized: list[str] = []
    for path in _application_set_files(tree, HUB_TEMPLATES_PREFIX):
        text, _error = read(path)
        if text is None:
            unrecognized.append(path)
            continue
        kind = feature_charts.classify_application_set(text, path)
        if kind == "unknown":
            unrecognized.append(path)
            continue
        if kind != "component" or not feature_charts.has_component_source(text):
            continue
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        parsed = feature_charts.parse_application_set(text, stem)
        lists.append(
            HubChartList(
                name=feature_charts.application_set_name(text, stem),
                components=parsed.components,
                gate_path=feature_charts.hub_gate_path(text),
            )
        )
    return lists, unrecognized


def _unrecognized_application_sets(
    tree: dict[str, Any], read: feature_charts.TextReader
) -> tuple[str, ...]:
    """Return every template file in either directory that has no known shape."""

    unrecognized: list[str] = []
    for prefix in (HUB_TEMPLATES_PREFIX, MANAGED_TEMPLATES_PREFIX):
        for path in _application_set_files(tree, prefix):
            text, _error = read(path)
            if text is None or (
                feature_charts.classify_application_set(text, path) == "unknown"
            ):
                unrecognized.append(path)
    return tuple(sorted(unrecognized))


def _hub_applies(item: HubChartList, hub: str, tree: dict[str, Any]) -> bool:
    if item.gate_path is None:
        return True
    return feature_charts.gated_path_for_hub(item.gate_path, hub) in tree


def _hub_rows(
    tree: dict[str, Any], hub: str, chart_lists: list[HubChartList]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in chart_lists:
        if not _hub_applies(item, hub, tree):
            continue
        for chart in dict.fromkeys(item.components):
            rows.append(_row(tree, hub, chart, item.name, "hub"))
    prefix = f"apps/{hub}/"
    files = sorted(
        path
        for path in tree
        if path.startswith(prefix) and "/" not in path[len(prefix) :]
    )
    for path in files:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        rows.append(_row(tree, hub, stem, "cluster-apps", "drop-in"))
    return rows


def _undeployed_chart_data(
    tree: dict[str, Any], read: feature_charts.TextReader
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Classify whole-repository charts as deployed, library, or undeployed."""

    charts = sorted(
        {
            parts[-2]
            for path in tree
            if (parts := path.split("/")) and len(parts) >= 3
            and parts[0] == "charts"
            and parts[-1] == "Chart.yaml"
        }
    )
    template_texts: list[tuple[str, str]] = []
    for path in _application_set_files(tree, APPLICATIONSET_PREFIX):
        text, _error = read(path)
        if text is not None:
            template_texts.append((path, text))
    app_texts: list[str] = []
    for path in sorted(
        path for path in tree if path.startswith("apps/")
    ):
        text, _error = read(path)
        if text is not None:
            app_texts.append(text)

    deployed: set[str] = set()
    commented_by_chart: dict[str, set[str]] = {}
    for path, text in template_texts:
        deployed.update(feature_charts.parse_application_set(text).components)
        deployed.update(feature_charts._LITERAL_CHART.findall(text))
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            match = re.search(
                r"component:\s*([a-z0-9-]+)\s*$",
                stripped.lstrip("#").strip(),
            )
            if match:
                name = match.group(1)
                commented_by_chart.setdefault(name, set()).add(path)
    for text in app_texts:
        deployed.update(feature_charts._LITERAL_CHART.findall(text))

    dependencies: set[str] = set()
    for chart in charts:
        text, _error = read(f"charts/{chart}/Chart.yaml")
        if text is None:
            continue
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        for dependency in data.get("dependencies") or ():
            if not isinstance(dependency, dict):
                continue
            name = dependency.get("name")
            repository = dependency.get("repository")
            if (
                isinstance(name, str)
                and name != chart
                and isinstance(repository, str)
                and repository.startswith("file://")
            ):
                dependencies.add(name)
    library = tuple(sorted(dependencies & set(charts)))
    deployed.update(library)

    rows: list[dict[str, Any]] = []
    for chart in charts:
        if chart in deployed:
            continue
        values_files = tuple(
            path
            for path in sorted(tree)
            if len(path.split("/")) in (3, 4)
            and path.split("/")[0] == "values"
            and path.split("/")[-1] == f"{chart}.yaml"
        )
        commented_in = tuple(sorted(commented_by_chart.get(chart, ())))
        rows.append(
            {
                "chart": chart,
                "values_files": list(values_files),
                "commented_out_in": list(commented_in),
            }
        )
    return tuple(rows), library


def _hub_literal_lists(
    tree: dict[str, Any], read: feature_charts.TextReader
) -> list[dict[str, Any]]:
    """Return hub templates that install one literal chart."""

    items: list[dict[str, Any]] = []
    for path in _application_set_files(tree, HUB_TEMPLATES_PREFIX):
        text, _error = read(path)
        if text is None:
            continue
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        parsed = feature_charts.parse_application_set(text, stem)
        if parsed.literal_chart is None:
            continue
        items.append(
            {
                "chart": parsed.literal_chart,
                "application_set": feature_charts.application_set_name(
                    text, stem
                ),
                "gate_path": _files_gate_path(text),
            }
        )
    return items


def _files_gate_path(text: str) -> str | None:
    """Return a git files-generator path that depends on ``$hub``."""

    in_files = False
    files_indent = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("files:"):
            in_files = True
            files_indent = indent
            continue
        if in_files:
            if indent <= files_indent:
                in_files = False
                continue
            if stripped.startswith("- path:"):
                value = stripped.split("path:", 1)[1].strip().strip("'\"")
                if "{{ $hub }}" in value or "{{$hub}}" in value:
                    return value
    return None


def _drop_in_names(tree: dict[str, Any]) -> tuple[str, ...]:
    """Return every Application manifest name dropped under apps/*/."""

    names: set[str] = set()
    for path in tree:
        parts = path.split("/")
        if len(parts) == 3 and parts[0] == "apps" and parts[2]:
            names.add(parts[2].rsplit(".", 1)[0])
    return tuple(sorted(names))


def _application_set_charts(
    application_set: feature_charts.ApplicationSet,
) -> tuple[str, ...]:
    charts = list(application_set.components)
    if application_set.literal_chart:
        charts.append(application_set.literal_chart)
    return tuple(dict.fromkeys(charts))


def _chart_entry(
    tree: dict[str, Any],
    read: feature_charts.TextReader,
    chart: str,
    used_by: tuple[str, ...],
) -> chart_reference.ChartEntry:
    chart_text, _error = read(f"charts/{chart}/Chart.yaml")
    description = ""
    if chart_text is not None:
        try:
            metadata = yaml.safe_load(chart_text)
        except yaml.YAMLError:
            metadata = None
        if isinstance(metadata, dict):
            description = str(metadata.get("description") or "")
    unconditional: set[str] = set()
    conditional: set[str] = set()
    conditions: dict[str, str] = {}
    for template_path in sorted(
        path
        for path in tree
        if path.startswith(f"charts/{chart}/templates/")
    ):
        template_text, _error = read(template_path)
        if template_text is None:
            continue
        (
            template_unconditional,
            template_conditional,
            template_conditions,
        ) = chart_reference.required_value_details(template_text)
        for path, condition in template_conditions.items():
            conditions.setdefault(path, condition)
        unconditional.update(template_unconditional)
        conditional.update(template_conditional)

    values_path = f"charts/{chart}/values.yaml"
    if values_path not in tree:
        values = chart_reference.ValuesReference(present=False)
    else:
        values_text, _error = read(values_path)
        values = (
            chart_reference.ValuesReference(present=False)
            if values_text is None
            else chart_reference.read_values(
                values_text,
                unconditional_required=unconditional,
                conditional_required=conditional,
                conditions=conditions,
            )
        )
    return chart_reference.ChartEntry(
        name=chart,
        description=description,
        used_by=used_by,
        values=values,
    )


def _collect_chart_reference(
    tree: dict[str, Any],
    read: feature_charts.TextReader,
    undeployed_charts: tuple[dict[str, Any], ...],
    library_charts: tuple[str, ...],
    ref: str,
    sha: str,
) -> chart_reference.ChartReference:
    """Read every deployed chart's values and build the reference sections."""

    hubs = hub_directories(tree)
    hub_chart_lists, _hub_errors = _hub_chart_lists(tree, read)
    literal_lists = _hub_literal_lists(tree, read)
    application_sets, _application_set_errors = (
        feature_charts.load_application_sets(tree, read)
    )
    placement_paths = feature_charts.placement_file_paths(tree)

    placements_by_name: dict[str, feature_charts.Placement] = {}
    for hub in hubs:
        placements, _error = feature_charts.load_placements(
            placement_paths.get(hub, {}), read
        )
        for placement in placements:
            placements_by_name.setdefault(placement.name, placement)

    hub_always = tuple(
        sorted(
            {
                chart
                for item in hub_chart_lists
                if item.gate_path is None
                for chart in item.components
            }
        )
    )
    hub_gated = tuple(
        chart_reference.ChartList(
            name=item.name,
            charts=tuple(sorted(set(item.components))),
            detail=feature_charts.gated_path_for_hub(item.gate_path, "<hub>"),
        )
        for item in hub_chart_lists
        if item.gate_path is not None
    )
    drop_ins = _drop_in_names(tree)

    workload_creators: list[chart_reference.ChartList] = []
    for item in sorted(literal_lists, key=lambda value: value["chart"]):
        detail = f"ApplicationSet {item['application_set']}"
        if item["gate_path"]:
            marker = feature_charts.gated_path_for_hub(
                item["gate_path"], "<hub>"
            )
            detail += (
                "; applies on compliant hubs (marker "
                f"{marker})"
            )
        workload_creators.append(
            chart_reference.ChartList(
                name=item["chart"], charts=(item["chart"],), detail=detail
            )
        )

    baseline_charts = tuple(
        sorted(
            {
                chart
                for application_set in application_sets
                if application_set.placement
                == feature_charts.ALL_MANAGED_PLACEMENT
                for chart in _application_set_charts(application_set)
            }
        )
    )

    features: list[chart_reference.ChartList] = []
    for placement_name, placement in placements_by_name.items():
        label_keys = sorted(
            key
            for key in placement.match_labels
            if "/feature-" in key
        )
        if not label_keys:
            continue
        feature_name = label_keys[0].split("/feature-", 1)[1]
        label = ", ".join(
            f'{key}: "{placement.match_labels[key]}"'
            for key in label_keys
        )
        charts = tuple(
            sorted(
                {
                    chart
                    for application_set in application_sets
                    if application_set.placement == placement_name
                    for chart in _application_set_charts(application_set)
                }
            )
        )
        features.append(
            chart_reference.ChartList(
                name=feature_name, charts=charts, detail=label
            )
        )
    features.sort(key=lambda item: item.name)

    used_by: dict[str, list[str]] = {}

    def add_usage(charts: Any, label: str) -> None:
        for chart in charts:
            labels = used_by.setdefault(chart, [])
            if label not in labels:
                labels.append(label)

    add_usage(hub_always, "Hub cluster: Charts every hub receives")
    for item in hub_gated:
        add_usage(
            item.charts,
            "Hub cluster: Charts compliant hubs also receive"
            f" ({item.name})",
        )
    add_usage(drop_ins, "Hub cluster: Per-hub drop-ins")
    add_usage(
        (item.name for item in workload_creators),
        "Workload cluster: Charts that create the cluster",
    )
    add_usage(baseline_charts, "Workload cluster: Baseline")
    for feature in features:
        add_usage(
            feature.charts, f"Workload cluster: Feature: {feature.name}"
        )

    all_charts = sorted(
        {
            parts[-2]
            for path in tree
            if (parts := path.split("/"))
            and len(parts) >= 3
            and parts[0] == "charts"
            and parts[-1] == "Chart.yaml"
        }
    )
    excluded = {row["chart"] for row in undeployed_charts}
    excluded.update(library_charts)
    charts = tuple(
        _chart_entry(
            tree, read, chart, tuple(used_by.get(chart, ()))
        )
        for chart in all_charts
        if chart not in excluded
    )
    return chart_reference.ChartReference(
        ref=ref,
        sha=sha,
        footer=source_line(ref, sha),
        hub_always=hub_always,
        hub_gated=hub_gated,
        hub_drop_ins=drop_ins,
        workload_creators=tuple(workload_creators),
        workload_baseline=baseline_charts,
        workload_features=tuple(features),
        charts=charts,
        undeployed_count=len(undeployed_charts),
        library_count=len(library_charts),
    )


def source_line(ref: str, sha: str) -> str:
    """Render the source sentence shared with the other chart views."""

    return (
        f"Source: {OAC_APPS_REPOSITORY} @ {ref} ({sha[:7]})."
        + FOOTER_SUFFIX
    )


def _row(
    tree: dict[str, Any],
    hub: str,
    chart: str,
    application_set: str,
    feature_label: str,
) -> dict[str, Any]:
    return {
        "chart": chart,
        "application_set": application_set,
        "placement": None,
        "feature_label": feature_label,
        "hub_values_file": f"values/{hub}/{chart}.yaml" in tree,
        "cluster_values_file": (
            f"values/{hub}/local-cluster/{chart}.yaml" in tree
        ),
        "unmet_required_values": [],
        "component": application_set == "hub-components",
    }


def _workload_labels(
    hub: str, workload: str, read: feature_charts.TextReader
) -> tuple[Any, str | None]:
    path = f"hosted-clusters/{hub}/{workload}/values.yaml"
    text, error = read(path)
    if text is None:
        return None, error or f"{path} is unavailable."
    try:
        values = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"{path} could not be parsed: {exc}"
    if not isinstance(values, dict):
        return None, f"{path} is not a YAML mapping."
    return values.get("clusterLabels"), None


def _select_scope(
    tree: dict[str, Any], environment: str | None, workload: str | None
) -> tuple[list[str], dict[str, list[str]]]:
    hubs = hub_directories(tree)
    workloads = workload_directories(tree)
    if environment is not None:
        selected = [
            hub
            for hub in hubs
            if hub == environment or environment_name(hub) == environment
        ]
        if not selected:
            known = ", ".join(environment_name(hub) for hub in hubs)
            raise ChartInventoryError(
                f"unknown environment: {environment}. Known environments: {known}"
            )
        hubs = selected
    if workload is not None:
        if environment is None:
            raise ChartInventoryError("--workload requires an environment")
        base = environment_name(environment)
        candidates = [
            name for hub in hubs for name in workloads.get(hub, [])
        ]
        matches = [
            name
            for name in candidates
            if name == workload
            or name == f"{base}-{workload}"
        ]
        if len(matches) != 1:
            known = ", ".join(candidates) or "(none)"
            raise ChartInventoryError(
                f"unknown workload cluster: {workload}. Known workload clusters: {known}"
            )
        workloads = {
            hub: [name for name in names if name == matches[0]]
            for hub, names in workloads.items()
            if matches[0] in names
        }
        hubs = [hub for hub in hubs if hub in workloads]
    return hubs, workloads


def collect_chart_inventory(
    client: GitHubClient,
    environment: str | None = None,
    workload: str | None = None,
    progress: Any = None,
    include_reference: bool = False,
) -> ChartInventory:
    """Read oac-apps and build the chart rows for the selected clusters."""

    try:
        tree = client.get_tree(OAC_APPS_REPOSITORY)
    except (GitHubError, AssertionError) as exc:
        raise ChartInventoryError(
            f"{OAC_APPS_REPOSITORY} tree could not be read: {exc}"
        ) from exc
    hubs, workloads = _select_scope(tree, environment, workload)
    read = _github_reader(client, progress)

    hub_chart_lists: list[HubChartList] = []
    if hubs:
        hub_chart_lists, _hub_errors = _hub_chart_lists(tree, read)
    unrecognized = _unrecognized_application_sets(tree, read)
    undeployed_charts, library_charts = _undeployed_chart_data(tree, read)

    application_sets: list[feature_charts.ApplicationSet] = []
    application_set_errors: list[str] = []
    if any(workloads.get(hub) for hub in hubs):
        application_sets, application_set_errors = (
            feature_charts.load_application_sets(tree, read)
        )

    placement_paths = feature_charts.placement_file_paths(tree)
    clusters: list[ChartCluster] = []
    for hub in hubs:
        if workload is None:
            clusters.append(
                ChartCluster(
                    name=hub,
                    kind="hub",
                    environment=environment_name(hub),
                    rows=tuple(_hub_rows(tree, hub, hub_chart_lists)),
                )
            )
        placements, placement_error = feature_charts.load_placements(
            placement_paths.get(hub, {}), read
        )
        for name in workloads.get(hub, []):
            error = None
            rows: list[dict[str, Any]] = []
            if application_set_errors:
                error = "Application-set templates could not be read: " + " ".join(
                    application_set_errors
                )
            elif not application_sets:
                error = "No managed ApplicationSet templates exist in the oac-apps tree."
            elif placement_error is not None:
                error = placement_error
            else:
                labels, label_error = _workload_labels(hub, name, read)
                if label_error is not None:
                    error = label_error
                else:
                    rows = feature_charts.workload_chart_rows(
                        tree,
                        hub,
                        name,
                        labels,
                        placements or [],
                        application_sets,
                        read,
                    )
            clusters.append(
                ChartCluster(
                    name=name,
                    kind="workload",
                    environment=environment_name(hub),
                    rows=tuple(rows),
                    error=error,
                )
            )

    try:
        sha = client.resolve_commit(OAC_APPS_REPOSITORY)
    except (GitHubError, AssertionError) as exc:
        raise ChartInventoryError(
            f"{OAC_APPS_REPOSITORY} commit could not be resolved: {exc}"
        ) from exc
    reference = None
    if include_reference:
        reference = _collect_chart_reference(
            tree,
            read,
            undeployed_charts,
            library_charts,
            client.ref_for(OAC_APPS_REPOSITORY),
            sha,
        )
    return ChartInventory(
        ref=client.ref_for(OAC_APPS_REPOSITORY),
        sha=sha,
        clusters=tuple(clusters),
        workload_counts=tuple(
            (hub, len(workloads.get(hub, []))) for hub in hubs
        ),
        compliance_hubs=tuple(
            hub
            for hub in hubs
            if f"hosted-clusters/{hub}/compliance.yaml" in tree
        ),
        unrecognized=unrecognized,
        undeployed_charts=undeployed_charts,
        library_charts=library_charts,
        reference=reference,
    )


_COLUMNS = (
    "Chart",
    "Application set",
    "Placement",
    "Feature label",
    "Hub values",
    "Cluster values",
    "Unmet required values",
)


def _row_values(row: dict[str, Any]) -> list[str]:
    return [
        str(row.get("chart") or "-"),
        str(row.get("application_set") or "-"),
        str(row.get("placement") or "-"),
        str(row.get("feature_label") or "-"),
        "yes" if row.get("hub_values_file") else "no",
        "yes" if row.get("cluster_values_file") else "no",
        ", ".join(row.get("unmet_required_values") or []) or "-",
    ]


def _text_table(rows: list[dict[str, Any]]) -> list[str]:
    rendered = [_row_values(row) for row in rows]
    widths = [
        max([len(_COLUMNS[index]), *(len(row[index]) for row in rendered)])
        for index in range(len(_COLUMNS))
    ]
    lines = [
        "  "
        + "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(_COLUMNS)
        )
    ]
    lines.extend(
        "  "
        + "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rendered
    )
    return [line.rstrip() for line in lines]


def _render_cluster_text(inventory: ChartInventory) -> str:
    lines: list[str] = []
    for cluster in inventory.clusters:
        lines.append(f"{cluster.name} · {cluster.kind}")
        if cluster.error:
            lines.append(f"  Error: {cluster.error}")
        else:
            lines.append("  Received charts:")
            lines.extend(_text_table(list(cluster.rows)))
        lines.append("")
    if inventory.unrecognized:
        lines.append(_unrecognized_line(inventory))
        lines.append("")
    lines.append(footer(inventory.ref, inventory.sha))
    return "\n".join(lines) + "\n"


def _feature_column(row: dict[str, Any]) -> str:
    """Name the feature column for a workload row's placement."""

    placement = str(row.get("placement") or "")
    if placement == feature_charts.ALL_MANAGED_PLACEMENT:
        return "baseline"
    label = str(row.get("feature_label") or "")
    marker = "/feature-"
    if label and label != "baseline" and "," not in label and marker in label:
        return label.split(marker, 1)[1]
    suffix = "-clusters"
    return placement[: -len(suffix)] if placement.endswith(suffix) else placement


def _summary_tables(inventory: ChartInventory) -> list[SummaryTable]:
    workloads = sorted(
        (cluster for cluster in inventory.clusters if cluster.kind == "workload"),
        key=lambda cluster: cluster.name,
    )
    hubs = sorted(
        (cluster for cluster in inventory.clusters if cluster.kind == "hub"),
        key=lambda cluster: cluster.name,
    )
    tables: list[SummaryTable] = []

    membership: dict[str, set[str]] = {}
    charts_by_column: dict[str, set[str]] = {}
    for cluster in workloads:
        columns: set[str] = set()
        for row in cluster.rows:
            column = _feature_column(row)
            columns.add(column)
            charts_by_column.setdefault(column, set()).add(str(row["chart"]))
        membership[cluster.name] = columns
    has_workloads = bool(workloads)
    features = sorted(
        column for column in charts_by_column if column != "baseline"
    )
    columns = ("", *(("baseline",) if has_workloads else ()), *features, "Charts")
    rows = tuple(
        (
            cluster.name,
            *(("x" if column in membership[cluster.name] else "") for column in columns[1:-1]),
            len({str(row["chart"]) for row in cluster.rows}),
        )
        for cluster in workloads
    )
    tables.append(SummaryTable("Workload clusters", columns, rows))

    feature_rows: list[tuple[Any, ...]] = []
    for column in columns[1:-1]:
        feature_rows.append(
            (column, tuple(sorted(charts_by_column.get(column, ()))))
        )
    tables.append(
        SummaryTable(
            "Workload features",
            ("Feature", "Charts it installs"),
            tuple(feature_rows),
        )
    )

    if not hubs:
        return tables

    dropins = sorted(
        {
            str(row["chart"])
            for hub in hubs
            for row in hub.rows
            if row.get("application_set") == "cluster-apps"
        }
    )
    hub_list_columns = sorted(
        {
            str(row["application_set"])
            for hub in hubs
            for row in hub.rows
            if row.get("feature_label") == "hub"
            and row.get("application_set") != "hub-components"
        }
    )
    hub_columns = ("", "hub charts", *hub_list_columns, *dropins, "Charts")
    hub_rows = tuple(
        (
            hub.name,
            *(
                "x"
                if (
                    any(
                        row.get("chart") == column
                        and row.get("application_set") == "cluster-apps"
                        for row in hub.rows
                    )
                    if column in dropins
                    else any(
                        row.get("application_set")
                        == (
                            "hub-components"
                            if column == "hub charts"
                            else column
                        )
                        for row in hub.rows
                    )
                )
                else ""
                for column in hub_columns[1:-1]
            ),
            len({str(row["chart"]) for row in hub.rows}),
        )
        for hub in hubs
    )
    tables.append(SummaryTable("Hubs", hub_columns, hub_rows))

    hub_charts = sorted(
        {
            str(row["chart"])
            for hub in hubs
            for row in hub.rows
            if row.get("application_set") == "hub-components"
        }
    )
    group_rows: list[tuple[Any, ...]] = [("hub charts", tuple(hub_charts))]
    for hub_list in hub_list_columns:
        group_rows.append(
            (
                hub_list,
                tuple(
                    sorted(
                        {
                            str(row["chart"])
                            for hub in hubs
                            for row in hub.rows
                            if row.get("application_set") == hub_list
                        }
                    )
                ),
            )
        )
    for dropin in dropins:
        group_rows.append(
            (
                dropin,
                tuple(
                    sorted(
                        {
                            str(row["chart"])
                            for hub in hubs
                            for row in hub.rows
                            if row.get("application_set") == "cluster-apps"
                            and row.get("chart") == dropin
                        }
                    )
                ),
            )
        )
    tables.append(
        SummaryTable(
            "Hub groups", ("Group", "Charts it installs"), tuple(group_rows)
        )
    )

    workload_counts = dict(inventory.workload_counts)
    compliance = set(inventory.compliance_hubs)
    tables.append(
        SummaryTable(
            "Hub add-ons",
            ("", "Compliance add-on", "Workload clusters"),
            tuple(
                (
                    hub.name,
                    "x" if hub.name in compliance else "",
                    workload_counts.get(hub.name, 0),
                )
                for hub in hubs
            ),
        )
    )
    tables.append(
        SummaryTable(
            "Charts not deployed by GitOps",
            ("Chart", "Values files", "Commented out in"),
            tuple(
                (
                    row["chart"],
                    tuple(row["values_files"]),
                    tuple(row["commented_out_in"]),
                )
                for row in inventory.undeployed_charts
            ),
        )
    )
    return tables


def _summary_cell(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _summary_text_table(table: SummaryTable) -> list[str]:
    headers = [str(column) for column in table.columns]
    rendered = [
        [_summary_cell(value) for value in row] for row in table.rows
    ]
    widths = [
        max([len(headers[index]), *(len(row[index]) for row in rendered)])
        for index in range(len(headers))
    ]
    list_columns = [
        index
        for index in range(len(headers))
        if any(isinstance(row[index], (list, tuple)) for row in table.rows)
    ]
    wrapped = list_columns[-1] if list_columns else None
    if wrapped is not None and wrapped == len(headers) - 1:
        prefix = 2 + sum(widths[index] + 2 for index in range(wrapped))
        widths[wrapped] = min(widths[wrapped], max(20, 110 - prefix))
    lines = [
        "  "
        + "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(headers)
        )
    ]

    def value_cell(value: str, index: int) -> str:
        if value == "x":
            return value.center(widths[index])
        return value.ljust(widths[index])

    for row in rendered:
        if wrapped is None:
            lines.append(
                "  "
                + "  ".join(
                    value_cell(value, index)
                    for index, value in enumerate(row)
                )
            )
            continue
        prefix = "  " + "  ".join(
            value_cell(row[index], index) for index in range(wrapped)
        )
        if wrapped:
            prefix += "  "
        chunks = textwrap.wrap(
            row[wrapped],
            width=widths[wrapped],
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        lines.append(prefix + chunks[0])
        continuation = " " * (2 + sum(widths[index] + 2 for index in range(wrapped)))
        lines.extend(continuation + chunk for chunk in chunks[1:])
    return [line.rstrip() for line in lines]


def _inventory_notes(inventory: ChartInventory) -> list[str]:
    return [
        UNDEPLOYED_NOTE,
        "Library charts (dependencies only): "
        + ", ".join(inventory.library_charts),
    ]


def _unrecognized_line(inventory: ChartInventory) -> str:
    return (
        "Unrecognized ApplicationSets (charts may be missing): "
        + ", ".join(inventory.unrecognized)
    )


def _render_summary_text(inventory: ChartInventory) -> str:
    lines: list[str] = []
    for table in _summary_tables(inventory):
        lines.append(table.name)
        lines.extend(_summary_text_table(table))
        lines.append("")
    lines.extend(_inventory_notes(inventory))
    lines.append("")
    errors = [cluster for cluster in inventory.clusters if cluster.error]
    if errors:
        lines.append("Errors")
        lines.extend(
            f"  {cluster.name}: {cluster.error}" for cluster in errors
        )
        lines.append("")
    if inventory.unrecognized:
        lines.append(_unrecognized_line(inventory))
        lines.append("")
    lines.append(footer(inventory.ref, inventory.sha))
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _markdown_table(
    headers: list[str],
    rows: list[list[str]],
    center_columns: set[int] | None = None,
) -> list[str]:
    centered = center_columns or set()
    lines = [
        "| " + " | ".join(_markdown_cell(header) for header in headers) + " |",
        "|"
        + "|".join(
            ":---:" if index in centered else "---"
            for index in range(len(headers))
        )
        + "|",
    ]
    lines.extend(
        "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    return lines


def _render_cluster_markdown(inventory: ChartInventory) -> str:
    lines: list[str] = []
    for cluster in inventory.clusters:
        lines.append(f"### {cluster.name} ({cluster.kind})")
        lines.append("")
        if cluster.error:
            lines.append(f"Error: {cluster.error}")
        else:
            lines.extend(
                _markdown_table(
                    list(_COLUMNS),
                    [_row_values(row) for row in cluster.rows],
                )
            )
        lines.append("")
    if inventory.unrecognized:
        lines.append(_unrecognized_line(inventory))
        lines.append("")
    lines.append(footer(inventory.ref, inventory.sha))
    return "\n".join(lines) + "\n"


def _render_summary_markdown(inventory: ChartInventory) -> str:
    lines: list[str] = []
    for table in _summary_tables(inventory):
        lines.append(f"## {table.name}")
        lines.append("")
        lines.extend(
            _markdown_table(
                [str(column) for column in table.columns],
                [
                    [_summary_cell(value) for value in row]
                    for row in table.rows
                ],
                {
                    index
                    for index in range(len(table.columns))
                    if any(row[index] == "x" for row in table.rows)
                },
            )
        )
        lines.append("")
    lines.extend(_inventory_notes(inventory))
    lines.append("")
    errors = [cluster for cluster in inventory.clusters if cluster.error]
    if errors:
        lines.append("## Errors")
        lines.append("")
        lines.extend(
            f"- {cluster.name}: {cluster.error}" for cluster in errors
        )
        lines.append("")
    if inventory.unrecognized:
        lines.append(_unrecognized_line(inventory))
        lines.append("")
    lines.append(footer(inventory.ref, inventory.sha))
    return "\n".join(lines) + "\n"


def _render_summary_json(inventory: ChartInventory) -> str:
    keys = {
        "Workload clusters": "workload_clusters",
        "Workload features": "workload_features",
        "Hubs": "hubs",
        "Hub groups": "hub_groups",
        "Hub add-ons": "hub_addons",
        "Charts not deployed by GitOps": "charts_not_deployed",
    }
    tables: dict[str, Any] = {}
    for table in _summary_tables(inventory):
        tables[keys[table.name]] = {
            "name": table.name,
            "columns": list(table.columns),
            "rows": [list(row) for row in table.rows],
        }
    document = {
        "repository": OAC_APPS_REPOSITORY,
        "ref": inventory.ref,
        "sha": inventory.sha,
        "short_sha": inventory.sha[:7],
        "view": "summary",
        "tables": tables,
        "undeployed_charts": [dict(row) for row in inventory.undeployed_charts],
        "library_charts": list(inventory.library_charts),
        "unrecognized": list(inventory.unrecognized),
        "errors": [
            {"cluster": cluster.name, "error": cluster.error}
            for cluster in inventory.clusters
            if cluster.error
        ],
        "footer": footer(inventory.ref, inventory.sha),
    }
    return json.dumps(document, indent=2) + "\n"


def render_chart_inventory(
    inventory: ChartInventory,
    *,
    view: str = "summary",
    format: str = "text",
    charts: Sequence[str] = (),
    command: Sequence[str] = (),
) -> str:
    """Render a chart inventory in the requested view and format."""

    if view == "summary":
        if format == "json":
            return _render_summary_json(inventory)
        if format == "markdown":
            return _render_summary_markdown(inventory)
        return _render_summary_text(inventory)
    if view == "reference":
        if inventory.reference is None:
            raise ChartInventoryError(
                "the chart reference was not collected for this inventory"
            )
        return chart_reference.render_chart_reference(
            inventory.reference,
            format=format,
            selected=charts,
            command=command,
        )
    if format == "json":
        clusters: dict[str, Any] = {}
        for cluster in inventory.clusters:
            entry: dict[str, Any] = {
                "type": cluster.kind,
                "environment": cluster.environment,
                "charts": [dict(row) for row in cluster.rows],
            }
            if cluster.error:
                entry["error"] = cluster.error
            clusters[cluster.name] = entry
        document = {
            "repository": OAC_APPS_REPOSITORY,
            "ref": inventory.ref,
            "sha": inventory.sha,
            "short_sha": inventory.sha[:7],
            "view": view,
            "clusters": clusters,
            "undeployed_charts": [dict(row) for row in inventory.undeployed_charts],
            "library_charts": list(inventory.library_charts),
            "unrecognized": list(inventory.unrecognized),
            "footer": footer(inventory.ref, inventory.sha),
        }
        return json.dumps(document, indent=2) + "\n"
    if format == "markdown":
        return _render_cluster_markdown(inventory)
    return _render_cluster_text(inventory)
