"""Cross-repository prerequisite observations and checks."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import yaml

from .github import GitHubClient, GitHubError, github_url
from .model import CheckResult, Environment
from .observed import (
    AppsObservation, HARDWARE_NETWORK_DOC_PATH, INVENTORY_PATH, InfraObservation,
)
from . import feature_charts
from .repositories import (
    ANSIBLE_SWITCHES_REPOSITORY,
    EVERPURE_REPOSITORY,
    MOC_AWS_REPOSITORY,
    MOC_DNS_REPOSITORY,
    OAC_APPS_REPOSITORY,
    OAC_INFRA_REPOSITORY,
)

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
        client.resolve_commit(repository)
        return client.get_file(repository, path), None
    except GitHubError as exc:
        if "(404)" in str(exc):
            return None, f"{repository}/{path} is absent or unavailable."
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


def _field_names_cluster(value: Any, cluster: str) -> bool:
    """Match a whole cluster token, not a substring of a longer name."""

    if not isinstance(value, str) or not value:
        return False
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(cluster)}(?![A-Za-z0-9])",
        value,
    ) is not None


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
    cluster: str,
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
        cluster=cluster,
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
    "workload.identity_provider": "Workload identity provider",
    "hub.moc_dns_records": "Hub moc-dns records",
    "workload.api_address_network": "Workload API address network",
    "workload.ingress_address_network": "Workload ingress address network",
    "workload.address_uniqueness": "Workload address uniqueness",
    "workload.address_internal_duplicates": "Workload internal address duplicates",
    "workload.dns_base_domain": "Workload DNS base domain",
    "workload.node_pool_hosts": "Workload node-pool host capacity",
    "workload.gpu_without_hosts": "Workload GPU feature support",
    "workload.feature_placements": "Workload feature placements",
    "workload.feature_chart_values": "Workload feature chart values",
}


def _result(
    check_id: str,
    scope: str,
    cluster: str,
    repository: str,
    path: str,
    state: str,
    severity: str,
    expected: Any,
    actual: Any,
    reason: str,
    missing: Any = None,
    evidence: dict[str, Any] | None = None,
    next_action: str | None = None,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage="Cross-repository prerequisites",
        check=_CHECK_LABELS[check_id],
        scope=scope,
        cluster=cluster,
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
        next_action=(
            next_action
            if next_action is not None
            else None
            if state == "declared_in_main"
            else _NEXT_ACTION[check_id]
        ),
    )


_NEXT_ACTION = {
    "hub.pure_storage_realm": "Add or correct the hub realm in everpure-moc realms.yaml.",
    "workload.pure_storage_realm": "Add or correct the workload realm in everpure-moc realms.yaml.",
    "hub.moc_aws_oidc_cluster": "Add or correct the hub entry in moc-aws local.openshift_oidc_clusters.",
    "workload.moc_aws_oidc_cluster": "Add or correct the workload entry in moc-aws local.openshift_oidc_clusters.",
    "hub.moc_aws_cert_manager_policy": "Add a cert-manager policy entry for the hub.",
    "workload.moc_aws_cert_manager_policy": "Add a cert-manager policy entry for the workload.",
    "hub.moc_aws_hosted_secret_prefix": "Add cluster/<hub>/hostedcluster/ to the hub's eso_writable_secret_prefixes.",
    "workload.keycloak_oidc_client": "Merge and apply the workload Keycloak OIDC client in CCI-MOC/moc-keycloak BEFORE enabling oauth.mocsso.enabled; the hosted cluster waits on the client secret.",
    "workload.identity_provider": "Re-enable oauth.mocsso.enabled or add the Keycloak OIDC client in moc-keycloak first.",
    "hub.moc_dns_records": "Add or correct api, api-int, and *.apps records in moc-dns.",
    "workload.api_address_network": "Move services.APIServer.ipAddress into the hub machine network.",
    "workload.ingress_address_network": "Move ingress.poolAddress outside the hub machine network and into the workload VLAN.",
    "workload.address_uniqueness": "Assign addresses that are not used by another cluster.",
    "workload.address_internal_duplicates": "Assign distinct addresses to the workload's own address fields.",
    "workload.dns_base_domain": "Use dns.records hostnames under the hub baseDomain.",
    "workload.node_pool_hosts": "Add matching inventory hosts or reduce node-pool replicas.",
    "workload.gpu_without_hosts": "Disable feature-gpu or add GPU hosts to the workload inventory.",
    "workload.feature_placements": "Add the missing placement to values/<hub>/local-cluster/acm-placements.yaml or remove the stale feature label.",
    "workload.feature_chart_values": "Set the missing required chart values, add the kustomize overlay, or remove values files for charts the cluster does not receive.",
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
        return _unknown(check_id, scope, cluster, EVERPURE_REPOSITORY, EVERPURE_PATH, parse_error or "realms.yaml does not contain a realms list.", {"name": cluster})
    realms = [item for item in data["realms"] if isinstance(item, dict) and item.get("name") == cluster]
    expected = {"name": cluster, "fields": ["subnet_vlan", "subnet_prefix", "s3_endpoint"]}
    if not realms:
        return _result(check_id, scope, cluster, EVERPURE_REPOSITORY, EVERPURE_PATH, "missing", "blocking", expected, None, f"No Pure storage realm named {cluster} was found.", {"realms": [cluster]})
    realm = realms[0]
    missing = [field for field in ("subnet_vlan", "subnet_prefix", "s3_endpoint") if realm.get(field) is None]
    observed = {field: realm.get(field) for field in ("subnet_vlan", "subnet_prefix", "s3_endpoint")}
    if missing:
        return _result(check_id, scope, cluster, EVERPURE_REPOSITORY, EVERPURE_PATH, "partial", "blocking", expected, observed, f"The {cluster} realm is missing: {', '.join(missing)}.", {"fields": missing}, {"realm": realm})
    return _result(check_id, scope, cluster, EVERPURE_REPOSITORY, EVERPURE_PATH, "declared_in_main", "info", expected, observed, f"The {cluster} Pure storage realm reports subnet_vlan, subnet_prefix and s3_endpoint.", evidence={"realm": observed})


def _moc_aws_checks(
    client: GitHubClient,
    environment: Environment,
    progress: ProgressCallback | None,
    hub_values_file: dict[str, Any] | None = None,
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
            results.append(_unknown(oidc_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, block_error, {"cluster_name": cluster}))
            continue
        matches = [body for _, body in blocks if _hcl_string(body, "cluster_name") == cluster]
        expected = {"cluster_name": cluster}
        if not matches:
            results.append(_result(oidc_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "missing", "blocking", expected, None, f"No moc-aws OIDC cluster entry has cluster_name {cluster}."))
        else:
            observed = {"cluster_name": _hcl_string(matches[0], "cluster_name"), "eso_writable_secret_prefixes": _hcl_strings(matches[0], "eso_writable_secret_prefixes")}
            results.append(_result(oidc_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "declared_in_main", "info", expected, observed, f"The moc-aws OIDC cluster entry for {cluster} is present."))

        cert_id = f"{scope}.moc_aws_cert_manager_policy"
        if cert_block_error:
            results.append(_unknown(cert_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, cert_block_error, {"cluster": cluster}))
            continue
        cert_matches = [
            (name, body)
            for name, body in cert_blocks
            if _field_names_cluster(
                _hcl_string(body, "cluster_subdomain"), cluster
            )
            or _field_names_cluster(_hcl_string(body, "policy_name"), cluster)
            or _field_names_cluster(
                _hcl_string(body, "policy_name"),
                cluster.replace("-", "_"),
            )
        ]
        if not cert_matches:
            expected_policy: dict[str, Any] = {"cluster": cluster}
            if scope == "workload":
                domain = (hub_values_file or {}).get("hcpExternalDomain")
                expected_policy.update({
                    "zone_name": domain,
                    "cluster_subdomain": f"{cluster}.{domain}" if domain else None,
                    "policy_name": f"cert-manager-{cluster}",
                })
            results.append(_result(cert_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, "missing", "blocking", expected_policy, None, f"No cert-manager policy entry names {cluster}."))
        else:
            name, body = cert_matches[0]
            results.append(_result(cert_id, scope, cluster, MOC_AWS_REPOSITORY, MOC_AWS_CERT_MANAGER, "declared_in_main", "info", {"cluster": cluster}, name, f"The cert-manager policy entry {name} names {cluster} in policy_name or cluster_subdomain.", evidence={"block": body}))

    if environment.workload_clusters:
        prefix = f"cluster/{environment.infra_cluster}/hostedcluster/"
        if block_error:
            results.append(_unknown("hub.moc_aws_hosted_secret_prefix", "hub", environment.infra_cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, block_error, [prefix]))
        else:
            hub = next((body for _, body in blocks if _hcl_string(body, "cluster_name") == environment.infra_cluster), None)
            writable = _hcl_strings(hub, "eso_writable_secret_prefixes") if hub else []
            if prefix in writable:
                results.append(_result("hub.moc_aws_hosted_secret_prefix", "hub", environment.infra_cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "declared_in_main", "info", {"eso_writable_secret_prefix": prefix}, {"eso_writable_secret_prefix": writable}, f"The hub can write hosted-cluster secrets at {prefix}."))
            else:
                results.append(_result("hub.moc_aws_hosted_secret_prefix", "hub", environment.infra_cluster, MOC_AWS_REPOSITORY, MOC_AWS_MAIN, "missing", "blocking", [prefix], writable, f"The hub entry does not list {prefix}; it cannot push hosted-cluster secrets.", {"prefix": prefix}))
    return results


def _dns_records_check(
    client: GitHubClient,
    environment: Environment,
    hub_values: dict[str, Any],
    progress: ProgressCallback | None,
) -> CheckResult | None:
    domain_parts = [hub_values.get("cluster_domain_name"), hub_values.get("base_domain")]
    api_ip, ingress_ip = hub_values.get("api_ip"), hub_values.get("ingress_ip")
    if not all(isinstance(part, str) and part for part in (*domain_parts, api_ip, ingress_ip)):
        return _unknown("hub.moc_dns_records", "hub", environment.infra_cluster, MOC_DNS_REPOSITORY, "zonefiles/", "Hub-image variables required for DNS validation are unavailable.", {"api": api_ip, "api-int": api_ip, "*.apps": ingress_ip})
    domain = ".".join(str(part) for part in domain_parts)
    _progress(progress, "read DNS zonefiles", MOC_DNS_REPOSITORY, "zonefiles/")
    try:
        tree = client.get_tree(MOC_DNS_REPOSITORY)
        zone_names = sorted(
            path.removeprefix("zonefiles/").removesuffix(".zone")
            for path in tree
            if path.startswith("zonefiles/") and path.endswith(".zone")
        )
        matching_zones = [
            zone for zone in zone_names
            if domain == zone or domain.endswith(f".{zone}")
        ]
        if not matching_zones:
            return _unknown(
                "hub.moc_dns_records",
                "hub",
                environment.infra_cluster,
                MOC_DNS_REPOSITORY,
                "zonefiles/",
                "No DNS zonefile is a suffix of the hub domain.",
                {"domain": domain, "zonefiles": zone_names},
            )
        zone = max(matching_zones, key=len)
        zone_path = f"zonefiles/{zone}.zone"
        text = client.get_file(MOC_DNS_REPOSITORY, zone_path)
    except GitHubError as exc:
        return _unknown("hub.moc_dns_records", "hub", environment.infra_cluster, MOC_DNS_REPOSITORY, "zonefiles/", f"moc-dns could not be read: {exc}", {"domain": domain})
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
        return _result("hub.moc_dns_records", "hub", environment.infra_cluster, MOC_DNS_REPOSITORY, zone_path, "missing", "blocking", expected, observed, "Missing DNS records: " + ", ".join(missing) + ".", {"records": missing})
    if mismatched:
        return _result("hub.moc_dns_records", "hub", environment.infra_cluster, MOC_DNS_REPOSITORY, zone_path, "value_mismatch", "blocking", expected, observed, "One or more DNS records point to the wrong address.", {"records": mismatched})
    return _result(
        "hub.moc_dns_records",
        "hub",
        environment.infra_cluster,
        MOC_DNS_REPOSITORY,
        zone_path,
        "declared_in_main",
        "info",
        expected,
        observed,
        f"All required hub DNS records in {zone_path} match the hub-image variables.",
        evidence={"zone": zone, "zonefile": zone_path, "records": observed},
    )


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


def _evaluate_keycloak_client(
    client: GitHubClient,
    environment: Environment,
    workload: str,
    hub_values_file: dict[str, Any] | None,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    """Read moc-keycloak main.tf once and compare the workload client."""

    external_domain = (hub_values_file or {}).get("hcpExternalDomain")
    if not isinstance(external_domain, str) or not external_domain:
        return {
            "error": "hcpExternalDomain is unavailable from the hub hosted-cluster defaults.",
        }
    text, error = _read_file(client, "CCI-MOC/moc-keycloak", "main.tf", progress)
    blocks, block_error = _hcl_blocks(text, error)
    if text is not None and not blocks:
        block_error = "CCI-MOC/moc-keycloak/main.tf did not contain readable HCL blocks."
    if block_error:
        return {"error": block_error}
    expected = {
        "cluster_name": workload,
        "openshift_redirect_uri": f"https://oauth-{workload}.{external_domain}:443/oauth2callback/mocsso",
        "client_secret_name": f"cluster/{environment.infra_cluster}/hostedcluster/{workload}/keycloak-oidc",
    }
    block = next((body for _, body in blocks if _hcl_string(body, "cluster_name") == workload), None)
    observed = {key: _hcl_string(block, key) if block else None for key in expected}
    nonmatching = [key for key, value in expected.items() if observed[key] != value]
    return {
        "expected": expected,
        "observed": observed,
        "block": block,
        "nonmatching": nonmatching,
        "matches": block is not None and not nonmatching,
        "error": None,
    }


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
    evaluation = _evaluate_keycloak_client(
        client, environment, workload, hub_values_file, progress
    )
    if evaluation["error"]:
        return _unknown("workload.keycloak_oidc_client", "workload", workload, "CCI-MOC/moc-keycloak", "main.tf", evaluation["error"], {})
    expected = evaluation["expected"]
    observed = evaluation["observed"]
    block = evaluation["block"]
    nonmatching = evaluation["nonmatching"]
    if block and not nonmatching:
        return _result("workload.keycloak_oidc_client", "workload", workload, "CCI-MOC/moc-keycloak", "main.tf", "declared_in_main", "info", expected, observed, f"The Keycloak OIDC client for {workload} matches cluster_name, openshift_redirect_uri and client_secret_name.")
    state = "missing" if block is None else "value_mismatch"
    return _result("workload.keycloak_oidc_client", "workload", workload, "CCI-MOC/moc-keycloak", "main.tf", state, "blocking", expected, observed, f"The Keycloak OIDC client for {workload} is absent or mismatched.", {"fields": nonmatching}, {"block": block})


def _open_keycloak_pulls(apps: AppsObservation) -> list[str]:
    """Name open moc-keycloak pull requests that touch main.tf."""

    labels = []
    for pull in getattr(apps, "pull_requests", ()):
        if (
            pull.repository.value == "CCI-MOC/moc-keycloak"
            and pull.classification.value == "open"
            and any(
                path == "main.tf"
                for path in pull.changed_files.value
            )
        ):
            labels.append(f"moc-keycloak#{pull.number.value}")
    return labels


def _identity_provider_check(
    client: GitHubClient,
    environment: Environment,
    workload: str,
    values: dict[str, Any] | None,
    hub_values_file: dict[str, Any] | None,
    apps: AppsObservation,
    progress: ProgressCallback | None,
) -> CheckResult | None:
    """Check that mocsso and the Keycloak OIDC client agree."""

    if values is None:
        return None
    mocsso_enabled = _nested(values, ("oauth", "mocsso", "enabled"))
    enabled = mocsso_enabled is True
    identity_providers = _nested(values, ("oauth", "identityProviders"))
    if (
        not enabled
        and isinstance(identity_providers, list)
        and identity_providers
    ):
        path = (
            f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
        )
        return _result(
            "workload.identity_provider",
            "workload",
            workload,
            "CCI-MOC/oac-apps",
            path,
            "declared_in_main",
            "info",
            {
                "oauth.mocsso.enabled": False,
                "oauth.identityProviders": identity_providers,
            },
            {
                "oauth.mocsso.enabled": mocsso_enabled,
                "oauth.identityProviders": identity_providers,
            },
            "oauth.mocsso.enabled is false or absent, but an explicit identity "
            "provider is configured in oauth.identityProviders, so the cluster "
            "has an identity provider.",
            evidence={"identity_providers": identity_providers},
        )
    evaluation = _evaluate_keycloak_client(
        client, environment, workload, hub_values_file, progress
    )
    if evaluation["error"]:
        return _unknown(
            "workload.identity_provider",
            "workload",
            workload,
            "CCI-MOC/moc-keycloak",
            "main.tf",
            evaluation["error"],
            {"oauth.mocsso.enabled": True, "keycloak_oidc_client": "matching"},
        )
    matches = evaluation["matches"]
    expected = {"oauth.mocsso.enabled": True}
    client_fields = {
        name: {
            "expected": value,
            "observed": evaluation["observed"].get(name),
        }
        for name, value in evaluation["expected"].items()
    }
    if enabled and matches:
        return _result(
            "workload.identity_provider",
            "workload",
            workload,
            "CCI-MOC/moc-keycloak",
            "main.tf",
            "declared_in_main",
            "info",
            expected,
            {"oauth.mocsso.enabled": True, "keycloak_oidc_client": "matches"},
            f"mocsso is enabled and the Keycloak OIDC client for {workload} matches "
            "cluster_name, openshift_redirect_uri and client_secret_name.",
            evidence={"client_fields": client_fields},
        )
    if enabled:
        state = "missing" if evaluation["block"] is None else "value_mismatch"
        result = _result(
            "workload.identity_provider",
            "workload",
            workload,
            "CCI-MOC/moc-keycloak",
            "main.tf",
            state,
            "advisory",
            expected,
            {
                "oauth.mocsso.enabled": True,
                "keycloak_oidc_client": (
                    "missing" if evaluation["block"] is None else "mismatched"
                ),
            },
            f"mocsso is enabled but workload.keycloak_oidc_client reports the "
            f"Keycloak OIDC client for {workload} as absent or mismatched.",
            evidence={
                "keycloak_oidc_client": "missing or mismatched",
                "client_fields": client_fields,
            },
        )
        return replace(
            result,
            state="blocked",
            next_action=None,
        )
    if matches:
        next_action = "re-enable oauth.mocsso.enabled."
        client_state = "matches"
    else:
        pulls = _open_keycloak_pulls(apps)
        next_action = "add the client in moc-keycloak first."
        if pulls:
            next_action += " Open PR: " + ", ".join(pulls) + "."
        client_state = "missing" if evaluation["block"] is None else "mismatched"
    return _result(
        "workload.identity_provider",
        "workload",
        workload,
        "CCI-MOC/moc-keycloak",
        "main.tf",
        "value_mismatch",
        "advisory",
        expected,
        {"oauth.mocsso.enabled": False, "keycloak_oidc_client": client_state},
        "mocsso is disabled; the cluster has no identity provider.",
        {"oauth.mocsso.enabled": True},
        evidence={"client_fields": client_fields},
        next_action=next_action,
    )


def _address_in(value: Any, network: Any) -> bool:
    try:
        address = (
            ipaddress.ip_interface(value).ip
            if isinstance(value, str) and "/" in value
            else ipaddress.ip_address(value)
        )
        return address in ipaddress.ip_network(network, strict=False)
    except (ValueError, TypeError):
        return False


def _is_address_or_interface(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        if "/" in value:
            ipaddress.ip_interface(value)
        else:
            ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _address_key(value: Any) -> str:
    """Normalize an address for comparison; compare literals when unparseable."""

    text = str(value)
    try:
        if "/" in text:
            return str(ipaddress.ip_interface(text).ip)
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text


def _workload_vlan(vlans: list[Any], workload: str) -> dict[str, Any] | None:
    """Match a full workload name, allowing documented network-name aliases."""

    def normalized(name: str) -> str:
        return "-".join(
            "PROD" if part == "PRODUCTION" else part
            for part in name.upper().split("-")
        )

    exact_name = normalized(workload)
    shared_name = re.sub(r"(?<=WORKLOAD)\d+$", "", exact_name)
    for name in dict.fromkeys((exact_name, shared_name)):
        matches = [
            item
            for item in vlans
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and normalized(item["name"]) == name
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _oac_apps_tree(
    client: GitHubClient, progress: ProgressCallback | None
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    try:
        return client.get_tree(OAC_APPS_REPOSITORY), None
    except GitHubError as exc:
        return None, f"{OAC_APPS_REPOSITORY} tree could not be read: {exc}"


def _placement_paths(
    tree: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Map each hub with placements files to its local and hub-wide paths."""

    return feature_charts.placement_file_paths(tree)


