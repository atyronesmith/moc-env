# bu-ist-demo — environment configuration status

**No deployment gaps in repository configuration.**

Generated 2026-11-16 12:34 UTC · MOC issue: [#666](https://github.com/CCI-MOC/MOC-issues/issues/666) (open)

## Phase summary

### Hub phases

| Phase | HUB bu-ist-demo-infra |
|---|---:|
| 1 Host inventory entry | OK 1/1 checks |
| 2 Hub image inventory and vars | OK 3/3 checks |
| 3 Discovery image reference | OK 1/1 checks |
| 4 Keycloak OIDC client | OK 1/1 checks |
| 5 GitOps values and apps | OK 8/8 checks |

### Workload phases

| Phase | WORKLOAD bu-ist-demo-workload0 |
|---|---:|
| 1 Host inventory entry | OK 1/1 checks |
| 2 Hub agent discovery ISO | OK 1/1 checks |
| 3 Agent ISO boot | verify by hand |
| 4 Agent visibility | verify by hand |
| 5 Agent labels and approval | OK 1/1 checks |
| 6 oac-apps values | OK 11/11 checks |
| 7 Shared-service prerequisites | OK 5/5 checks |

## Next actions

Nothing to do in the repositories this tool reads.

## Not checked — verify by hand

- **Configure cluster and storage networks and firewalls for bu-ist-demo-infra** (phase 1) — The repositories read by this tool do not describe the switch, network, or firewall state required for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#infrastructure-configuration).
- **Store the bu-ist-demo-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/bu-ist-demo-infra/sshkey or cluster/bu-ist-demo-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Place the pull secret and SSH key under hub-images/credentials/bu-ist-demo-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Run create_agent_install_media and copy the bu-ist-demo-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Bootstrap Argo CD for bu-ist-demo-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration).
- **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).
- **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).

## Details

<details>
<summary>OK: bu-ist-demo-infra host inventory — The inventory contains a bu-ist-demo-infra group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Host management: Not recorded.

Verifies: Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and walks every Ansible group in every child group. The check passes when at least one group declares vars.cluster == `bu-ist-demo-infra`; the host count does not affect the state.
Not verified: Host names, node_name values, MAC addresses, boot images and group nesting are not validated here, and a matching group with zero hosts still passes.

| Field | Expected | Observed |
|---|---|---|
| `cluster_group` | `a group with vars.cluster == bu-ist-demo-infra` | `bu-ist-demo-infra` |
| `host_count` | `reported (not required)` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL | Management (bm_management) |
|---|---|---|---|---|
| `control-0` | `MOC-R4PAC10U31-S1A` | — | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` | `Not recorded` |

</details>

<details>
<summary>OK: Hub image inventory — The hub-image inventory contains the all.children.bu-ist-demo-infra key.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ main (2222222)

Verifies: Reads hub-images/inventory.yml in CCI-MOC/oac-infra as YAML and looks for the all.children.bu-ist-demo-infra key. The check passes when that key exists, whatever hosts or variables it contains.
Not verified: The hosts, images and variables under the key are not inspected, so an empty or placeholder entry passes.

| Field | Expected | Observed |
|---|---|---|
| `inventory_key` | `key all.children.bu-ist-demo-infra` | `bu-ist-demo-infra` |

</details>

<details>
<summary>OK: Hub image variables — All six required hub-image variables are present in main; their values are not validated.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/bu-ist-demo-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/bu-ist-demo-infra/vars.yml) @ main (2222222)

Verifies: Reads hub-images/group_vars/bu-ist-demo-infra/vars.yml in CCI-MOC/oac-infra and requires six keys to be non-empty: cluster_domain_name, base_domain, machine_network, api_ip, ingress_ip and dns_ip. The check passes when all six are present.
Not verified: The six values are not validated, so the addresses need not be parseable or inside machine_network and the domains need not resolve.

| Field | Expected | Observed |
|---|---|---|
| `cluster_domain_name` | `present` | `bu-ist-demo` |
| `base_domain` | `present` | `int.massopen.cloud` |
| `machine_network` | `present` | `10.20.26.0/23` |
| `api_ip` | `present` | `10.20.27.11` |
| `ingress_ip` | `present` | `10.20.27.12` |
| `dns_ip` | `present` | `8.8.8.8` |

</details>

<details>
<summary>OK: Hub moc-dns records — All required hub DNS records in zonefiles/int.massopen.cloud.zone match the hub-image variables.</summary>

Source: CCI-MOC/moc-dns · [`zonefiles/int.massopen.cloud.zone`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/int.massopen.cloud.zone) @ main (7777777)

Verifies: Picks the longest moc-dns zonefile under zonefiles/ whose name is a suffix of `bu-ist-demo.int.massopen.cloud`, parses its A records, and requires api.bu-ist-demo.int.massopen.cloud and api-int.bu-ist-demo.int.massopen.cloud to equal the hub api_ip and *.apps.bu-ist-demo.int.massopen.cloud to equal the hub ingress_ip. The check passes when all three records point at those addresses.
Not verified: Only A records in that one zonefile are compared; CNAMEs, TTLs, delegation and live DNS resolution are not checked.

| Field | Expected | Observed |
|---|---|---|
| `api.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `api-int.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `*.apps.bu-ist-demo.int.massopen.cloud` | `10.20.27.12` | `10.20.27.12` |

</details>

<details>
<summary>OK: bu-ist-demo-infra boot image — The boot image URL is specific to bu-ist-demo-infra.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and collects every boot_image_url inherited by the `bu-ist-demo-infra` host group. The check passes when exactly one URL is declared and its filename contains `bu-ist-demo-infra` or the oac-shortened `bu-ist-demo-infra`; the generic `discovery.iso` name, several different URLs, or an unrecognized filename do not pass.
Not verified: The URL is never fetched, so the ISO's existence, checksum and contents are not verified; only the filename is examined.

Status rule: The boot-image filename must contain the full cluster name `bu-ist-demo-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `boot_image_url` | `filename contains bu-ist-demo-infra` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>OK: Hub OIDC client — All expected Keycloak OIDC client fields match.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

