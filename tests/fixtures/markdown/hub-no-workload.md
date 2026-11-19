# dizzy — environment configuration status

**10 blocking gaps, 0 advisories, and 3 of 14 checks pass; 1 check blocked by action 1**

Generated 2026-11-16 12:34 UTC · MOC issue: not set — pass `--issue N`

## Phase summary

### Hub phases

| Phase | HUB dizzy-infra |
|---|---:|
| 1 Host inventory entry | ✅ 1/1 checks |
| 2 Hub image inventory and vars | ❌ 1/3 checks, 1 blocked |
| 3 Discovery image reference | ❌ 0/1 checks |
| 4 Keycloak OIDC client | ❌ 0/1 checks |
| 5 GitOps values and apps | ❌ 0/7 checks |

## Next actions

1. **oac-infra** — [`hub-images/group_vars/dizzy-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/tree/main): Edit CCI-MOC/oac-infra at hub-images/group_vars/dizzy-infra/vars.yml and provide cluster_domain_name, base_domain, machine_network, api_ip, ingress_ip, and dns_ip. cluster_domain_name is not found; expected present. base_domain is not found; expected present. machine_network is not found; expected present. api_ip is not found; expected present. ingress_ip is not found; expected present. dns_ip is not found; expected present.
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment)
2. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/tree/main): Generate and publish a hub-specific discovery ISO, then replace the generic boot_image_url for every host in the hub cluster group. boot_image_url is none; expected filename contains dizzy-infra. (after 1)
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment)
3. **moc-keycloak** — [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf): Edit CCI-MOC/moc-keycloak at main.tf and add the hub's OIDC client, redirect URI, and secret reference. Set cluster_name = `dizzy-infra`, openshift_redirect_uri = `https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso`, and client_secret_name = `cluster/dizzy-infra/keycloak-oidc`. client is not found; expected dizzy-infra. openshift_redirect_uri is not found; expected https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso. client_secret_name is not found; expected cluster/dizzy-infra/keycloak-oidc. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
4. **oac-apps** — [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete the hub hosted-cluster defaults file at hosted-clusters/dizzy-infra/values.yaml in CCI-MOC/oac-apps. hosted-clusters/dizzy-infra/values.yaml is missing; expected present. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
5. **everpure-moc** — [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/tree/main): Add or correct the hub realm in everpure-moc realms.yaml. name is not found; expected dizzy-infra. subnet_vlan is not found; expected present. subnet_prefix is not found; expected present. s3_endpoint is not found; expected present. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
6. **oac-apps** — [`values/dizzy-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main): Copy the required local-cluster component files from an existing hub environment and adjust cluster-specific names and addresses. values/dizzy-infra/local-cluster/acm.yaml is missing; expected present. values/dizzy-infra/local-cluster/acm-placements.yaml is missing; expected present. values/dizzy-infra/local-cluster/cert-manager.yaml is missing; expected present. values/dizzy-infra/local-cluster/cluster-certificates.yaml is missing; expected present. values/dizzy-infra/local-cluster/cluster-version.yaml is missing; expected present. values/dizzy-infra/local-cluster/external-dns-operator.yaml is missing; expected present. values/dizzy-infra/local-cluster/external-secrets.yaml is missing; expected present. values/dizzy-infra/local-cluster/hcp-config.yaml is missing; expected present. values/dizzy-infra/local-cluster/keycloak-oauth.yaml is missing; expected present. values/dizzy-infra/local-cluster/metallb.yaml is missing; expected present. values/dizzy-infra/local-cluster/openshift-gitops.yaml is missing; expected present. values/dizzy-infra/local-cluster/portworx.yaml is missing; expected present. values/dizzy-infra/local-cluster/user-workload-monitoring.yaml is missing; expected present. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
7. **moc-aws** — [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf): Add or correct the hub entry in moc-aws local.openshift_oidc_clusters. cluster_name is not found; expected dizzy-infra. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
8. **moc-aws** — [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf): Add a cert-manager policy entry for the hub. policy entry is not found; expected policy_name or cluster_subdomain names dizzy-infra. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
9. **oac-apps** — [`values/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete values/dizzy-infra/hcp-config.yaml in CCI-MOC/oac-apps for hub-wide HCP and secret-selector values. values/dizzy-infra/hcp-config.yaml is missing; expected present. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
10. **oac-apps** — [`apps/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Add Argo CD application manifests for the hub after its hosted-cluster, hub-wide component, and local-cluster values are present, and reference the correct clusters. apps/dizzy-infra/keycloak-oauth.yaml is missing; expected present. (after 4, 9, 6, 3)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)