def _read_cached(
    client: GitHubClient,
    path: str,
    cache: dict[str, str | None],
    progress: ProgressCallback | None,
) -> tuple[str | None, str | None]:
    if path in cache:
        text = cache[path]
        return text, None if text is not None else f"{path} is unavailable."
    try:
        text, error = _read_file(client, OAC_APPS_REPOSITORY, path, progress)
    except (GitHubError, AssertionError) as exc:
        # A missing or unreadable fixture must make the feature check unknown,
        # not abort the whole status run.
        text, error = None, f"{path} could not be read: {exc}"
    cache[path] = text
    return text, error


def _load_placements(
    client: GitHubClient,
    paths: dict[str, str],
    cache: dict[str, str | None],
    progress: ProgressCallback | None,
) -> tuple[list[feature_charts.Placement] | None, str | None]:
    """Load local-cluster placements over any hub-wide placements file."""

    return feature_charts.load_placements(
        paths, lambda path: _read_cached(client, path, cache, progress)
    )


def _load_application_sets(
    client: GitHubClient,
    tree: dict[str, dict[str, Any]],
    cache: dict[str, str | None],
    progress: ProgressCallback | None,
) -> tuple[list[feature_charts.ApplicationSet], list[str]]:
    return feature_charts.load_application_sets(
        tree, lambda path: _read_cached(client, path, cache, progress)
    )


