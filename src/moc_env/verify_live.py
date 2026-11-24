"""Offline declared-versus-snapshot comparisons. This module never invokes oc."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic
from typing import Any

import yaml

from . import feature_charts
from .charts import ChartInventoryError, collect_chart_inventory
from .github import GitHubClient
from .observed import find_cluster_group, flatten_host
from .report import _markdown_table, render_json

APPS = "CCI-MOC/oac-apps"
INFRA = "CCI-MOC/oac-infra"
TRACKING = "argocd.argoproj.io/tracking-id"
VERDICTS = ("match", "drift", "expected-absent", "unverifiable")


class LocalRepositories(GitHubClient):
    """An explicitly selected, filesystem-only source using the chart reader API."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def get_tree(self, repository: str, ref: str = "main") -> dict[str, Any]:
        base = self.root / repository.split("/")[-1]
        if not base.is_dir():
            raise ValueError(f"repository directory is missing: {base}")
        return {str(path.relative_to(base)): {} for path in base.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(base).parts}

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        base = self.root / repository.split("/")[-1]
        target = (base / path).resolve()
        if not target.is_relative_to(base):
            raise ValueError("repository path escapes its root")
        return target.read_text(encoding="utf-8")

    def resolve_commit(self, repository: str, ref: str = "main") -> str:
        source = self.root / repository.split("/")[-1] / ".moc-env-source.json"
        return str(json.loads(source.read_text())["sha"]) if source.exists() else "local-unversioned"

    def ref_for(self, repository: str, ref: str = "main") -> str:
        return "local"


