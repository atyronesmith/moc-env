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


def _markdown_value(value: Any) -> str:
    if value is None:
        return "None"
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True) + "\n```"


def _state(state: str) -> str:
    return f"{STATE_SYMBOLS.get(state, '•')} {state}"


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
        lines.extend(
            [
                "-" * 78,
                f"[{_state(check['state'])}] {check['stage']} / {check['check']}",
                f"  Why checked:  {check['reason']}",
                f"  Repository:   {check['repository']}",
                f"  Path:         {check['path']} @ {check['ref']}",
                f"  Expected:     {_value(check['expected'])}",
                f"  Present:      {_value(check.get('present'))}",
                f"  Missing:      {_value(check.get('missing'))}",
                f"  Actual:       {_value(check['actual'])}",
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
            "**Expected**",
            "",
            _markdown_value(check["expected"]),
            "",
            "**What is present**",
            "",
            _markdown_value(check.get("present")),
            "",
            "**What is missing**",
            "",
            _markdown_value(check.get("missing")),
            "",
            "**Actual repository state**",
            "",
            _markdown_value(check["actual"]),
            "",
            "<details>",
            "<summary>Evidence</summary>",
            "",
            _markdown_value(check.get("evidence", {})),
            "",
            "</details>",
            "",
        ]
    )
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
            gap = _value(missing_value)
            if check["state"] == "pr_open":
                gap = "Merge or close the relevant open pull request."
            lines.append(
                f"| {priority} | {check['stage']} / {check['check']} | `{gap}` |"
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
            "## Raw report data",
            "",
            "<details>",
            "<summary>Expand the normalized JSON report</summary>",
            "",
            "```json",
            json.dumps(report, indent=2, sort_keys=True),
            "```",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"
