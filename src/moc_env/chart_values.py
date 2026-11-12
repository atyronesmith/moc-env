"""Render chart-values documentation from normalized observations."""

from __future__ import annotations

import json
from typing import Any

from .github import github_url
from .model import Environment
from .observed import ChartValuesObservation, OAC_APPS_REPOSITORY

_SCOPE_DESCRIPTIONS = {
    "hub-wide": (
        "Values shared by applications scoped to the hub cluster. These files "
        "live under the hub's `values/` directory but outside `local-cluster/` "
        "and any workload directory."
    ),
    "hub-local-cluster": (
        "Values for components installed in the hub cluster's local cluster. "
        "This is where shared hub services such as ACM are configured."
    ),
    "hosted-cluster": (
        "Values that define the hosted cluster. The hosted control plane runs "
        "on the hub cluster; node pools and workload-facing settings are "
        "declared here."
    ),
    "workload-components": (
        "Values for charts installed into the hosted workload cluster. Each "
        "file is normally named after the component it configures."
    ),
}


def _inline(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        rendered = str(value)
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def _secret_like(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in ("secret", "token", "password", "credential")
    )


def render_chart_values_markdown(
    environment: Environment,
    observation: ChartValuesObservation,
) -> str:
    """Render a human-readable guide to an environment's chart values."""

    lines = [
        "# 📘 Hub and Hosted Cluster Chart Values",
        "",
        f"## `{environment.name}`",
        "",
        "This guide documents values currently declared in merged "
        "`CCI-MOC/oac-apps` `main`. It explains where values live and what "
        "each scope controls; it does not replace upstream chart documentation.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Environment | `{environment.name}` |",
        f"| Hub cluster | `{environment.infra_cluster}` |",
        f"| Hosted workload cluster | `{environment.workload_cluster}` |",
        f"| Source repository | `{observation.source_repository}` |",
        "",
        "## Scope summary",
        "",
        "| Scope | Path pattern | Present | Files |",
        "|---|---|---|---:|",
    ]
    for scope in observation.scopes:
        lines.append(
            f"| `{scope.scope.value}` | `{scope.prefix.value}` | "
            f"{'Yes' if scope.present.value else 'No'} | "
            f"{len(scope.files)} |"
        )

    lines.extend(
        [
            "",
            "## How the scopes relate",
            "",
            "- The **hub cluster** is the management cluster. It runs shared "
            "services and the hosted control planes.",
            "- A **hosted cluster** has its control plane hosted on the hub "
            "cluster; its worker nodes form the workload cluster's data plane.",
            "- Hub-wide and hub-local-cluster values configure the hub and its "
            "shared services.",
            "- Hosted-cluster values define the hosted workload cluster.",
            "- Workload-component values configure charts installed into that "
            "hosted workload cluster.",
            "",
        ]
    )

    for scope in observation.scopes:
        scope_name = scope.scope.value
        lines.extend(
            [
                f"## {scope_name}",
                "",
                _SCOPE_DESCRIPTIONS.get(
                    scope_name,
                    "Values in this scope are documented from repository state.",
                ),
                "",
            ]
        )
        if not scope.present.value:
            lines.extend(
                [
                    f"No values files were found under `{scope.prefix.value}`.",
                    "",
                ]
            )
            continue

        for file_observation in scope.files:
            path = file_observation.path.value
            chart = file_observation.chart.value
            lines.extend(
                [
                    f"### `{chart}`",
                    "",
                    "| Source | Value |",
                    "|---|---|",
                    f"| Repository | `{observation.source_repository}` |",
                    f"| Path | `{path}` |",
                    f"| Ref | `main` |",
                    f"| Link | [Open values file]({github_url(OAC_APPS_REPOSITORY, path)}) |",
                    "",
                ]
            )
            if not file_observation.present.value:
                lines.extend(
                    [
                        "This expected values file is absent from merged `main`.",
                        "",
                    ]
                )
                continue
            if file_observation.values.confidence == "unsupported":
                lines.extend(
                    [
                        "The file exists, but its YAML shape is unsupported for "
                        "value extraction.",
                        "",
                    ]
                )
                continue
            if not file_observation.entries:
                lines.extend(["The file contains no scalar leaf values.", ""])
                continue

            lines.extend(
                [
                    "| Key | Current value | Type | Notes |",
                    "|---|---|---|---|",
                ]
            )
            for entry in file_observation.entries:
                key = entry.key.value
                value = entry.value.value
                notes = (
                    "⚠️ Secret-like name; verify before sharing."
                    if _secret_like(key)
                    else "—"
                )
                lines.append(
                    f"| `{_inline(key)}` | `{_inline(value)}` | "
                    f"`{type(value).__name__}` | {notes} |"
                )
            lines.append("")

    lines.extend(
        [
            "## Using this guide",
            "",
            "- Values shown here are the current merged-`main` declarations, "
            "not defaults from each upstream chart.",
            "- Change proposals should still be reviewed against the chart's "
            "upstream documentation and maintainers.",
            "- Secret-like key names are flagged, but this guide does not "
            "attempt to prove whether a value is sensitive.",
            "- This report is read-only and does not claim that applications "
            "are deployed or healthy.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
