"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from .github import github_url


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
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _markdown_inline(value: Any) -> str:
    """Render a compact, human-readable Markdown table cell."""

    if value is None:
        return "—"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
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
    source_url = _github_location(
        check.get("repository"), check.get("path"), check.get("ref")
    )
    rows = [
        [
            _linked_code(host.get("name"), source_url),
            _linked_code(host.get("node_name"), source_url),
            _linked_code(host.get("bmc_addr"), source_url),
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
            "Present" if path in found else "Missing",
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


def _pull_request_table(evidence: dict[str, Any]) -> list[str]:
    pull_requests = evidence.get("pull_requests")
    if not isinstance(pull_requests, list) or not pull_requests:
        return []

    def repository(pull: dict[str, Any]) -> str:
        value = pull.get("repository")
        if isinstance(value, dict):
            return str(value.get("value"))
        return str(value or "unknown")

    lines: list[str] = []
    for pull_repository in sorted({repository(pull) for pull in pull_requests}):
        rows = [
            [
                pull.get("number"),
                pull.get("title"),
                pull.get("state"),
                pull.get("merged"),
                pull.get("classification"),
                pull.get("head_ref"),
                pull.get("html_url"),
                pull.get("changed_files"),
            ]
            for pull in pull_requests
            if repository(pull) == pull_repository
        ]
        lines.extend(
            [
                f"**Relevant pull requests — {pull_repository}**",
                "",
                *_markdown_table(
                    [
                        "PR",
                        "Title",
                        "State",
                        "Merged",
                        "Classification",
                        "Head branch",
                        "Link",
                        "Changed files",
                    ],
                    rows,
                ),
            ]
        )
    return lines


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
            rendered_value = str(value)
        elif isinstance(value, (dict, list)):
            rendered_value = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            rendered_value = str(value)
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
    expected_width = max(len(str(expected)) for _, expected, _ in rows) + 2
    observed_width = max(len(str(observed)) for _, _, observed in rows) + 2
    lines = [
        "  Keycloak OIDC fields:",
        "  Field:".ljust(field_width)
        + "Expected:".ljust(expected_width)
        + "Observed:",
    ]
    for field, expected, observed in rows:
        lines.append(
            f"  {field:<{field_width - 2}}  "
            f"{str(expected):<{expected_width - 2}}  "
            f"{str(observed)}"
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


def _phase_rows(report: dict[str, Any], scope: str) -> list[tuple[int, str]]:
    phases = report.get("phases", {})
    if scope == "environment":
        hub_definitions = phases.get("hub", []) if isinstance(phases, dict) else []
        workload_definitions = phases.get("workload", []) if isinstance(phases, dict) else []
    else:
        hub_definitions = phases if isinstance(phases, list) else []
        workload_definitions = []
    by_phase: dict[int, str] = {}
    for phase in hub_definitions:
        by_phase[phase["phase"]] = phase["title"]
    for phase in workload_definitions:
        number = phase["phase"]
        if number not in by_phase:
            by_phase[number] = phase["title"]
        elif by_phase[number] != phase["title"]:
            by_phase[number] = f"{by_phase[number]} / {phase['title']}"
    return sorted(by_phase.items())


def _phase_cell(checks: list[dict[str, Any]], ascii_mode: bool) -> str:
    if not checks:
        return "[--]" if ascii_mode else "–"
    if any(check["state"] == "unknown" for check in checks):
        symbol = "[??]" if ascii_mode else "⚪"
        return f"{symbol} unknown"
    passing = all(check["state"] in {"declared_in_main", "requested", "pr_merged"} for check in checks)
    if passing:
        if any(check["id"].endswith(".inventory") for check in checks):
            hosts = sum(len((check.get("evidence") or {}).get("hosts") or []) for check in checks)
            detail = f"{hosts} hosts"
        elif any(isinstance(check.get("expected"), list) for check in checks):
            expected = sum(len(check["expected"]) for check in checks if isinstance(check.get("expected"), list))
            observed = sum(
                len(check.get("actual") or [])
                for check in checks
                if isinstance(check.get("expected"), list) and isinstance(check.get("actual"), list)
            )
            detail = f"{observed}/{expected} variables"
        elif any((check.get("evidence") or {}).get("expected_path_count") for check in checks):
            expected = sum((check.get("evidence") or {}).get("expected_path_count", 0) for check in checks)
            found = sum((check.get("evidence") or {}).get("path_count", 0) for check in checks)
            detail = f"{found}/{expected} files"
        else:
            detail = f"{len(checks)}/{len(checks)} checks"
        return f"{'[ok]' if ascii_mode else '✅'} {detail}"

    if any(check["state"] == "missing" for check in checks):
        return f"{'[fail]' if ascii_mode else '❌'} none"
    if any(check["state"] == "partial" for check in checks):
        return f"{'[warn]' if ascii_mode else '🟡'} partial"
    if any(check["state"] in {"value_mismatch", "pr_open"} for check in checks):
        return f"{'[warn]' if ascii_mode else '🟡'} " + (
            "open PR" if any(check["state"] == "pr_open" for check in checks) else "mismatch"
        )
    return f"{'[warn]' if ascii_mode else '🟡'} gap"


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
    if not isinstance(pulls, list):
        return None
    fixes = []
    for pull in pulls:
        if not isinstance(pull, dict) or pull.get("classification", {}).get("value") != "open":
            continue
        repository_value = pull.get("repository", "")
        repository = (
            repository_value.get("value", "")
            if isinstance(repository_value, dict)
            else repository_value
        )
        if repository != check.get("repository"):
            continue
        changed = pull.get("changed_files", [])
        if any(
            path == check.get("path") or path.startswith(f"{check.get('path')}/")
            for path in changed
        ):
            number = pull.get("number")
            short_repo = repository.removeprefix("CCI-MOC/")
            fixes.append(f"{short_repo}#{number}")
    if fixes:
        return "fix in open PR " + ", ".join(sorted(fixes))
    return None


def _status_command(report: dict[str, Any], suffix: str) -> str:
    name = report["environment"]["name"]
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


def _detail_section(check: dict[str, Any], ascii_mode: bool) -> list[str]:
    expected = check.get("expected")
    observed = check.get("actual")
    if isinstance(expected, dict) and isinstance(observed, dict):
        keys = list(dict.fromkeys((*expected, *observed)))
        rows = [(key, expected.get(key), observed.get(key)) for key in keys]
    elif isinstance(expected, list) and isinstance(observed, list):
        rows = [
            (f"[{index}]", value, observed[index] if index < len(observed) else None)
            for index, value in enumerate(expected)
        ]
    else:
        rows = [("value", expected, observed)]
    width = max([len("Expected")] + [len(name) for name, _, _ in rows]) + 2
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
            f"{_symbol(check['state'], ascii_mode)} "
            f"{check.get('phase_title', 'Check')} / {check['check']}",
            2,
        ),
        *_wrap(f"Finding: {check['reason']}", 2),
        *_wrap(
            f"Source: {check['repository']} · {check['path']} @ {short_sha}",
            2,
        ),
        f"  {'Field':<{width}} Expected                       Observed",
    ]
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
        lines.extend(
            _wrap(
                f"{name:<{width}} {_plain_value(expected_value):<30} {_plain_value(observed_value)}",
                2,
            )
        )
    url = _detail_url(check)
    if url:
        lines.extend(_wrap(f"URL: {url}", 2))
    return lines


def render_text(
    report: dict[str, Any],
    details: bool = False,
    ascii_mode: bool = False,
) -> str:
    environment = report["environment"]
    scope = report.get("scope", "environment")
    dash = "[--]" if ascii_mode else "–"
    generated = (report.get("metadata") or {}).get("generated_at", "")
    generated_text = generated.replace("T", " ").replace("Z", " UTC")
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
    lines = [first, *_wrap(_source_line(report)), ""]

    checks = report["checks"]
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    passing = sum(check["state"] in pass_states for check in checks)
    blocking = [
        check for check in checks
        if check["severity"] == "blocking"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    advisories = [
        check for check in checks
        if check["severity"] == "advisory"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    unknown = [check for check in checks if check["state"] == "unknown"]
    scope_blocking = {
        cluster: sum(check["scope"] == "workload" for check in blocking)
        for cluster in environment.get("workload_clusters", [])
    }
    scope_text = (
        f" (workload {sum(scope_blocking.values())})"
        if scope_blocking and scope == "environment"
        else ""
    )
    result = (
        f"RESULT: {len(blocking)} blocking gaps{scope_text} · "
        f"{len(advisories)} advisories · {passing} of {len(checks)} checks pass"
    )
    lines.extend(_wrap(result))
    if unknown:
        reasons = "; ".join(f"{check['check']}: {check['reason']}" for check in unknown)
        lines.append(f"UNKNOWN: {textwrap.shorten(reasons, width=92, placeholder='…')}")
    lines.append("")

    columns: list[tuple[str, list[dict[str, Any]]]] = []
    if scope in {"environment", "hub"}:
        columns.append((f"HUB {environment['infra_cluster']}", [c for c in checks if c["scope"] == "hub"]))
    if scope in {"environment", "workload"}:
        for workload in environment.get("workload_clusters", []):
            columns.append((f"WORKLOAD {workload}", [c for c in checks if c["scope"] == "workload"]))
    phase_rows = _phase_rows(report, scope)
    labels = [f"{phase} {title}" for phase, title in phase_rows]
    phase_width = min(max([len("PHASE")] + [len(label) for label in labels]) + 2, 29)
    cell_width = min(max([len(header) for header, _ in columns] + [14]) + 2, 32)
    lines.append(f"{'PHASE':<{phase_width}}" + "".join(f"{header:<{cell_width}}" for header, _ in columns))
    for phase, title in phase_rows:
        label = f"{phase} {title}"
        label = textwrap.shorten(label, width=phase_width, placeholder="…")
        cells = []
        for _header, scope_checks in columns:
            phase_checks = [check for check in scope_checks if check.get("phase") == phase]
            cell = _phase_cell(phase_checks, ascii_mode)
            cells.append(textwrap.shorten(cell, width=cell_width, placeholder="…"))
        lines.append(f"{label:<{phase_width}}" + "".join(f"{cell:<{cell_width}}" for cell in cells))
    lines.append("")

    lines.append("NEXT")
    gaps = [*blocking, *advisories]
    gaps.sort(key=lambda check: (check["severity"] != "blocking", check.get("phase", 0)))
    if not gaps:
        lines.append("Nothing to do in the repositories this tool reads.")
    else:
        open_pulls = [
            pull
            for check in checks
            for pull in (check.get("evidence") or {}).get("pull_requests", [])
            if isinstance(pull, dict)
            and pull.get("classification", {}).get("value") == "open"
        ]
        action_numbers: dict[str, int] = {}
        for number, check in enumerate(gaps, start=1):
            action_numbers.setdefault(check["id"], number)
        for number, check in enumerate(gaps, start=1):
            action = check.get("next_action") or f"Resolve {check['check']}."
            repository = check["repository"].removeprefix("CCI-MOC/")
            after = [str(action_numbers[item]) for item in check.get("blocked_by", []) if item in action_numbers]
            suffix = f" (after {', '.join(after)})" if after else ""
            pr_fix = _open_pr_fix(check, open_pulls)
            if pr_fix:
                suffix += f" · {pr_fix}"
            lines.extend(_wrap(f"{number}. [{repository}] {action}{suffix}", 2))
            guide = _guide(report, check["scope"], check.get("phase", 0))
            if guide:
                lines.extend(_wrap(f"guide: {guide}", 7))

    lines.extend(["", "NOT CHECKED — verify by hand:"])
    titles = [entry["title"] for entry in report.get("not_checked", [])]
    if titles:
        lines.extend(_wrap("; ".join(titles), 2))
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            *_wrap(f"Details:  {_status_command(report, '--details')}"),
            *_wrap(f"Markdown: {_status_command(report, '--format markdown --output report.md')}"),
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


def _markdown_human_value(value: Any) -> str:
    if value is None:
        return "—"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
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
    expected = check.get("expected")
    actual = check.get("actual")

    expected_paths = evidence.get("expected_paths")
    if isinstance(expected_paths, list):
        found_paths = set(evidence.get("paths") or [])
        return [
            [
                _linked_code(path, _path_url(check, path, report)),
                "present",
                "present" if path in found_paths else "missing",
            ]
            for path in expected_paths
        ]

    if check.get("id") == "hub.oidc_client" and isinstance(
        evidence.get("fields"), dict
    ):
        return [
            [field, result.get("expected"), result.get("observed")]
            for field, result in evidence["fields"].items()
            if isinstance(result, dict)
        ]

    values = evidence.get("values")
    if isinstance(expected, list) and isinstance(values, dict):
        return [
            [field, "present", values.get(field)] for field in expected
        ]

    if isinstance(expected, dict):
        keys = expected if isinstance(actual, dict) else list(expected)
        return [
            [
                key,
                expected.get(key),
                actual.get(key) if isinstance(actual, dict) else actual,
            ]
            for key in keys
        ]
    if isinstance(expected, list) and isinstance(actual, list):
        return [
            [f"item {index}", value, actual[index] if index < len(actual) else None]
            for index, value in enumerate(expected)
        ]
    if isinstance(actual, dict):
        return [[key, "—", value] for key, value in actual.items()]
    return [["value", expected, actual]]


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
            _expand_field_row(f"item {index}", item, observed_value, expanded)
        return
    if isinstance(observed, dict):
        for key, value in observed.items():
            _expand_field_row(str(key), expected, value, expanded)
        return
    if isinstance(observed, list) and any(isinstance(item, dict) for item in observed):
        for index, item in enumerate(observed):
            _expand_field_row(f"item {index}", expected, item, expanded)
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
        f"<summary>{_state(check['state'])} · {check['severity']} — {check['check']}</summary>",
        "",
        f"Finding: {check['reason']}",
        "",
        f"Source: {check['repository']} · {path_text} @ {short_sha}",
        "",
    ]
    if check_rule:
        lines.extend([f"Status rule: {check_rule}", ""])
    rows = [
        [
            field if isinstance(field, MarkdownCell) else _markdown_human_value(field),
            _markdown_human_value(expected),
            _markdown_human_value(observed),
        ]
        for field, expected, observed in _expanded_field_rows(
            _detail_field_rows(check, report)
        )
    ]
    lines.extend(_markdown_table(["Field", "Expected", "Observed"], rows))
    lines.extend(_host_table(check, evidence))
    lines.extend(_agent_label_markdown_table(check))
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
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    blocking = [
        check
        for check in checks
        if check["severity"] == "blocking"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    advisories = [
        check
        for check in checks
        if check["severity"] == "advisory"
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    unknown = [check for check in checks if check["state"] == "unknown"]
    passing = sum(check["state"] in pass_states for check in checks)
    verdict = (
        f"{len(blocking)} blocking gaps, {len(advisories)} advisories, "
        f"and {passing} of {len(checks)} checks pass"
    )
    if unknown:
        reasons = "; ".join(f"{check['check']}: {check['reason']}" for check in unknown)
        verdict += f"; unknown: {textwrap.shorten(reasons, width=180, placeholder='…')}"
    return verdict


def _markdown_metadata(report: dict[str, Any]) -> str:
    metadata = report.get("metadata") or {}
    generated = metadata.get("generated_at", "unknown").replace("T", " ").replace("Z", " UTC")
    parts = [f"Generated {generated}"]
    sources = []
    non_main = False
    for source in metadata.get("sources", []):
        short_sha = source.get("sha", "")[:7] or "—"
        label = f"{source.get('repository', 'unknown')}@{short_sha}"
        if source.get("ref") != "main":
            label = f"{label}@{source.get('ref')}"
            non_main = True
        url = f"https://github.com/{source.get('repository')}/commit/{source.get('sha')}"
        sources.append(f"[{label}]({url})" if source.get("sha") else label)
    if sources:
        parts.append("Sources: " + " · ".join(sources))
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
    prefix = "**This is not a report on main.** " if non_main else ""
    return prefix + " · ".join(parts)


def _markdown_phase_table(report: dict[str, Any]) -> list[str]:
    environment = report["environment"]
    checks = report["checks"]
    scope = report.get("scope", "environment")
    columns: list[tuple[str, list[dict[str, Any]]]] = []
    if scope in {"environment", "hub"}:
        columns.append(
            (f"HUB {environment['infra_cluster']}", [c for c in checks if c["scope"] == "hub"])
        )
    if scope in {"environment", "workload"}:
        for workload in environment.get("workload_clusters", []):
            columns.append(
                (f"WORKLOAD {workload}", [c for c in checks if c["scope"] == "workload"])
            )
    lines = ["| Phase | " + " | ".join(header for header, _ in columns) + " |"]
    lines.append("|---|" + "|".join("---:" for _ in columns) + "|")
    for phase, title in _phase_rows(report, scope):
        cells = []
        for _header, scope_checks in columns:
            phase_checks = [
                check for check in scope_checks if check.get("phase") == phase
            ]
            cells.append(_phase_cell(phase_checks, False))
        lines.append(f"| {phase} {title} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _markdown_next_actions(report: dict[str, Any]) -> list[str]:
    checks = report["checks"]
    pass_states = {"declared_in_main", "requested", "pr_merged"}
    gaps = [
        check
        for check in checks
        if check["severity"] in {"blocking", "advisory"}
        and check["state"] not in pass_states
        and check["state"] != "unknown"
    ]
    gaps.sort(key=lambda check: (check["severity"] != "blocking", check.get("phase", 0)))
    lines = ["## Next actions", ""]
    if not gaps:
        lines.extend(["Nothing to do in the repositories this tool reads.", ""])
        return lines
    open_pulls = [
        pull
        for check in checks
        for pull in (check.get("evidence") or {}).get("pull_requests", [])
        if isinstance(pull, dict)
        and pull.get("classification", {}).get("value") == "open"
    ]
    action_numbers: dict[str, int] = {}
    for number, check in enumerate(gaps, start=1):
        action_numbers.setdefault(check["id"], number)
    for number, check in enumerate(gaps, start=1):
        action = check.get("next_action") or f"Resolve {check['check']}."
        action = action.replace("<", "&lt;").replace(">", "&gt;")
        repository = check["repository"].removeprefix("CCI-MOC/")
        path_url = _markdown_check_url(report, check)
        path_label = _markdown_inline(check.get("path"))
        path = f"[{path_label}]({path_url})" if path_url else path_label
        after = [
            str(action_numbers[item])
            for item in check.get("blocked_by", [])
            if item in action_numbers
        ]
        suffix = f" (after {', '.join(after)})" if after else ""
        pr_fix = _open_pr_fix(check, open_pulls)
        if pr_fix:
            suffix += f" · {pr_fix}"
        lines.append(f"{number}. **{repository}** — {path}: {action}{suffix}")
        guide = _guide(report, check["scope"], check.get("phase", 0))
        if guide:
            document, heading = guide.split(" → ", 1)
            lines.append(f"   Guide: [{document} → {heading}]({document})")
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
        lines.append(
            f"- [ ] **{entry['title']}** (phase {entry['phase']}) — {entry['why']} "
            f"Documented at [{where['document']} → {where['heading']}]({where['document']})."
        )
    lines.append("")
    return lines


def _pull_field(pull: dict[str, Any], field: str) -> Any:
    value = pull.get(field)
    return value.get("value") if isinstance(value, dict) else value


def _markdown_pull_requests(report: dict[str, Any]) -> list[str]:
    pulls = {
        (
            _pull_field(pull, "repository"),
            _pull_field(pull, "number"),
        ): pull
        for check in report.get("checks", [])
        for pull in (check.get("evidence") or {}).get("pull_requests", [])
        if isinstance(pull, dict)
    }
    lines = ["## Pull requests", ""]
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
                    f"[#{number}]({url})",
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
    lines.extend(_markdown_manual_checks(report))
    lines.extend(["## Details", ""])
    sources = (report.get("metadata") or {}).get("sources", [])
    for check in report.get("checks", []):
        lines.extend(_check_markdown_details(check, sources, report))
    lines.extend(_markdown_pull_requests(report))
    lines.extend(_markdown_legend(report))
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