## Not checked — verify by hand

- [ ] **Configure cluster and storage networks and firewalls for dizzy-infra** (phase 1) — The repositories read by this tool do not describe the switch, network, or firewall state required for dizzy-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#infrastructure-configuration).
- [ ] **Store the dizzy-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/dizzy-infra/sshkey or cluster/dizzy-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Place the pull secret and SSH key under hub-images/credentials/dizzy-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for dizzy-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Run create_agent_install_media and copy the dizzy-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Bootstrap Argo CD for dizzy-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration).
- [ ] **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).
- [ ] **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).

## Details

<details>
<summary>✅ dizzy-infra host inventory — The inventory contains a dizzy-infra group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and walks every Ansible group in every child group. The check passes when at least one group declares vars.cluster == `dizzy-infra`; the host count does not affect the state.
Not verified: Host names, node_name values, MAC addresses, boot images and group nesting are not validated here, and a matching group with zero hosts still passes.

| Field | Expected | Observed |
|---|---|---|
| `cluster_group` | `a group with vars.cluster == dizzy-infra` | `dizzy-infra` |
| `host_count` | `reported (not required)` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| `control-0` | `MOC-R4PAC10U31-S1D` | — | — |

</details>

<details>
<summary>✅ Hub image inventory — The hub-image inventory contains the all.children.dizzy-infra key.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ main (2222222)

Verifies: Reads hub-images/inventory.yml in CCI-MOC/oac-infra as YAML and looks for the all.children.dizzy-infra key. The check passes when that key exists, whatever hosts or variables it contains.
Not verified: The hosts, images and variables under the key are not inspected, so an empty or placeholder entry passes.

| Field | Expected | Observed |
|---|---|---|
| `inventory_key` | `key all.children.dizzy-infra` | `dizzy-infra` |

</details>

<details open>
<summary>❌ Hub image variables — The hub-image variable file is absent from main.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/dizzy-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/tree/main) @ main (2222222)

Verifies: Reads hub-images/group_vars/dizzy-infra/vars.yml in CCI-MOC/oac-infra and requires six keys to be non-empty: cluster_domain_name, base_domain, machine_network, api_ip, ingress_ip and dns_ip. The check passes when all six are present.
Not verified: The six values are not validated, so the addresses need not be parseable or inside machine_network and the domains need not resolve.

| Field | Expected | Observed |
|---|---|---|
| `cluster_domain_name` | `present` | `—` |
| `base_domain` | `present` | `—` |
| `machine_network` | `present` | `—` |
| `api_ip` | `present` | `—` |
| `ingress_ip` | `present` | `—` |
| `dns_ip` | `present` | `—` |

</details>

<details open>
<summary>• Hub moc-dns records — Blocked until Hub image variables is complete.</summary>

Source: CCI-MOC/moc-dns · [`zonefiles/`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/) @ main (—)

Verifies: Picks the longest moc-dns zonefile under zonefiles/ whose name is a suffix of `dizzy.int.massopen.cloud`, parses its A records, and requires api.dizzy.int.massopen.cloud and api-int.dizzy.int.massopen.cloud to equal the hub api_ip and *.apps.dizzy.int.massopen.cloud to equal the hub ingress_ip. The check passes when all three records point at those addresses.
Not verified: Only A records in that one zonefile are compared; CNAMEs, TTLs, delegation and live DNS resolution are not checked.

| Field | Expected | Observed |
|---|---|---|
| `api` | `—` | `—` |
| `api-int` | `—` | `—` |
| `*.apps` | `—` | `—` |

</details>

<details open>
<summary>❌ dizzy-infra boot image — No boot image URL is inherited by the cluster host group.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/tree/main) @ main (2222222)

