"""Plain-language statements of what each status check reads and proves.

Every entry is written from the code that implements the check: the repository
and path that is read, the keys or files that are examined, and the exact rule
that produces a passing state.  The ``not_verified`` half records what a reader
would reasonably assume is covered but is not.

Descriptions are templates.  ``describe`` substitutes the environment values
(cluster, hub, domain, machine network, required component files, VLAN subnet)
so the rendered text names the real paths instead of placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CheckDescription:
    """What one check verifies, and what it explicitly does not."""

    verifies: str
    not_verified: str


@dataclass(frozen=True)
class DescriptionContext:
    """Environment values substituted into the description templates."""

    hub: str
    workload: str | None = None
    workloads: tuple[str, ...] = ()
    issue: int | None = None
    domain: str = ""
    machine_network: str | None = None
    base_domain: str | None = None
    hcp_external_domain: str | None = None
    required_components: tuple[str, ...] = ()
    optional_components: tuple[str, ...] = ()
    keycloak_client: str = ""
    vlan_name: str | None = None
    vlan_subnet: str | None = None


CHECK_DESCRIPTIONS: dict[str, CheckDescription] = {
    "request.issue": CheckDescription(
        verifies=(
            "Reads CCI-MOC/MOC-issues issue #{issue} through the GitHub issues "
            "API and inspects only its state field. The check passes when that "
            "state is `open`, which records the environment request as still "
            "open."
        ),
        not_verified=(
            "The issue body, title, labels, assignee and comments are not "
            "interpreted, so the check does not confirm that the issue describes "
            "this environment or that anyone has accepted the work."
        ),
    ),
    "hub.inventory": CheckDescription(
        verifies=(
            "Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and "
            "walks every Ansible group in every child group. The check passes "
            "when at least one group declares vars.cluster == `{hub}`; the "
            "host count does not affect the state."
        ),
        not_verified=(
            "Host names, node_name values, MAC addresses, boot images and group "
            "nesting are not validated here, and a matching group with zero "
            "hosts still passes."
        ),
    ),
    "workload.inventory": CheckDescription(
        verifies=(
            "Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and "
            "walks every Ansible group in every child group. The check passes "
            "when at least one group declares vars.cluster == `{workload}`; the "
            "host count does not affect the state."
        ),
        not_verified=(
            "Host names, node_name values, MAC addresses, boot images and group "
            "nesting are not validated here, and a matching group with zero "
            "hosts still passes."
        ),
    ),
    "hub.boot_image": CheckDescription(
        verifies=(
            "Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and "
            "collects every boot_image_url inherited by the `{hub}` host group. "
            "The check passes when exactly one URL is declared and its filename "
            "contains `{hub}` or the oac-shortened `{hub_short}`; the generic "
            "`discovery.iso` name, several different URLs, or an unrecognized "
            "filename do not pass."
        ),
        not_verified=(
            "The URL is never fetched, so the ISO's existence, checksum and "
            "contents are not verified; only the filename is examined."
        ),
    ),
    "workload.boot_image": CheckDescription(
        verifies=(
            "Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and "
            "collects every boot_image_url inherited by the `{workload}` host "
            "group. The check passes when exactly one URL is declared and its "
            "filename contains `{workload}`, its oac-shortened name, the parent "
            "hub `{hub}`, or the hub's oac-shortened name; `discovery.iso` and "
            "unrecognized names do not pass."
        ),
        not_verified=(
            "The URL is never fetched, so the image's existence, checksum and "
            "contents are not verified; only the filename is examined."
        ),
    ),
    "workload.agent_labels_inputs": CheckDescription(
        verifies=(
            "Reads infra/inventory/00hosts.yaml and infra/update-agents.yaml in "
            "CCI-MOC/oac-infra. Every `{workload}` host whose bm_management is "
            "not `openstack` must declare both mac_addr and resource_class, and "
            "the check passes when none of those hosts is missing either field. "
            "resource_class is also compared with the node table in "
            "docs/hardware-and-network-configuration.md, and a mismatch only "
            "adds an advisory note."
        ),
        not_verified=(
            "MAC address and resource-class formats are not validated, the "
            "update-agents playbook is only checked for existence, and hosts "
            "using bm_management openstack are skipped."
        ),
    ),
    "hub.image_inventory": CheckDescription(
        verifies=(
            "Reads hub-images/inventory.yml in CCI-MOC/oac-infra as YAML and "
            "looks for the all.children.{hub} key. The check passes when that "
            "key exists, whatever hosts or variables it contains."
        ),
        not_verified=(
            "The hosts, images and variables under the key are not inspected, "
            "so an empty or placeholder entry passes."
        ),
    ),
    "hub.image_vars": CheckDescription(
        verifies=(
            "Reads hub-images/group_vars/{hub}/vars.yml in CCI-MOC/oac-infra "
            "and requires six keys to be non-empty: cluster_domain_name, "
            "base_domain, machine_network, api_ip, ingress_ip and dns_ip. The "
            "check passes when all six are present."
        ),
        not_verified=(
            "The six values are not validated, so the addresses need not be "
            "parseable or inside machine_network and the domains need not "
            "resolve."
        ),
    ),
    "hub.oidc_client": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the "
            "block whose cluster_name equals `{keycloak_client}`. The check "
            "passes when openshift_redirect_uri equals `{hub_redirect_uri}` and "
            "client_secret_name equals `cluster/{hub}/keycloak-oidc`."
        ),
        not_verified=(
            "Only those three string attributes are compared; the HCL is never "
            "applied, so Keycloak runtime state and the referenced secret's "
            "existence are not verified."
        ),
    ),
    "hub.hosted_cluster_defaults": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and requires the path "
            "hosted-clusters/{hub}/values.yaml to exist. The check passes when "
            "that single path is present in the selected ref."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "missing or malformed hosted-cluster defaults still pass."
        ),
    ),
    "hub.component_values": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and requires "
            "values/{hub}/hcp-config.yaml for hub-wide HCP and secret-selector "
            "values. The check passes when that path exists; the file is never "
            "opened."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "the HCP and secret-selector keys are never checked."
        ),
    ),
    "hub.local_cluster_values": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and requires {required_count} files "
            "under values/{hub}/local-cluster/: {required_components}. Configured "
            "optional components ({optional_components}) must exist too, and the "
            "check passes only when every required and optional file is present."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "operator versions, values and cluster-specific names are never "
            "validated."
        ),
    ),
    "hub.argocd_apps": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and requires "
            "apps/{hub}/keycloak-oauth.yaml. The check passes when that Argo CD "
            "application manifest path exists."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "the manifest's destination cluster and sync policy are not checked."
        ),
    ),
    "workload.hosted_cluster_values": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and requires "
            "hosted-clusters/{hub}/{workload}/values.yaml. The check passes when "
            "that path exists."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "the cluster name, parent hub, networking and node pools are not "
            "verified here."
        ),
    ),
    "workload.component_values": CheckDescription(
        verifies=(
            "Lists the CCI-MOC/oac-apps tree and counts files under "
            "values/{hub}/{workload}/. The check passes when at least one file "
            "exists there; there is no fixed required-file list."
        ),
        not_verified=(
            "Only path existence is tested; the file contents are not read, so "
            "individual components such as hcp-config.yaml are not confirmed."
        ),
    ),
    "hub.pure_storage_realm": CheckDescription(
        verifies=(
            "Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and "
            "selects the realms entry whose name equals `{hub}`. The check "
            "passes when subnet_vlan, subnet_prefix and s3_endpoint are all "
            "non-null."
        ),
        not_verified=(
            "The three values are not validated against the hub machine network "
            "or DNS, and no Pure array is contacted."
        ),
    ),
    "workload.pure_storage_realm": CheckDescription(
        verifies=(
            "Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and "
            "selects the realms entry whose name equals `{workload}`. The check "
            "passes when subnet_vlan, subnet_prefix and s3_endpoint are all "
            "non-null."
        ),
        not_verified=(
            "The three values are not validated against the workload VLAN or "
            "DNS, and no Pure array is contacted."
        ),
    ),
    "hub.moc_aws_oidc_cluster": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block "
            "whose cluster_name equals `{hub}`. The check passes when such a "
            "block exists; its eso_writable_secret_prefixes are reported as "
            "context but nothing about them is required."
        ),
        not_verified=(
            "The block's other attributes are not inspected, and the OIDC "
            "provider, IAM role and secret store are not exercised in AWS."
        ),
    ),
    "workload.moc_aws_oidc_cluster": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block "
            "whose cluster_name equals `{workload}`. The check passes when such "
            "a block exists; its eso_writable_secret_prefixes are reported as "
            "context but nothing about them is required."
        ),
        not_verified=(
            "The block's other attributes are not inspected, and the OIDC "
            "provider, IAM role and secret store are not exercised in AWS."
        ),
    ),
    "hub.moc_aws_cert_manager_policy": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and "
            "matches a block whose cluster_subdomain or policy_name names "
            "`{hub}` (policy_name is also tried with `-` replaced by `_`). The "
            "check passes when any block matches by name."
        ),
        not_verified=(
            "The match is textual, so the certificate zone, DNS records and AWS "
            "permissions are not verified."
        ),
    ),
    "workload.moc_aws_cert_manager_policy": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and "
            "matches a block whose cluster_subdomain or policy_name names "
            "`{workload}` (policy_name is also tried with `-` replaced by `_`). "
            "The check passes when any block matches by name."
        ),
        not_verified=(
            "The match is textual, so the certificate zone, DNS records and AWS "
            "permissions are not verified."
        ),
    ),
    "hub.moc_aws_hosted_secret_prefix": CheckDescription(
        verifies=(
            "Reads the CCI-MOC/moc-aws main.tf block whose cluster_name equals "
            "`{hub}` and inspects its eso_writable_secret_prefixes list. The "
            "check passes when `cluster/{hub}/hostedcluster/` is one of the "
            "listed prefixes."
        ),
        not_verified=(
            "The rest of the hub block and the AWS-side secret store are not "
            "inspected, so an unwritable or missing store is not detected."
        ),
    ),
    "hub.moc_dns_records": CheckDescription(
        verifies=(
            "Picks the longest moc-dns zonefile under zonefiles/ whose name is a "
            "suffix of `{domain}`, parses its A records, and requires "
            "api.{domain} and api-int.{domain} to equal the hub api_ip and "
            "*.apps.{domain} to equal the hub ingress_ip. The check passes when "
            "all three records point at those addresses."
        ),
        not_verified=(
            "Only A records in that one zonefile are compared; CNAMEs, TTLs, "
            "delegation and live DNS resolution are not checked."
        ),
    ),
    "workload.keycloak_oidc_client": CheckDescription(
        verifies=(
            "Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the "
            "block whose cluster_name equals `{workload}`. The check passes when "
            "openshift_redirect_uri equals `{workload_redirect_uri}` and "
            "client_secret_name equals "
            "`cluster/{hub}/hostedcluster/{workload}/keycloak-oidc`."
        ),
        not_verified=(
            "Only those three attributes are compared; the secret is not read "
            "and the Keycloak server is not contacted."
        ),
    ),
    "workload.identity_provider": CheckDescription(
        verifies=(
            "Reads hosted-clusters/{hub}/{workload}/values.yaml in "
            "CCI-MOC/oac-apps. When oauth.mocsso.enabled is not true the check "
            "passes if oauth.identityProviders is a non-empty list; when it is "
            "true the same three moc-keycloak client fields as "
            "workload.keycloak_oidc_client must match."
        ),
        not_verified=(
            "The configured identity-provider entries are not validated against "
            "Keycloak, and a disabled mocsso with an explicit provider is "
            "accepted without checking that the provider works."
        ),
    ),
    "workload.api_address_network": CheckDescription(
        verifies=(
            "Reads services.APIServer.ipAddress from "
            "hosted-clusters/{hub}/{workload}/values.yaml and tests it with the "
            "ipaddress module against the hub machine network "
            "`{machine_network}` from hub-images/group_vars/{hub}/vars.yml. The "
            "check passes when the address is inside that network."
        ),
        not_verified=(
            "The address is not checked against other clusters here (see "
            "workload.address_uniqueness) and the live API endpoint is not "
            "contacted."
        ),
    ),
    "workload.ingress_address_network": CheckDescription(
        verifies=(
            "Reads ingress.poolAddress from "
            "hosted-clusters/{hub}/{workload}/values.yaml and requires a "
            "parseable IP address or CIDR. The check passes when the address is "
            "outside the hub machine network `{machine_network}` and inside "
            "{vlan_clause}."
        ),
        not_verified=(
            "Address availability, MetalLB runtime allocation and the switch "
            "configuration itself are not verified."
        ),
    ),
    "workload.address_uniqueness": CheckDescription(
        verifies=(
            "Reads every hosted-clusters/<hub>/<cluster>/values.yaml in "
            "CCI-MOC/oac-apps and collects services.APIServer.ipAddress, "
            "ingress.poolAddress, services.APIServer.externalIpAddress and "
            "ingress.externalIpAddress for each cluster. The check passes when "
            "no address used by `{workloads}` is also used by a different "
            "cluster."
        ),
        not_verified=(
            "Duplicate addresses inside one cluster are not reported, and "
            "addresses are compared as strings, so equivalent CIDR and bare-IP "
            "spellings are not unified."
        ),
    ),
    "workload.dns_base_domain": CheckDescription(
        verifies=(
            "Reads dns.records[].hostname from "
            "hosted-clusters/{hub}/{workload}/values.yaml. The check passes when "
            "every hostname ends with the hub baseDomain `{base_domain}` or "
            "hcpExternalDomain `{hcp_external_domain}` taken from "
            "hosted-clusters/{hub}/values.yaml."
        ),
        not_verified=(
            "Only the suffix is compared; the records are not looked up in "
            "moc-dns and missing records are not detected."
        ),
    ),
    "workload.node_pool_hosts": CheckDescription(
        verifies=(
            "For each nodePools entry in the workload values file, counts "
            "inventory hosts in infra/inventory/00hosts.yaml whose fields equal "
            "the agentLabelSelector string values (resource_class also consults "
            "the documented hardware table). The check passes when every pool "
            "has at least as many matching hosts as its replicas."
        ),
        not_verified=(
            "Host readiness, scheduling and non-string selector operators are "
            "not evaluated."
        ),
    ),
    "workload.gpu_without_hosts": CheckDescription(
        verifies=(
            "Reads clusterLabels.massopen.cloud/feature-gpu from the workload "
            "values file. When it is true the check passes only if at least one "
            "inventory host has gpu: true or a resource_class, flavor or "
            "documented class containing gpu, a100 or h100."
        ),
        not_verified=(
            "GPU model, count and allocatable resources are not inspected, and "
            "feature-gpu false is accepted without checking that the gate is "
            "absent."
        ),
    ),
}


def describe(
    check_id: str,
    context: DescriptionContext,
) -> tuple[str, str]:
    """Return the rendered ``(verifies, not_verified)`` pair for one check."""

    entry = CHECK_DESCRIPTIONS[check_id]
    values = _values(check_id, context)
    return entry.verifies.format(**values), entry.not_verified.format(**values)


def apply_descriptions(checks, context: DescriptionContext) -> None:
    """Attach rendered descriptions to every check that has an entry."""

    for check in checks:
        if check.id not in CHECK_DESCRIPTIONS:
            continue
        verifies, not_verified = describe(check.id, _context_for(check, context))
        check.verifies = verifies
        check.not_verified = not_verified


def _context_for(check, context: DescriptionContext) -> DescriptionContext:
    """Substitute the per-check values that are not shared by the report."""

    if check.id == "workload.ingress_address_network":
        expected = check.expected if isinstance(check.expected, dict) else {}
        return replace(
            context,
            workload=check.cluster or context.workload,
            machine_network=expected.get("machine_network")
            or context.machine_network,
            vlan_name=expected.get("vlan_name") or context.vlan_name,
            vlan_subnet=expected.get("vlan_subnet") or context.vlan_subnet,
        )
    return replace(context, workload=check.cluster or context.workload)


def _values(check_id: str, context: DescriptionContext) -> dict[str, str]:
    workloads = context.workloads or (
        (context.workload,) if context.workload else ()
    )
    workload = context.workload or (workloads[0] if workloads else context.hub)
    required = ", ".join(context.required_components) or "none configured"
    optional = ", ".join(context.optional_components) or "none configured"
    return {
        "hub": context.hub,
        "hub_short": context.hub.removeprefix("oac-"),
        "workload": workload,
        "cluster": workload,
        "workloads": ", ".join(workloads) or workload,
        "issue": str(context.issue) if context.issue is not None else "unknown",
        "domain": context.domain
        or "an unknown domain (hub image variables are unavailable)",
        "machine_network": context.machine_network
        or "an unknown hub machine network (hub image variables are unavailable)",
        "base_domain": context.base_domain or "an unknown baseDomain",
        "hcp_external_domain": context.hcp_external_domain
        or "an unknown hcpExternalDomain",
        "required_count": str(len(context.required_components)),
        "required_components": required,
        "optional_components": optional,
        "keycloak_client": context.keycloak_client or f"{context.hub}-infra",
        "hub_redirect_uri": (
            f"https://oauth-openshift.apps.{context.domain}"
            "/oauth2callback/mocsso"
        ),
        "workload_redirect_uri": (
            f"https://oauth-{workload}.{context.hcp_external_domain}"
            ":443/oauth2callback/mocsso"
        ),
        "vlan_clause": _vlan_clause(context, workload),
    }


def _vlan_clause(context: DescriptionContext, workload: str) -> str:
    if context.vlan_name and context.vlan_subnet:
        return (
            f"the subnet4 `{context.vlan_subnet}` of the ansible-switches VLAN "
            f"`{context.vlan_name}`"
        )
    if context.vlan_subnet:
        return (
            f"the subnet4 `{context.vlan_subnet}` of the ansible-switches VLAN "
            f"that matches {workload}"
        )
    return (
        "the subnet4 of the ansible-switches VLAN that matches "
        f"{workload} (no VLAN matched in this run)"
    )