Verifies: Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the block whose cluster_name equals `bu-ist-demo-infra`. The check passes when openshift_redirect_uri equals `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` and client_secret_name equals `cluster/bu-ist-demo-infra/keycloak-oidc`.
Not verified: Only those three string attributes are compared; the HCL is never applied, so Keycloak runtime state and the referenced secret's existence are not verified.

| Field | Expected | Observed |
|---|---|---|
| `client` | `bu-ist-demo-infra` | `bu-ist-demo-infra` |
| `openshift_redirect_uri` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` |
| `client_secret_name` | `cluster/bu-ist-demo-infra/keycloak-oidc` | `cluster/bu-ist-demo-infra/keycloak-oidc` |

</details>

<details>
<summary>OK: Hub hosted-cluster defaults — 1 of 1 required file exists in main under hosted-clusters/bu-ist-demo-infra (values.yaml). File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires the path hosted-clusters/bu-ist-demo-infra/values.yaml to exist. The check passes when that single path is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so missing or malformed hosted-cluster defaults still pass.

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) | `present` | `present` |

</details>

<details>
<summary>OK: Hub-wide component values — 1 of 1 required file exists in main under values/bu-ist-demo-infra (hcp-config.yaml). File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires values/bu-ist-demo-infra/hcp-config.yaml for hub-wide HCP and secret-selector values. The check passes when that path exists in `main`; the file is never opened.
Not verified: Only path existence is tested; the file contents are not read, so the HCP and secret-selector keys are never checked.

| Field | Expected | Observed |
|---|---|---|
| [`values/bu-ist-demo-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/hcp-config.yaml) | `present` | `present` |

</details>

<details>
<summary>OK: Hub local-cluster values — 13 of 13 required files exist in main under values/bu-ist-demo-infra/local-cluster (acm.yaml, acm-placements.yaml, cert-manager.yaml, cluster-certificates.yaml, cluster-version.yaml, external-dns-operator.yaml, external-secrets.yaml, hcp-config.yaml, keycloak-oauth.yaml, metallb.yaml, openshift-gitops.yaml, portworx.yaml, user-workload-monitoring.yaml). File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires 13 files under values/bu-ist-demo-infra/local-cluster/: acm.yaml, acm-placements.yaml, cert-manager.yaml, cluster-certificates.yaml, cluster-version.yaml, external-dns-operator.yaml, external-secrets.yaml, hcp-config.yaml, keycloak-oauth.yaml, metallb.yaml, openshift-gitops.yaml, portworx.yaml, user-workload-monitoring.yaml. Configured optional components (none configured) must exist too, and the check passes only when every required and optional file is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so operator versions, values and cluster-specific names are never validated.