class Snapshot:
    """Read only manifest-listed files; denied/missing/malformed never means empty."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.manifest = json.loads((directory / "manifest.json").read_text())
        if not isinstance(self.manifest, dict):
            raise ValueError("snapshot manifest must be a JSON object")
        if self.manifest.get("schema_version") != 1:
            raise ValueError("unsupported snapshot schema_version")
        self.resources = self.manifest.get("resources", {})
        if not isinstance(self.resources, dict) or not all(
            isinstance(key, str) and isinstance(entry, dict)
            for key, entry in self.resources.items()
        ):
            raise ValueError("snapshot resources must be a mapping of resource descriptions")
        self.cache: dict[str, tuple[list[dict[str, Any]] | None, str]] = {}

    def read(self, key: str) -> tuple[list[dict[str, Any]] | None, str]:
        if key in self.cache:
            return self.cache[key]
        entry = self.resources.get(key, {})
        if key in self.manifest.get("forbidden", []):
            return None, f"{key}: Forbidden"
        status = entry.get("status", "not captured")
        if status == "not-served":
            return [], ""  # API discovery confirmed absence, not a denied read.
        if status != "captured":
            return None, f"{key}: {status}"
        path = (self.directory / entry.get("file", f"{key}.json")).resolve()
        if not path.is_relative_to(self.directory):
            raise ValueError("snapshot file escapes its directory")
        try:
            data = json.loads(path.read_text())
            items = data["items"]
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items) or data.get("metadata", {}).get("continue"):
                raise ValueError("not a complete resource list")
            result: tuple[list[dict[str, Any]] | None, str] = items, ""
        except (OSError, ValueError, KeyError, TypeError):
            result = None, f"{key}: missing or invalid snapshot file"
        self.cache[key] = result
        return result

    def kind_keys(self, kind: str) -> list[str]:
        return [key for key, entry in self.resources.items() if entry.get("kind") == kind]

    def tracked(self, application: str) -> list[str]:
        found = []
        for key in sorted(self.resources):
            objects, _ = self.read(key)
            for obj in objects or []:
                metadata = obj.get("metadata") or {}
                value = (metadata.get("annotations") or {}).get(TRACKING, "")
                if not isinstance(value, str):
                    continue
                # Argo's annotation is app:group/Kind:namespace/name. Require
                # self-reference so copied annotations on controller children
                # cannot masquerade as Argo-applied resources.
                match = re.fullmatch(r"([^:]+):([^/]*)/([^:]+):([^/]*)/(.+)", value)
                if not match or match[1] != application:
                    continue
                group = obj.get("apiVersion", "").partition("/")[0] if "/" in obj.get("apiVersion", "") else ""
                if (match[2], match[3], match[4], match[5]) != (
                    group, obj.get("kind"), metadata.get("namespace") or "", metadata.get("name")):
                    continue
                found.append(f"{obj['kind']}:{metadata.get('namespace') or ''}/{metadata['name']}")
        return sorted(set(found))


def _row(name: str, verdict: str, declared: Any, live: Any, detail: str = "") -> dict[str, Any]:
    assert verdict in VERDICTS
    return {"name": name, "verdict": verdict, "declared": declared, "live": live, "detail": detail}


def _quantity(value: Any) -> Decimal | str:
    text = str(value)
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))([a-zA-Z]*|[eE][+-]?\d+)", text)
    if not match:
        try:
            return Decimal(text)
        except InvalidOperation:
            return text
    suffixes = {"n": Decimal("1e-9"), "u": Decimal("1e-6"), "m": Decimal("1e-3"),
                **{s: Decimal(1000) ** i for i, s in enumerate(("", "k", "M", "G", "T", "P", "E"))},
                **{s: Decimal(1024) ** i for i, s in enumerate(("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei"))}}
    suffix = match[2]
    try:
        return Decimal(match[1]) * (Decimal("1" + suffix) if suffix.startswith(("e", "E")) and len(suffix) > 1 else suffixes[suffix])
    except (KeyError, InvalidOperation):
        return text


def _values(client: GitHubClient, tree: dict[str, Any], paths: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    merged: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for path in paths:
        if path not in tree:
            continue
        text = client.get_file(APPS, path)
        data = yaml.safe_load(text)
        node = yaml.compose(text)
        if not isinstance(data, dict) or not isinstance(node, yaml.MappingNode):
            raise ValueError(f"{path}: expected a YAML values mapping")
        # Walk the YAML node tree for exact final-layer line provenance.
        def walk(mapping: yaml.Node, prefix: str = "") -> None:
            if isinstance(mapping, yaml.MappingNode):
                for key, value in mapping.value:
                    dotted = f"{prefix}.{key.value}".lstrip(".")
                    provenance[dotted] = f"{path}:{key.start_mark.line + 1}"
                    walk(value, dotted)
        walk(node)
        merged = feature_charts.deep_merge(merged, data)
    return merged, provenance


def _template_kinds(texts: list[str]) -> tuple[set[tuple[str | None, str]], bool]:
    """Extract literal group/kind pairs without rendering or running Helm."""
    kinds: set[tuple[str | None, str]] = set()
    unresolved = False
    for text in texts:
        group: str | None = None
        for line in text.splitlines():
            api = re.match(r"^apiVersion:\s*[\"']?([^\"'\s]+)", line)
            if api:
                version = api[1]
                group = None if "{{" in version else version.partition("/")[0] if "/" in version else ""
            kind = re.match(r"^kind:\s*[\"']?([A-Za-z][A-Za-z0-9]+)[\"']?\s*$", line)
            if kind:
                kinds.add((group, kind[1]))
            elif re.match(r"^kind:", line):
                unresolved = True
    return kinds, unresolved or not kinds


def _chart_visibility(snapshot: Snapshot, texts: list[str]) -> str:
    """Only complete readable template-kind coverage can establish absence."""
    kinds, unresolved = _template_kinds(texts)
    problems = []
    for group, kind in sorted(kinds, key=str):
        keys = [key for key in snapshot.kind_keys(kind)
                if group is None or snapshot.resources[key].get("group", key.partition(".")[2]) == group]
        if not keys:
            problems.append(f"{kind}: not captured")
        for key in keys:
            _, error = snapshot.read(key)
            if error:
                problems.append(error)
    if unresolved:
        problems.append("template resource kinds could not be resolved")
    return "; ".join(problems)


def _templates(client: GitHubClient, tree: dict[str, Any], chart: str,
            seen: frozenset[str] = frozenset()) -> list[str]:
    """Include local library dependencies, not just the parent's include calls."""
    if chart in seen:
        return []
    texts = [client.get_file(APPS, path) for path in sorted(tree)
            if path.startswith(f"charts/{chart}/templates/")]
    chart_path = f"charts/{chart}/Chart.yaml"
    metadata = yaml.safe_load(client.get_file(APPS, chart_path)) if chart_path in tree else {}
    for dependency in (metadata or {}).get("dependencies", []):
        repository = dependency.get("repository", "")
        if repository.startswith("file://../"):
            name = repository.removeprefix("file://../")
            dependency_texts = _templates(client, tree, name, seen | {chart})
            if not dependency_texts:
                texts.append("kind: {{ unread_dependency }}")
            texts.extend(dependency_texts)
        else:
            texts.append("kind: {{ unread_dependency }}")
    return texts


