"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
from typing import Any


STATE_SYMBOLS = {
    "requested": "📝",
    "declared_in_main": "✅",
    "pr_merged": "🔀",
    "pr_open": "🚧",
    "partial": "🟡",
    "missing": "❌",
    "unknown": "❓",
}


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
        return f"`{_markdown_escape_cell(value)}`" if value else "—"
    return f"`{value}`"


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


def _host_table(evidence: dict[str, Any]) -> list[str]:
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
        [path, "Present" if path in found else "Missing"]
        for path in expected_paths
    ]
    return [
        "**Expected paths**",
        "",
        *_markdown_table(["Path", "Status"], rows),
    ]


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
            values.get(field),
            "Present" if values.get(field) not in (None, False) else "Missing",
        ]
        for field in expected_fields
    ]
    return [
        "**Expected fields**",
        "",
        *_markdown_table(["Field", "Observed value", "Status"], rows),
    ]


def _source_value_table(evidence: dict[str, Any]) -> list[str]:
    client = evidence.get("client")
    if not isinstance(client, dict):
        return []
    rows: list[list[Any]] = []
    for field, source_value in client.items():
        if not isinstance(source_value, dict):
            continue
        provenance = source_value.get("provenance", {})
        rows.append(
            [
                field,
                source_value.get("value"),
                source_value.get("confidence"),
                (
                    f"{provenance.get('repository', '—')} / "
                    f"{provenance.get('path', '—')} @ {provenance.get('ref', '—')}"
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
    rows = [
        [
            pull.get("number"),
            pull.get("title"),
            pull.get("state"),
            pull.get("merged"),
            pull.get("head_ref"),
            pull.get("changed_files"),
        ]
        for pull in pull_requests
    ]
    return [
        "**Relevant pull requests**",
        "",
        *_markdown_table(
            ["PR", "Title", "State", "Merged", "Head branch", "Changed files"],
            rows,
        ),
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
    required = {"matching_pr_count", "open_count", "merged_count"}
    if not isinstance(actual, dict) or not required.issubset(actual):
        return None

    counts = [
        ("Matching PRs", actual["matching_pr_count"]),
        ("Merged PRs", actual["merged_count"]),
        ("Open PRs", actual["open_count"]),
    ]
    label_width = max(len(label) for label, _ in counts) + 2
    value_width = max(len(str(value)) for _, value in counts) + 2
    lines = ["  Pull request counts:"]
    lines.extend(
        f"    {label:<{label_width}} {str(value):>{value_width}}"
        for label, value in counts
    )
    return lines


def _structured_summary(check: dict[str, Any]) -> list[str] | None:
    """Route a check to the most specific compact text renderer."""
    return (
        _path_checklist(check)
        or _field_value_checklist(check)
        or _path_scope_summary(check)
        or _pull_request_count_summary(check)
        or _mapping_summary(check)
    )


def render_text(report: dict[str, Any]) -> str:
    environment = report["environment"]
    lines = [
        "=" * 78,
        f"MOC environment status: {environment['name']}",
        "=" * 78,
        f"Infra cluster:    {environment['infra_cluster']}",
        f"Workload cluster: {environment['workload_cluster']}",
        f"Domain:           {environment['domain']}",
        f"Overall:          {report['overall_state']}",
        "",
        "State summary:",
    ]
    for state, count in report["summary"]["state_counts"].items():
        lines.append(f"  {_state(state)}  {count}")

    lines.extend(["", "Stage summary:"])
    for stage in report["summary"]["stages"]:
        states = ", ".join(
            f"{state}={count}"
            for state, count in stage["state_counts"].items()
        )
        lines.append(f"  {stage['stage']} ({stage['check_count']} checks): {states}")

    lines.extend(["", "Detailed checks:"])
    for check in report["checks"]:
        summary_lines = _structured_summary(check)
        lines.extend(
            [
                "-" * 78,
                f"[{_state(check['state'])}] {check['stage']} / {check['check']}",
                f"  Why checked:  {check['reason']}",
                f"  Repository:   {check['repository']}",
                f"  Path:         {check['path']} @ {check['ref']}",
            ]
        )
        if summary_lines is not None:
            lines.extend(summary_lines)
        else:
            lines.extend(
                [
                    f"  Expected:     {_text_value(check['expected'], 16)}",
                    f"  Present:      {_text_value(check.get('present'), 16)}",
                    f"  Missing:      {_text_value(check.get('missing'), 16)}",
                    f"  Actual:       {_text_value(check['actual'], 16)}",
                ]
            )
        if check.get("url"):
            lines.append(f"  URL:          {check['url']}")
        lines.append("")

    lines.extend(
        [
            "=" * 78,
            "Scope: repository configuration state only; this report does not",
            "claim live OpenShift or Argo CD health.",
            "=" * 78,
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _check_markdown(check: dict[str, Any], number: int) -> list[str]:
    evidence = check.get("evidence") or {}
    lines = [
        f"#### {_state(check['state'])} — {number}. {check['check']}",
        "",
        f"**Why this was checked:** {check['reason']}",
        "",
        "| Source | Value |",
        "|---|---|",
        f"| Repository | `{check['repository']}` |",
        f"| Path | `{check['path']}` |",
        f"| Ref | `{check['ref']}` |",
    ]
    if check.get("url"):
        lines.append(f"| Link | [Open source]({check['url']}) |")

    lines.extend(
        [
            "",
            "**Result**",
            "",
        ]
    )
    result_rows = [
        ["Expected", check.get("expected")],
        ["Present", check.get("present")],
    ]
    if check.get("missing") is not None:
        result_rows.append(["Missing", check.get("missing")])
    result_rows.append(["Actual", check.get("actual")])
    lines.extend(
        _markdown_table(["Aspect", "Value"], result_rows, plain_first_column=True)
    )
    lines.extend(_host_table(evidence))
    lines.extend(_path_table(check, evidence))
    lines.extend(_field_table(check, evidence))
    lines.extend(_source_value_table(evidence))
    lines.extend(_pull_request_table(evidence))
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    environment = report["environment"]
    state_counts = report["summary"]["state_counts"]
    lines = [
        "# 🛰️ MOC Environment Configuration Status",
        "",
        f"## `{environment['name']}` — {report['overall_state']}",
        "",
        "This report describes **repository configuration state only**. It does not claim that OpenShift, Argo CD, or any shared service is live or healthy.",
        "",
        "## Environment identity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Environment | `{environment['name']}` |",
        f"| MOC issue | `{environment['issue_number']}` |",
        f"| Infra cluster | `{environment['infra_cluster']}` |",
        f"| Workload cluster | `{environment['workload_cluster']}` |",
        f"| Domain | `{environment['domain']}` |",
        f"| Overall state | **{report['overall_state']}** |",
        "",
        "## Executive summary",
        "",
        "| State | Meaning | Count |",
        "|---|---|---:|",
        f"| ✅ `declared_in_main` | Present in a merged `main` branch | {state_counts.get('declared_in_main', 0)} |",
        f"| 🟡 `partial` | Some information exists, but required details are missing | {state_counts.get('partial', 0)} |",
        f"| ❌ `missing` | No relevant configuration was found | {state_counts.get('missing', 0)} |",
        f"| 🚧 `pr_open` | Relevant configuration exists only in an open PR | {state_counts.get('pr_open', 0)} |",
        f"| 🔀 `pr_merged` | A relevant PR has been merged | {state_counts.get('pr_merged', 0)} |",
        f"| 📝 `requested` | The MOC issue is open and records the request | {state_counts.get('requested', 0)} |",
        "",
        f"**Total checks:** {report['summary']['check_count']}",
        "",
        "## Stage summary",
        "",
        "| Stage | Checks | States |",
        "|---|---:|---|",
    ]

    for stage in report["summary"]["stages"]:
        states = ", ".join(
            f"{STATE_SYMBOLS.get(state, '•')} `{state}` × {count}"
            for state, count in stage["state_counts"].items()
        )
        lines.append(f"| {stage['stage']} | {stage['check_count']} | {states} |")

    current_stage = None
    check_number = 0
    lines.extend(["", "## Detailed findings by stage", ""])
    for check in report["checks"]:
        if check["stage"] != current_stage:
            current_stage = check["stage"]
            lines.extend([f"### {current_stage}", ""])
        check_number += 1
        lines.extend(_check_markdown(check, check_number))

    followups = []
    for check in report["checks"]:
        if check["state"] in {"partial", "missing", "pr_open"}:
            followups.append((check, check.get("missing")))

    lines.extend(["## Suggested next actions", ""])
    if not followups:
        lines.append("No configuration gaps were detected by the current repository-state checks.")
    else:
        lines.extend(
            [
                "These actions are derived directly from the missing or partial checks above.",
                "",
                "| Priority | Stage / check | Gap to resolve |",
                "|---:|---|---|",
            ]
        )
        for priority, (check, missing_value) in enumerate(followups, start=1):
            gap = _markdown_inline(missing_value)
            if check["state"] == "pr_open":
                gap = "Merge or close the relevant open pull request."
            lines.append(f"| {priority} | {check['stage']} / {check['check']} | {gap} |")

    lines.extend(
        [
            "",
            "## Interpretation rules",
            "",
            "- `declared_in_main` means desired-state text is present in a merged repository branch.",
            "- `partial` means some configuration exists, but one or more required values or files are absent.",
            "- `missing` means the expected repository path or declaration was not found.",
            "- `pr_open` means configuration exists only in an open pull request and is not yet merged desired state.",
            "- This report does **not** prove live cluster synchronization, node readiness, or application health.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_environment_list_text(environments: list[dict[str, Any]]) -> str:
    lines = [
        "=" * 78,
        "Defined MOC environments",
        "=" * 78,
    ]
    if not environments:
        lines.append("No infra-cluster environments were found in oac-infra.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            f"{'Environment':<20} {'Infra cluster':<24} Workload clusters",
            "-" * 78,
        ]
    )
    for environment in environments:
        workloads = ", ".join(environment["workload_clusters"]) or "-"
        lines.append(
            f"{environment['name']:<20} "
            f"{environment['infra_cluster']:<24} {workloads}"
        )

    lines.extend(
        [
            "",
            "Get a status report with:",
            "",
        ]
    )
    for environment in environments:
        lines.append(f"  {environment['status_command']}")
    lines.extend(["", "Source: CCI-MOC/oac-infra/hub-images/inventory.yml"])
    return "\n".join(lines).rstrip() + "\n"


def render_environment_list_json(environments: list[dict[str, Any]]) -> str:
    return json.dumps(environments, indent=2, sort_keys=True) + "\n"
