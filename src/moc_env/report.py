"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
from typing import Any

from .github import github_url


STATE_SYMBOLS = {
    "requested": "📝",
    "declared_in_main": "✅",
    "pr_merged": "🔀",
    "pr_open": "🚧",
    "partial": "🟡",
    "missing": "❌",
    "unknown": "❓",
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
    source_url = _github_location(
        check.get("repository"), check.get("path"), check.get("ref")
    )
    rows = [
        [
            _linked_code(path, source_url),
            "Present" if path in found else "Missing",
        ]
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
    ]
    return [
        "**Relevant pull requests**",
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
        _oidc_field_table(check)
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


def render_text(report: dict[str, Any]) -> str:
    environment = report["environment"]
    scope = report.get("scope", "environment")
    workload_clusters = environment.get("workload_clusters", [])
    workload_summary = (
        ", ".join(workload_clusters)
        if workload_clusters
        else environment.get(
            "workload_notice",
            "No workload cluster is declared for this hub.",
        )
    )
    lines = [
        "=" * 78,
        f"{_scope_title(scope)}: {environment['name']}",
        "=" * 78,
        f"Hub cluster:      {environment['infra_cluster']}",
        f"Workload clusters: {workload_summary}",
        f"Domain:           {environment['domain']}",
        f"Overall:          {report['overall_state']}",
        f"Advisory gaps:    {report['summary']['advisory_count']}",
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
                f"[{_state(check['state'])}; {check['severity']}] "
                f"{check['stage']} / {check['check']}",
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
        check_rule = (check.get("evidence") or {}).get("check_rule")
        if check_rule:
            lines.append(f"  Check rule:   {check_rule}")
        lines.append("")

    followups = [
        check
        for check in report["checks"]
        if check["state"] in {"partial", "missing", "pr_open"}
    ]
    lines.extend(["Suggested next actions:", ""])
    if not followups:
        lines.append("No configuration gaps were detected by the current repository-state checks.")
    else:
        lines.append("These actions are derived directly from the missing or partial checks above.")
        lines.append("")
        for priority, check in enumerate(followups, start=1):
            lines.extend(
                [
                    f"{priority}. [{_state(check['state'])}] "
                    f"{check['stage']} / {check['check']}",
                    f"   Gap: {_followup_gap(check)}",
                    f"   Next: {check['next_action']}",
                ]
            )

    lines.extend(
        [
            "=" * 78,
            "Scope: repository configuration state only; this report does not",
            "claim live OpenShift or Argo CD health.",
            "=" * 78,
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


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


def _check_markdown(check: dict[str, Any], number: int) -> list[str]:
    evidence = check.get("evidence") or {}
    check_rule = evidence.get("check_rule")
    lines = [
        f"#### {_state(check['state'])} · `{check['severity']}` — "
        f"{number}. {check['check']}",
        "",
        f"**Why this was checked:** {check['reason']}",
        "",
        *([f"**Status rule:** {check_rule}", ""] if check_rule else []),
        "| Source | Value |",
        "|---|---|",
        f"| Repository | `{check['repository']}` |",
        f"| Path | `{check['path']}` |",
        f"| Ref | `{check['ref']}` |",
    ]
    if check.get("url"):
        lines.append(f"| Link | [Open source]({check['url']}) |")

    oidc_table = _oidc_markdown_table(check)
    field_table = _field_table(check, evidence)
    if oidc_table:
        lines.append("")
        lines.extend(oidc_table)
    elif field_table:
        lines.append("")
        lines.extend(field_table)
    else:
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
    lines.extend(_host_table(check, evidence))
    lines.extend(_path_table(check, evidence))
    if not field_table and not oidc_table:
        lines.extend(_field_table(check, evidence))
    lines.extend(_source_value_table(check, evidence))
    lines.extend(_pull_request_table(evidence))
    return lines


def _identity_link(value: Any, url: str | None) -> str:
    rendered = f"`{value}`"
    return f"[{rendered}]({url})" if url else rendered


def _identity_source_url(report: dict[str, Any], check_name: str) -> str | None:
    for check in report.get("checks", []):
        if check.get("check") == check_name:
            return check.get("url")
    return None


def _deployment_context_diagram(scope: str) -> list[str]:
    if scope == "hub":
        sequence = """\
sequenceDiagram
    autonumber
    participant Request as MOC issue
    participant Infra as oac-infra inventory and hub-image variables
    participant Identity as moc-keycloak OIDC client
    participant HubGitOps as oac-apps hub GitOps
    participant Hub as Hub cluster
    Request->>Infra: Record requested hardware, network, and build inputs
    Infra->>Hub: Build and start the hub cluster
    Identity->>Hub: Register the hub OIDC client
    HubGitOps->>Hub: Apply hub local-cluster components and applications\
"""
    elif scope == "workload":
        sequence = """\
sequenceDiagram
    autonumber
    participant Hub as Parent hub cluster
    participant Inventory as oac-infra workload inventory
    participant Hosted as Hosted-cluster values
    participant Components as Workload component values
    participant Apps as Workload Argo CD applications
    participant Workload as Workload cluster
    Hub->>Inventory: Provide parent hub and network context
    Inventory->>Hosted: Define workload hosts and boot image
    Hosted->>Workload: Create the hosted control plane
    Components->>Workload: Configure shared workload components
    Apps->>Workload: Apply workload applications\
"""
    else:
        sequence = """\
sequenceDiagram
    autonumber
    participant Request as MOC issue
    participant Infra as oac-infra inventory and variables
    participant Identity as moc-keycloak OIDC client
    participant HubGitOps as oac-apps hub GitOps
    participant Hub as Hub cluster
    participant WorkloadGitOps as oac-apps workload GitOps
    participant Workload as Workload cluster
    Request->>Infra: Record requested hardware, network, and build inputs
    Infra->>Hub: Build and start the hub cluster
    Identity->>Hub: Register the hub OIDC client
    HubGitOps->>Hub: Apply hub local-cluster components and applications
    Hub->>WorkloadGitOps: Provide parent hub context
    WorkloadGitOps->>Workload: Define and configure the hosted workload\
"""
    return [
        "## Deployment context",
        "",
        "This compact sequence shows where the checked repository evidence fits. "
        "It does not claim that these deployment steps have run.",
        "",
        "```mermaid",
        sequence,
        "```",
        "",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    environment = report["environment"]
    state_counts = report["summary"]["state_counts"]
    scope = report.get("scope", "environment")
    environment_name = environment["name"]
    infra_cluster = environment["infra_cluster"]
    workload_clusters = environment.get("workload_clusters", [])
    issue_url = _identity_source_url(report, "MOC issue") or (
        f"https://github.com/CCI-MOC/MOC-issues/issues/{environment['issue_number']}"
        if environment["issue_number"] is not None
        else None
    )
    inventory_url = github_url(
        "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml"
    )
    hub_url = _identity_source_url(
        report, f"{infra_cluster} host inventory"
    ) or inventory_url
    domain_url = _identity_source_url(report, "Hub image variables") or github_url(
        "CCI-MOC/oac-infra",
        f"hub-images/group_vars/{infra_cluster}/vars.yml",
    )
    lines = [
        f"# {_scope_title(scope)}",
        "",
        f"## `{environment['name']}` — {report['overall_state']}",
        "",
        "This report describes **repository configuration state only**. It does not claim that OpenShift, Argo CD, or any shared service is live or healthy.",
        "",
        "## Environment identity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Scope | `{scope}` |",
        f"| Environment | {_identity_link(environment_name, issue_url)} |",
        f"| MOC issue | {_identity_link(environment['issue_number'], issue_url)} |",
        f"| Hub cluster | {_identity_link(infra_cluster, hub_url)} |",
    ]
    for workload_cluster in workload_clusters:
        workload_url = _identity_source_url(
            report, f"{workload_cluster} host inventory"
        ) or inventory_url
        lines.append(
            f"| Workload cluster | {_identity_link(workload_cluster, workload_url)} |"
        )
    if not workload_clusters:
        notice = environment.get(
            "workload_notice",
            "No workload cluster is declared for this hub.",
        )
        lines.append(
            f"| Workload clusters | {notice} |"
        )
    lines.extend([
        f"| Domain | {_identity_link(environment['domain'], domain_url)} |",
        f"| Overall state | **{report['overall_state']}** |",
        f"| Advisory gaps | {report['summary']['advisory_count']} |",
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
        *_deployment_context_diagram(scope),
        "## Stage summary",
        "",
        "| Stage | Checks | States |",
        "|---|---:|---|",
    ])

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
                "| Priority | Stage / check | Gap to resolve | Suggested action |",
                "|---:|---|---|---|",
            ]
        )
        for priority, (check, missing_value) in enumerate(followups, start=1):
            gap = _markdown_inline(missing_value)
            if check["state"] == "pr_open":
                gap = "Merge or close the relevant open pull request."
            lines.append(
                f"| {priority} | {check['stage']} / {check['check']} | {gap} "
                f"| {_markdown_inline(check['next_action'])} |"
            )

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
