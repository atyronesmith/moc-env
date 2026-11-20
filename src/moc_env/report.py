"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from .github import github_url
from .report_fields import field_rows, failing_field_rows, plain


STATE_SYMBOLS = {
    "requested": "📝",
    "declared_in_main": "✅",
    "pr_merged": "🔀",
    "pr_open": "🚧",
    "partial": "🟡",
    "missing": "❌",
    "unknown": "⚪",
    "value_mismatch": "⚠️",
}

ASCII_STATE_SYMBOLS = {
    "requested": "[req]",
    "declared_in_main": "[ok]",
    "pr_merged": "[merged]",
    "pr_open": "[pr]",
    "partial": "[warn]",
    "missing": "[fail]",
    "unknown": "[??]",
    "value_mismatch": "[warn]",
}


class MarkdownCell(str):
    """A pre-rendered Markdown table cell that must not be escaped again."""


def _value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _markdown_inline(value: Any) -> str:
    """Render a compact, human-readable Markdown table cell."""

    if value is None:
        return "—"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str) and value in {"Present", "Missing"}:
        return f"**{value}**"
    if isinstance(value, dict):
        if "value" in value:
            return _markdown_inline(value["value"])
        return ", ".join(
            f"{_markdown_inline(key)}: {_markdown_inline(item)}"
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return "—"
        return "<br>".join(_markdown_inline(item) for item in value)
    if isinstance(value, str):
        if isinstance(value, MarkdownCell):
            return str(value)
        if value.startswith("https://github.com/"):
            return f"[{value}]({value})"
        return f"`{_markdown_escape_cell(value)}`" if value else "—"
    return f"`{value}`"


def _github_location(
    repository: str | None, path: str | None, ref: str | None = None
) -> str | None:
    if not repository or not path:
        return None
    return github_url(repository, path, ref or "main")


def _linked_code(value: Any, url: str | None) -> str:
    rendered = _markdown_inline(value)
    return MarkdownCell(f"[{rendered}]({url})") if url else rendered


def _markdown_table(
    headers: list[str],
    rows: list[list[Any]],
    plain_first_column: bool = False,
) -> list[str]:
    if not rows:
        return []
    lines = [
        "| " + " | ".join(_markdown_escape_cell(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        cells = [
            _markdown_escape_cell(str(value))
            if plain_first_column and index == 0
            else _markdown_inline(value)
            for index, value in enumerate(row)
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _markdown_escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _host_table(check: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    hosts = evidence.get("hosts")
    if not isinstance(hosts, list) or not all(isinstance(host, dict) for host in hosts):
        return []
    rows = [
        [
            host.get("name"),
            host.get("node_name"),
            host.get("bmc_addr"),
            host.get("boot_image_url"),
        ]
        for host in hosts
    ]
    return [
        "**Observed hosts**",
        "",
        *_markdown_table(["Host", "Node name", "BMC address", "Boot image URL"], rows),
    ]


def _path_table(check: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    expected_paths = evidence.get("expected_paths")
    found_paths = evidence.get("paths")
    if not isinstance(expected_paths, list) or not expected_paths:
        return []
    found = set(found_paths or [])
    rows = [
        [
            _linked_code(path, _path_url(check, path)),
            "present" if path in found else "missing",
        ]
        for path in expected_paths
    ]
    return [
        "**Expected paths**",
        "",
        *_markdown_table(["Path", "Status"], rows),
    ]


def _path_url(check: dict[str, Any], path: str, report: dict[str, Any] | None = None) -> str | None:
    evidence = check.get("evidence") or {}
    if path in set(evidence.get("paths") or []):
        return _github_location(check.get("repository"), path, check.get("ref"))
    if report is not None:
        return _nearest_existing_parent_url(report, check, path)
    synthetic = {**check, "path": path, "state": "missing"}
    return _detail_url(synthetic)


def _known_repository_paths(report: dict[str, Any], repository: str | None) -> set[str]:
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    paths: set[str] = set()
    for check in report.get("checks", []):
        if check.get("repository") != repository:
            continue
        evidence = check.get("evidence") or {}
        evidence_paths = evidence.get("paths")
        if isinstance(evidence_paths, list):
            paths.update(path for path in evidence_paths if isinstance(path, str))
        if check.get("state") in pass_states and isinstance(check.get("path"), str):
            paths.add(check["path"])
    return paths


def _nearest_existing_parent_url(
    report: dict[str, Any], check: dict[str, Any], path: str
) -> str | None:
    repository = check.get("repository")
    ref = check.get("ref") or "main"
    if not repository:
        return None
    if "/" not in path:
        return f"https://github.com/{repository}/tree/{ref}"
    candidate = path.rsplit("/", 1)[0]
    known_paths = _known_repository_paths(report, repository)
    while candidate:
        if candidate.rstrip("/") in known_paths:
            return f"https://github.com/{repository}/tree/{ref}/{candidate.rstrip('/')}"
        if "/" not in candidate:
            break
        candidate = candidate.rsplit("/", 1)[0]
    return f"https://github.com/{repository}/tree/{ref}"


def _field_table(check: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    expected_fields = check.get("expected")
    values = evidence.get("values")
    declarations = evidence.get("declarations")
    if isinstance(declarations, dict):
        values = declarations
    if (
        not isinstance(expected_fields, list)
        or not expected_fields
        or not isinstance(values, dict)
    ):
        return []
    rows = [
        [
            field,
            "Present" if values.get(field) not in (None, False) else "Missing",
            values.get(field),
        ]
        for field in expected_fields
    ]
    return [
        "**Expected fields**",
        "",
        *_markdown_table(["Expected field", "Status", "Observed value"], rows),
    ]


def _source_value_table(check: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    client = evidence.get("client")
    if not isinstance(client, dict):
        return []
    rows: list[list[Any]] = []
    for field, source_value in client.items():
        if not isinstance(source_value, dict):
            continue
        provenance = source_value.get("provenance", {})
        source_url = _github_location(
            provenance.get("repository"),
            provenance.get("path"),
            provenance.get("ref"),
        )
        rows.append(
            [
                field,
                source_value.get("value"),
                source_value.get("confidence"),
                _linked_code(
                    f"{provenance.get('repository', '—')} / "
                    f"{provenance.get('path', '—')} @ {provenance.get('ref', '—')}"
                    if not source_url
                    else f"{provenance.get('repository')} / {provenance.get('path')}",
                    source_url,
                ),
            ]
        )
    if not rows:
        return []
    return [
        "**Observed declarations**",
        "",
        *_markdown_table(["Field", "Value", "Confidence", "Source"], rows),
    ]


def _text_value(value: Any, indent: int) -> str:
    if value is None:
        return "-"
    if not isinstance(value, (dict, list)):
        return str(value)

    rendered = json.dumps(value, indent=2, sort_keys=True)
    lines = rendered.splitlines()
    if len(lines) <= 1:
        return rendered
    continuation = " " * indent
    return "\n".join([lines[0], *(continuation + line for line in lines[1:])])


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _state(state: str) -> str:
    return f"{STATE_SYMBOLS.get(state, '•')} {state}"


def _path_checklist(check: dict[str, Any]) -> list[str] | None:
    evidence = check.get("evidence") or {}
    expected_paths = evidence.get("expected_paths")
    found_paths = set(evidence.get("paths") or [])
    if not isinstance(expected_paths, list) or not expected_paths:
        return None

    width = max(len(path) for path in expected_paths) + 2
    lines = ["  Expected paths:"]
    present_count = 0
    for path in expected_paths:
        present = path in found_paths
        present_count += int(present)
        symbol = "✅" if present else "❌"
        lines.append(f"    {path:<{width}} {symbol}")
    lines.append(
        f"  Result:       {present_count} of {len(expected_paths)} expected paths present"
    )
    return lines


def _field_value_checklist(check: dict[str, Any]) -> list[str] | None:
    """Render expected fields and their present values or MISSING."""
    expected_fields = check.get("expected")
    evidence = check.get("evidence") or {}
    values = evidence.get("values")
    if (
        values is None
        and isinstance(expected_fields, list)
        and expected_fields
        and all(isinstance(field, str) for field in expected_fields)
        and isinstance(evidence, dict)
        and all(field in evidence for field in expected_fields)
        and all(isinstance(evidence[field], bool) for field in expected_fields)
    ):
        values = {field: "present" if evidence[field] else None for field in expected_fields}
    if (
        not isinstance(expected_fields, list)
        or not expected_fields
        or not all(isinstance(field, str) for field in expected_fields)
        or not isinstance(values, dict)
    ):
        return None

    rendered_values: list[str] = []
    present_count = 0
    for field in expected_fields:
        value = values.get(field)
        if value is None:
            rendered_values.append("MISSING")
            continue
        if isinstance(value, bool):
            rendered_value = _scalar_text(value)
        elif isinstance(value, (dict, list)):
            rendered_value = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            rendered_value = _scalar_text(value)
        rendered_values.append(rendered_value)
        present_count += 1

    field_width = max(len(field) for field in expected_fields) + 2
    value_width = max(len(value) for value in rendered_values) + 2
    lines = ["  Expected fields:"]
    for field, rendered_value in zip(expected_fields, rendered_values):
        lines.append(f"    {field:<{field_width}} {rendered_value:>{value_width}}")
    lines.append(
        f"  Result:       {present_count} of {len(expected_fields)} expected fields present"
    )
    return lines


def _oidc_field_table(check: dict[str, Any]) -> list[str] | None:
    if check.get("id") != "hub.oidc_client":
        return None
    evidence = check.get("evidence") or {}
    fields = evidence.get("fields")
    if not isinstance(fields, dict):
        return None

    rows = [
        (field, result.get("expected"), result.get("observed"))
        for field, result in fields.items()
        if isinstance(result, dict)
    ]
    if not rows:
        return None
    field_width = max(len(field) for field, _, _ in rows) + 2
    expected_width = max(len(_scalar_text(expected)) for _, expected, _ in rows) + 2
    lines = [
        "  Keycloak OIDC fields:",
        "  Field:".ljust(field_width)
        + "Expected:".ljust(expected_width)
        + "Observed:",
    ]
    for field, expected, observed in rows:
        lines.append(
            f"  {field:<{field_width - 2}}  "
            f"{_scalar_text(expected):<{expected_width - 2}}  "
            f"{_scalar_text(observed)}"
        )
    return lines


def _mapping_summary(check: dict[str, Any]) -> list[str] | None:
    """Render present and missing scalar fields without duplicate JSON."""
    present = check.get("present")
    missing = check.get("missing")
    if not isinstance(present, dict) or not present:
        return None
    if any(isinstance(value, dict) for value in present.values()):
        return None

    lines: list[str] = []
    present_items = [
        (str(field), "MISSING" if value is None else _inline_value(value))
        for field, value in present.items()
    ]
    field_width = max(len(field) for field, _ in present_items) + 2
    value_width = max(len(value) for _, value in present_items) + 2
    lines.append("  Fields:")
    lines.extend(
        f"    {field:<{field_width}} {value:>{value_width}}"
        for field, value in present_items
    )

    if isinstance(missing, dict) and missing:
        missing_fields = [str(field) for field in missing]
        missing_width = max(len(field) for field in missing_fields) + 2
        lines.append("  Missing fields:")
        lines.extend(
            f"    {field:<{missing_width}} {'MISSING':>{value_width}}"
            for field in missing_fields
        )
    return lines


def _inline_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _path_scope_summary(check: dict[str, Any]) -> list[str] | None:
    """Summarize open-ended path-scope checks without repeating count objects."""
    actual = check.get("actual")
    evidence = check.get("evidence") or {}
    if (
        check.get("expected") != "At least one matching path"
        or not isinstance(actual, dict)
        or not isinstance(actual.get("matched_file_count"), int)
    ):
        return None

    lines: list[str] = []
    found_paths = evidence.get("paths")
    if isinstance(found_paths, list) and found_paths:
        lines.append("  Matching paths:")
        lines.extend(f"    {path}" for path in found_paths)
    lines.append(
        f"  Result:       {actual['matched_file_count']} matching paths; "
        "expected at least one"
    )
    return lines


def _pull_request_count_summary(check: dict[str, Any]) -> list[str] | None:
    """Render pull-request counts once instead of three nested JSON objects."""
    actual = check.get("actual")
    required = {
        "matching_pr_count",
        "open_count",
        "merged_count",
        "closed_unmerged_count",
    }
    if not isinstance(actual, dict) or not required.issubset(actual):
        return None

    counts = [
        ("Matching PRs", actual["matching_pr_count"]),
        ("Merged PRs", actual["merged_count"]),
        ("Closed-unmerged PRs", actual["closed_unmerged_count"]),
        ("Open PRs", actual["open_count"]),
    ]
    repository_counts = actual.get("repository_counts")
    label_width = max(len(label) for label, _ in counts) + 2
    value_width = max(len(str(value)) for _, value in counts) + 2
    lines = ["  Pull request counts:"]
    lines.extend(
        f"    {label:<{label_width}} {str(value):>{value_width}}"
        for label, value in counts
    )
    if isinstance(repository_counts, dict) and repository_counts:
        lines.append("  Pull requests by repository:")
        lines.extend(
            f"    {repository}: {count}"
            for repository, count in sorted(repository_counts.items())
        )
    return lines


def _agent_label_inputs_table(check: dict[str, Any]) -> list[str] | None:
    evidence = check.get("evidence") or {}
    rows = evidence.get("agent_label_hosts")
    if check.get("id") != "workload.agent_labels_inputs" or not isinstance(rows, list):
        return None

    def display(value: Any) -> str:
        return "MISSING" if value is None else str(value)

    rendered = [
        (
            display(row.get("host")),
            display(row.get("bm_management")),
            display(row.get("mac_addr")),
            display(row.get("resource_class")),
        )
        for row in rows
        if isinstance(row, dict)
    ]
    if not rendered:
        return []
    widths = [
        max(len(header), *(len(row[index]) for row in rendered)) + 2
        for index, header in enumerate(("Host", "bm_management", "mac_addr", "resource_class"))
    ]
    lines = [
        "  Agent label inputs:",
        "  "
        + "Host:".ljust(widths[0])
        + "bm_management:".ljust(widths[1])
        + "mac_addr:".ljust(widths[2])
        + "resource_class:",
    ]
    lines.extend(
        "  "
        + host.ljust(widths[0])
        + management.ljust(widths[1])
        + mac_addr.ljust(widths[2])
        + resource_class
        for host, management, mac_addr, resource_class in rendered
    )
    return lines


def _structured_summary(check: dict[str, Any]) -> list[str] | None:
    """Route a check to the most specific compact text renderer."""
    return (
        _oidc_field_table(check)
        or
        _agent_label_inputs_table(check)
        or
        _path_checklist(check)
        or _field_value_checklist(check)
        or _path_scope_summary(check)
        or _pull_request_count_summary(check)
        or _mapping_summary(check)
    )


def _feature_chart_text_table(check: dict[str, Any]) -> list[str]:
    evidence = check.get("evidence") or {}
    rows = evidence.get("charts")
    if check.get("id") != "workload.feature_chart_values" or not isinstance(
        rows, list
    ):
        return []
    rendered = [
        [
            str(row.get("chart") or "-"),
            str(row.get("application_set") or "-"),
            str(row.get("placement") or "-"),
            str(row.get("feature_label") or "-"),
            "yes" if row.get("hub_values_file") else "no",
            "yes" if row.get("cluster_values_file") else "no",
            ", ".join(row.get("unmet_required_values") or []) or "-",
        ]
        for row in rows
        if isinstance(row, dict)
    ]
    if not rendered:
        return []
    headers = (
        "Chart",
        "Application set",
        "Placement",
        "Feature label",
        "Hub values",
        "Cluster values",
        "Unmet required values",
    )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rendered))
        for index in range(len(headers))
    ]
    lines = ["  Received charts:"]
    lines.append(
        "  "
        + "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(headers)
        )
    )
    lines.extend(
        "  "
        + "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rendered
    )
    return lines


def _followup_gap(check: dict[str, Any]) -> str:
    if check["state"] == "pr_open":
        return "Merge or close the relevant open pull request."
    missing = check.get("missing")
    if missing is None:
        return "Resolve the missing or partial configuration."
    return _text_value(missing, 4)


def _scope_title(scope: str) -> str:
    titles = {
        "environment": "Environment configuration status",
        "hub": "Hub environment configuration status",
        "workload": "Workload environment configuration status",
    }
    return titles.get(scope, f"{scope.title()} environment configuration status")


def _metadata_header_lines(report: dict[str, Any]) -> list[str]:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return []
    sources = " ".join(
        f"{source['repository']}@{source['sha'][:7]}"
        for source in metadata.get("sources", [])
    )
    non_main_refs = [
        f"{source['repository']}@{source['ref']}"
        for source in metadata.get("sources", [])
        if source.get("ref") != "main"
    ]
    lines = [
        f"Generated: {metadata['generated_at']}",
        f"Sources: {sources or '-'}",
    ]
    if non_main_refs:
        lines.append(f"Non-main refs: {', '.join(non_main_refs)}")
    return lines


def _symbol(state: str, ascii_mode: bool = False) -> str:
    if ascii_mode:
        return ASCII_STATE_SYMBOLS.get(state, "[?]")
    return STATE_SYMBOLS.get(state, "•")


def _wrap(text: str, indent: int = 0, width: int = 96) -> list[str]:
    prefix = " " * indent
    return textwrap.wrap(
        text,
        width=width,
        initial_indent=prefix,
        subsequent_indent=prefix,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [prefix]


def _generated_timestamp(report: dict[str, Any]) -> str:
    generated = (report.get("metadata") or {}).get("generated_at", "")
    if not generated:
        return "unknown"
    try:
        seconds = generated.removesuffix("Z")
        return seconds[:16].replace("T", " ") + " UTC"
    except ValueError:
        return generated


def _sources_table(report: dict[str, Any]) -> list[str]:
    sources = (report.get("metadata") or {}).get("sources", [])
    if not sources:
        return ["Sources: —"]
    rows = ["Repository                 Ref      Commit"]
    for source in sources:
        repository = source.get("repository", "unknown")
        ref = source.get("ref", "main")
        sha = source.get("sha", "")
        rows.append(f"{repository:<27} {ref:<8} {sha[:7]}")
        if source.get("from_cache"):
            rows.append(f"  from cache, fetched {source.get('fetched_at') or 'unknown'}")
    return rows


def _markdown_sources_table(report: dict[str, Any]) -> list[str]:
    sources = (report.get("metadata") or {}).get("sources", [])
    if not sources:
        return ["Sources: —"]
    rows = []
    for source in sources:
        repository = source.get("repository", "unknown")
        ref = source.get("ref", "main")
        sha = source.get("sha", "")
        commit_url = f"https://github.com/{repository}/commit/{sha}"
        rows.append(
            [
                repository.removeprefix("CCI-MOC/"),
                ref,
                MarkdownCell(f"[{sha[:7]}]({commit_url})") if sha else "—",
            ]
        )
    return _markdown_table(["Repository", "Ref", "Commit"], rows)


def _workload_checks(
    checks: list[dict[str, Any]], workload: str
) -> list[dict[str, Any]]:
    return [
        check
        for check in checks
        if check.get("cluster") == workload
    ]


def _report_pulls(
    report: dict[str, Any], classifications: set[str] | None = None
) -> list[dict[str, Any]]:
    pulls = [
        pull
        for pull in report.get("pull_requests", [])
        if isinstance(pull, dict)
        and (
            classifications is None
            or _pull_field(pull, "classification") in classifications
        )
    ]
    return sorted(
        pulls,
        key=lambda pull: (
            _pull_field(pull, "repository") or "",
            _pull_field(pull, "number") or 0,
        ),
    )


def _unknown_headline(checks: list[dict[str, Any]]) -> str:
    unknown = [
        check
        for check in checks
        if check["state"] == "unknown" and not check.get("deferred")
    ]
    if not unknown:
        return ""
    names = [check["check"] for check in unknown]
    shown = ", ".join(names[:2])
    if len(names) > 2:
        shown += f", and {len(names) - 2} more"
    return f"UNKNOWN: {shown}"


def _blocked_summary(report: dict[str, Any]) -> str | None:
    checks = report.get("checks", [])
    hub_cluster = report["environment"].get("infra_cluster")
    by_key = {
        (check.get("id"), check.get("cluster")): check for check in checks
    }
    blocked = [
        check
        for check in checks
        if check.get("state") == "blocked" and not check.get("deferred")
    ]
    if not blocked:
        return None
    gaps = _sorted_actions(
        _action_checks(report),
        hub_cluster,
    )
    action_numbers = {
        (check.get("id"), check.get("cluster")): number
        for number, check in enumerate(gaps, 1)
    }
    actions = []
    for check in blocked:
        for blocker_id in check.get("blocked_by", []):
            same_cluster = (blocker_id, check.get("cluster"))
            hub_dependency = (blocker_id, hub_cluster)
            key = (
                same_cluster
                if same_cluster in by_key
                else hub_dependency
                if hub_dependency in by_key
                else None
            )
            number = action_numbers.get(key) if key is not None else None
            if number is not None and number not in actions:
                actions.append(number)
    action = ", ".join(str(number) for number in sorted(actions))
    noun = "check" if len(blocked) == 1 else "checks"
    return f"{len(blocked)} {noun} blocked by action {action}" if actions else f"{len(blocked)} {noun} blocked by missing inputs"


def _action_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check for check in report.get("checks", [])
        if not check.get("deferred")
        if check.get("severity") in {"blocking", "advisory"}
        and check.get("state") not in {"declared_in_main", "requested", "pr_merged", "unknown", "blocked"}
    ]


def _pull_status_line(report: dict[str, Any]) -> str | None:
    unavailable = report.get("pull_requests_unavailable")
    if unavailable:
        return f"Pull requests: unavailable ({unavailable})"
    if report.get("pull_requests_skipped"):
        reason = report.get("pull_requests_skip_reason")
        return f"Pull requests: {reason}" if reason else "Pull requests: skipped because this run is unauthenticated; use --prs to inspect them."
    return None


def _cache_header_lines(report: dict[str, Any]) -> list[str]:
    return [
        f"{source['repository'].removeprefix('CCI-MOC/')}: from cache, fetched {source.get('fetched_at') or 'unknown'}"
        for source in (report.get("metadata") or {}).get("sources", [])
        if source.get("from_cache")
    ]


def _deferred_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [check for check in report.get("checks", []) if check.get("deferred")]


def _resolved_deferred_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    resolved = [
        check
        for check in report.get("checks", [])
        if check.get("deferred_resolved")
    ]
    seen: set[tuple[Any, Any]] = set()
    unique = []
    for check in resolved:
        key = (check.get("id"), check.get("cluster"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(check)
    return unique


def _expired_deferred_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check
        for check in report.get("checks", [])
        if check.get("deferred_expired")
    ]


def _deferred_text_lines(report: dict[str, Any]) -> list[str]:
    deferred = _deferred_checks(report)
    resolved = _resolved_deferred_checks(report)
    expired = _expired_deferred_checks(report)
    if not deferred and not resolved and not expired:
        return []
    lines = ["", "Deferred"]
    for check in deferred:
        until = (
            f"; deferred until {check['defer_until']}"
            if check.get("defer_until")
            else ""
        )
        lines.extend(
            _wrap(
                f"- {check.get('check')} ({check.get('id')}, "
                f"{check.get('cluster')}) — {check.get('defer_reason')}{until}",
                2,
            )
        )
    for check in expired:
        lines.extend(
            _wrap(
                f"- {check.get('check')} ({check.get('id')}, "
                f"{check.get('cluster')}) — {check.get('defer_reason')}; "
                f"deferral expired {check.get('defer_until')}",
                2,
            )
        )
    for check in resolved:
        lines.extend(
            _wrap(
                f"- {check.get('check')} ({check.get('id')}): deferred item "
                "resolved; remove it from the registry.",
                2,
            )
        )
    return lines


def _action_evidence(check: dict[str, Any], report: dict[str, Any]) -> str:
    if check.get("id") == "workload.address_uniqueness":
        duplicates = (check.get("missing") or {}).get("duplicates") or check.get("actual") or {}
        addresses = ", ".join(duplicates)
        current = report.get("environment", {}).get("workload_clusters") or []
        clusters = sorted({cluster for uses in duplicates.values() for cluster, _ in uses if cluster not in current})
        return f"{addresses} are also used by {', '.join(clusters)}; expected addresses unique to this cluster."
    rows = failing_field_rows(check)
    if check.get("id") in {"workload.api_address_network", "workload.ingress_address_network"}:
        return " ".join(f"{name} is {plain(observed)}; it must be {plain(expected)}." for name, expected, observed in rows)
    return " ".join(f"{name} is {plain(observed)}; expected {plain(expected)}." for name, expected, observed in rows)


def _action_description(check: dict[str, Any], report: dict[str, Any]) -> str:
    action = _substitute_action(check.get("next_action") or f"Resolve {check['check']}.", check, report)
    cluster = check.get("cluster")
    if check.get("scope") == "workload" and cluster and (
        cluster not in action
        or check.get("id") == "workload.feature_chart_values"
    ):
        action = f"{cluster}: {action}"
    advisory = " (advisory)" if check.get("severity") == "advisory" else ""
    return f"{action}{advisory} {_action_evidence(check, report)}"


def _substitute_action(
    action: str, check: dict[str, Any], report: dict[str, Any]
) -> str:
    environment = report["environment"]
    hub = environment.get("infra_cluster", environment.get("name", ""))
    cluster = check.get("cluster") or hub
    return action.replace("<hub>", hub).replace("<cluster>", cluster)


def _sorted_actions(
    gaps: list[dict[str, Any]], hub_cluster: str | None = None
) -> list[dict[str, Any]]:
    by_key = {
        (check.get("id"), check.get("cluster")): check for check in gaps
    }
    hub_cluster = hub_cluster or next(
        (
            check.get("cluster")
            for check in gaps
            if check.get("scope") == "hub" and check.get("cluster")
        ),
        None,
    )

    def dependencies(check: dict[str, Any]) -> list[tuple[Any, Any]]:
        keys: list[tuple[Any, Any]] = []
        for dependency in check.get("blocked_by", []):
            same_cluster = (dependency, check.get("cluster"))
            hub_dependency = (dependency, hub_cluster)
            if same_cluster in by_key and same_cluster not in keys:
                keys.append(same_cluster)
            elif hub_dependency in by_key and hub_dependency not in keys:
                keys.append(hub_dependency)
        return keys

    remaining = set(by_key)
    ordered: list[dict[str, Any]] = []

    def key(check: dict[str, Any]) -> tuple[Any, ...]:
        return (
            0 if check.get("scope") == "hub" else 1,
            0 if check.get("severity") == "blocking" else 1,
            check.get("phase") or 0,
            check.get("check") or "",
            check.get("cluster") or "",
        )

    while remaining:
        ready = [
            by_key[item]
            for item in remaining
            if not any(
                dependency in remaining
                for dependency in dependencies(by_key[item])
            )
        ]
        if not ready:
            ready = [by_key[item] for item in remaining]
        selected = min(ready, key=key)
        ordered.append(selected)
        remaining.remove((selected.get("id"), selected.get("cluster")))
    return ordered


def _phase_rows(report: dict[str, Any], scope: str) -> list[tuple[int, str]]:
    phases = report.get("phases", {})
    key = scope if scope in {"hub", "workload"} else "hub"
    definitions = phases.get(key, []) if isinstance(phases, dict) else phases
    return sorted((phase["phase"], phase["title"]) for phase in definitions)


def _workload_phase_rows(report: dict[str, Any]) -> list[tuple[int, str]]:
    phases = report.get("phases", {})
    definitions = (
        phases
        if isinstance(phases, list)
        else phases.get("workload", [])
    )
    return sorted((phase["phase"], phase["title"]) for phase in definitions)


def _phase_cell(checks: list[dict[str, Any]], ascii_mode: bool) -> str:
    if not checks:
        return "verify by hand"
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    passing = sum(check["state"] in pass_states for check in checks)
    unknown = sum(check["state"] == "unknown" for check in checks)
    blocked = sum(check["state"] == "blocked" for check in checks)
    failures = [check for check in checks if check["state"] not in pass_states | {"unknown"}]
    if not failures and (not unknown or passing):
        symbol = "[ok]" if ascii_mode else "✅"
    elif not failures:
        symbol = "[??]" if ascii_mode else "⚪"
    elif any(check.get("severity") == "blocking" for check in failures):
        symbol = "[fail]" if ascii_mode else "❌"
    else:
        symbol = "[warn]" if ascii_mode else "🟡"
    detail = f"{passing}/{len(checks)} checks"
    if unknown:
        detail += f", {unknown} unknown"
    if blocked:
        detail += f", {blocked} blocked"
    return f"{symbol} {detail}"


def _guide(report: dict[str, Any], scope: str, phase: int) -> str:
    phases = report.get("phases", {})
    definitions = phases.get(scope, []) if isinstance(phases, dict) and scope != "environment" else (
        phases.get("hub", []) + phases.get("workload", [])
        if isinstance(phases, dict)
        else []
    )
    match = next((item for item in definitions if item["phase"] == phase), None)
    if not match:
        return ""
    guide = match["guide"]
    return f"{guide['document']} → {guide['heading']}"


def _open_pr_fix(
    check: dict[str, Any], pulls: list[dict[str, Any]]
) -> str | None:
    # File overlap alone is never evidence that a PR fixes a check.
    return "; ".join((check.get("evidence") or {}).get("pr_evaluations", [])) or None


def _dependency_action_numbers(
    check: dict[str, Any],
    action_numbers: dict[tuple[Any, Any], int],
    hub_cluster: str | None,
) -> list[str]:
    numbers: list[str] = []
    for dependency in check.get("blocked_by", []):
        number = action_numbers.get((dependency, check.get("cluster")))
        if number is None:
            number = action_numbers.get((dependency, hub_cluster))
        if number is not None and str(number) not in numbers:
            numbers.append(str(number))
    return numbers


def _status_command(report: dict[str, Any], suffix: str) -> str:
    name = report["environment"]["name"]
    flags = []
    command = (report.get("metadata") or {}).get("command", [])
    for index, argument in enumerate(command):
        if argument in {"--ref", "--scope"} and index + 1 < len(command):
            flags.extend([argument, command[index + 1]])
        elif argument.startswith(("--ref=", "--scope=")):
            flags.append(argument)
    suffix = " ".join([*flags, suffix])
    if report.get("scope") == "hub":
        return f"moc-env status-hub {name} {suffix}".strip()
    if report.get("scope") == "workload":
        workload = (report["environment"].get("workload_clusters") or ["workload0"])[0]
        short = workload.removeprefix(f"{name}-")
        return f"moc-env status-workload {name} --workload {short} {suffix}".strip()
    return f"moc-env status {name} {suffix}".strip()


def _source_line(report: dict[str, Any]) -> str:
    metadata = report.get("metadata") or {}
    parts = []
    for source in metadata.get("sources", []):
        label = f"{source['repository'].removeprefix('CCI-MOC/')}@{source['sha'][:7]}"
        if source.get("ref") != "main":
            label += f"@{source['ref']}"
        parts.append(label)
    sources = "  ".join(parts)
    issue = next((check for check in report["checks"] if check["id"] == "request.issue"), None)
    if issue:
        number = report["environment"].get("issue_number")
        state = issue.get("actual")
        sources += f"  issue #{number} ({state})"
    return sources or "-"


def _detail_url(check: dict[str, Any]) -> str | None:
    if check.get("state") not in {"missing", "unknown"} or "/" not in check["path"]:
        return check.get("url")
    parent = check["path"].rsplit("/", 1)[0]
    return f"https://github.com/{check['repository']}/tree/{check['ref']}/{parent}"


def _plain_rows(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        return [(str(key), _value(item)) for key, item in value.items()]
    if isinstance(value, list):
        return [(f"[{index}]", _value(item)) for index, item in enumerate(value)]
    return [("value", _value(value))]


def _plain_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dict):
        return ", ".join(f"{key}={_plain_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_plain_value(item) for item in value)
    return str(value)


def _check_symbol(check: dict[str, Any], ascii_mode: bool = False) -> str:
    if check.get("state") not in {"declared_in_main", "requested", "pr_merged", "unknown", "blocked"}:
        if check.get("severity") == "blocking":
            return "[fail]" if ascii_mode else "❌"
        return "[warn]" if ascii_mode else "🟡"
    return _symbol(check["state"], ascii_mode)


def _detail_section(check: dict[str, Any], ascii_mode: bool) -> list[str]:
    rows = field_rows(check)
    field_width = max([len("Field")] + [len(plain(row[0])) for row in rows])
    expected_width = max([len("Expected")] + [len(plain(row[1])) for row in rows])
    source = next(
        (
            item for item in check.get("_sources", [])
            if item.get("repository") == check["repository"] and item.get("ref") == check["ref"]
        ),
        {},
    )
    short_sha = source.get("sha", "")[:7] or "-"
    lines = [
        "-" * 100,
        *_wrap(
            f"{_check_symbol(check, ascii_mode)} "
            f"{check['check']} — {check['reason']}",
            2,
        ),
        f"  Source: {check['repository']} · {check['path']} @ {check['ref']} ({short_sha})",
    ]
    if check.get("verifies"):
        lines.extend(_wrap(f"Verifies: {check['verifies']}", 2))
    if check.get("not_verified"):
        lines.extend(_wrap(f"Not verified: {check['not_verified']}", 2))
    lines.append(
        f"  {'Field':<{field_width}}  {'Expected':<{expected_width}}  Observed"
    )
    if check.get("id") == "pull_requests":
        pulls = (check.get("evidence") or {}).get("pull_requests", [])
        by_repository: dict[str, int] = {}
        for pull in pulls:
            repository_value = pull.get("repository", "")
            repository = (
                repository_value.get("value", "")
                if isinstance(repository_value, dict)
                else repository_value
            )
            by_repository[repository] = by_repository.get(repository, 0) + 1
        lines.append("  Pull requests by repository:")
        for repository, count in sorted(by_repository.items()):
            lines.append(f"    {repository}: {count}")
    for name, expected_value, observed_value in rows:
        lines.append(f"  {plain(name):<{field_width}}  {plain(expected_value):<{expected_width}}  {plain(observed_value)}")
    lines.extend(_feature_chart_text_table(check))
    url = _detail_url(check)
    if url:
        lines.append(f"  URL: {url}")
    return lines


def render_text(
    report: dict[str, Any],
    details: bool = False,
    ascii_mode: bool = False,
) -> str:
    environment = report["environment"]
    scope = report.get("scope", "environment")
    generated_text = _generated_timestamp(report)
    non_main = [
        source for source in (report.get("metadata") or {}).get("sources", [])
        if source.get("ref") != "main"
    ]
    title_scope = (
        "hub + workload"
        if scope == "environment" and environment.get("workload_clusters")
        else ("hub" if scope == "environment" else scope)
    )
    first = (
        f"{environment['name']} · {title_scope} · repo config as of {generated_text}"
    )
    if non_main:
        first += " · NOT A REPORT ON MAIN"
    lines = [first, *_cache_header_lines(report), ""]

    checks = report["checks"]
    active_checks = [check for check in checks if not check.get("deferred")]
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    passing = sum(check["state"] in pass_states for check in active_checks)
    blocking = [
        check for check in active_checks
        if check["severity"] == "blocking"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    advisories = [
        check for check in active_checks
        if check["severity"] == "advisory"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
        and check["state"] != "blocked"
    ]
    unknown = [check for check in active_checks if check["state"] == "unknown"]
    scope_blocking = {
        cluster: sum(check["scope"] == "workload" for check in blocking)
        for cluster in environment.get("workload_clusters", [])
    }
    scope_text = (
        f" (workload {sum(scope_blocking.values())})"
        if scope_blocking and scope == "environment"
        else ""
    )
    if not blocking and not advisories and not unknown:
        result = "RESULT: No deployment gaps in repository configuration."
    else:
        result = (
            f"RESULT: {len(blocking)} blocking gaps{scope_text} · "
            f"{len(advisories)} advisories · {passing} of {len(active_checks)} checks pass"
        )
    lines.extend(_wrap(result))
    if unknown:
        lines.append(_unknown_headline(checks))
    blocked_summary = _blocked_summary(report)
    if blocked_summary:
        lines.append(blocked_summary)
    pull_status = _pull_status_line(report)
    if pull_status:
        lines.append(pull_status)
    lines.append("")

    def phase_table(title: str, phase_rows: list[tuple[int, str]], columns: list[tuple[str, list[dict[str, Any]]]]) -> None:
        if not phase_rows or not columns:
            return
        lines.extend(["", title])
        labels = [f"{phase} {phase_title}" for phase, phase_title in phase_rows]
        phase_width = min(max([len("PHASE")] + [len(label) for label in labels]) + 2, 29)
        cell_width = min(max([len(header) for header, _ in columns] + [14]) + 2, 32)
        lines.append(f"{'PHASE':<{phase_width}}" + "".join(f"{header:<{cell_width}}" for header, _ in columns))
        for phase, phase_title in phase_rows:
            label = textwrap.shorten(f"{phase} {phase_title}", width=phase_width, placeholder="…")
            cells = []
            for _header, scope_checks in columns:
                phase_checks = [check for check in scope_checks if check.get("phase") == phase]
                cell = _phase_cell(phase_checks, ascii_mode)
                cells.append(textwrap.shorten(cell, width=cell_width, placeholder="…"))
            lines.append(f"{label:<{phase_width}}" + "".join(f"{cell:<{cell_width}}" for cell in cells))

    if scope in {"environment", "hub"}:
        phase_table(
            "HUB PHASES",
            _phase_rows(report, "hub"),
            [(
                f"HUB {environment['infra_cluster']}",
                [
                    c for c in checks
                    if c.get("cluster") == environment["infra_cluster"]
                    and not c.get("deferred")
                ],
            )],
        )
    if scope in {"environment", "workload"}:
        columns = [
            (
                f"WORKLOAD {workload}",
                [
                    c
                    for c in _workload_checks(checks, workload)
                    if not c.get("deferred")
                ],
            )
            for workload in environment.get("workload_clusters", [])
        ]
        phase_table("WORKLOAD PHASES", _workload_phase_rows(report), columns)
    lines.append("")

    lines.append("NEXT")
    gaps = _sorted_actions(
        [*blocking, *advisories],
        environment["infra_cluster"],
    )
    if not gaps:
        lines.append("Nothing to do in the repositories this tool reads.")
    else:
        open_pulls = _report_pulls(report, {"open"})
        action_numbers: dict[tuple[Any, Any], int] = {}
        for number, check in enumerate(gaps, start=1):
            action_numbers.setdefault(
                (check.get("id"), check.get("cluster")), number
            )
        for number, check in enumerate(gaps, start=1):
            action = _action_description(check, report)
            repository = check["repository"].removeprefix("CCI-MOC/")
            after = _dependency_action_numbers(
                check, action_numbers, environment["infra_cluster"]
            )
            suffix = f" (after {', '.join(after)})" if after else ""
            pr_fix = _open_pr_fix(check, open_pulls)
            if pr_fix:
                suffix += f" · {pr_fix}"
            lines.extend(_wrap(f"{number}. [{repository}] {action}{suffix}", 2))
            lines.extend(_suggestion_lines(check, markdown=False, details=details))
            guide = _guide(report, check["scope"], check.get("phase", 0))
            if guide:
                lines.extend(_wrap(f"guide: {guide}", 7))

    lines.extend(_deferred_text_lines(report))
    lines.extend(["", "NOT CHECKED — verify by hand:"])
    titles = [entry["title"] for entry in report.get("not_checked", [])]
    if titles:
        lines.extend(_wrap("; ".join(titles), 2))
    else:
        lines.append("None.")

    open_pulls = _report_pulls(report, {"open"})
    pr_lines = []
    for pull in open_pulls:
        repository = (_pull_field(pull, "repository") or "").removeprefix("CCI-MOC/")
        number = _pull_field(pull, "number")
        title = _pull_field(pull, "title")
        files = _pull_field(pull, "changed_files") or []
        pr_lines.append(f"  {repository} #{number} — {title}")
        pr_lines.extend(f"    {path}" for path in files)
    if not pull_status:
        lines.extend([
            "",
            "PULL REQUESTS",
            f"{len(open_pulls)} open {'PR' if len(open_pulls) == 1 else 'PRs'} touch this environment.",
            *pr_lines,
        ])

    lines.extend(["", "Sources"])
    lines.extend(_sources_table(report))
    lines.extend(
        [
            "",
            *([] if details else [f"Details:  {_status_command(report, '--details')}"]),
            f"Markdown: {_status_command(report, '--format markdown --output report.md')}",
        ]
    )

    if details:
        lines.extend(["", "DETAILED CHECKS", ""])
        for check in checks:
            lines.extend(_detail_section({**check, "_sources": (report.get("metadata") or {}).get("sources", [])}, ascii_mode))
    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


def _oidc_markdown_table(check: dict[str, Any]) -> list[str] | None:
    if check.get("id") != "hub.oidc_client":
        return None
    evidence = check.get("evidence") or {}
    fields = evidence.get("fields")
    if not isinstance(fields, dict):
        return None
    rows = [
        [field, result.get("expected"), result.get("observed")]
        for field, result in fields.items()
        if isinstance(result, dict)
    ]
    if not rows:
        return None
    return [
        "**Keycloak OIDC fields**",
        "",
        *_markdown_table(["Field", "Expected", "Observed"], rows),
    ]


def _agent_label_markdown_table(check: dict[str, Any]) -> list[str] | None:
    evidence = check.get("evidence") or {}
    rows = evidence.get("agent_label_hosts")
    if not isinstance(rows, list):
        return []
    table_rows = [
        [
            row.get("host"),
            row.get("bm_management"),
            row.get("mac_addr"),
            row.get("resource_class"),
        ]
        for row in rows
        if isinstance(row, dict)
    ]
    if not table_rows:
        return []
    return [
        "**Agent label inputs**",
        "",
        *_markdown_table(
            ["Host", "bm_management", "mac_addr", "resource_class"], table_rows
        ),
    ]


def _feature_chart_markdown_table(check: dict[str, Any]) -> list[str]:
    evidence = check.get("evidence") or {}
    rows = evidence.get("charts")
    if check.get("id") != "workload.feature_chart_values" or not isinstance(
        rows, list
    ):
        return []
    table_rows = [
        [
            row.get("chart"),
            row.get("application_set"),
            row.get("placement"),
            row.get("feature_label"),
            row.get("hub_values_file"),
            row.get("cluster_values_file"),
            row.get("unmet_required_values") or [],
        ]
        for row in rows
        if isinstance(row, dict)
    ]
    if not table_rows:
        return []
    return [
        "**Received charts**",
        "",
        *_markdown_table(
            [
                "Chart",
                "Application set",
                "Placement",
                "Feature label",
                "Hub values",
                "Cluster values",
                "Unmet required values",
            ],
            table_rows,
        ),
    ]


def _markdown_human_value(value: Any) -> str:
    if value is None:
        return "—"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, dict):
        if "value" in value:
            return _markdown_human_value(value["value"])
        return ", ".join(
            f"{key} = {_markdown_human_value(item)}" for key, item in value.items()
        ) or "—"
    if isinstance(value, (list, tuple)):
        return ", ".join(_markdown_human_value(item) for item in value) or "—"
    if isinstance(value, str):
        if "\n" in value or " = " in value:
            rendered = value.replace(" = ", " ")
            rendered = rendered.replace("{", "").replace("}", "")
            rendered = rendered.replace("[", "").replace("]", "")
            rendered = rendered.replace('"', "")
            rendered = "<br>".join(
                line.strip()
                for line in rendered.splitlines()
                if line.strip()
            )
            return MarkdownCell(rendered)
        return value or "—"
    return str(value)


def _detail_field_rows(check: dict[str, Any], report: dict[str, Any]) -> list[list[Any]]:
    evidence = check.get("evidence") or {}
    expected_paths = evidence.get("expected_paths")
    if isinstance(expected_paths, list) and expected_paths:
        found_paths = set(evidence.get("paths") or [])
        return [
            [
                _linked_code(path, _path_url(check, path, report)),
                "present",
                "present" if path in found_paths else "missing",
            ]
            for path in expected_paths
        ]

    return field_rows(check)


def _expanded_field_rows(rows: list[list[Any]]) -> list[list[Any]]:
    expanded: list[list[Any]] = []
    for field, expected, observed in rows:
        _expand_field_row(field, expected, observed, expanded)
    return expanded


def _expand_field_row(
    field: str, expected: Any, observed: Any, expanded: list[list[Any]]
) -> None:
    if isinstance(expected, dict):
        for key, value in expected.items():
            observed_value = observed.get(key) if isinstance(observed, dict) else observed
            _expand_field_row(str(key), value, observed_value, expanded)
        return
    if isinstance(expected, list) and any(isinstance(item, dict) for item in expected):
        for index, item in enumerate(expected):
            observed_value = observed[index] if isinstance(observed, list) and index < len(observed) else observed
            label = str(item.get("name", index)) if isinstance(item, dict) else str(index)
            _expand_field_row(label, item, observed_value, expanded)
        return
    if isinstance(observed, dict):
        for key, value in observed.items():
            _expand_field_row(str(key), expected, value, expanded)
        return
    if isinstance(observed, list) and any(isinstance(item, dict) for item in observed):
        for index, item in enumerate(observed):
            label = str(item.get("name", index)) if isinstance(item, dict) else str(index)
            _expand_field_row(label, expected, item, expanded)
        return
    expanded.append([field, expected, observed])


def _check_markdown_details(
    check: dict[str, Any], sources: list[dict[str, Any]], report: dict[str, Any]
) -> list[str]:
    evidence = check.get("evidence") or {}
    source = next(
        (
            item
            for item in sources
            if item.get("repository") == check.get("repository")
            and item.get("ref") == check.get("ref")
        ),
        {},
    )
    short_sha = source.get("sha", "")[:7] or "—"
    path_url = _markdown_check_url(report, check)
    path_label = _markdown_inline(check.get("path"))
    path_text = f"[{path_label}]({path_url})" if path_url else path_label
    check_rule = evidence.get("check_rule")
    open_state = check.get("state") not in {
        "declared_in_main", "requested", "pr_merged"
    }
    lines = [
        f"<details{' open' if open_state else ''}>",
        f"<summary>{_check_symbol(check)} {check['check']} — {check['reason']}</summary>",
        "",
        f"Source: {check['repository']} · {path_text} @ {check['ref']} ({short_sha})",
        "",
    ]
    if check.get("verifies"):
        lines.append(f"Verifies: {check['verifies']}")
    if check.get("not_verified"):
        lines.append(f"Not verified: {check['not_verified']}")
    if check.get("verifies") or check.get("not_verified"):
        lines.append("")
    if check_rule:
        lines.extend([f"Status rule: {check_rule}", ""])
    field_rows = _expanded_field_rows(_detail_field_rows(check, report))
    rows = [
        [
            field if isinstance(field, MarkdownCell) else _markdown_human_value(field),
            _markdown_human_value(expected),
            _markdown_human_value(observed),
        ]
        for field, expected, observed in field_rows
    ]
    lines.extend(_markdown_table(["Field", "Expected", "Observed"], rows))
    if check.get("id") == "hub.local_cluster_values":
        required = set(evidence.get("expected_paths") or [])
        found = set(evidence.get("paths") or [])
        lines.extend(
            [
                "**Required files**",
                "",
                *_markdown_table(
                    ["Path", "Status"],
                    [
                        [path, "present" if path in found else "missing"]
                        for path in sorted(required)
                    ],
                ),
                "**Additional files present**",
                "",
            ]
        )
        extra = sorted(found - required)
        if extra:
            lines.extend(_markdown_table(["Path"], [[path] for path in extra]))
        else:
            lines.extend(["None.", ""])
    lines.extend(_host_table(check, evidence))
    lines.extend(_agent_label_markdown_table(check))
    lines.extend(_feature_chart_markdown_table(check))
    lines.extend(["</details>", ""])
    return lines


def _markdown_check_url(report: dict[str, Any], check: dict[str, Any]) -> str | None:
    if check.get("state") in {"missing", "unknown"} and "/" in (check.get("path") or ""):
        return _nearest_existing_parent_url(report, check, check["path"])
    return check.get("url") or _github_location(
        check.get("repository"), check.get("path"), check.get("ref")
    )


def _identity_link(value: Any, url: str | None) -> str:
    rendered = f"`{value}`"
    return f"[{rendered}]({url})" if url else rendered


def _identity_source_url(report: dict[str, Any], check_name: str) -> str | None:
    for check in report.get("checks", []):
        if check.get("check") == check_name:
            return check.get("url")
    return None


def _markdown_verdict(report: dict[str, Any]) -> str:
    checks = report["checks"]
    active_checks = [check for check in checks if not check.get("deferred")]
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    blocking = [
        check
        for check in active_checks
        if check["severity"] == "blocking"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    advisories = [
        check
        for check in active_checks
        if check["severity"] == "advisory"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
        and check["state"] != "blocked"
    ]
    unknown = [check for check in active_checks if check["state"] == "unknown"]
    passing = sum(check["state"] in pass_states for check in active_checks)
    if not blocking and not advisories and not unknown:
        return "No deployment gaps in repository configuration."
    verdict = (
        f"{len(blocking)} blocking gaps, {len(advisories)} advisories, "
        f"and {passing} of {len(active_checks)} checks pass"
    )
    unknown_headline = _unknown_headline(checks)
    if unknown_headline:
        verdict += f"; {unknown_headline}"
    blocked_summary = _blocked_summary(report)
    if blocked_summary:
        verdict += f"; {blocked_summary}"
    return verdict


def _markdown_metadata(report: dict[str, Any]) -> str:
    metadata = report.get("metadata") or {}
    generated = _generated_timestamp(report)
    parts = [f"Generated {generated}"]
    non_main = any(
        source.get("ref") != "main"
        for source in metadata.get("sources", [])
    )
    issue = next((check for check in report.get("checks", []) if check.get("id") == "request.issue"), None)
    issue_number = report.get("environment", {}).get("issue_number")
    if issue_number is None:
        parts.append("MOC issue: not set — pass `--issue N`")
    elif issue and issue.get("url"):
        parts.append(
            f"MOC issue: [#{issue_number}]({issue['url']}) ({issue.get('actual')})"
        )
    else:
        parts.append(f"MOC issue: #{issue_number}")
    parts.extend(_cache_header_lines(report))
    prefix = "**This is not a report on main.** " if non_main else ""
    return prefix + " · ".join(parts)


def _markdown_phase_table(report: dict[str, Any]) -> list[str]:
    environment = report["environment"]
    checks = report["checks"]
    scope = report.get("scope", "environment")

    def table(
        heading: str,
        phase_rows: list[tuple[int, str]],
        columns: list[tuple[str, list[dict[str, Any]]]],
    ) -> list[str]:
        if not phase_rows or not columns:
            return []
        rendered = [f"### {heading}", ""]
        rendered.append("| Phase | " + " | ".join(header for header, _ in columns) + " |")
        rendered.append("|---|" + "|".join("---:" for _ in columns) + "|")
        for phase, title in phase_rows:
            cells = [
                _phase_cell(
                    [
                        check
                        for check in scope_checks
                        if check.get("phase") == phase
                        and not check.get("deferred")
                    ],
                    False,
                )
                for _header, scope_checks in columns
            ]
            rendered.append(f"| {phase} {title} | " + " | ".join(cells) + " |")
        rendered.append("")
        return rendered

    lines: list[str] = []
    if scope in {"environment", "hub"}:
        lines.extend(
            table(
                "Hub phases",
                _phase_rows(report, "hub"),
                [(
                    f"HUB {environment['infra_cluster']}",
                    [
                        c for c in checks
                        if c.get("cluster") == environment["infra_cluster"]
                        and not c.get("deferred")
                    ],
                )],
            )
        )
    if scope in {"environment", "workload"}:
        lines.extend(
            table(
                "Workload phases",
                _workload_phase_rows(report),
                [
                    (
                        f"WORKLOAD {workload}",
                        [
                            c
                            for c in _workload_checks(checks, workload)
                            if not c.get("deferred")
                        ],
                    )
                    for workload in environment.get("workload_clusters", [])
                ],
            )
        )
    return lines


def _suggestion_lines(check: dict[str, Any], *, markdown: bool, details: bool = False) -> list[str]:
    suggestion = check.get("suggestion")
    indent = "   " if markdown else "       "
    if not suggestion:
        reason = check.get("suggestion_skipped_reason")
        return [indent + reason] if reason else []
    if not markdown and not details:
        return [indent + "suggested code available: re-run with --details"]
    header = (
        f"Suggested code (modeled on {suggestion['reference']}; "
        "not applied, no terraform plan run):"
    )
    url = github_url(suggestion['repository'], suggestion['path'], suggestion['commit'])
    url += f"#L{suggestion['after_line']}"
    path = f"[{suggestion['path']}]({url})" if markdown else suggestion['path']
    source = (f"File: {suggestion['repository']} {path} @ {suggestion['commit'][:7]}, "
              f"{suggestion['location']}")
    if not markdown:
        source += f" ({url})"
    lines = ["", indent + header, indent + source]
    if markdown:
        lines.extend(["", indent + "```hcl"])
    lines.extend(indent + line for line in suggestion['code'].splitlines())
    if markdown:
        lines.extend([indent + "```", ""])
    return lines


def _markdown_next_actions(report: dict[str, Any]) -> list[str]:
    checks = report["checks"]
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    gaps = [
        check
        for check in checks
        if not check.get("deferred")
        if check["severity"] in {"blocking", "advisory"}
        and check["state"] not in pass_states
        and check["state"] != "unknown"
        and check["state"] != "blocked"
    ]
    gaps = _sorted_actions(gaps, report["environment"].get("infra_cluster"))
    lines = ["## Next actions", ""]
    if not gaps:
        lines.extend(["Nothing to do in the repositories this tool reads.", ""])
        return lines
    open_pulls = _report_pulls(report, {"open"})
    action_numbers: dict[tuple[Any, Any], int] = {}
    for number, check in enumerate(gaps, start=1):
        action_numbers.setdefault(
            (check.get("id"), check.get("cluster")), number
        )
    for number, check in enumerate(gaps, start=1):
        action = _action_description(check, report)
        repository = check["repository"].removeprefix("CCI-MOC/")
        path_url = _markdown_check_url(report, check)
        path_label = _markdown_inline(check.get("path"))
        path = f"[{path_label}]({path_url})" if path_url else path_label
        after = _dependency_action_numbers(
            check,
            action_numbers,
            report["environment"].get("infra_cluster"),
        )
        suffix = f" (after {', '.join(after)})" if after else ""
        pr_fix = _open_pr_fix(check, open_pulls)
        if pr_fix:
            suffix += f" · {pr_fix}"
        lines.append(f"{number}. **{repository}** — {path}: {action}{suffix}")
        lines.extend(_suggestion_lines(check, markdown=True))
        guide = _guide(report, check["scope"], check.get("phase", 0))
        if guide:
            document, heading = guide.split(" → ", 1)
            guide_url = (
                f"https://github.com/CCI-MOC/oac-apps/blob/main/{document}"
            )
            lines.append(
                f"   Guide: [{document} → {heading}]({guide_url}#{heading.lower().replace(' ', '-')})"
            )
    lines.append("")
    return lines


def _markdown_manual_checks(report: dict[str, Any]) -> list[str]:
    lines = ["## Not checked — verify by hand", ""]
    entries = report.get("not_checked", [])
    if not entries:
        lines.extend(["None.", ""])
        return lines
    for entry in entries:
        where = entry["where"]
        guide_url = (
            f"https://github.com/CCI-MOC/oac-apps/blob/main/{where['document']}"
        )
        lines.append(
            f"- [ ] **{entry['title']}** (phase {entry['phase']}) — {entry['why']} "
            f"Documented at [{where['document']} → {where['heading']}]({guide_url}#{where['heading'].lower().replace(' ', '-')})."
        )
    lines.append("")
    return lines


def _markdown_deferred(report: dict[str, Any]) -> list[str]:
    deferred = _deferred_checks(report)
    resolved = _resolved_deferred_checks(report)
    expired = _expired_deferred_checks(report)
    if not deferred and not resolved and not expired:
        return []
    lines = ["## Deferred", ""]
    for check in deferred:
        until = (
            f" (deferred until {check['defer_until']})"
            if check.get("defer_until")
            else ""
        )
        lines.append(
            f"- **{check.get('check')}** (`{check.get('id')}`, "
            f"{check.get('cluster')}) — {check.get('defer_reason')}{until}"
        )
    for check in expired:
        lines.append(
            f"- **{check.get('check')}** (`{check.get('id')}`, "
            f"{check.get('cluster')}) — {check.get('defer_reason')}; "
            f"deferral expired {check.get('defer_until')}"
        )
    for check in resolved:
        lines.append(
            f"- **{check.get('check')}** (`{check.get('id')}`): deferred item "
            "resolved; remove it from the registry."
        )
    lines.append("")
    return lines


def _pull_field(pull: dict[str, Any], field: str) -> Any:
    value = pull.get(field)
    return value.get("value") if isinstance(value, dict) else value


def _markdown_pull_requests(report: dict[str, Any]) -> list[str]:
    status = _pull_status_line(report)
    if status:
        return [status, ""]
    pulls = {
        (
            _pull_field(pull, "repository"),
            _pull_field(pull, "number"),
        ): pull
        for pull in report.get("pull_requests", [])
        if isinstance(pull, dict)
    }
    lines = ["## Pull requests", ""]
    open_count = sum(
        _pull_field(pull, "classification") == "open"
        for pull in pulls.values()
    )
    lines.append(
        f"**{open_count} open {'PR' if open_count == 1 else 'PRs'} touch this environment.**"
    )
    lines.append("")
    if not pulls:
        lines.extend(["None.", ""])
        return lines

    environment = report["environment"]
    environment_parts = [
        environment["name"],
        environment["infra_cluster"],
        *environment.get("workload_clusters", []),
    ]

    def changed_files(pull: dict[str, Any]) -> list[str]:
        files = _pull_field(pull, "changed_files") or []
        relevant = [
            path
            for path in files
            if any(part in path for part in environment_parts)
        ]
        return relevant

    def pull_rows(classifications: set[str]) -> list[list[Any]]:
        rows = []
        for pull in sorted(
            pulls.values(),
            key=lambda item: (
                _pull_field(item, "repository") or "",
                _pull_field(item, "number") or 0,
            ),
        ):
            if _pull_field(pull, "classification") not in classifications:
                continue
            if not changed_files(pull):
                continue
            repository = _pull_field(pull, "repository")
            number = _pull_field(pull, "number")
            url = _pull_field(pull, "html_url")
            files = [
                f"[{path}]({url}/files)" for path in changed_files(pull)
            ]
            rows.append(
                [
                    repository.removeprefix("CCI-MOC/"),
                    MarkdownCell(f"[#{number}]({url})"),
                    _pull_field(pull, "title"),
                    _pull_field(pull, "head_ref"),
                    MarkdownCell("<br>".join(files)),
                ]
            )
        return rows

    headers = ["Repository", "PR", "Title", "Head branch", "Changed files"]
    open_rows = pull_rows({"open"})
    if open_rows:
        lines.extend(["### Open", "", *_markdown_table(headers, open_rows, True)])
    else:
        lines.extend(["### Open", "", "None.", ""])

    closed_rows = pull_rows({"merged", "closed_unmerged"})
    lines.extend(["<details>", "<summary>Merged and closed without merging</summary>", ""])
    if closed_rows:
        lines.extend(_markdown_table(headers, closed_rows, True))
    else:
        lines.append("None.")
        lines.append("")
    lines.extend(["</details>", ""])
    return lines


def _markdown_legend(report: dict[str, Any]) -> list[str]:
    meanings = {
        "requested": "The MOC issue records the request.",
        "declared_in_main": "Desired configuration is present on merged main.",
        "pr_merged": "A relevant pull request has been merged.",
        "pr_open": "Relevant configuration exists only in an open pull request.",
        "partial": "Some required configuration is present.",
        "missing": "Required configuration was not found.",
        "unknown": "The source could not be read or parsed.",
        "value_mismatch": "Observed values do not match the expected values.",
    }
    states = {
        check["state"] for check in report.get("checks", [])
    }
    lines = ["## Legend", ""]
    for state, meaning in meanings.items():
        if state in states:
            symbol = STATE_SYMBOLS.get(state, "•")
            lines.append(f"- {symbol} `{state}` — {meaning}")
    lines.extend(
        [
            "",
            "Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.",
            "",
        ]
    )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    environment = report["environment"]
    scope = report.get("scope", "environment")
    lines = [
        f"# {environment['name']} — {_scope_title(scope).lower()}",
        "",
        f"**{_markdown_verdict(report)}**",
        "",
        _markdown_metadata(report),
        "",
        "## Phase summary",
        "",
    ]
    lines.extend(_markdown_phase_table(report))
    lines.extend(_markdown_next_actions(report))
    lines.extend(_markdown_deferred(report))
    lines.extend(_markdown_manual_checks(report))
    lines.extend(["## Details", ""])
    sources = (report.get("metadata") or {}).get("sources", [])
    for check in report.get("checks", []):
        lines.extend(_check_markdown_details(check, sources, report))
    lines.extend(_markdown_pull_requests(report))
    lines.extend(["## Sources", "", *_markdown_sources_table(report), ""])
    lines.extend(_markdown_legend(report))
    return "\n".join(lines).rstrip() + "\n"


def _diff_scopes(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    environment = report["environment"]
    scopes = {"hub": [c for c in report["checks"] if c.get("scope") == "hub"]}
    for position, workload in enumerate(environment.get("workload_clusters", []), 1):
        scopes[f"workload {position}"] = _workload_checks(
            report["checks"], workload
        )
    return scopes


def _diff_files(
    checks: list[dict[str, Any]], environment: dict[str, Any]
) -> set[str]:
    names = {
        environment["infra_cluster"]: "<hub>",
        **{name: "<workload>" for name in environment.get("workload_clusters", [])},
    }

    def normalize(path: str) -> str:
        return "/".join(names.get(part, part) for part in path.split("/"))

    files: set[str] = set()
    for check in checks:
        evidence = check.get("evidence") or {}
        if isinstance(evidence.get("paths"), list):
            files.update(normalize(str(path)) for path in evidence["paths"])
    return files


def _structural_facts(
    checks: list[dict[str, Any]], report: dict[str, Any]
) -> dict[str, Any]:
    by_id = {check.get("id"): check for check in checks}
    facts: dict[str, Any] = {}
    inventory = next(
        (
            check for check in checks
            if check.get("id", "").endswith(".inventory")
            and isinstance(check.get("actual"), dict)
        ),
        None,
    )
    if inventory:
        facts["node_count"] = inventory["actual"].get("host_count")
    dns = by_id.get("hub.moc_dns_records")
    if dns:
        facts["dns_zone"] = (dns.get("evidence") or {}).get("zone")
    if "hub.hosted_cluster_defaults" in by_id:
        facts.update(report.get("diff_facts") or {})
    boot = next(
        (
            check for check in checks
            if check.get("id", "").endswith(".boot_image")
            and isinstance(check.get("actual"), list)
            and check["actual"]
        ),
        None,
    )
    if boot:
        facts["boot_image_naming"] = sorted(
            str(url).rsplit("/", 1)[-1] for url in boot["actual"]
        )
    agent = next(
        (
            check for check in checks
            if isinstance((check.get("evidence") or {}).get("agent_label_hosts"), list)
        ),
        None,
    )
    if agent:
        management_counts: dict[str, int] = {}
        for row in agent["evidence"]["agent_label_hosts"]:
            if isinstance(row, dict):
                value = "true" if row.get("bm_management") is True else "false" if row.get("bm_management") is False else str(row.get("bm_management"))
                management_counts[value] = management_counts.get(value, 0) + 1
        facts["bm_management_mix"] = management_counts
    return facts


def build_environment_diff(
    report_a: dict[str, Any], report_b: dict[str, Any]
) -> dict[str, Any]:
    """Compare structural repository state without environment-specific values."""

    scopes_a, scopes_b = _diff_scopes(report_a), _diff_scopes(report_b)
    scopes: list[dict[str, Any]] = []
    for scope in sorted(set(scopes_a) | set(scopes_b)):
        checks_a, checks_b = scopes_a.get(scope, []), scopes_b.get(scope, [])
        labels_a = {check.get("id"): check.get("check") or check.get("id") for check in checks_a}
        labels_b = {check.get("id"): check.get("check") or check.get("id") for check in checks_b}
        pass_states = {"declared_in_main", "requested", "pr_merged"}
        passing_a = {
            check.get("id")
            for check in checks_a if check.get("state") in pass_states
        }
        passing_b = {
            check.get("id")
            for check in checks_b if check.get("state") in pass_states
        }
        files_a = _diff_files(checks_a, report_a["environment"])
        files_b = _diff_files(checks_b, report_b["environment"])
        facts_a = _structural_facts(checks_a, report_a)
        facts_b = _structural_facts(checks_b, report_b)
        scopes.append(
            {
                "scope": scope,
                "checks_only_in_a": [
                    {"id": check_id, "check": labels_a[check_id]}
                    for check_id in sorted(passing_a - passing_b)
                ],
                "checks_only_in_b": [
                    {"id": check_id, "check": labels_b[check_id]}
                    for check_id in sorted(passing_b - passing_a)
                ],
                "files_only_in_a": sorted(files_a - files_b),
                "files_only_in_b": sorted(files_b - files_a),
                "structural_facts": {
                    "a": facts_a,
                    "b": facts_b,
                    "different": {
                        key: {"a": facts_a.get(key), "b": facts_b.get(key)}
                        for key in sorted(set(facts_a) | set(facts_b))
                        if facts_a.get(key) != facts_b.get(key)
                    },
                },
            }
        )
    return {
        "environment_a": report_a["environment"]["name"],
        "environment_b": report_b["environment"]["name"],
        "comparison_sources": {
            "a": (report_a.get("metadata") or {}).get("sources", []),
            "b": (report_b.get("metadata") or {}).get("sources", []),
        },
        "metadata": {
            "generated_at": (report_b.get("metadata") or {}).get("generated_at"),
            "sources": list({
                (source["repository"], source["ref"]): source
                for report in (report_a, report_b)
                for source in (report.get("metadata") or {}).get("sources", [])
            }.values()),
        },
        "scopes": scopes,
    }


def _diff_plain_value(value: Any) -> str:
    """Render structural facts without leaking Python container reprs."""

    if value is None:
        return "not found"
    if isinstance(value, dict):
        return ", ".join(f"{key} {_diff_plain_value(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(_diff_plain_value(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_diff_text(diff: dict[str, Any]) -> str:
    lines = [
        f"{diff['environment_a']} → {diff['environment_b']}",
        *_cache_header_lines(diff),
        "",
    ]
    for scope in diff["scopes"]:
        lines.append(f"SCOPE: {scope['scope']}")
        lines.append(f"  Passing only in {diff['environment_a']}: {', '.join(item['id'] for item in scope['checks_only_in_a']) or 'none'}")
        lines.append(f"  Passing only in {diff['environment_b']}: {', '.join(item['id'] for item in scope['checks_only_in_b']) or 'none'}")
        for side in ("a", "b"):
            lines.append(f"  Files only in {diff['environment_' + side]}:")
            lines.extend(f"    {path}" for path in scope["files_only_in_" + side])
            if not scope["files_only_in_" + side]:
                lines.append("    none")
        for key, values in scope["structural_facts"]["different"].items():
            lines.append(f"  {key}: {_diff_plain_value(values['a'])} → {_diff_plain_value(values['b'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_diff_markdown(diff: dict[str, Any]) -> str:
    lines = [f"# {diff['environment_a']} → {diff['environment_b']}", "", *_cache_header_lines(diff)]
    for side in ("a", "b"):
        sources = diff.get("comparison_sources", {}).get(side, [])
        if sources:
            overrides = [f"`{source['repository']}@{source['ref']}`" for source in sources if source["ref"] != "main"]
            selection = "; ".join(overrides) + "; other repositories on `main`" if overrides else "all repositories on `main`"
            lines.extend([f"**{diff[f'environment_{side}']}:** {selection}.", ""])
    lines.extend([
        "This report compares the configuration recorded in Git repositories for two environments. "
        "It is not a live cluster health check or proof that either cluster is deployed.",
        "",
        "Environment-specific path prefixes are normalized so equivalent files can be compared. "
        "Differences are not automatically defects: hardware, enabled components, and deployment "
        "choices can legitimately vary. A check passing only on one side is a prompt for review; "
        "use the individual status reports for severity, explanations, and next actions.",
        "",
    ])
    if (diff.get("metadata") or {}).get("generated_at"):
        lines.extend([f"Generated {_generated_timestamp(diff)}.", ""])
    for scope in diff["scopes"]:
        lines.extend([f"## {scope['scope']}", ""])
        lines.extend(_markdown_table(
            ["Direction", "Checks passing"],
            [
                [
                    f"Only in {diff['environment_a']}",
                    ", ".join(item.get("check", item["id"]) for item in scope["checks_only_in_a"]) or "—",
                ],
                [
                    f"Only in {diff['environment_b']}",
                    ", ".join(item.get("check", item["id"]) for item in scope["checks_only_in_b"]) or "—",
                ],
            ],
        ))
        for side in ("a", "b"):
            lines.extend([f"**Files only in {diff['environment_' + side]}**", ""])
            lines.extend(f"- `{path}`" for path in scope["files_only_in_" + side])
            if not scope["files_only_in_" + side]:
                lines.append("None.")
            lines.append("")
        facts = scope["structural_facts"]["different"]
        if facts:
            lines.extend(["**Structural facts**", ""])
            lines.extend(_markdown_table(
                ["Fact", diff["environment_a"], diff["environment_b"]],
                [[key, _diff_plain_value(values["a"]), _diff_plain_value(values["b"])] for key, values in facts.items()],
            ))
    source_rows = [
        [diff[f"environment_{side}"], source["repository"], source["ref"],
         MarkdownCell(f"[{source['sha'][:7]}](https://github.com/{source['repository']}/commit/{source['sha']})")]
        for side in ("a", "b")
        for source in diff.get("comparison_sources", {}).get(side, [])
    ]
    if source_rows:
        lines.extend(["## Compared source snapshots", ""])
        lines.extend(_markdown_table(["Environment", "Repository", "Ref", "Commit"], source_rows))
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_environment_list_text(environments: list[dict[str, Any]]) -> str:
    lines = [
        "=" * 78,
        "Defined MOC environment clusters",
        "=" * 78,
    ]
    if not environments:
        lines.append("No hub or workload clusters were found in oac-infra.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            f"{'Environment':<20} {'Cluster':<30} {'Type':<10} Status command",
            "-" * 78,
        ]
    )
    for environment in environments:
        lines.append(
            f"{environment['environment']:<20} "
            f"{environment['cluster']:<30} "
            f"{environment['type']:<10} "
            f"{environment['status_command']}"
        )

    lines.extend(
        [
            "",
            "Use the listed command for a hub- or workload-scoped status report.",
            "",
            "Sources:",
            "  Hub clusters: CCI-MOC/oac-infra/hub-images/inventory.yml",
            "  Workload clusters: CCI-MOC/oac-infra/infra/inventory/00hosts.yaml",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_environment_list_json(environments: list[dict[str, Any]]) -> str:
    return json.dumps(environments, indent=2, sort_keys=True) + "\n"