Verifies: Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and collects every boot_image_url inherited by the `dizzy-infra` host group. The check passes when exactly one URL is declared and its filename contains `dizzy-infra` or the oac-shortened `dizzy-infra`; the generic `discovery.iso` name, several different URLs, or an unrecognized filename do not pass.
Not verified: The URL is never fetched, so the ISO's existence, checksum and contents are not verified; only the filename is examined.

Status rule: The boot-image filename must contain the full cluster name `dizzy-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `boot_image_url` | `filename contains dizzy-infra` | `none` |

</details>

<details open>
<summary>❌ Hub OIDC client — No Keycloak OIDC client block exists for this hub.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

Verifies: Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the block whose cluster_name equals `dizzy-infra`. The check passes when openshift_redirect_uri equals `https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso` and client_secret_name equals `cluster/dizzy-infra/keycloak-oidc`.
Not verified: Only those three string attributes are compared; the HCL is never applied, so Keycloak runtime state and the referenced secret's existence are not verified.

| Field | Expected | Observed |
|---|---|---|
| `client` | `dizzy-infra` | `—` |
| `openshift_redirect_uri` | `https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso` | `—` |
| `client_secret_name` | `cluster/dizzy-infra/keycloak-oidc` | `—` |

</details>

<details open>
<summary>❌ Hub hosted-cluster defaults — None of the 1 required file exist in main under hosted-clusters/dizzy-infra. Missing: hosted-clusters/dizzy-infra/values.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires the path hosted-clusters/dizzy-infra/values.yaml to exist. The check passes when that single path is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so missing or malformed hosted-cluster defaults still pass.

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ Hub-wide component values — None of the 1 required file exist in main under values/dizzy-infra. Missing: values/dizzy-infra/hcp-config.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires values/dizzy-infra/hcp-config.yaml for hub-wide HCP and secret-selector values. The check passes when that path exists in `main`; the file is never opened.
Not verified: Only path existence is tested; the file contents are not read, so the HCP and secret-selector keys are never checked.

| Field | Expected | Observed |
|---|---|---|
| [`values/dizzy-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ Hub local-cluster values — None of the 13 required files exist in main under values/dizzy-infra/local-cluster. Missing: values/dizzy-infra/local-cluster/acm.yaml, values/dizzy-infra/local-cluster/acm-placements.yaml, values/dizzy-infra/local-cluster/cert-manager.yaml, values/dizzy-infra/local-cluster/cluster-certificates.yaml, values/dizzy-infra/local-cluster/cluster-version.yaml, values/dizzy-infra/local-cluster/external-dns-operator.yaml, values/dizzy-infra/local-cluster/external-secrets.yaml, values/dizzy-infra/local-cluster/hcp-config.yaml, values/dizzy-infra/local-cluster/keycloak-oauth.yaml, values/dizzy-infra/local-cluster/metallb.yaml, values/dizzy-infra/local-cluster/openshift-gitops.yaml, values/dizzy-infra/local-cluster/portworx.yaml, values/dizzy-infra/local-cluster/user-workload-monitoring.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/dizzy-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires 13 files under values/dizzy-infra/local-cluster/: acm.yaml, acm-placements.yaml, cert-manager.yaml, cluster-certificates.yaml, cluster-version.yaml, external-dns-operator.yaml, external-secrets.yaml, hcp-config.yaml, keycloak-oauth.yaml, metallb.yaml, openshift-gitops.yaml, portworx.yaml, user-workload-monitoring.yaml. Configured optional components (none configured) must exist too, and the check passes only when every required and optional file is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so operator versions, values and cluster-specific names are never validated.

