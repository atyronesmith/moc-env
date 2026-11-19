"""Field-level comparisons shared by human-readable status reports."""

from __future__ import annotations

from typing import Any


def plain(value: Any) -> str:
    """Render nested repository evidence without Python or JSON reprs."""

    if value is None:
        return "not found"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return ", ".join(f"{key} {plain(item)}" for key, item in value.items()) or "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(plain(item) for item in value) or "none"
    return str(value)


def _boot_image_rule(check: dict[str, Any]) -> str:
    """Name the filename tokens that identify the check's cluster."""

    cluster = str(check.get("cluster") or "")
    tokens = [cluster]
    shortened = cluster.removeprefix("oac-")
    if shortened != cluster:
        tokens.append(shortened)
    if check.get("scope") == "workload":
        hub = str(check.get("hub") or "")
        if not hub:
            parts = cluster.split("-")
            hub = "-".join([*parts[:-1], "infra"]) if parts else ""
        if hub and hub not in tokens:
            tokens.append(hub)
            hub_short = hub.removeprefix("oac-")
            if hub_short != hub and hub_short not in tokens:
                tokens.append(hub_short)
    if len(tokens) == 1:
        return f"filename contains {tokens[0]}"
    return "filename contains " + " or ".join(tokens)


def field_rows(check: dict[str, Any]) -> list[list[Any]]:
    """Describe actual fields, retaining full paths for nested evidence."""

    check_id = check.get("id", "")
    expected = check.get("expected")
    actual = check.get("actual")
    evidence = check.get("evidence") or {}
    expected_map = expected if isinstance(expected, dict) else {}
    actual_map = actual if isinstance(actual, dict) else {}
    values = evidence.get("values")
    if isinstance(expected, list) and isinstance(values, dict):
        return [[name, "present", values.get(name)] for name in expected]
    if check_id.endswith(".boot_image"):
        return [["boot_image_url", _boot_image_rule(check), plain(actual)]]
    if check_id == "request.issue":
        return [["issue_state", "open", actual]]
    if check_id.endswith(".inventory"):
        cluster = str(check.get("cluster") or "")
        return [
            ["cluster_group", f"a group with vars.cluster == {cluster}", actual_map.get("cluster_group")],
            ["host_count", "reported (not required)", actual_map.get("host_count")],
        ]
    if check_id == "workload.component_values":
        found = [str(path) for path in evidence.get("paths") or []]
        scope = str(check.get("path") or "values/")
        return [
            [path, "present", "present"] for path in found
        ] + [[scope, "at least 1 file", f"{len(found)} file(s)"]]
    if check_id.endswith(".moc_aws_oidc_cluster"):
        return [
            ["cluster_name", expected_map.get("cluster_name"), actual_map.get("cluster_name")],
            [
                "eso_writable_secret_prefixes",
                "not constrained by this check",
                actual_map.get("eso_writable_secret_prefixes") or "none listed",
            ],
        ]
    if check_id == "workload.identity_provider":
        explicit = "oauth.identityProviders" in actual_map
        rows = [
            [
                "oauth.mocsso.enabled",
                (
                    "false or absent, with a non-empty "
                    "oauth.identityProviders list"
                    if explicit
                    else True
                ),
                actual_map.get("oauth.mocsso.enabled"),
            ]
        ]
        client_fields = evidence.get("client_fields")
        if isinstance(client_fields, dict):
            rows.extend(
                [
                    [f"moc-keycloak {name}", item.get("expected"), item.get("observed")]
                    for name, item in client_fields.items()
                    if isinstance(item, dict)
                ]
            )
        elif "oauth.identityProviders" in actual_map:
            rows.append(
                [
                    "oauth.identityProviders",
                    "non-empty list when mocsso is disabled",
                    actual_map.get("oauth.identityProviders"),
                ]
            )
        return rows
    if check_id == "workload.api_address_network":
        return [["services.APIServer.ipAddress", f"inside {expected_map.get('machine_network')}", actual]]
    if check_id == "workload.ingress_address_network":
        network = expected_map.get("machine_network")
        subnet = expected_map.get("vlan_subnet")
        requirement = f"outside {network}"
        requirement += f" and inside {subnet}" if subnet else "; no matching workload VLAN"
        return [["ingress.poolAddress", requirement, actual]]
    if check_id == "workload.dns_base_domain":
        domains = expected_map.get("domains") or list(dict.fromkeys(
            domain for key, domain in expected_map.items()
            if key in {"baseDomain", "hcpExternalDomain"} and domain
        ))
        return [
            [f"dns.records[{index}].hostname", "under " + plain(domains), hostname]
            for index, hostname in enumerate(actual or [])
        ] or [["dns.records", "hostnames under " + plain(domains), actual]]
    if check_id == "workload.gpu_without_hosts":
        label = actual_map.get("clusterLabels.massopen.cloud/feature-gpu", expected_map.get("feature-gpu"))
        return [
            ['clusterLabels["massopen.cloud/feature-gpu"]', "false or at least 1 GPU host", label],
            ["gpu_host_count", "at least 1 when feature-gpu is true", actual_map.get("gpu_host_count")],
        ]
    if check_id == "workload.feature_placements":
        return [
            [
                "matched placements",
                "a matching placement on this hub",
                evidence.get("matched_placements") or [],
            ],
            [
                "unused labels",
                "no placement on any hub",
                evidence.get("unused_labels") or [],
            ],
            [
                "labels with no placement on this hub",
                "none",
                "; ".join(
                    f"{label} (defined on: {', '.join(origins)})"
                    for label, origins in (
                        evidence.get("missing_on_hub") or {}
                    ).items()
                )
                or [],
            ],
        ]
    if check_id == "workload.feature_chart_values":
        return [
            [
                "charts received",
                "every chart selected by a matched placement",
                evidence.get("chart_count", 0),
            ],
            [
                "unmet required values",
                "none",
                evidence.get("unmet_required_values") or [],
            ],
            [
                "missing kustomize overlays",
                "none",
                evidence.get("missing_overlays") or [],
            ],
            [
                "orphan values files",
                "none",
                evidence.get("orphan_values_files") or [],
            ],
        ]
    if check_id == "workload.node_pool_hosts":
        pools = {item.get("name"): item for item in expected or [] if isinstance(item, dict)}
        return [
            [f"nodePools.{item.get('name')}.matching_hosts", f"at least {pools.get(item.get('name'), {}).get('replicas', item.get('replicas'))}", item.get("matching_hosts")]
            for item in actual or [] if isinstance(item, dict)
        ]
    if check_id == "workload.address_uniqueness":
        rows = []
        for item in evidence.get("address_rows") or []:
            if not isinstance(item, dict):
                continue
            others = item.get("used_by_others") or []
            rows.append(
                [
                    f"{item.get('cluster')} {item.get('field')} {item.get('address')}",
                    "used by no other cluster",
                    ", ".join(str(other) for other in others) or "none",
                ]
            )
        return rows
    if check_id == "workload.address_internal_duplicates":
        cluster = str(check.get("cluster") or "")
        rows = []
        for item in evidence.get("address_rows") or []:
            if not isinstance(item, dict):
                continue
            others = item.get("duplicate_fields") or []
            rows.append(
                [
                    f"{item.get('field')} {item.get('address')}",
                    f"not used by another field of {cluster}",
                    ", ".join(str(other) for other in others) or "none",
                ]
            )
        return rows
    paths = evidence.get("expected_paths")
    if isinstance(paths, list) and paths:
        found = set(evidence.get("paths") or [])
        return [[path, "present", "present" if path in found else "missing"] for path in paths]
    if check_id == "workload.agent_labels_inputs":
        return [
            [f"{host.get('host')}.{key}",
             ("present (not required for openstack)" if host.get("bm_management") == "openstack"
              else (host.get("documented_resource_class") or "present") if key == "resource_class" else "present"),
             host.get(key)]
            for host in evidence.get("agent_label_hosts", [])
            for key in ("mac_addr", "resource_class")
        ]
    fields = evidence.get("fields")
    if isinstance(fields, dict) and all(isinstance(item, dict) for item in fields.values()):
        return [[name, item.get("expected"), item.get("observed")] for name, item in fields.items()]
    if check_id.endswith(".pure_storage_realm"):
        realm = evidence.get("realm") or actual_map
        return [
            ["name", expected_map.get("name"), realm.get("name", expected_map.get("name") if actual is not None else None)],
            *[[name, "present", realm.get(name)] for name in expected_map.get("fields", [])],
        ]
    if check_id.endswith(".moc_aws_cert_manager_policy"):
        cluster = str(check.get("cluster") or expected_map.get("cluster") or "")
        return [["policy entry", f"policy_name or cluster_subdomain names {cluster}", actual]]
    if check_id.endswith(".moc_aws_hosted_secret_prefix"):
        prefix = expected_map.get("eso_writable_secret_prefix", expected)
        return [["eso_writable_secret_prefixes", prefix, actual_map.get("eso_writable_secret_prefix", actual)]]
    if check_id == "hub.image_inventory":
        hub = str(check.get("cluster") or "")
        return [["inventory_key", f"key all.children.{hub}", actual_map.get("inventory_key")]]
    if isinstance(expected, dict):
        return _flatten(expected, actual_map)
    if isinstance(actual, dict):
        return [[name, expected, item] for name, item in actual.items()]
    label = check.get("path") or check.get("check") or check_id or "configuration"
    return [[label, expected, actual]]