def _feature_placement_check(
    hub: str,
    workload: str,
    labels: Any,
    placements: list[feature_charts.Placement],
    placements_by_hub: dict[str, list[feature_charts.Placement]],
    path: str,
) -> CheckResult:
    feature = feature_charts.feature_labels(labels)
    matched = feature_charts.matched_placement_names(placements, labels)
    unused: list[str] = []
    missing_on_hub: dict[str, list[str]] = {}
    for label in feature:
        if any(
            label in placement.match_labels
            and feature_charts.labels_match(placement.match_labels, labels)
            for placement in placements
        ):
            continue
        other_hubs = [
            f"{other_hub}:{placement.name}"
            for other_hub, other_placements in placements_by_hub.items()
            if other_hub != hub
            for placement in other_placements
            if label in placement.match_labels
            and feature_charts.labels_match(placement.match_labels, labels)
        ]
        if other_hubs:
            missing_on_hub[label] = sorted(dict.fromkeys(other_hubs))
        else:
            unused.append(label)
    evidence = {
        "matched_placements": matched,
        "unused_labels": unused,
        "missing_on_hub": missing_on_hub,
        "feature_labels": feature,
    }
    expected = {
        "feature_labels": sorted(feature),
        "placement": "a matching placement on this hub",
    }
    if missing_on_hub:
        details = "; ".join(
            f"{label} is defined by {', '.join(origins)} in another hub"
            for label, origins in missing_on_hub.items()
        )
        return _result(
            "workload.feature_placements",
            "workload",
            workload,
            OAC_APPS_REPOSITORY,
            path,
            "value_mismatch",
            "blocking",
            expected,
            {"unused_labels": unused, "missing_on_hub": missing_on_hub},
            f"This hub's placements file is missing an entry: {details}.",
            evidence=evidence,
        )
    matched_text = ", ".join(matched)
    reason = (
        f"Matched placements: {matched_text}. "
        f"unused_labels: {json.dumps(unused)}."
    )
    return _result(
        "workload.feature_placements",
        "workload",
        workload,
        OAC_APPS_REPOSITORY,
        path,
        "declared_in_main",
        "info",
        expected,
        {"matched_placements": matched, "unused_labels": unused},
        reason,
        evidence=evidence,
    )