def verify_live(client: GitHubClient, environment: str, workload: str, directory: Path,
                *, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Compare snapshot evidence, optionally emitting report-independent events."""
    def emit(event: str, **details: Any) -> None:
        if progress is not None:
            progress({"event": event, **details})

    def chart_progress(stage: str, action: str, repository: str, path: str) -> None:
        emit("chart", stage=stage, action=action, repository=repository, path=path)

    emit("manifest", message="Reading snapshot manifest")
    snapshot = Snapshot(directory)
    if snapshot.manifest.get("workload") != workload:
        raise ValueError(f"snapshot workload {snapshot.manifest.get('workload')} does not match requested workload {workload}")
    emit("inventory", message="Reading chart declarations")
    inventory = collect_chart_inventory(client, environment, workload,
                                        progress=chart_progress if progress is not None else None)
    cluster = inventory.clusters[0]
    if cluster.error:
        raise ChartInventoryError(cluster.error)
    tree = client.get_tree(APPS)
    def reader(path: str) -> tuple[str | None, str | None]:
        return client.get_file(APPS, path), None
    appsets, errors = feature_charts.load_application_sets(tree, reader)
    if errors:
        raise ValueError("; ".join(errors))
    by_appset = {item.name: item for item in appsets}
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in ("Charts", "Nodes", "Quotas", "OpenShift AI", "Health")}
    resolved: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}
    for position, declared in enumerate(sorted(cluster.rows, key=lambda item: item["chart"]), 1):
        chart = declared["chart"]
        started = monotonic()
        details = {"chart": chart, "position": position, "total": len(cluster.rows)}
        emit("chart_start", **details)
        appset = by_appset[declared["application_set"]]
        paths = [f"charts/{chart}/values.yaml"]
        for entry in appset.value_files:
            path = feature_charts.resolve_value_file(entry, f"{environment}-infra", workload, chart)
            if path is None:
                raise ValueError(f"unresolved values file for {chart}: {entry}")
            paths.append(path)
        values, sources = _values(client, tree, paths)
        resolved[chart] = values, sources
        live = snapshot.tracked(f"{workload}-{chart}")
        templates = _templates(client, tree, chart)
        visibility = _chart_visibility(snapshot, templates)
        enabled = values.get("enabled", True) is not False
        if enabled and live:
            verdict = "match"
        elif not enabled and live:
            verdict = "drift"
        elif visibility:
            verdict = "unverifiable"
        else:
            verdict = "drift" if enabled else "expected-absent"
        detail = visibility
        if verdict == "match":
            detail = ""
        elif verdict == "drift":
            detail = "tracking: declared absent, live tracked objects found" if not enabled else "live: missing"
        elif not enabled:
            detail = "; ".join(filter(None, (detail, f"{sources.get('enabled', 'unknown source')} enabled: false")))
        sections["Charts"].append(_row(chart, verdict, "enabled" if enabled else "disabled", len(live), detail))
        emit("chart_end", **details, verdict=verdict, elapsed=monotonic() - started)

    emit("section", section="Nodes")
    hosts_text = client.get_file(INFRA, "infra/inventory/00hosts.yaml")
    group = find_cluster_group(yaml.safe_load(hosts_text), workload)
    if group is None:
        raise ValueError(f"no inventory cluster group for {workload}")
    hosts = flatten_host(group)
    nodes, node_error = snapshot.read("nodes")
    declared_nodes = {host["node_name"].casefold(): host for host in hosts if host.get("node_name")}
    live_nodes = {obj["metadata"]["name"].casefold(): obj["metadata"]["name"] for obj in nodes or []}
    missing = sorted(set(declared_nodes) - set(live_nodes))
    extra = sorted(set(live_nodes) - set(declared_nodes))
    missing_names = [host for host in hosts if not host.get("node_name")]
    node_verdict = "unverifiable" if node_error or missing_names else "drift" if missing or extra else "match"
    sections["Nodes"].append(_row("inventory total", node_verdict, len(hosts), None if node_error else len(live_nodes), node_error))
    for key, host in sorted(declared_nodes.items()):
        sections["Nodes"].append(_row(f"{host['node_name']} ({host['name']})",
            "unverifiable" if node_error else "match" if key in live_nodes else "drift",
            "present", None if node_error else live_nodes.get(key, "missing"), node_error))
    for key in extra:
        sections["Nodes"].append(_row(live_nodes[key], "drift", "not in inventory", "present"))
    for host in missing_names:
        sections["Nodes"].append(_row(host["name"], "unverifiable", None, None, "inventory node_name missing"))

    emit("section", section="Quotas")
    quotas, quota_error = snapshot.read("resourcequotas")
    values, _ = resolved.get("user-projects", ({}, {}))
    for project in values.get("projects", []):
        name = project["name"]
        expected = feature_charts.deep_merge(values.get("defaultQuota", {}), project.get("quota") or {}).get("hard", {})
        found = [obj for obj in quotas or [] if obj.get("metadata", {}).get("namespace") == f"project-{name}"
                and obj.get("metadata", {}).get("name") == f"project-{name}-quota"]
        actual = found[0].get("spec", {}).get("hard", {}) if len(found) == 1 else {}
        differences = [f"{key}: declared {expected.get(key, 'absent')}, live {actual.get(key, 'absent')}"
                    for key in sorted(set(expected) | set(actual))
                    if key not in expected or key not in actual or _quantity(expected[key]) != _quantity(actual[key])]
        verdict = "unverifiable" if quota_error else "match" if len(found) == 1 and not differences else "drift"
        sections["Quotas"].append(_row(name, verdict, expected, None if quota_error else actual,
            quota_error or "; ".join(differences) or ("" if found else "ResourceQuota missing")))

    emit("section", section="OpenShift AI")
    rhoai, sources = resolved.get("rhoai", ({}, {}))
    if rhoai:
        dscs, dsc_error = snapshot.read("datascienceclusters.datasciencecluster.opendatahub.io")
        dsc_values = rhoai.get("dataScienceCluster", {})
        components = dsc_values.get(f"v{rhoai.get('rhoaiVersion', 2)}", dsc_values).get("components", {})
        found = [obj for obj in dscs or [] if obj.get("metadata", {}).get("name") == dsc_values.get("name", "default-dsc")]
        actual_components = found[0].get("spec", {}).get("components", {}) if len(found) == 1 else {}
        for name in sorted(set(components) | set(actual_components)):
            wanted = components.get(name)
            actual = actual_components.get(name, {}).get("managementState")
            if name not in components and actual is None:
                continue
            disabled = rhoai.get("enabled") is False or wanted == "Removed"
            verdict = "unverifiable" if dsc_error else (
                "expected-absent" if actual is None and disabled else
                "match" if actual == wanted and rhoai.get("enabled") is not False else "drift")
            detail = dsc_error
            if verdict == "expected-absent":
                key = "enabled" if rhoai.get("enabled") is False else f"dataScienceCluster.v{rhoai.get('rhoaiVersion', 2)}.components.{name}"
                detail = f"{sources.get(key, 'unknown source')} {key}: {rhoai.get('enabled') if key == 'enabled' else wanted}"
            sections["OpenShift AI"].append(_row(f"component/{name}", verdict, wanted, actual, detail))
        profiles, profile_error = snapshot.read("hardwareprofiles.infrastructure.opendatahub.io")
        actual_profiles = {obj["metadata"]["name"]: obj for obj in profiles or []
                        if obj.get("metadata", {}).get("namespace") == rhoai.get("applicationsNamespace", "redhat-ods-applications")}
        expected_profiles = {item["name"]: item for item in rhoai.get("hardwareProfiles", [])}
        enabled_profiles = set(rhoai.get("enabledHardwareProfiles", [])) if rhoai.get("enabled") is not False else set()
        for name in sorted(set(expected_profiles) | set(actual_profiles) | enabled_profiles):
            expected_profile = expected_profiles.get(name, {})
            obj = actual_profiles.get(name)
            wanted_profile = {key: expected_profile[key] for key in ("identifiers", "scheduling") if key in expected_profile}
            actual_profile = obj.get("spec", {}) if obj else None
            disabled = name not in enabled_profiles
            if profile_error:
                verdict = "unverifiable"
            elif disabled:
                verdict = "drift" if obj else "expected-absent"
            else:
                annotations = obj.get("metadata", {}).get("annotations", {}) if obj else {}
                verdict = "match" if obj and actual_profile is not None and all(actual_profile.get(key) == value for key, value in wanted_profile.items()) and annotations.get("opendatahub.io/disabled") == "false" else "drift"
            detail = profile_error
            if verdict == "drift" and disabled:
                detail = "presence: declared absent, live present"
            if verdict == "expected-absent":
                key = "enabled" if rhoai.get("enabled") is False else "enabledHardwareProfiles"
                detail = f"{sources.get(key, 'unknown source')} {name} not enabled"
            if verdict == "drift" and obj and not disabled:
                detail = _field_differences(wanted_profile, actual_profile)
                annotation = (obj.get("metadata", {}).get("annotations") or {}).get("opendatahub.io/disabled")
                if annotation != "false":
                    detail = "; ".join(filter(None, (detail, f"opendatahub.io/disabled: declared false, live {annotation}")))
            sections["OpenShift AI"].append(_row(f"hardwareprofile/{name}", verdict,
                "disabled" if disabled else wanted_profile, actual_profile, detail))

    emit("section", section="Health")
    pods, pod_error = snapshot.read("pods")
    reported_pods: dict[str, list[dict[str, Any]]] = {}
    for pod in pods or []:
        status = pod.get("status", {})
        if status.get("phase") == "Succeeded":
            continue
        ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in status.get("conditions", []))
        restarts = sum(item.get("restartCount", 0) for field in (
            "containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses") for item in status.get(field, []))
        if not ready or restarts > 50:
            node = pod.get("spec", {}).get("nodeName") or "unscheduled"
            metadata = pod["metadata"]
            reported_pods.setdefault(node, []).append({
                "namespace": metadata.get("namespace", ""), "name": metadata["name"],
                "ready": ready, "restarts": restarts,
                "phase": status.get("phase"),
                **({"init": _ready_total(status["initContainerStatuses"])}
                    if status.get("initContainerStatuses") else {}),
                "containers": _ready_total(status["containerStatuses"]) if "containerStatuses" in status else None,
                "reason": next((state["reason"]
                    for field in ("initContainerStatuses", "containerStatuses", "ephemeralContainerStatuses")
                    for container in status.get(field, [])
                    for key in ("waiting", "terminated")
                    if (state := (container.get("state") or {}).get(key) or {}).get("reason")), None),
                "age_seconds": _age_seconds(snapshot.manifest.get("timestamp"), metadata.get("creationTimestamp")),
            })
    if pod_error:
        sections["Health"].append({**_row("pods", "unverifiable", "Ready", None, pod_error), "pods": []})
    else:
        for node in sorted(set(live_nodes.values()) | set(reported_pods)):
            node_pods = sorted(reported_pods.get(node, []), key=lambda pod: (
                pod["ready"], -pod["restarts"], pod["namespace"], pod["name"]))
            not_ready = sum(not pod["ready"] for pod in node_pods)
            ready_restarting = len(node_pods) - not_ready
            detail = ""
            if not_ready:
                detail = f"{not_ready} pod{'s' if not_ready != 1 else ''} not Ready"
            elif ready_restarting:
                detail = f"note: {ready_restarting} Ready pod{'s' if ready_restarting != 1 else ''} over 50 restarts"
            live = [f"{pod['namespace']}/{pod['name']} Ready={str(pod['ready']).lower()} restarts={pod['restarts']}"
                for pod in node_pods]
            sections["Health"].append({**_row(node, "drift" if not_ready else "match",
                "Ready", live or "healthy", detail), "pods": node_pods})
        if not nodes and not reported_pods:
            sections["Health"].append({**_row("pods", "match", "Ready", f"{len(pods or [])} pods checked"), "pods": []})
    return {"environment": environment, "workload": workload, "snapshot": snapshot.manifest,
            "sources": {APPS: inventory.sha, INFRA: client.resolve_commit(INFRA)},
            "sections": sections,
            "summary": {verdict: sum(row["verdict"] == verdict for rows in sections.values() for row in rows) for verdict in VERDICTS}}


def _ready_total(containers: list[dict[str, Any]]) -> str | None:
    if any(not isinstance(container.get("ready"), bool) for container in containers):
        return None
    return f"{sum(container['ready'] for container in containers)}/{len(containers)}"


def _age_seconds(timestamp: str | None, created: str | None) -> int | None:
    if not timestamp or not created:
        return None
    try:
        return int((datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds())
    except (ValueError, TypeError):
        return None


def _pod_health_text(pod: dict[str, Any]) -> str:
    parts = ["Ready" if pod["ready"] else "not Ready"]
    if pod.get("phase"):
        parts.append(pod["phase"])
    for field in ("init", "containers"):
        if pod.get(field) is not None:
            parts.append(f"{field} {pod[field]}")
    if pod.get("reason"):
        parts.append(pod["reason"])
    age = pod.get("age_seconds")
    if age is not None:
        minutes = age // 60
        hours = minutes // 60
        parts.append(f"{hours // 24}d{hours % 24}h" if hours >= 24 else
            f"{hours}h{minutes % 60}m" if hours >= 1 else f"{minutes}m")
    if pod.get("restarts") is not None:
        parts.append(f"{pod['restarts']} restarts")
    return " · ".join(parts)


def _display(value: Any) -> str:
    if value is None:
        return "not observed"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _field_differences(declared: Any, live: Any, prefix: str = "") -> str:
    if isinstance(declared, dict) and isinstance(live, dict):
        return "; ".join(filter(None, (_field_differences(declared.get(key), live.get(key),
            f"{prefix}.{key}".lstrip(".")) for key in sorted(set(declared) | set(live)))))
    if isinstance(declared, list) and isinstance(live, list):
        return "; ".join(filter(None, (_field_differences(
            declared[index] if index < len(declared) else None,
            live[index] if index < len(live) else None, f"{prefix}[{index}]")
            for index in range(max(len(declared), len(live))))))
    return "" if declared == live else f"{prefix or 'value'}: declared {_display(declared)}, live {_display(live)}"


def _row_evidence(row: dict[str, Any], section: str) -> str:
    if row["verdict"] == "match":
        return ""
    if row["verdict"] != "drift":
        return row["detail"]
    if row["live"] in (None, "missing") or row["live"] == {}:
        return "live: missing"
    if row["detail"]:
        return row["detail"]
    field = "count" if row["name"] == "inventory total" else "managementState" if section == "OpenShift AI" else "value"
    return _field_differences(row["declared"], row["live"], field)


def render_live_report(report: dict[str, Any], format: str = "text") -> str:
    """Use shared JSON and Markdown table machinery and CLI output conventions."""
    if format == "json":
        return render_json(report)
    title = f"{report['workload']} · live verification · snapshot {report['snapshot']['timestamp']}"
    lines = [("# " if format == "markdown" else "") + title, "",
            "RESULT: " + " · ".join(f"{count} {verdict}" for verdict, count in report["summary"].items())]
    if report["snapshot"].get("identity_verified") is not True:
        reason = " ".join(str(report["snapshot"].get("identity_reason", "not recorded in manifest")).split())
        lines.append(f"Snapshot's cluster identity was not verified: {reason}.")
    lines.append("")
    for section, rows in report["sections"].items():
        lines.extend([("## " if format == "markdown" else "") + section, ""])
        rendered_rows = []
        for row in rows:
            evidence = row["detail"] if section == "Health" else _row_evidence(row, section)
            pod_lines = []
            if section == "Health":
                pod_names = [f"{pod['namespace']}/{pod['name']}" for pod in row.get("pods", [])]
                width = max(map(len, pod_names), default=0)
                pod_lines = [f"{name:<{width}}  {_pod_health_text(pod)}"
                    for name, pod in zip(pod_names, row.get("pods", []))]
            rendered_rows.append((row, evidence, pod_lines))
        if format == "markdown":
            lines.extend(_markdown_table(["Name", "Verdict", "Evidence"],
                [[row["name"], row["verdict"], list(filter(None, [evidence, *pod_lines]))]
                    for row, evidence, pod_lines in rendered_rows]))
        else:
            for row, evidence, pod_lines in rendered_rows:
                lines.append(f"  {row['verdict']:<15} {row['name']}" + (f" | {evidence}" if evidence else ""))
                lines.extend(f"{'':20}{pod_line}" for pod_line in pod_lines)
            if not rows:
                lines.append("  No declared rows.")
            lines.append("")
    lines.extend(["Sources: " + "  ".join(f"{repo}@{sha}" for repo, sha in report["sources"].items()),
                "Snapshot evidence only; chart matches indicate tracked-object presence, not full manifest equality."])
    return "\n".join(lines) + "\n"