def failing_field_rows(check: dict[str, Any]) -> list[list[Any]]:
    """Keep only unsatisfied fields in next actions; retain all rows in details."""
    rows = field_rows(check)
    missing = check.get("missing") or {}
    evidence = check.get("evidence") or {}
    if check.get("id") == "workload.feature_chart_values":
        failing = {
            "unmet required values",
            "missing kustomize overlays",
            "orphan values files",
        }
        return [row for row in rows if row[0] in failing and row[2]]
    if check.get("id") == "workload.feature_placements":
        return [
            row
            for row in rows
            if row[0] == "labels with no placement on this hub" and row[2]
        ]
    if check.get("id", "").endswith(".inventory"):
        actual = check.get("actual") or {}
        return [row for row in rows if
                (row[0] == "cluster_group" and actual.get("cluster_group") is None)
                or (row[0] == "host_count" and (actual.get("host_count") or 0) < 1)]
    if check.get("id") == "workload.address_internal_duplicates":
        return [row for row in rows if row[2] != "none"]
    if check.get("id") == "workload.dns_base_domain" and "hostnames" in missing:
        return [row for row in rows if row[2] in missing["hostnames"]]
    if check.get("id") == "workload.node_pool_hosts":
        return [row for row, item in zip(rows, check.get("actual") or [])
                if (item.get("matching_hosts") or 0) < (item.get("replicas") or 0)]
    if check.get("id") == "workload.agent_labels_inputs":
        failed = {f"{host}.{name}" for host, names in evidence.get("missing_variables", {}).items() for name in names}
        failed.update(f"{item['host']}.resource_class" for item in evidence.get("resource_class_mismatches", []))
        return [row for row in rows if row[0] in failed]
    if isinstance(missing, dict) and isinstance(missing.get("fields"), (dict, list)):
        return [row for row in rows if row[0] in missing["fields"]]
    return [row for row in rows if row[1] != row[2]
            and not (row[1] == "none" and row[2] in ([], {}, "", ()))
            and row[1] != "not constrained by this check"
            and not (row[1] == "present" and row[2] not in (None, False, "missing"))]


def _flatten(expected: dict[str, Any], observed: dict[str, Any], prefix: str = "") -> list[list[Any]]:
    rows = []
    for name in dict.fromkeys((*expected, *observed)):
        label = f"{prefix}.{name}" if prefix else str(name)
        wanted, found = expected.get(name, "not constrained by this check"), observed.get(name)
        if isinstance(wanted, dict) or isinstance(found, dict):
            rows.extend(_flatten(wanted if isinstance(wanted, dict) else {}, found if isinstance(found, dict) else {}, label))
        else:
            rows.append([label, wanted, found])
    return rows