| Field | Expected | Observed |
|---|---|---|
| [`values/bu-ist-demo-infra/local-cluster/acm.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/acm.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/acm-placements.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cert-manager.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cert-manager.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-version.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cluster-version.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/external-secrets.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/external-secrets.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/hcp-config.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/metallb.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/metallb.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/portworx.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/portworx.yaml) | `present` | `present` |
| [`values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml) | `present` | `present` |

**Required files**

| Path | Status |
|---|---|
| `values/bu-ist-demo-infra/local-cluster/acm-placements.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/acm.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/cert-manager.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/cluster-version.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/external-secrets.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/hcp-config.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/metallb.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/portworx.yaml` | `present` |
| `values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml` | `present` |

**Additional files present**

None.

</details>

<details>
<summary>OK: Hub ArgoCD applications — 1 of 1 required file exists in main under apps/bu-ist-demo-infra (keycloak-oauth.yaml). File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`apps/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires apps/bu-ist-demo-infra/keycloak-oauth.yaml. The check passes when that Argo CD application manifest path exists in `main`.
Not verified: Only path existence is tested; the file contents are not read, so the manifest's destination cluster and sync policy are not checked.

| Field | Expected | Observed |
|---|---|---|
| [`apps/bu-ist-demo-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra/keycloak-oauth.yaml) | `present` | `present` |

</details>

<details>
<summary>OK: Hub Pure storage realm — The bu-ist-demo-infra Pure storage realm reports subnet_vlan, subnet_prefix and s3_endpoint.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

Verifies: Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and selects the realms entry whose name equals `bu-ist-demo-infra`. The check passes when subnet_vlan, subnet_prefix and s3_endpoint are all non-null.
Not verified: The three values are not validated against the hub machine network or DNS, and no Pure array is contacted.

| Field | Expected | Observed |
|---|---|---|
| `name` | `bu-ist-demo-infra` | `bu-ist-demo-infra` |
| `subnet_vlan` | `present` | `2321` |
| `subnet_prefix` | `present` | `10.9.15.0/24` |
| `s3_endpoint` | `present` | `s3.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>OK: Hub moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-infra is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block whose cluster_name equals `bu-ist-demo-infra`. The check passes when such a block exists; its eso_writable_secret_prefixes are reported as context but nothing about them is required.
Not verified: The block's other attributes are not inspected, and the OIDC provider, IAM role and secret store are not exercised in AWS.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-infra` | `bu-ist-demo-infra` |
| `eso_writable_secret_prefixes` | `not constrained by this check` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>OK: Hub moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policies names bu-ist-demo-infra in policy_name or cluster_subdomain.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and matches a block whose cluster_subdomain or policy_name names `bu-ist-demo-infra` (policy_name is also tried with `-` replaced by `_`). The check passes when any block matches by name.
Not verified: The match is textual, so the certificate zone, DNS records and AWS permissions are not verified.

| Field | Expected | Observed |
|---|---|---|
| `policy entry` | `policy_name or cluster_subdomain names bu-ist-demo-infra` | `cert_manager_policies` |

</details>

<details>
<summary>OK: Hub hosted-cluster secret prefix — The hub can write hosted-cluster secrets at cluster/bu-ist-demo-infra/hostedcluster/.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Reads the CCI-MOC/moc-aws main.tf block whose cluster_name equals `bu-ist-demo-infra` and inspects its eso_writable_secret_prefixes list. The check passes when `cluster/bu-ist-demo-infra/hostedcluster/` is one of the listed prefixes.
Not verified: The rest of the hub block and the AWS-side secret store are not inspected, so an unwritable or missing store is not detected.

| Field | Expected | Observed |
|---|---|---|
| `eso_writable_secret_prefixes` | `cluster/bu-ist-demo-infra/hostedcluster/` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>OK: bu-ist-demo-workload0 host inventory — The inventory contains a bu-ist-demo-workload0 group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Host management: Other management (ipmi; treated as non-OpenStack).

Verifies: Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and walks every Ansible group in every child group. The check passes when at least one group declares vars.cluster == `bu-ist-demo-workload0`; the host count does not affect the state.
Not verified: Host names, node_name values, MAC addresses, boot images and group nesting are not validated here, and a matching group with zero hosts still passes.