def _feature_chart_values_next_action(
    evidence: dict[str, Any], hub: str, workload: str
) -> str:
    """Describe only the problems present in one chart-values check."""

    clauses: list[str] = []
    unmet = evidence.get("unmet_required_values") or {}
    if unmet:
        paths = ", ".join(
            f"values/{hub}/{workload}/{chart}.yaml" for chart in unmet
        )
        clauses.append(f"set the missing required chart values in {paths}")
    if evidence.get("missing_overlays"):
        clauses.append("add the kustomize overlay")
    if evidence.get("orphan_values_files"):
        clauses.append(
            "remove the values files for charts the cluster does not receive"
        )
    if not clauses:
        return _NEXT_ACTION["workload.feature_chart_values"]
    text = (
        clauses[0]
        if len(clauses) == 1
        else ", ".join(clauses[:-1]) + " and " + clauses[-1]
    )
    return text[:1].upper() + text[1:] + "."


def _feature_chart_values_check(
    client: GitHubClient,
    tree: dict[str, dict[str, Any]],
    hub: str,
    workload: str,
    labels: Any,
    placements: list[feature_charts.Placement],
    application_sets: list[feature_charts.ApplicationSet],
    path: str,
    cache: dict[str, str | None],
    progress: ProgressCallback | None,
) -> CheckResult:
    matched = feature_charts.matched_placement_names(placements, labels)
    rows = feature_charts.workload_chart_rows(
        tree,
        hub,
        workload,
        labels,
        placements,
        application_sets,
        lambda item: _read_cached(client, item, cache, progress),
    )

    missing_overlays: list[str] = []
    for application_set in application_sets:
        if application_set.placement not in matched:
            continue
        if not application_set.kustomize_path:
            continue
        prefix = feature_charts.kustomize_overlay_prefix(
            application_set.kustomize_path, workload
        )
        if not any(path.startswith(prefix) for path in tree):
            missing_overlays.append(prefix.rstrip("/"))

    received = {row["chart"] for row in rows}
    cluster_prefix = f"values/{hub}/{workload}/"
    orphans = sorted(
        path[len(cluster_prefix) : -len(".yaml")]
        for path in tree
        if path.startswith(cluster_prefix)
        and path.endswith(".yaml")
        and "/" not in path[len(cluster_prefix) :]
        and path[len(cluster_prefix) : -len(".yaml")] not in received
    )

    total = len(rows)
    components = sum(bool(row["component"]) for row in rows)
    literal_names = [
        str(row["chart"]) for row in rows if not row["component"]
    ]
    if literal_names:
        count_text = (
            f"{total} charts received ({components} component charts plus "
            f"{', '.join(literal_names)})"
        )
    else:
        count_text = f"{total} chart{'s' if total != 1 else ''} received"
    findings = [
        f"{row['chart']} unmet required values: "
        + ", ".join(row["unmet_required_values"])
        for row in rows
        if row["unmet_required_values"]
    ]
    findings.extend(f"missing overlay: {overlay}" for overlay in missing_overlays)
    evidence = {
        "charts": rows,
        "chart_count": total,
        "component_chart_count": components,
        "unmet_required_values": {
            str(row["chart"]): row["unmet_required_values"]
            for row in rows
            if row["unmet_required_values"]
        },
        "missing_overlays": missing_overlays,
        "orphan_values_files": orphans,
        "matched_placements": matched,
    }
    expected = {
        "received_charts": "every chart selected by a placement on this hub",
        "required_values": "every required .Values call outside template blocks",
    }
    if findings:
        return _result(
            "workload.feature_chart_values",
            "workload",
            workload,
            OAC_APPS_REPOSITORY,
            path,
            "missing",
            "blocking",
            expected,
            {"findings": findings},
            f"{count_text}. " + "; ".join(findings) + ".",
            missing={"findings": findings},
            evidence=evidence,
            next_action=_feature_chart_values_next_action(evidence, hub, workload),
        )
    if orphans:
        return _result(
            "workload.feature_chart_values",
            "workload",
            workload,
            OAC_APPS_REPOSITORY,
            path,
            "value_mismatch",
            "advisory",
            expected,
            {"orphan_values_files": orphans},
            f"{count_text}. Values files are present for charts the cluster "
            "does not receive: " + ", ".join(orphans) + ".",
            missing={"orphan_values_files": orphans},
            evidence=evidence,
            next_action=_feature_chart_values_next_action(evidence, hub, workload),
        )
    return _result(
        "workload.feature_chart_values",
        "workload",
        workload,
        OAC_APPS_REPOSITORY,
        path,
        "declared_in_main",
        "info",
        expected,
        {"charts": total},
        f"{count_text}; all required values are set and every kustomize "
        "overlay exists.",
        evidence=evidence,
    )


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
    base_domain = (hub_values_file or {}).get("baseDomain")
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

    apps_tree, apps_tree_error = _oac_apps_tree(client, progress)
    placements_by_hub: dict[str, list[feature_charts.Placement]] = {}
    placement_errors: dict[str, str] = {}
    application_sets: list[feature_charts.ApplicationSet] = []
    application_set_errors: list[str] = []
    oac_file_cache: dict[str, str | None] = {}
    if apps_tree is not None:
        for hub_name, hub_paths in _placement_paths(apps_tree).items():
            placements, placement_error = _load_placements(
                client, hub_paths, oac_file_cache, progress
            )
            if placements is None:
                placement_errors[hub_name] = (
                    placement_error or "acm-placements.yaml is unavailable."
                )
            else:
                placements_by_hub[hub_name] = placements
        application_sets, application_set_errors = _load_application_sets(
            client, apps_tree, oac_file_cache, progress
        )

    for workload in environment.workload_clusters or ():
        path = f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
        values, values_error = _workload_values(apps, environment, workload)
        if values is None:
            results.extend([
                _unknown(
                    check_id,
                    "workload",
                    workload,
                    "CCI-MOC/oac-apps",
                    path,
                    values_error or "Workload values are unavailable.",
                    {},
                )
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
            results.append(_result("workload.api_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected, api_ip, "The API address is inside the hub machine network."))
        else:
            results.append(_result("workload.api_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected, api_ip, "The API address is not inside the hub machine network."))

        if not vlans_available:
            results.append(_unknown("workload.ingress_address_network", "workload", workload, ANSIBLE_SWITCHES_REPOSITORY, ANSIBLE_SWITCHES_VLANS, vlans_error or vlans_parse or "vlans.yaml does not contain a vlans list.", {}))
        else:
            pool = _nested(values, ("ingress", "poolAddress"))
            vlan = _workload_vlan(vlans, workload)
            expected_pool = {
                "poolAddress": pool,
                "machine_network": machine_network,
                "vlan_name": vlan.get("name") if vlan else None,
                "vlan_subnet": vlan.get("subnet4") if vlan else None,
            }
            if pool is None:
                results.append(_result("workload.ingress_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "missing", "blocking", expected_pool, None, "The ingress pool address is absent from ingress.poolAddress."))
            elif not _is_address_or_interface(pool):
                results.append(_result("workload.ingress_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected_pool, pool, f"The ingress pool address {pool!r} is not a valid IP address or interface."))
            elif vlan is None:
                results.append(_unknown("workload.ingress_address_network", "workload", workload, "CCI-MOC/oac-apps", path, f"No VLAN matched {workload}, so ingress pool address membership could not be checked.", expected_pool))
            else:
                vlan_reason = f" Selected VLAN {vlan['name']} ({vlan.get('subnet4')})."
                if not _address_in(pool, machine_network) and _address_in(pool, vlan.get("subnet4")):
                    results.append(_result("workload.ingress_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected_pool, pool, "The ingress pool address is on the expected network." + vlan_reason))
                else:
                    results.append(_result("workload.ingress_address_network", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected_pool, pool, "The ingress pool address is on the wrong network." + vlan_reason))

        hostnames = [record.get("hostname") for record in (_nested(values, ("dns", "records")) or []) if isinstance(record, dict)]
        external_domain = (hub_values_file or {}).get("hcpExternalDomain")
        valid_domains = tuple(
            domain
            for domain in (base_domain, external_domain)
            if isinstance(domain, str) and domain
        )
        invalid = [
            name
            for name in hostnames
            if not isinstance(name, str)
            or not any(
                name.rstrip(".").lower().endswith("." + domain.rstrip(".").lower())
                for domain in valid_domains
            )
        ]
        expected_domains = {"baseDomain": base_domain, "hcpExternalDomain": external_domain}
        if not valid_domains:
            results.append(_unknown("workload.dns_base_domain", "workload", workload, "CCI-MOC/oac-apps", path, "Hosted-cluster baseDomain and hcpExternalDomain are unavailable from the hub hosted-cluster defaults.", expected_domains))
        elif not invalid:
            reason = (
                "All DNS record hostnames use the hub hosted-cluster domains."
                if hostnames
                else "No dns.records are declared, so there are no hostnames to compare."
            )
            results.append(_result("workload.dns_base_domain", "workload", workload, "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected_domains, hostnames, reason))
        else:
            results.append(_result("workload.dns_base_domain", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected_domains, hostnames, "Some DNS record hostnames do not use the hub hosted-cluster domains.", {"hostnames": invalid}))

        cluster_observation = infra.clusters.get(workload)
        hosts = cluster_observation.hosts.value if cluster_observation else []
        pools = values.get("nodePools")
        pool_results: list[dict[str, Any]] = []
        pool_errors: list[str] = []
        if pools is None:
            pools = []
        elif not isinstance(pools, list):
            pool_errors.append(
                "nodePools must be a list of pool mappings; "
                f"got {type(pools).__name__}."
            )
            pools = []

        for index, pool_item in enumerate(pools):
            if not isinstance(pool_item, dict):
                pool_errors.append(
                    f"nodePools[{index}] must be a mapping; "
                    f"got {type(pool_item).__name__}."
                )
                continue
            raw_name = pool_item.get("name")
            pool_name = raw_name
            if raw_name is not None and not isinstance(raw_name, str):
                pool_errors.append(
                    f"nodePools[{index}].name must be a string when provided; "
                    f"got {type(raw_name).__name__}."
                )
                pool_name = repr(raw_name)
            selector = pool_item.get("agentLabelSelector", {})
            if selector is None:
                selector = {}
            if not isinstance(selector, dict):
                pool_errors.append(
                    f"nodePools[{index}].agentLabelSelector must be a mapping."
                )
                selector = {}
            invalid_selector_keys = [
                key for key, value in selector.items()
                if not isinstance(key, str) or not isinstance(value, str)
            ]
            if invalid_selector_keys:
                pool_errors.append(
                    f"nodePools[{index}].agentLabelSelector values must be strings; "
                    f"invalid keys: {', '.join(map(str, invalid_selector_keys))}."
                )
            raw_replicas = pool_item.get("replicas", 0)
            replicas: int | None
            if isinstance(raw_replicas, bool):
                replicas = None
            elif isinstance(raw_replicas, int):
                replicas = raw_replicas if raw_replicas >= 0 else None
            elif isinstance(raw_replicas, str) and re.fullmatch(r"[0-9]+", raw_replicas.strip()):
                try:
                    replicas = int(raw_replicas.strip())
                except ValueError:
                    replicas = None
            else:
                replicas = None
            if replicas is None:
                pool_errors.append(
                    f"nodePools[{index}].replicas must be a non-negative integer; "
                    f"got {raw_replicas!r}."
                )
                replicas = 0
            documented = infra.hardware_resource_classes.value

            resource_keys = {"resource_class", "openstack/resource-class"}
            required_classes = [
                value for key, value in selector.items()
                if key in resource_keys and isinstance(value, str)
            ]
            candidates = [
                host for host in hosts
                if all(
                    host.get("cluster" if key == "massopen.cloud/cluster" else key) == value
                    for key, value in selector.items()
                    if key not in resource_keys and isinstance(value, str)
                )
            ]
            matching = 0
            unclassified = 0
            unclassified_names: list[str] = []
            notes: list[str] = []
            bases: set[str] = set()
            matching_bases: set[str] = set()
            for host in candidates:
                inventory_class = host.get("resource_class")
                documented_class = documented.get(host.get("node_name"))
                if not required_classes:
                    basis = "inventory"
                    matches = True
                elif inventory_class is not None:
                    # Explicit inventory data is authoritative, even when the
                    # documentation would otherwise match the selector.
                    basis = "inventory"
                    matches = all(inventory_class == value for value in required_classes)
                elif host.get("bm_management") != "openstack":
                    basis = "inventory"
                    matches = False
                    host_name = host.get("node_name") or host.get("name") or "unnamed host"
                    notes.append(
                        f"{host_name}: no resource_class in the inventory, so "
                        "update-agents.yaml will not label it; see workload.agent_labels_inputs."
                    )
                elif isinstance(documented_class, str) and documented_class:
                    basis = "documented class"
                    matches = all(
                        value == documented_class or value.endswith("-" + documented_class)
                        for value in required_classes
                    )
                else:
                    unclassified += 1
                    unclassified_names.append(
                        host.get("node_name") or host.get("name") or "unnamed host"
                    )
                    continue
                bases.add(basis)
                if matches:
                    matching += 1
                    matching_bases.add(basis)
            pool_state = (
                "declared_in_main" if matching >= replicas
                else "value_mismatch" if matching + unclassified < replicas
                else "unknown"
            )
            pool_result: dict[str, Any] = {
                "name": pool_name,
                "replicas": replicas,
                "matching_hosts": matching if bases or pool_state != "unknown" else None,
                "classified_hosts": len(candidates) - unclassified,
                "unclassified_hosts": unclassified,
                "basis": ", ".join(sorted(matching_bases or bases)) or (
                    None if unclassified else "inventory"
                ),
                "state": pool_state,
            }
            if required_classes:
                pool_result["required_class"] = ", ".join(required_classes)
            if pool_state == "value_mismatch":
                pool_result["reason"] = (
                    f"Pool {pool_name or index} requires {replicas} "
                    f"{'host' if replicas == 1 else 'hosts'}: "
                    f"{matching} confirmed matching {'host' if matching == 1 else 'hosts'}"
                )
                if unclassified:
                    pool_result["reason"] += (
                        f"; {unclassified} unclassified {'host' if unclassified == 1 else 'hosts'}. "
                        "The pool is short even if every unclassified host matched."
                    )
                else:
                    pool_result["reason"] += "."
            if unclassified and pool_state == "declared_in_main":
                notes.append(
                    f"{unclassified} unclassified hosts ({', '.join(unclassified_names)}); "
                    "enough confirmed matching hosts are already available."
                )
            if notes and pool_state == "value_mismatch":
                pool_result["reason"] += " " + " ".join(notes)
            elif notes:
                pool_result["notes"] = notes
            if pool_state == "unknown":
                required_class = ", ".join(required_classes)
                count = f"{matching} confirmed matching hosts; " if bases else ""
                pool_result["reason"] = (
                    f"Pool {pool_name or index} requires resource class {required_class}: "
                    f"{count}{unclassified} hosts matched the cluster selector but could not "
                    f"be classified. No resource_class on these hosts in "
                    f"{OAC_INFRA_REPOSITORY}/{INVENTORY_PATH}, and no documented class "
                    f"for them in {OAC_INFRA_REPOSITORY}/{HARDWARE_NETWORK_DOC_PATH}. "
                    "The hosts' actual resource-class labels are held in OpenStack "
                    "and are not recorded in the repositories."
                )
            pool_results.append(pool_result)
        unknown_reasons = [item["reason"] for item in pool_results if item["state"] == "unknown"]
        shortage_reasons = [
            item["reason"] for item in pool_results if item["state"] == "value_mismatch"
        ]
        shortages = bool(shortage_reasons)
        if not pool_errors and not shortages and not unknown_reasons:
            results.append(_result("workload.node_pool_hosts", "workload", workload, "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "declared_in_main", "info", pools, pool_results, "Every node pool has enough matching inventory hosts."))
        elif not pool_errors and not shortages:
            results.append(_result(
                "workload.node_pool_hosts", "workload", workload, OAC_INFRA_REPOSITORY,
                INVENTORY_PATH, "unknown", "advisory", pools, pool_results,
                " ".join(unknown_reasons),
                next_action="Verify the hosts' actual resource-class labels in OpenStack.",
            ))
        else:
            reason = "At least one node pool lacks matching inventory hosts."
            if pool_errors:
                reason = "Malformed nodePools configuration: " + " ".join(pool_errors)
            if shortage_reasons:
                reason += " " + " ".join(shortage_reasons)
            if unknown_reasons:
                reason += " " + " ".join(unknown_reasons)
            results.append(_result("workload.node_pool_hosts", "workload", workload, "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "value_mismatch", "blocking", pools, pool_results, reason))

        gpu_enabled = str(_nested(values, ("clusterLabels", "massopen.cloud/feature-gpu"))).lower() == "true"
        gpu_hosts = [
            host
            for host in hosts
            if host.get("gpu") is True
            or any(
                re.search(r"(?:^|[-_])(?:gpu|a100|h100)(?:[-_]|\d|$)", str(value).lower())
                for value in (
                    host.get("resource_class"),
                    host.get("flavor"),
                    infra.hardware_resource_classes.value.get(host.get("node_name")),
                )
            )
        ]
        gpu_observed = {
            "clusterLabels.massopen.cloud/feature-gpu": str(gpu_enabled).lower(),
            "gpu_host_count": len(gpu_hosts),
        }
        gpu_evidence = {"gpu_hosts": [host.get("name") for host in gpu_hosts]}
        if not gpu_enabled or gpu_hosts:
            results.append(_result("workload.gpu_without_hosts", "workload", workload, "CCI-MOC/oac-apps", path, "declared_in_main", "info", {"gpu_host_count": "At least 1 when clusterLabels.massopen.cloud/feature-gpu is true"}, gpu_observed, "GPU configuration is consistent with the inventory.", evidence=gpu_evidence))
        else:
            results.append(_result("workload.gpu_without_hosts", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "advisory", {"gpu_host_count": "At least 1 when clusterLabels.massopen.cloud/feature-gpu is true"}, gpu_observed, "clusterLabels.massopen.cloud/feature-gpu is true, but no GPU hosts were found in the inventory.", evidence=gpu_evidence))

        placements_path = (
            f"values/{environment.infra_cluster}/local-cluster/acm-placements.yaml"
        )
        placements = placements_by_hub.get(environment.infra_cluster)
        if apps_tree is None:
            feature_unknown = apps_tree_error
        elif environment.infra_cluster in placement_errors:
            feature_unknown = placement_errors[environment.infra_cluster]
        elif environment.infra_cluster not in placements_by_hub:
            feature_unknown = (
                f"values/{environment.infra_cluster}/local-cluster/"
                "acm-placements.yaml is absent or unavailable, so feature "
                "labels cannot be resolved."
            )
        else:
            feature_unknown = None
        chart_values_path = f"values/{environment.infra_cluster}/{workload}"
        if feature_unknown:
            for check_id, check_path in (
                ("workload.feature_placements", placements_path),
                ("workload.feature_chart_values", chart_values_path),
            ):
                results.append(
                    replace(
                        _unknown(
                            check_id,
                            "workload",
                            workload,
                            OAC_APPS_REPOSITORY,
                            check_path,
                            feature_unknown,
                            {
                                "clusterLabels": (
                                    "readable from the workload values file"
                                )
                            },
                        ),
                        severity="info",
                    )
                )
        else:
            labels = values.get("clusterLabels")
            results.append(
                _feature_placement_check(
                    environment.infra_cluster,
                    workload,
                    labels,
                    placements or [],
                    placements_by_hub,
                    placements_path,
                )
            )
            if application_set_errors or not application_sets:
                detail = (
                    "Application-set templates could not be read: "
                    + " ".join(application_set_errors)
                    if application_set_errors
                    else "No managed ApplicationSet templates exist in the oac-apps tree."
                )
                results.append(
                    replace(
                        _unknown(
                            "workload.feature_chart_values",
                            "workload",
                            workload,
                            OAC_APPS_REPOSITORY,
                            chart_values_path,
                            detail,
                            {
                                "charts": (
                                    "every chart selected by a placement on "
                                    "this hub"
                                )
                            },
                        ),
                        severity="info",
                    )
                )
            else:
                results.append(
                    _feature_chart_values_check(
                        client,
                        apps_tree or {},
                        environment.infra_cluster,
                        workload,
                        labels,
                        placements or [],
                        application_sets,
                        chart_values_path,
                        oac_file_cache,
                        progress,
                    )
                )

        keycloak = _keycloak_workload_check(client, environment, workload, values, hub_values_file, progress)
        if keycloak:
            results.append(keycloak)
        identity = _identity_provider_check(
            client, environment, workload, values, hub_values_file, apps, progress
        )
        if identity:
            results.append(identity)

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
    address_rows = []
    for path, values in all_values.items():
        cluster = path.split("/")[2]
        if cluster not in current:
            continue
        own_fields = {
            "services.APIServer.ipAddress": _nested(
                values, ("services", "APIServer", "ipAddress")
            ),
            "ingress.poolAddress": _nested(values, ("ingress", "poolAddress")),
            "services.APIServer.externalIpAddress": _nested(
                values, ("services", "APIServer", "externalIpAddress")
            ),
            "ingress.externalIpAddress": _nested(
                values, ("ingress", "externalIpAddress")
            ),
        }
        for field, address in own_fields.items():
            if address is None:
                continue
            address_rows.append(
                {
                    "cluster": cluster,
                    "field": field,
                    "address": str(address),
                    "used_by_others": sorted(
                        f"{other}: {name}"
                        for other, name in usage.get(str(address), [])
                        if other != cluster
                    ),
                }
            )
    uniqueness_cluster = next(iter(current), environment.infra_cluster)
    if values_parse_errors:
        results.append(_unknown("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "One or more hosted-cluster values files could not be parsed: " + ", ".join(values_parse_errors) + ".", "No address used by another cluster"))
    elif not duplicates:
        results.append(_result("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "declared_in_main", "info", "No address used by another cluster", usage, "No workload address is used by another cluster.", evidence={"address_rows": address_rows}))
    else:
        other_clusters = sorted({cluster for uses in duplicates.values() for cluster, _ in uses})
        results.append(_result("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "value_mismatch", "blocking", "No address used by another cluster", duplicates, "Workload addresses are also used by: " + ", ".join(other_clusters) + ".", {"duplicates": duplicates}, {"address_rows": address_rows}))

    # Duplicate addresses inside one workload cluster.
    internal_fields = (
        "services.APIServer.ipAddress",
        "ingress.poolAddress",
        "services.APIServer.externalIpAddress",
        "ingress.externalIpAddress",
    )
    for workload in current:
        path = f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
        if path not in all_values:
            reason = (
                f"{path} could not be parsed or is unavailable, so duplicate "
                "addresses inside this workload could not be checked."
            )
            results.append(
                _unknown(
                    "workload.address_internal_duplicates",
                    "workload",
                    workload,
                    "CCI-MOC/oac-apps",
                    path,
                    reason,
                    f"No address is used by more than one field of {workload}.",
                )
            )
            continue
        values = all_values[path]
        own_fields = {
            field: _nested(values, tuple(field.split(".")))
            for field in internal_fields
        }
        groups: dict[str, list[str]] = {}
        for field, address in own_fields.items():
            if address is not None:
                groups.setdefault(_address_key(address), []).append(field)
        allowed_external_share = {
            "services.APIServer.externalIpAddress",
            "ingress.externalIpAddress",
        }
        internal_duplicates = {
            address: fields
            for address, fields in groups.items()
            if len(fields) > 1 and set(fields) != allowed_external_share
        }
        allowed_pairs = {
            address: fields
            for address, fields in groups.items()
            if len(fields) == 2 and set(fields) == allowed_external_share
        }
        rows = [
            {
                "cluster": workload,
                "field": field,
                "address": str(address),
                "duplicate_fields": (
                    [other for other in groups[_address_key(address)] if other != field]
                    if _address_key(address) in internal_duplicates
                    else []
                ),
            }
            for field, address in own_fields.items()
            if address is not None
        ]
        expected_reason = f"No address is used by more than one field of {workload}."
        if not internal_duplicates:
            reason = expected_reason
            if allowed_pairs:
                address, shared_fields = next(iter(allowed_pairs.items()))
                expected_reason = (
                    f"No other address is used by more than one field of {workload}."
                )
                reason = (
                    f"{address} is shared by {shared_fields[0]} and "
                    f"{shared_fields[1]}, which is allowed. {expected_reason}"
                )
            results.append(
                _result(
                    "workload.address_internal_duplicates",
                    "workload",
                    workload,
                    "CCI-MOC/oac-apps",
                    path,
                    "declared_in_main",
                    "info",
                    expected_reason,
                    {"duplicates": {}},
                    reason,
                    evidence={"address_rows": rows},
                )
            )
            continue
        reasons = []
        actions = []
        for address, shared_fields in internal_duplicates.items():
            used = (
                f"{shared_fields[0]} and {shared_fields[1]}"
                if len(shared_fields) == 2
                else ", ".join(shared_fields[:-1]) + f" and {shared_fields[-1]}"
            )
            reasons.append(
                f"{address} is used by "
                f"{'both ' if len(shared_fields) == 2 else ''}{used}; "
                "possible error unless the address is shared on purpose."
            )
            actions.append(
                f"Confirm whether {used} are meant to share {address}; assign "
                "distinct addresses if not."
            )
        results.append(
            _result(
                "workload.address_internal_duplicates",
                "workload",
                workload,
                "CCI-MOC/oac-apps",
                path,
                "value_mismatch",
                "advisory",
                expected_reason,
                {"duplicates": internal_duplicates},
                " ".join(reasons),
                evidence={"address_rows": rows},
                next_action=" ".join(actions),
            )
        )
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
    results.extend(_moc_aws_checks(client, environment, progress, hub_values_file))
    results.extend(_workload_value_checks(client, environment, infra, apps, hub_values, hub_values_file, progress))
    return results
