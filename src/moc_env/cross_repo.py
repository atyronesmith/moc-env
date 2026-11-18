"""Cross-repository prerequisite observations and checks."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import yaml

from .github import GitHubClient, GitHubError, github_url
from .model import CheckResult, Environment
from .observed import AppsObservation, InfraObservation
from .repositories import (
    ANSIBLE_SWITCHES_REPOSITORY,
    EVERPURE_REPOSITORY,
    MOC_AWS_REPOSITORY,
    MOC_DNS_REPOSITORY,
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
    "workload.dns_base_domain": "Workload DNS base domain",
    "workload.node_pool_hosts": "Workload node-pool host capacity",
    "workload.gpu_without_hosts": "Workload GPU feature support",
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
            expected_policy = {"cluster": cluster}
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
    domain = ".".join(domain_parts)
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


def _address_in(value: Any, network: str) -> bool:
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

    for workload in environment.workload_clusters or ():
        path = f"hosted-clusters/{environment.infra_cluster}/{workload}/values.yaml"
        values, values_error = _workload_values(apps, environment, workload)
        if values is None:
            results.extend([
                _unknown(check_id, "workload", workload, "CCI-MOC/oac-apps", path, values_error, {})
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
            results.append(_result("workload.dns_base_domain", "workload", workload, "CCI-MOC/oac-apps", path, "declared_in_main", "info", expected_domains, hostnames, "All DNS record hostnames use the hub hosted-cluster domains."))
        else:
            results.append(_result("workload.dns_base_domain", "workload", workload, "CCI-MOC/oac-apps", path, "value_mismatch", "blocking", expected_domains, hostnames, "Some DNS record hostnames do not use the hub hosted-cluster domains.", {"hostnames": invalid}))

        cluster_observation = infra.clusters.get(workload)
        hosts = cluster_observation.hosts.value if cluster_observation else []
        pools = values.get("nodePools") or []
        pool_results = []
        for pool_item in pools:
            if not isinstance(pool_item, dict):
                continue
            selector = pool_item.get("agentLabelSelector") or {}
            replicas = int(pool_item.get("replicas") or 0)
            documented = infra.hardware_resource_classes.value

            def selector_values(host: dict[str, Any], key: str) -> tuple[Any, ...]:
                if key == "massopen.cloud/cluster":
                    return (host.get("cluster"),)
                if key in {"resource_class", "openstack/resource-class"}:
                    return tuple(
                        value
                        for value in (
                            host.get("resource_class"),
                            documented.get(host.get("node_name")),
                        )
                        if value is not None
                    )
                return (host.get(key),)

            def selector_matches(
                host: dict[str, Any], selector: dict[str, Any]
            ) -> bool:
                return all(
                    any(
                        value == expected
                        or (
                            isinstance(value, str)
                            and isinstance(expected, str)
                            and expected.endswith(value)
                        )
                        for value in selector_values(host, key)
                    )
                    for key, expected in selector.items()
                    if isinstance(expected, str)
                )

            matching = sum(
                1
                for host in hosts
                if selector_matches(host, selector)
            )
            pool_results.append({"name": pool_item.get("name"), "replicas": replicas, "matching_hosts": matching})
        if all(item["matching_hosts"] >= item["replicas"] for item in pool_results):
            results.append(_result("workload.node_pool_hosts", "workload", workload, "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "declared_in_main", "info", pools, pool_results, "Every node pool has enough matching inventory hosts."))
        else:
            results.append(_result("workload.node_pool_hosts", "workload", workload, "CCI-MOC/oac-infra", "infra/inventory/00hosts.yaml", "value_mismatch", "blocking", pools, pool_results, "At least one node pool lacks matching inventory hosts."))

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
                        if other not in current
                    ),
                }
            )
    uniqueness_cluster = next(iter(current), environment.infra_cluster)
    if values_parse_errors:
        results.append(_unknown("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "One or more hosted-cluster values files could not be parsed: " + ", ".join(values_parse_errors) + ".", "No address used by another cluster"))
    elif not duplicates:
        results.append(_result("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "declared_in_main", "info", "No address used by another cluster", usage, "No workload address is used by another cluster.", evidence={"address_rows": address_rows}))
    else:
        other_clusters = sorted({cluster for uses in duplicates.values() for cluster, _ in uses if cluster not in current})
        results.append(_result("workload.address_uniqueness", "workload", uniqueness_cluster, "CCI-MOC/oac-apps", "hosted-clusters/", "value_mismatch", "blocking", "No address used by another cluster", duplicates, "Workload addresses are also used by: " + ", ".join(other_clusters) + ".", {"duplicates": duplicates}, {"address_rows": address_rows}))
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
