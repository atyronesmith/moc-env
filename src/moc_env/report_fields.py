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
        return [["boot_image_url", plain(check.get("missing") or expected), plain(actual)]]
    if check_id == "request.issue":
        return [["issue_state", "open", actual]]
    if check_id.endswith(".inventory"):
        return [
            ["cluster_group", expected, actual_map.get("cluster_group")],
            ["host_count", "at least 1", actual_map.get("host_count")],
        ]
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
    if check_id == "workload.node_pool_hosts":
        pools = {item.get("name"): item for item in expected or [] if isinstance(item, dict)}
        return [
            [f"nodePools.{item.get('name')}.matching_hosts", f"at least {pools.get(item.get('name'), {}).get('replicas', item.get('replicas'))}", item.get("matching_hosts")]
            for item in actual or [] if isinstance(item, dict)
        ]
    if check_id == "workload.address_uniqueness":
        return [
            [address, "used by only one cluster", "; ".join(f"{cluster}: {field}" for cluster, field in uses)]
            for address, uses in actual_map.items()
        ]
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
        return [["policy entry", "covers " + plain(expected_map.get("cluster")), actual]]
    if check_id.endswith(".moc_aws_hosted_secret_prefix"):
        prefix = expected_map.get("eso_writable_secret_prefix", expected)
        return [["eso_writable_secret_prefixes", prefix, actual_map.get("eso_writable_secret_prefix", actual)]]
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
    if check.get("id", "").endswith(".inventory"):
        actual = check.get("actual") or {}
        return [row for row in rows if
                (row[0] == "cluster_group" and actual.get("cluster_group") is None)
                or (row[0] == "host_count" and (actual.get("host_count") or 0) < 1)]
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