| Field | Expected | Observed |
|---|---|---|
| `cluster_group` | `a group with vars.cluster == bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `host_count` | `reported (not required)` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL | Management (bm_management) |
|---|---|---|---|---|
| `compute-0` | `MOC-R4PAC10U31-S1B` | — | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` | `Other management (ipmi; treated as non-OpenStack)` |

</details>

<details>
<summary>OK: bu-ist-demo-workload0 boot image — The boot image URL identifies the workload or its parent hub bu-ist-demo-infra.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and collects every boot_image_url inherited by the `bu-ist-demo-workload0` host group. The check passes when exactly one URL is declared and its filename contains `bu-ist-demo-workload0`, its oac-shortened name, the parent hub `bu-ist-demo-infra`, or the hub's oac-shortened name; `discovery.iso` and unrecognized names do not pass.
Not verified: The URL is never fetched, so the image's existence, checksum and contents are not verified; only the filename is examined.

Status rule: The workload boot-image filename may contain the workload name `bu-ist-demo-workload0`, its oac-shortened name, the parent hub name `bu-ist-demo-infra`, or the hub's oac-shortened name. Unrecognized names are advisory because naming is not consistent across environments; generic `discovery.iso` remains a gap.

| Field | Expected | Observed |
|---|---|---|
| `boot_image_url` | `filename contains bu-ist-demo-workload0 or bu-ist-demo-infra` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>OK: bu-ist-demo-workload0 update-agents inputs — Every non-openstack host has the mac_addr and resource_class inputs required by infra/update-agents.yaml.</summary>

