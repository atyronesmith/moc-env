"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
from typing import Any


def _value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def render_text(report: dict[str, Any]) -> str:
    environment = report["environment"]
    lines = [
        f"Environment: {environment['name']}",
        f"Infra cluster: {environment['infra_cluster']}",
        f"Workload cluster: {environment['workload_cluster']}",
        f"Domain: {environment['domain']}",
        f"Overall: {report['overall_state']}",
        "",
        "State summary:",
    ]
    for state, count in report["summary"]["state_counts"].items():
        lines.append(f"  {state}: {count}")

    lines.extend(["", "Checks:"])
    for check in report["checks"]:
        lines.append(f"[{check['state']}] {check['stage']} / {check['check']}")
        lines.append(f"  Repository: {check['repository']}")
        lines.append(f"  Path: {check['path']} @ {check['ref']}")
        lines.append(f"  Expected: {_value(check['expected'])}")
        lines.append(f"  Actual: {_value(check['actual'])}")
        if check.get("url"):
            lines.append(f"  URL: {check['url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    environment = report["environment"]
    lines = [
        f"# MOC environment status: `{environment['name']}`",
        "",
        f"- **Infra cluster:** `{environment['infra_cluster']}`",
        f"- **Workload cluster:** `{environment['workload_cluster']}`",
        f"- **Domain:** `{environment['domain']}`",
        f"- **Overall:** **{report['overall_state']}**",
        "",
        "## State summary",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state, count in report["summary"]["state_counts"].items():
        lines.append(f"| `{state}` | {count} |")

    lines.extend(["", "## Checks", ""])
    for check in report["checks"]:
        lines.append(f"### `{check['state']}` — {check['stage']} / {check['check']}")
        lines.append("")
        lines.append(f"- Repository: `{check['repository']}`")
        lines.append(f"- Path: `{check['path']} @ {check['ref']}`")
        lines.append(f"- Expected: `{_value(check['expected'])}`")
        lines.append(f"- Actual: `{_value(check['actual'])}`")
        if check.get("url"):
            lines.append(f"- URL: {check['url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"
