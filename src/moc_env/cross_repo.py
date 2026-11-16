"""Cross-repository prerequisite observations and checks."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from typing import Any

import yaml

from .github import GitHubClient, GitHubError, github_url
from .model import CheckResult, Environment
from .observed import AppsObservation, InfraObservation

EVERPURE_REPOSITORY = "CCI-MOC/everpure-moc"
MOC_AWS_REPOSITORY = "CCI-MOC/moc-aws"
MOC_DNS_REPOSITORY = "CCI-MOC/moc-dns"
ANSIBLE_SWITCHES_REPOSITORY = "CCI-MOC/ansible-switches"

EVERPURE_PATH = "ansible/group_vars/all/realms.yaml"
MOC_AWS_MAIN = "main.tf"
MOC_AWS_CERT_MANAGER = "cert-manager-policies.tf"
ANSIBLE_SWITCHES_VLANS = "group_vars/all/vlans.yaml"

ProgressCallback = Callable[[str, str, str, str], None]

_HCL_MERGE_BLOCK = re.compile(
    r'^\s*"?([A-Za-z0-9_-]+)"?\s*=\s*merge\((?P<body>.*?)\n\s*\}\)',
    re.MULTILINE | re.DOTALL,
)
_HCL_OBJECT_BLOCK = re.compile(
    r'^\s*"?([A-Za-z0-9_-]+)"?\s*=\s*\{(?P<body>.*?)\n\s*\}',
    re.MULTILINE | re.DOTALL,
)


def _progress(
    progress: ProgressCallback | None,
    action: str,
    repository: str,
    path: str,
) -> None:
    if progress is not None:
        progress("Cross-repository prerequisites", action, repository, path)


def _read_file(
    client: GitHubClient,
    repository: str,
    path: str,
    progress: ProgressCallback | None = None,
) -> tuple[str | None, str | None]:
    _progress(progress, f"read {path}", repository, path)
    try:
        tree = client.get_tree(repository)
        if path not in tree:
            return None, f"{repository}/{path} is absent or unavailable."
        return client.get_file(repository, path), None
    except GitHubError as exc:
        return None, f"{repository} could not be read: {exc}"


def _parse_yaml(text: str | None, error: str | None) -> tuple[Any, str | None]:
    if text is None:
        return None, error
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as exc:
        return None, f"YAML could not be parsed: {exc}"


def _hcl_string(body: str, key: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"', body, re.MULTILINE)
    return match.group(1) if match else None


def _hcl_strings(body: str, key: str) -> list[str]:
    match = re.search(
        rf'^\s*{re.escape(key)}\s*=\s*\[(?P<values>.*?)\]',
        body,
        re.MULTILINE | re.DOTALL,
    )
    return re.findall(r'"([^"]+)"', match.group("values")) if match else []


def _hcl_blocks(text: str | None, error: str | None) -> tuple[list[tuple[str, str]], str | None]:
    if text is None:
        return [], error
    blocks = [
        (match.group(1), match.group("body"))
        for match in _HCL_MERGE_BLOCK.finditer(text)
    ]
    blocks.extend(
        (match.group(1), match.group("body"))
        for match in _HCL_OBJECT_BLOCK.finditer(text)
    )
    return blocks, None


def _unknown(
    check_id: str,
    scope: str,
    repository: str,
    path: str,
    reason: str,
    expected: Any,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage="Cross-repository prerequisites",
        check=_CHECK_LABELS[check_id],
        scope=scope,
        repository=repository,
        path=path,
        ref="main",
        state="unknown",
        severity="advisory",
        expected=expected,
        actual=None,
        reason=reason,
        evidence={"error": reason},
        url=github_url(repository, path),
        next_action=f"Verify {path} is readable and correctly formatted.",
    )


_CHECK_LABELS = {
    "hub.pure_storage_realm": "Hub Pure storage realm",
    "workload.pure_storage_realm": "Workload Pure storage realm",
    "hub.moc_aws_oidc_cluster": "Hub moc-aws OIDC cluster",
    "workload.moc_aws_oidc_cluster": "Workload moc-aws OIDC cluster",
    "hub.moc_aws_cert_manager_policy": "Hub moc-aws cert-manager policy",
    "workload.moc_aws_cert_manager_policy": "Workload moc-aws cert-manager policy",
    "hub.moc_aws_hosted_secret_prefix": "Hub hosted-cluster secret prefix",
    "workload.keycloak_oidc_client": "Workload Keycloak OIDC client",
    "hub.moc_dns_records": "Hub moc-dns records",
    "workload.api_address_network": "Workload API address network",
    "workload.ingress_address_network": "Workload ingress address network",
    "workload.address_uniqueness": "Workload address uniqueness",
    "workload.dns_base_domain": "Workload DNS base domain",
    "workload.node_pool_hosts": "Workload node-pool host capacity",
    "workload.gpu_without_hosts": "Workload GPU feature support",
}


def _result(
    check_id: str,
    scope: str,
    repository: str,
    path: str,
    state: str,
    severity: str,
    expected: Any,
    actual: Any,
    reason: str,
    missing: Any = None,
    evidence: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage="Cross-repository prerequisites",
        check=_CHECK_LABELS[check_id],
        scope=scope,
        repository=repository,
        path=path,
        ref="main",
        state=state,
        severity=severity,
        expected=expected,
        actual=actual,
        reason=reason,
        missing=missing,
        evidence=evidence or {},
        url=github_url(repository, path),
        next_action=None if state == "declared_in_main" else _NEXT_ACTION[check_id],
    )


_NEXT_ACTION = {
    "hub.pure_storage_realm": "Add or correct the hub realm in everpure-moc realms.yaml.",
    "workload.pure_storage_realm": "Add or correct the workload realm in everpure-moc realms.yaml.",
    "hub.moc_aws_oidc_cluster": "Add or correct the hub entry in moc-aws local.openshift_oidc_clusters.",
    "workload.moc_aws_oidc_cluster": "Add or correct the workload entry in moc-aws local.openshift_oidc_clusters.",
    "hub.moc_aws_cert_manager_policy": "Add a cert-manager policy entry for the hub.",
    "workload.moc_aws_cert_manager_policy": "Add a cert-manager policy entry for the workload.",
    "hub.moc_aws_hosted_secret_prefix": "Add cluster/<hub>/hostedcluster/ to the hub's eso_writable_secret_prefixes.",
    "workload.keycloak_oidc_client": "Add or correct the workload Keycloak OIDC client.",
    "hub.moc_dns_records": "Add or correct api, api-int, and *.apps records in moc-dns.",
    "workload.api_address_network": "Move services.APIServer.ipAddress into the hub machine network.",
    "workload.ingress_address_network": "Move ingress.poolAddress outside the hub machine network and into the workload VLAN.",
    "workload.address_uniqueness": "Assign addresses that are not used by another cluster.",
    "workload.dns_base_domain": "Use dns.records hostnames under the hub baseDomain.",
    "workload.node_pool_hosts": "Add matching inventory hosts or reduce node-pool replicas.",
    "workload.gpu_without_hosts": "Disable feature-gpu or add GPU hosts to the workload inventory.",
}


def _realm_check(
    client: GitHubClient,
    cluster: str,
    scope: str,
    progress: ProgressCallback | None,
) -> CheckResult:
    check_id = f"{scope}.pure_storage_realm"
    text, error = _read_file(client, EVERPURE_REPOSITORY, EVERPURE_PATH, progress)
    data, parse_error = _parse_yaml(text, error)
    if parse_error or not isinstance(data, dict) or not isinstance(data.get("realms"), list):
        return _unknown(check_id, scope, EVERPURE_REPOSITORY, EVERPURE_PATH, parse_error or "realms.yaml does not contain a realms list.", {"name": cluster})
    realms = [item for item in data["realms"] if isinstance(item, dict) and item.get("name") == cluster]
    expected = {"name": cluster, "fields": ["subnet_vlan", "subnet_prefix", "s3_endpoint"]}
    if not realms:
        return _result(check_id, scope, EVERPURE_REPOSITORY, EVERPURE_PATH, "missing", "blocking", expected, None, f"No Pure storage realm named {cluster} was found.", {"realms": [cluster]})
    realm = realms[0]
    missing = [field for field in ("subnet_vlan", "subnet_prefix", "s3_endpoint") if realm.get(field) is None]
    observed = {field: realm.get(field) for field in ("subnet_vlan", "subnet_prefix", "s3_endpoint")}
    if missing:
        return _result(check_id, scope, EVERPURE_REPOSITORY, EVERPURE_PATH, "partial", "blocking", expected, observed, f"The {cluster} realm is missing: {', '.join(missing)}.", {"fields": missing}, {"realm": realm})
    return _result(check_id, scope, EVERPURE_REPOSITORY, EVERPURE_PATH, "declared_in_main", "info", expected, observed, f"The {cluster} Pure storage realm is complete.")


def _moc_aws_checks(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None,
) -> list[CheckResult]:
    main_text, main_error = _read_file(client, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, progress)
    blocks, block_error = _hcl_blocks(main_text, main_error)
    if main_text is not None and not blocks:
        block_error = f"{MOC_AWS_REPOSITORY}/{MOC_AWS_MAIN} did not contain readable HCL blocks."
    cert_text, cert_error = _read_file(client, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, progress)
    cert_blocks, cert_block_error = _hcl_blocks(cert_text, cert_error)
    if cert_text is not None and not cert_blocks:
        cert_block_error = f"{MOC_AWS_REPOSITORY}/{MOC_AWS_CERT_MANAGER} did not contain readable HCL blocks."
    results: list[CheckResult] = []
    clusters = [
        (environment.infra_cluster, "hub"),
        *((workload, "workload") for workload in environment.workload_clusters or ()),
    ]
    for cluster, scope_name in clusters:
        scope = "hub" if scope_name == "hub" else "workload"
        oidc_id = f"{scope}.moc_aws_oidc_cluster"
        if block_error:
            results.append(_unknown(oidc_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, block_error, {"cluster_name": cluster}))
            continue
        matches = [body for _, body in blocks if _hcl_string(body, "cluster_name") == cluster]
        expected = {"cluster_name": cluster}
        if not matches:
            results.append(_result(oidc_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "missing", "blocking", expected, None, f"No moc-aws OIDC cluster entry has cluster_name {cluster}."))
        else:
            results.append(_result(oidc_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "declared_in_main", "info", expected, matches[0], f"The moc-aws OIDC cluster entry for {cluster} is present.", evidence={"block": matches[0]}))

        cert_id = f"{scope}.moc_aws_cert_manager_policy"
        if cert_block_error:
            results.append(_unknown(cert_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, cert_block_error, {"cluster": cluster}))
            continue
        cert_matches = [
            (name, body)
            for name, body in cert_blocks
            if cluster in (_hcl_string(body, "cluster_subdomain") or "")
            or cluster in (_hcl_string(body, "policy_name") or "")
            or cluster.replace("-", "_") in (_hcl_string(body, "policy_name") or "")
        ]
        if not cert_matches:
            results.append(_result(cert_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, "missing", "blocking", {"cluster": cluster}, None, f"No cert-manager policy entry names {cluster}."))
        else:
            name, body = cert_matches[0]
            results.append(_result(cert_id, scope, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, "declared_in_main", "info", {"cluster": cluster}, name, f"The cert-manager policy entry {name} covers {cluster}.", evidence={"block": body}))

    if environment.workload_clusters:
        prefix = f"cluster/{environment.infra_cluster}/hostedcluster/"
        if block_error:
            results.append(_unknown("hub.moc_aws_hosted_secret_prefix", "hub", MOC_AWS_REPOSITORY, MOC_AWS_MAIN, block_error, [prefix]))
        else:
            hub = next((body for _, body in blocks if _hcl_string(body, "cluster_name") == environment.infra_cluster), None)
            writable = _hcl_strings(hub, "eso_writable_secret_prefixes") if hub else []
            if prefix in writable:
                results.append(_result("hub.moc_aws_hosted_secret_prefix", "hub", MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "declared_in_main", "info", [prefix], writable, f"The hub can write hosted-cluster secrets at {prefix}."))
            else:
                results.append(_result("hub.moc_aws_hosted_secret_prefix", "hub", MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "missing", "blocking", [prefix], writable, f"The hub entry does not list {prefix}; it cannot push hosted-cluster secrets.", {"prefix": prefix}))
    return results


def _dns_records_check(
    client: GitHubClient,
    environment: Environment,
    hub_values: dict[str, Any],
    progress: ProgressCallback | None,
) -> CheckResult | None:
    domain_parts = [hub_values.get("cluster_domain_name"), hub_values.get("base_domain")]
    api_ip, ingress_ip, machine_network = hub_values.get("api_ip"), hub_values.get("ingress_ip"), hub_values.get("machine_network")
    if not all(isinstance(part, str) and part for part in (*domain_parts, api_ip, ingress_ip, machine_network)):
        return _unknown("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, "zonefiles/", "Hub-image variables required for DNS validation are unavailable.", {"api": api_ip, "api-int": api_ip, "*.apps": ingress_ip})
    domain = ".".join(domain_parts)
    _progress(progress, "read DNS zonefiles", MOC_DNS_REPOSITORY, "zonefiles/")
    try:
        tree = client.get_tree(MOC_DNS_REPOSITORY)
        zone_path = f"zonefiles/{domain_parts[1]}.zone"
        if zone_path not in tree:
            return _unknown("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, zone_path, "The expected DNS zonefile is absent or unavailable.", {"domain": domain})
        text = client.get_file(MOC_DNS_REPOSITORY, zone_path)
    except GitHubError as exc:
        return _unknown("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, "zonefiles/", f"moc-dns could not be read: {exc}", {"domain": domain})
    records: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^(\S+?)\.?\s+\d+\s+IN\s+A\s+(\S+)", line)
        if match:
            records[match.group(1)] = match.group(2)
    expected = {f"api.{domain}": api_ip, f"api-int.{domain}": api_ip, f"*.apps.{domain}": ingress_ip}
    observed = {name: records.get(name) for name in expected}
    missing = [name for name, value in observed.items() if value is None]
    mismatched = {name: {"expected": value, "observed": observed[name]} for name, value in expected.items() if observed[name] != value}
    if missing:
        return _result("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, zone_path, "missing", "blocking", expected, observed, "Missing DNS records: " + ", ".join(missing) + ".", {"records": missing})
    if mismatched:
        return _result("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, zone_path, "value_mismatch", "blocking", expected, observed, "One or more DNS records point to the wrong address.", {"records": mismatched})
    return _result("hub.moc_dns_records", "hub", MOC_DNS_REPOSITORY, zone_path, "declared_in_main", "info", expected, observed, "All required hub DNS records match the hub-image variables.")


def _nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _workload_values(
    apps: AppsObservation,
    environment: Environment,
    workload: str,
) -> tuple[dict[str, Any] | None, str | None]:
    path = f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
    if path not in apps.paths.value:
        return None, f"{path} is absent or unavailable."
    try:
        data = yaml.safe_load(apps.files.get(path, "")) if hasattr(apps, "files") else None
    except yaml.YAMLError as exc:
        return None, str(exc)
    return data if isinstance(data, dict) else None, "The hosted-cluster values file is not a mapping."


def _keycloak_workload_check(
    client: GitHubClient,
    environment: Environment,
    workload: str,
    values: dict[str, Any] | None,
    hub_values_file: dict[str, Any] | None,
    progress: ProgressCallback | None,
) -> CheckResult | None:
    enabled = _nested(values or {}, ("oauth", "mocsso", "enabled")) is True
    if not enabled:
        return None
    external_domain = (hub_values_file or {}).get("hcpExternalDomain")
    if not isinstance(external_domain, str) or not external_domain:
        return _unknown("workload.keycloak_oidc_client", "workload", "CCI-MOC/moc-keycloak", "main.tf", "hcpExternalDomain is unavailable from the hub hosted-cluster defaults.", {})
    text, error = _read_file(client, "CCI-MOC/moc-keycloak", "main.tf", progress)
    blocks, block_error = _hcl_blocks(text, error)
    if text is not None and not blocks:
        block_error = "CCI-MOC/moc-keycloak/main.tf did not contain readable HCL blocks."
    if block_error:
        return _unknown("workload.keycloak_oidc_client", "workload", "CCI-MOC/moc-keycloak", "main.tf", block_error, {})
    expected = {
        "cluster_name": workload,
        "openshift_redirect_uri": f"https://oauth-{workload}.{external_domain}:443/oauth2callback/mocsso",
        "client_secret_name": f"cluster/{environment.infra_cluster}/hostedcluster/{workload}/keycloak-oidc",
    }
    block = next((body for _, body in blocks if _hcl_string(body, "cluster_name") == workload), None)
    observed = {key: _hcl_string(block, key) if block else None for key in expected}
    nonmatching = [key for key, value in expected.items() if observed[key] != value]
    if block and not nonmatching:
        return _result("workload.keycloak_oidc_client", "workload", "CCI-MOC/moc-keycloak", "main.tf", "declared_in_main", "info", expected, observed, f"The Keycloak OIDC client for {workload} matches.")
    state = "missing" if block is None else "value_mismatch"
    return _result("workload.keycloak_oidc_client", "workload", "CCI-MOC/moc-keycloak", "main.tf", state, "blocking", expected, observed, f"The Keycloak OIDC client for {workload} is absent or mismatched.", {"fields": nonmatching}, {"block": block})


def _address_in(value: Any, network: str) -> bool:
    try:
        return ipaddress.ip_address(value) in ipaddress.ip_network(network, strict=False)
    except (ValueError, TypeError):
        return False


def _workload_value_checks(
    client: GitHubClient,
    environment: Environment,
    infra: InfraObservation,
    apps: AppsObservation,
    hub_values: dict[str, Any],
    hub_values_file: dict[str, Any] | None,
    progress: ProgressCallback | None,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    machine_network = hub_values.get("machine_network")
    base_domain = hub_values.get("base_domain")
    vlans_text, vlans_error = _read_file(client, ANSIBLE_SWITCHES_REPOSITORY, ANSIBLE_SWITCHES_VLANS, progress)
    vlans_data, vlans_parse = _parse_yaml(vlans_text, vlans_error)
    vlans = vlans_data.get("vlans", []) if isinstance(vlans_data, dict) and isinstance(vlans_data.get("vlans"), list) else []
    vlans_available = (
        vlans_text is not None
        and vlans_error is None
        and vlans_parse is None
        and isinstance(vlans_data, dict)
        and isinstance(vlans_data.get("vlans"), list)
    )

    all_values: dict[str, dict[str, Any]] = {}
    values_parse_errors: list[str] = []
    for path in apps.paths.value:
        parts = path.split("/")
        if len(parts) == 4 and parts[0] == "hosted-clusters" and parts[3] == "values.yaml":
            try:
                data = yaml.safe_load(apps.files.get(path, "")) if hasattr(apps, "files") else None
            except yaml.YAMLError:
                data = None
            if isinstance(data, dict):
                all_values[path] = data
            else:
                values_parse_errors.append(path)

    for workload in environment.workload_clusters or ():
        path = f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
        values, values_error = _workload_values(apps, environment, workload)
        if values is None:
            results.extend([
                _unknown(check_id, "workload", "CCI-MOC/oac-apps", path, values_error, {})
                for check_id in (
                    "workload.api_address_network", "workload.ingress_address_network",
                    "workload.dns_base_domain", "workload.node_pool_hosts",
                    "workload.gpu_without_hosts",
                )
            ])
            continue

        api_ip = _nested(values, ("services", "APIServer", "ipAddress"))
        expected = {"ipAddress": api_ip, "machine_network": machine_network}
        if _address_in(api_ip, machine_network):
            results.append(_result("workload.api_address_network", "workload", "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected, api_ip, "The API address is inside the hub machine network."))
        else:
            results.append(_result("workload.api_address_network", "workload", "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected, api_ip, "The API address is not inside the hub machine network."))

        if not vlans_available:
            results.append(_unknown("workload.ingress_address_network", "workload", ANSIBLE_SWITCHES_REPOSITORY, ANSIBLE_SWITCHES_VLANS, vlans_error or vlans_parse or "vlans.yaml does not contain a vlans list.", {}))
        else:
            pool = _nested(values, ("ingress", "poolAddress"))
            vlan = next((item for item in vlans if isinstance(item, dict) and workload.removeprefix(environment.base_name + "-").upper() in str(item.get("name", "")).upper()), None)
            expected_pool = {"poolAddress": pool, "machine_network": machine_network, "vlan_subnet": vlan.get("subnet4") if vlan else None}
            valid = not _address_in(pool, machine_network) and (vlan is None or _address_in(pool, vlan["subnet4"]))
            if valid:
                results.append(_result("workload.ingress_address_network", "workload", "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected_pool, pool, "The ingress pool address is on the expected network."))
            else:
                results.append(_result("workload.ingress_address_network", "workload", "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected_pool, pool, "The ingress pool address is on the wrong network."))

        hostnames = [record.get("hostname") for record in (_nested(values, ("dns", "records")) or []) if isinstance(record, dict)]
        invalid = [name for name in hostnames if not isinstance(name, str) or not name.endswith(base_domain)]
        if not invalid:
            results.append(_result("workload.dns_base_domain", "workload", "CCI-MOC/oac-apps", path, "declared_in_main", "info", {"baseDomain": base_domain}, hostnames, "All DNS record hostnames use the hub base domain."))
        else:
            results.append(_result("workload.dns_base_domain", "workload", "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", {"baseDomain": base_domain}, hostnames, "Some DNS record hostnames do not use the hub base domain.", {"hostnames": invalid}))

        cluster_observation = infra.clusters.get(workload)
        hosts = cluster_observation.hosts.value if cluster_observation else []
        pools = values.get("nodePools") or []
        pool_results = []
        for pool_item in pools:
            if not isinstance(pool_item, dict):
                continue
            selector = pool_item.get("agentLabelSelector") or {}
            replicas = int(pool_item.get("replicas") or 0)
            matching = sum(1 for host in hosts if all(host.get(key) == value or (key == "resource_class" and host.get("resource_class") == value) for key, value in selector.items() if isinstance(value, str)))
            pool_results.append({"name": pool_item.get("name"), "replicas": replicas, "matching_hosts": matching})
        if all(item["matching_hosts"] >= item["replicas"] for item in pool_results):
            results.append(_result("workload.node_pool_hosts", "workload", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "declared_in_main", "info", pools, pool_results, "Every node pool has enough matching inventory hosts."))
        else:
            results.append(_result("workload.node_pool_hosts", "workload", "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "value_mismatch", "blocking", pools, pool_results, "At least one node pool lacks matching inventory hosts."))

        gpu_enabled = str(values.get("feature-gpu")).lower() == "true"
        gpu_hosts = [host for host in hosts if host.get("gpu") is True or "gpu" in str(host.get("resource_class", "")).lower()]
        if not gpu_enabled or gpu_hosts:
            results.append(_result("workload.gpu_without_hosts", "workload", "CCI-MOC/oac-apps", path, "declared_in_main", "info", {"feature-gpu": str(gpu_enabled).lower()}, {"gpu_host_count": len(gpu_hosts)}, "GPU configuration is consistent with the inventory."))
        else:
            results.append(_result("workload.gpu_without_hosts", "workload", "CCI-MOC/oac-apps", path, "value_mismatch", "advisory", {"feature-gpu": "true"}, {"gpu_host_count": 0}, "feature-gpu is enabled, but no GPU hosts were found in the inventory."))

        keycloak = _keycloak_workload_check(client, environment, workload, values, hub_values_file, progress)
        if keycloak:
            results.append(keycloak)

    # Address uniqueness across all workload values files.
    usage: dict[str, list[tuple[str, str]]] = {}
    for path, values in all_values.items():
        cluster = path.split("/")[2]
        fields = {
            "services.APIServer.ipAddress": _nested(values, ("services", "APIServer", "ipAddress")),
            "ingress.poolAddress": _nested(values, ("ingress", "poolAddress")),
            "services.APIServer.externalIpAddress": _nested(values, ("services", "APIServer", "externalIpAddress")),
            "ingress.externalIpAddress": _nested(values, ("ingress", "externalIpAddress")),
        }
        for field, address in fields.items():
            if address is not None:
                usage.setdefault(str(address), []).append((cluster, field))
    duplicates = {}
    current = environment.workload_clusters or ()
    for address, uses in usage.items():
        clusters = {cluster for cluster, _ in uses}
        if len(clusters) > 1 and any(cluster in current for cluster in clusters):
            duplicates[address] = uses
    if values_parse_errors:
        results.append(_unknown("workload.address_uniqueness", "workload", "CCI-MOC/oac-apps", "hosted-clusters/", "One or more hosted-cluster values files could not be parsed: " + ", ".join(values_parse_errors) + ".", "No address used by another cluster"))
    elif not duplicates:
        results.append(_result("workload.address_uniqueness", "workload", "CCI-MOC/oac-apps", "hosted-clusters/", "declared_in_main", "info", "No address used by another cluster", usage, "No workload address is used by another cluster."))
    else:
        other_clusters = sorted({cluster for uses in duplicates.values() for cluster, _ in uses if cluster not in current})
        results.append(_result("workload.address_uniqueness", "workload", "CCI-MOC/oac-apps", "hosted-clusters/", "value_mismatch", "blocking", "No address used by another cluster", duplicates, "Workload addresses are also used by: " + ", ".join(other_clusters) + ".", {"duplicates": duplicates}))
    return results


def cross_repository_checks(
    client: GitHubClient,
    environment: Environment,
    infra: InfraObservation,
    apps: AppsObservation,
    progress: ProgressCallback | None = None,
) -> list[CheckResult]:
    """Build all cross-repository prerequisite checks."""

    results: list[CheckResult] = [ _realm_check(client, environment.infra_cluster, "hub", progress) ]
    for workload in environment.workload_clusters or ():
        results.append(_realm_check(client, workload, "workload", progress))
    results.extend(_moc_aws_checks(client, environment, progress))
    hub_values = infra.hub_variables.values.value
    if not isinstance(hub_values, dict):
        hub_values = {}
    dns = _dns_records_check(client, environment, hub_values, progress)
    if dns:
        results.append(dns)
    hub_defaults_path = f"hosted-clusters/{environment.infra_cluster}/values.yaml"
    hub_values_file = None
    if hub_defaults_path in apps.paths.value:
        try:
            parsed = yaml.safe_load(apps.files.get(hub_defaults_path, "")) if hasattr(apps, "files") else None
            hub_values_file = parsed if isinstance(parsed, dict) else None
        except yaml.YAMLError:
            hub_values_file = None
    results.extend(_workload_value_checks(client, environment, infra, apps, hub_values, hub_values_file, progress))
    return results