Source: CCI-MOC/oac-infra · [`infra/update-agents.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/update-agents.yaml) @ main (2222222)

Host management: Other management (ipmi; treated as non-OpenStack).

Verifies: Applies input requirements per host using the observed bm_management value. Hosts with bm_management=openstack obtain MAC addresses and resource classes from OpenStack; all other hosts require mac_addr and resource_class inventory inputs. Hardware-documentation differences are advisory only.
Not verified: Address and resource-class formats, management-system connectivity, and actual agent labels or approval are not verified. The playbook is checked only for existence.

**Agent input requirements by host**

| Field | Expected | Observed |
|---|---|---|
| `compute-0.mac_addr` | `present` | `00:11:22:33:44:55` |
| `compute-0.resource_class` | `present` | `bu-ist-demo-worker` |

**Resource-class documentation comparison (advisory only)**

Documented hardware classes are reference information, not defaults or required values. Agent resource-class labels must match the NodePool selectors.

| Host | Inventory resource_class | Documented hardware class | Comparison |
|---|---|---|---|
| `compute-0` | `bu-ist-demo-worker` | `bu-ist-demo-worker` | `Matches documentation` |

**Agent label inputs**

| Host | bm_management | mac_addr | resource_class | Management |
|---|---|---|---|---|
| `compute-0` | `ipmi` | `00:11:22:33:44:55` | `bu-ist-demo-worker` | `Other management (ipmi; treated as non-OpenStack)` |

</details>

<details>
<summary>OK: Workload hosted-cluster values — 1 of 1 required file exists in main under hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0 (values.yaml). File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml. The check passes when that path exists in `main`.
Not verified: Only path existence is tested; the file contents are not read, so the cluster name, parent hub, networking and node pools are not verified here.

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) | `present` | `present` |

</details>

<details>
<summary>OK: Workload component values — 1 file exists in main under values/bu-ist-demo-infra/bu-ist-demo-workload0; at least 1 is required. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/bu-ist-demo-workload0) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and counts files under values/bu-ist-demo-infra/bu-ist-demo-workload0/. The check passes when at least one file exists there in `main`; there is no fixed required-file list.
Not verified: Only path existence is tested; the file contents are not read, so individual components such as hcp-config.yaml are not confirmed.

| Field | Expected | Observed |
|---|---|---|
| `values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml` | `present` | `present` |
| `values/bu-ist-demo-infra/bu-ist-demo-workload0` | `at least 1 file` | `1 file(s)` |

</details>

<details>
<summary>OK: Workload API address network — The API address is inside the hub machine network.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Reads services.APIServer.ipAddress from hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml and tests it with the ipaddress module against the hub machine network `10.20.26.0/23` from hub-images/group_vars/bu-ist-demo-infra/vars.yml. The check passes when the address is inside that network.
Not verified: The address is not checked against other clusters here (see workload.address_uniqueness) and the live API endpoint is not contacted.

| Field | Expected | Observed |
|---|---|---|
| `services.APIServer.ipAddress` | `inside 10.20.26.0/23` | `10.20.26.10` |

</details>

<details>
<summary>OK: Workload ingress address network — The ingress pool address is on the expected network. Selected VLAN BU-IST-DEMO-WORKLOAD0 (10.20.28.0/24).</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Reads ingress.poolAddress from hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml and requires a parseable IP address or CIDR. The check passes when the address is outside the hub machine network `10.20.26.0/23` and inside the subnet4 `10.20.28.0/24` of the ansible-switches VLAN `BU-IST-DEMO-WORKLOAD0`.
Not verified: Address availability, MetalLB runtime allocation and the switch configuration itself are not verified.

| Field | Expected | Observed |
|---|---|---|
| `ingress.poolAddress` | `outside 10.20.26.0/23 and inside 10.20.28.0/24` | `10.20.28.10` |

</details>

<details>
<summary>OK: Workload DNS base domain — All DNS record hostnames use the hub hosted-cluster domains.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Reads dns.records[].hostname from hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml. The check passes when every hostname ends with the hub baseDomain `int.massopen.cloud` or hcpExternalDomain `hcp.bu-ist-demo.int.massopen.cloud` taken from hosted-clusters/bu-ist-demo-infra/values.yaml.
Not verified: Only the suffix is compared; the records are not looked up in moc-dns and missing records are not detected.

| Field | Expected | Observed |
|---|---|---|
| `dns.records[0].hostname` | `under int.massopen.cloud, hcp.bu-ist-demo.int.massopen.cloud` | `api.bu-ist-demo-workload0.int.massopen.cloud` |

</details>

<details>
<summary>OK: Workload node-pool host capacity — Every node pool has enough matching inventory hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: For each nodePools entry in the workload values file, counts inventory hosts in infra/inventory/00hosts.yaml whose fields equal the agentLabelSelector string values (resource_class also consults the documented hardware table). The check passes when every pool has at least as many matching hosts as its replicas.
Not verified: Host readiness, scheduling and non-string selector operators are not evaluated.

| Field | Expected | Observed |
|---|---|---|
| `nodePools.compute.matching_hosts` | `at least 1` | `1` |

</details>

<details>
<summary>OK: Workload GPU feature support — GPU configuration is consistent with the inventory.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Reads clusterLabels.massopen.cloud/feature-gpu from the workload values file. When it is true the check passes only if at least one inventory host has gpu: true or a resource_class, flavor or documented class containing gpu, a100 or h100.
Not verified: GPU model, count and allocatable resources are not inspected, and feature-gpu false is accepted without checking that the gate is absent.

| Field | Expected | Observed |
|---|---|---|
| `clusterLabels["massopen.cloud/feature-gpu"]` | `false or at least 1 GPU host` | `false` |
| `gpu_host_count` | `at least 1 when feature-gpu is true` | `0` |

</details>

<details>
<summary>OK: Workload feature placements — Matched placements: all-managed-clusters. unused_labels: [].</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/acm-placements.yaml) @ main (3333333)

Verifies: Reads clusterLabels from the workload hosted-cluster values file and compares every feature label whose value is true with the matchLabels of this hub's acm-placements.yaml. The check passes when this hub defines a matching placement, or no hub in the tree defines one at all; a placement that exists only on another hub is a blocking gap.
Not verified: Only string equality of matchLabels is compared, so label selectors other than matchLabels and placements applied outside this repository are not evaluated.

| Field | Expected | Observed |
|---|---|---|
| `matched placements` | `a matching placement on this hub` | `all-managed-clusters` |
| `unused labels` | `no placement on any hub` | `—` |
| `labels with no placement on this hub` | `none` | `—` |

</details>

<details>
<summary>OK: Workload feature chart values — 1 chart received; all required values are set and every kustomize overlay exists.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/bu-ist-demo-workload0) @ main (3333333)

Verifies: Resolves the workload's feature labels through this hub's placements and the managed ApplicationSet templates, then lists the charts each matched placement deploys. Required .Values calls outside if, with, and range blocks must resolve to a non-empty value in the layered chart, hub, and per-cluster values files; kustomize overlays must exist and per-cluster values files must name received charts.
Not verified: Required calls inside if/with/range blocks and inside range-scoped variables are not evaluated; charts are not rendered; the live Argo CD Applications are not read.

| Chart / item | Requirement | Finding |
|---|---|---|
| `charts received` | `Every chart selected by a matched placement` | `1` |
| `chart values` | `All required values supplied` | `No missing required values` |
| `kustomize overlays` | `All required overlays present` | `No missing overlays` |
| `values files` | `Each values file belongs to a received chart` | `No orphan values files` |

**Received charts**

| Chart | Application set | Placement | Feature label | Hub values | Cluster values | Unmet required values |
|---|---|---|---|---|---|---|
| `example` | `example-clusters` | `all-managed-clusters` | `baseline` | false | true | — |

</details>

<details>
<summary>OK: Workload address uniqueness — No workload address is used by another cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ main (3333333)

Verifies: Reads every hosted-clusters/<hub>/<cluster>/values.yaml in CCI-MOC/oac-apps and collects services.APIServer.ipAddress, ingress.poolAddress, services.APIServer.externalIpAddress and ingress.externalIpAddress for each cluster. The check passes when no address used by `bu-ist-demo-workload0` is also used by a different cluster.
Not verified: Addresses are compared as strings, so equivalent CIDR and bare-IP spellings are not unified; duplicates inside one cluster are covered separately by workload.address_internal_duplicates.

| Field | Expected | Observed |
|---|---|---|
| `bu-ist-demo-workload0 services.APIServer.ipAddress 10.20.26.10` | `used by no other cluster` | `none` |
| `bu-ist-demo-workload0 ingress.poolAddress 10.20.28.10` | `used by no other cluster` | `none` |
| `bu-ist-demo-workload0 services.APIServer.externalIpAddress 10.20.29.10` | `used by no other cluster` | `none` |
| `bu-ist-demo-workload0 ingress.externalIpAddress 10.20.29.11` | `used by no other cluster` | `none` |

</details>

<details>
<summary>OK: Workload internal address duplicates — No address is used by more than one field of bu-ist-demo-workload0.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

Verifies: Reads services.APIServer.ipAddress, ingress.poolAddress, services.APIServer.externalIpAddress and ingress.externalIpAddress from hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml in CCI-MOC/oac-apps. Each value is parsed with the ipaddress module and compared across the four fields of that workload; the check passes when no address is used by more than one field, and reports an advisory when one is. The one exception is a shared address between exactly services.APIServer.externalIpAddress and ingress.externalIpAddress, which is allowed; any group with three or four fields that includes that pair is still reported.
Not verified: The report does not prove whether sharing an address is intentional; it only flags the duplicate inside this workload, apart from the allowed API-server and ingress external address pair. Cross-cluster duplicates are covered by workload.address_uniqueness.

| Field | Expected | Observed |
|---|---|---|
| `services.APIServer.ipAddress 10.20.26.10` | `not used by another field of bu-ist-demo-workload0` | `none` |
| `ingress.poolAddress 10.20.28.10` | `not used by another field of bu-ist-demo-workload0` | `none` |
| `services.APIServer.externalIpAddress 10.20.29.10` | `not used by another field of bu-ist-demo-workload0` | `none` |
| `ingress.externalIpAddress 10.20.29.11` | `not used by another field of bu-ist-demo-workload0` | `none` |

</details>

<details>
<summary>OK: Workload Pure storage realm — The bu-ist-demo-workload0 Pure storage realm reports subnet_vlan, subnet_prefix and s3_endpoint.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

Verifies: Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and selects the realms entry whose name equals `bu-ist-demo-workload0`. The check passes when subnet_vlan, subnet_prefix and s3_endpoint are all non-null.
Not verified: The three values are not validated against the workload VLAN or DNS, and no Pure array is contacted.

| Field | Expected | Observed |
|---|---|---|
| `name` | `bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `subnet_vlan` | `present` | `2322` |
| `subnet_prefix` | `present` | `10.20.28.0/24` |
| `s3_endpoint` | `present` | `s3.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>OK: Workload moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-workload0 is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block whose cluster_name equals `bu-ist-demo-workload0`. The check passes when such a block exists; its eso_writable_secret_prefixes are reported as context but nothing about them is required.
Not verified: The block's other attributes are not inspected, and the OIDC provider, IAM role and secret store are not exercised in AWS.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `eso_writable_secret_prefixes` | `not constrained by this check` | `none listed` |

</details>

<details>
<summary>OK: Workload moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policy_bu_ist_demo_workload0 names bu-ist-demo-workload0 in policy_name or cluster_subdomain.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and matches a block whose cluster_subdomain or policy_name names `bu-ist-demo-workload0` (policy_name is also tried with `-` replaced by `_`). The check passes when any block matches by name.
Not verified: The match is textual, so the certificate zone, DNS records and AWS permissions are not verified.

| Field | Expected | Observed |
|---|---|---|
| `policy entry` | `policy_name or cluster_subdomain names bu-ist-demo-workload0` | `cert_manager_policy_bu_ist_demo_workload0` |

</details>

<details>
<summary>OK: Workload Keycloak OIDC client — The Keycloak OIDC client for bu-ist-demo-workload0 matches cluster_name, openshift_redirect_uri and client_secret_name.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

Verifies: Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the block whose cluster_name equals `bu-ist-demo-workload0`. The check passes when openshift_redirect_uri equals `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` and client_secret_name equals `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc`.
Not verified: Only those three attributes are compared; the secret is not read and the Keycloak server is not contacted.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `openshift_redirect_uri` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` |
| `client_secret_name` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` |

</details>

<details>
<summary>OK: Workload identity provider — mocsso is enabled and the Keycloak OIDC client for bu-ist-demo-workload0 matches cluster_name, openshift_redirect_uri and client_secret_name.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

Verifies: Reads hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml in CCI-MOC/oac-apps. When oauth.mocsso.enabled is not true the check passes if oauth.identityProviders is a non-empty list; when it is true the moc-keycloak client must have cluster_name `bu-ist-demo-workload0`, openshift_redirect_uri `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` and client_secret_name `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc`.
Not verified: The configured identity-provider entries are not validated against Keycloak, and a disabled mocsso with an explicit provider is accepted without checking that the provider works.

| Field | Expected | Observed |
|---|---|---|
| `oauth.mocsso.enabled` | `true` | `true` |
| `moc-keycloak cluster_name` | `bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `moc-keycloak openshift_redirect_uri` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` |
| `moc-keycloak client_secret_name` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` |

</details>

<details>
<summary>REQUESTED: MOC issue — Issue #666 is open and records the environment request.</summary>

Source: CCI-MOC/MOC-issues · [`issues/666`](https://github.com/CCI-MOC/MOC-issues/issues/666) @ main (1111111)

Verifies: Reads CCI-MOC/MOC-issues issue #666 through the GitHub issues API and inspects only its state field. The check passes when that state is `open`, which records the environment request as still open.
Not verified: The issue body, title, labels, assignee and comments are not interpreted, so the check does not confirm that the issue describes this environment or that anyone has accepted the work.

| Field | Expected | Observed |
|---|---|---|
| `issue_state` | `open` | `open` |

</details>

Pull requests: skipped (--no-prs)

## Sources

| Repository | Ref | Commit |
|---|---|---|
| `MOC-issues` | `main` | [1111111](https://github.com/CCI-MOC/MOC-issues/commit/1111111111111111111111111111111111111111) |
| `ansible-switches` | `main` | [8888888](https://github.com/CCI-MOC/ansible-switches/commit/8888888888888888888888888888888888888888) |
| `everpure-moc` | `main` | [5555555](https://github.com/CCI-MOC/everpure-moc/commit/5555555555555555555555555555555555555555) |
| `moc-aws` | `main` | [6666666](https://github.com/CCI-MOC/moc-aws/commit/6666666666666666666666666666666666666666) |
| `moc-dns` | `main` | [7777777](https://github.com/CCI-MOC/moc-dns/commit/7777777777777777777777777777777777777777) |
| `moc-keycloak` | `main` | [4444444](https://github.com/CCI-MOC/moc-keycloak/commit/4444444444444444444444444444444444444444) |
| `oac-apps` | `main` | [3333333](https://github.com/CCI-MOC/oac-apps/commit/3333333333333333333333333333333333333333) |
| `oac-infra` | `main` | [2222222](https://github.com/CCI-MOC/oac-infra/commit/2222222222222222222222222222222222222222) |


## Legend

- REQUESTED: `requested` — The MOC issue records the request.
- OK: `declared_in_main` — Desired configuration is present on merged main.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