| Field | Expected | Observed |
|---|---|---|
| [`values/dizzy-infra/local-cluster/acm.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/cert-manager.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/cluster-certificates.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/cluster-version.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/external-dns-operator.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/external-secrets.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/metallb.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/openshift-gitops.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/portworx.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/dizzy-infra/local-cluster/user-workload-monitoring.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

**Required files**

| Path | Status |
|---|---|
| `values/dizzy-infra/local-cluster/acm-placements.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/acm.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/cert-manager.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/cluster-certificates.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/cluster-version.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/external-dns-operator.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/external-secrets.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/hcp-config.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/keycloak-oauth.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/metallb.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/openshift-gitops.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/portworx.yaml` | `missing` |
| `values/dizzy-infra/local-cluster/user-workload-monitoring.yaml` | `missing` |

**Additional files present**

None.

</details>

<details open>
<summary>❌ Hub ArgoCD applications — None of the 1 required file exist in main under apps/dizzy-infra. Missing: apps/dizzy-infra/keycloak-oauth.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`apps/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires apps/dizzy-infra/keycloak-oauth.yaml. The check passes when that Argo CD application manifest path exists in `main`.
Not verified: Only path existence is tested; the file contents are not read, so the manifest's destination cluster and sync policy are not checked.

| Field | Expected | Observed |
|---|---|---|
| [`apps/dizzy-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ Hub Pure storage realm — No Pure storage realm named dizzy-infra was found.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/tree/main) @ main (5555555)

Verifies: Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and selects the realms entry whose name equals `dizzy-infra`. The check passes when subnet_vlan, subnet_prefix and s3_endpoint are all non-null.
Not verified: The three values are not validated against the hub machine network or DNS, and no Pure array is contacted.

| Field | Expected | Observed |
|---|---|---|
| `name` | `dizzy-infra` | `—` |
| `subnet_vlan` | `present` | `—` |
| `subnet_prefix` | `present` | `—` |
| `s3_endpoint` | `present` | `—` |

</details>

<details open>
<summary>❌ Hub moc-aws OIDC cluster — No moc-aws OIDC cluster entry has cluster_name dizzy-infra.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block whose cluster_name equals `dizzy-infra`. The check passes when such a block exists; its eso_writable_secret_prefixes are reported as context but nothing about them is required.
Not verified: The block's other attributes are not inspected, and the OIDC provider, IAM role and secret store are not exercised in AWS.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `dizzy-infra` | `—` |
| `eso_writable_secret_prefixes` | `not constrained by this check` | `none listed` |

</details>

<details open>
<summary>❌ Hub moc-aws cert-manager policy — No cert-manager policy entry names dizzy-infra.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and matches a block whose cluster_subdomain or policy_name names `dizzy-infra` (policy_name is also tried with `-` replaced by `_`). The check passes when any block matches by name.
Not verified: The match is textual, so the certificate zone, DNS records and AWS permissions are not verified.

| Field | Expected | Observed |
|---|---|---|
| `policy entry` | `policy_name or cluster_subdomain names dizzy-infra` | `—` |

</details>

<details>
<summary>✅ Workload address uniqueness — No workload address is used by another cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ main (3333333)

Verifies: Reads every hosted-clusters/<hub>/<cluster>/values.yaml in CCI-MOC/oac-apps and collects services.APIServer.ipAddress, ingress.poolAddress, services.APIServer.externalIpAddress and ingress.externalIpAddress for each cluster. The check passes when no address used by `dizzy-infra` is also used by a different cluster.
Not verified: Addresses are compared as strings, so equivalent CIDR and bare-IP spellings are not unified; duplicates inside one cluster are covered separately by workload.address_internal_duplicates.

</details>

Pull requests: skipped (--no-prs)

## Sources

| Repository | Ref | Commit |
|---|---|---|
| `ansible-switches` | `main` | [8888888](https://github.com/CCI-MOC/ansible-switches/commit/8888888888888888888888888888888888888888) |
| `everpure-moc` | `main` | [5555555](https://github.com/CCI-MOC/everpure-moc/commit/5555555555555555555555555555555555555555) |
| `moc-aws` | `main` | [6666666](https://github.com/CCI-MOC/moc-aws/commit/6666666666666666666666666666666666666666) |
| `moc-keycloak` | `main` | [4444444](https://github.com/CCI-MOC/moc-keycloak/commit/4444444444444444444444444444444444444444) |
| `oac-apps` | `main` | [3333333](https://github.com/CCI-MOC/oac-apps/commit/3333333333333333333333333333333333333333) |
| `oac-infra` | `main` | [2222222](https://github.com/CCI-MOC/oac-infra/commit/2222222222222222222222222222222222222222) |


## Legend

- ✅ `declared_in_main` — Desired configuration is present on merged main.
- ❌ `missing` — Required configuration was not found.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
