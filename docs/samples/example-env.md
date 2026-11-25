SAMPLE — generated from a synthetic fixture, not a live environment.

# example-env — environment configuration status

**8 blocking gaps, 0 advisories, and 15 of 29 checks pass; 6 checks blocked by action 7**

Generated 2026-11-16 12:34 UTC · MOC issue: not set — pass `--issue N`

## Phase summary

### Hub phases

| Phase | HUB example-env-infra |
|---|---:|
| 1 Host inventory entry | OK 1/1 checks |
| 2 Hub image inventory and vars | OK 3/3 checks |
| 3 Discovery image reference | FAIL 0/1 checks |
| 4 Keycloak OIDC client | OK 1/1 checks |
| 5 GitOps values and apps | FAIL 4/8 checks |

### Workload phases

| Phase | WORKLOAD example-env-workload0 |
|---|---:|
| 1 Host inventory entry | OK 1/1 checks |
| 2 Hub agent discovery ISO | FAIL 0/1 checks |
| 3 Agent ISO boot | verify by hand |
| 4 Agent visibility | verify by hand |
| 5 Agent labels and approval | OK 1/1 checks |
| 6 oac-apps values | FAIL 1/9 checks, 6 blocked |
| 7 Shared-service prerequisites | OK 3/3 checks |

## Next actions

1. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml): Generate and publish a hub-specific discovery ISO, then replace the generic boot_image_url for every host in the hub cluster group. boot_image_url is http://10.2.0.82/boot/discovery.iso; expected filename contains example-env-infra.
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment)
2. **oac-apps** — [`hosted-clusters/example-env-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete the hub hosted-cluster defaults file at hosted-clusters/example-env-infra/values.yaml in CCI-MOC/oac-apps. hosted-clusters/example-env-infra/values.yaml is missing; expected present. (after 1)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
3. **oac-apps** — [`values/example-env-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main): Copy the required local-cluster component files from an existing hub environment and adjust cluster-specific names and addresses. values/example-env-infra/local-cluster/acm.yaml is missing; expected present. values/example-env-infra/local-cluster/acm-placements.yaml is missing; expected present. values/example-env-infra/local-cluster/cert-manager.yaml is missing; expected present. values/example-env-infra/local-cluster/cluster-certificates.yaml is missing; expected present. values/example-env-infra/local-cluster/cluster-version.yaml is missing; expected present. values/example-env-infra/local-cluster/external-dns-operator.yaml is missing; expected present. values/example-env-infra/local-cluster/external-secrets.yaml is missing; expected present. values/example-env-infra/local-cluster/hcp-config.yaml is missing; expected present. values/example-env-infra/local-cluster/keycloak-oauth.yaml is missing; expected present. values/example-env-infra/local-cluster/metallb.yaml is missing; expected present. values/example-env-infra/local-cluster/openshift-gitops.yaml is missing; expected present. values/example-env-infra/local-cluster/portworx.yaml is missing; expected present. values/example-env-infra/local-cluster/user-workload-monitoring.yaml is missing; expected present. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
4. **oac-apps** — [`values/example-env-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete values/example-env-infra/hcp-config.yaml in CCI-MOC/oac-apps for hub-wide HCP and secret-selector values. values/example-env-infra/hcp-config.yaml is missing; expected present. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
5. **oac-apps** — [`apps/example-env-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Add Argo CD application manifests for the hub after its hosted-cluster, hub-wide component, and local-cluster values are present, and reference the correct clusters. apps/example-env-infra/keycloak-oauth.yaml is missing; expected present. (after 2, 4, 3)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
6. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml): example-env-workload0: Generate and publish the parent hub's agent discovery ISO, then replace the generic boot_image_url for every host in the workload cluster group. boot_image_url is http://10.2.0.82/boot/discovery.iso; expected filename contains example-env-workload0 or example-env-infra. (after 1)
   Guide: [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration)
7. **oac-apps** — [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): example-env-workload0: Create the missing hosted-cluster values file from the closest existing environment; set the cluster name, parent hub, networking, and node pools before adding components. hosted-clusters/example-env-infra/example-env-workload0/values.yaml is missing; expected present. (after 2)
   Guide: [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#cluster-deployment-and-configuration)
8. **oac-apps** — [`values/example-env-infra/example-env-workload0`](https://github.com/CCI-MOC/oac-apps/tree/main): example-env-workload0: Create the workload component-values directory, starting with hcp-config.yaml and only the shared components this workload needs. values/example-env-infra/example-env-workload0 is 0 file(s); expected at least 1 file. (after 7)
   Guide: [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#cluster-deployment-and-configuration)

## Not checked — verify by hand

- **Configure cluster and storage networks and firewalls for example-env-infra** (phase 1) — The repositories read by this tool do not describe the switch, network, or firewall state required for example-env-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#infrastructure-configuration).
- **Store the example-env-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/example-env-infra/sshkey or cluster/example-env-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Place the pull secret and SSH key under hub-images/credentials/example-env-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for example-env-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Run create_agent_install_media and copy the example-env-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- **Bootstrap Argo CD for example-env-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration).
- **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).
- **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).

## Details

<details>
<summary>OK: example-env-infra host inventory — The inventory contains a example-env-infra group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Host management: Not recorded.

Verifies: Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and walks every Ansible group in every child group. The check passes when at least one group declares vars.cluster == `example-env-infra`; the host count does not affect the state.
Not verified: Host names, node_name values, MAC addresses, boot images and group nesting are not validated here, and a matching group with zero hosts still passes.

| Field | Expected | Observed |
|---|---|---|
| `cluster_group` | `a group with vars.cluster == example-env-infra` | `example-env-infra` |
| `host_count` | `reported (not required)` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL | Management (bm_management) |
|---|---|---|---|---|
| `control-0` | `MOC-R4PAC10U31-S1A` | — | `http://10.2.0.82/boot/discovery.iso` | `Not recorded` |

</details>

<details>
<summary>OK: Hub image inventory — The hub-image inventory contains the all.children.example-env-infra key.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ main (2222222)

Verifies: Reads hub-images/inventory.yml in CCI-MOC/oac-infra as YAML and looks for the all.children.example-env-infra key. The check passes when that key exists, whatever hosts or variables it contains.
Not verified: The hosts, images and variables under the key are not inspected, so an empty or placeholder entry passes.

| Field | Expected | Observed |
|---|---|---|
| `inventory_key` | `key all.children.example-env-infra` | `example-env-infra` |

</details>

<details>
<summary>OK: Hub image variables — All six required hub-image variables are present in main; their values are not validated.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/example-env-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/example-env-infra/vars.yml) @ main (2222222)

Verifies: Reads hub-images/group_vars/example-env-infra/vars.yml in CCI-MOC/oac-infra and requires six keys to be non-empty: cluster_domain_name, base_domain, machine_network, api_ip, ingress_ip and dns_ip. The check passes when all six are present.
Not verified: The six values are not validated, so the addresses need not be parseable or inside machine_network and the domains need not resolve.

| Field | Expected | Observed |
|---|---|---|
| `cluster_domain_name` | `present` | `example-env` |
| `base_domain` | `present` | `int.massopen.cloud` |
| `machine_network` | `present` | `10.20.26.0/23` |
| `api_ip` | `present` | `10.20.27.11` |
| `ingress_ip` | `present` | `10.20.27.12` |
| `dns_ip` | `present` | `8.8.8.8` |

</details>

<details>
<summary>OK: Hub moc-dns records — All required hub DNS records in zonefiles/int.massopen.cloud.zone match the hub-image variables.</summary>

Source: CCI-MOC/moc-dns · [`zonefiles/int.massopen.cloud.zone`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/int.massopen.cloud.zone) @ main (7777777)

Verifies: Picks the longest moc-dns zonefile under zonefiles/ whose name is a suffix of `example-env.int.massopen.cloud`, parses its A records, and requires api.example-env.int.massopen.cloud and api-int.example-env.int.massopen.cloud to equal the hub api_ip and *.apps.example-env.int.massopen.cloud to equal the hub ingress_ip. The check passes when all three records point at those addresses.
Not verified: Only A records in that one zonefile are compared; CNAMEs, TTLs, delegation and live DNS resolution are not checked.

| Field | Expected | Observed |
|---|---|---|
| `api.example-env.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `api-int.example-env.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `*.apps.example-env.int.massopen.cloud` | `10.20.27.12` | `10.20.27.12` |

</details>

<details open>
<summary>FAIL: example-env-infra boot image — A boot image URL is present, but it points to the generic discovery.iso rather than a cluster-specific image.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and collects every boot_image_url inherited by the `example-env-infra` host group. The check passes when exactly one URL is declared and its filename contains `example-env-infra` or the oac-shortened `example-env-infra`; the generic `discovery.iso` name, several different URLs, or an unrecognized filename do not pass.
Not verified: The URL is never fetched, so the ISO's existence, checksum and contents are not verified; only the filename is examined.

Status rule: The boot-image filename must contain the full cluster name `example-env-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `boot_image_url` | `filename contains example-env-infra` | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details>
<summary>OK: Hub OIDC client — All expected Keycloak OIDC client fields match.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

Verifies: Parses HCL blocks in CCI-MOC/moc-keycloak main.tf and selects the block whose cluster_name equals `example-env-infra`. The check passes when openshift_redirect_uri equals `https://oauth-openshift.apps.example-env.int.massopen.cloud/oauth2callback/mocsso` and client_secret_name equals `cluster/example-env-infra/keycloak-oidc`.
Not verified: Only those three string attributes are compared; the HCL is never applied, so Keycloak runtime state and the referenced secret's existence are not verified.

| Field | Expected | Observed |
|---|---|---|
| `client` | `example-env-infra` | `example-env-infra` |
| `openshift_redirect_uri` | `https://oauth-openshift.apps.example-env.int.massopen.cloud/oauth2callback/mocsso` | `https://oauth-openshift.apps.example-env.int.massopen.cloud/oauth2callback/mocsso` |
| `client_secret_name` | `cluster/example-env-infra/keycloak-oidc` | `cluster/example-env-infra/keycloak-oidc` |

</details>

<details open>
<summary>FAIL: Hub hosted-cluster defaults — None of the 1 required file exist in main under hosted-clusters/example-env-infra. Missing: hosted-clusters/example-env-infra/values.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires the path hosted-clusters/example-env-infra/values.yaml to exist. The check passes when that single path is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so missing or malformed hosted-cluster defaults still pass.

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/example-env-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>FAIL: Hub-wide component values — None of the 1 required file exist in main under values/example-env-infra. Missing: values/example-env-infra/hcp-config.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/example-env-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires values/example-env-infra/hcp-config.yaml for hub-wide HCP and secret-selector values. The check passes when that path exists in `main`; the file is never opened.
Not verified: Only path existence is tested; the file contents are not read, so the HCP and secret-selector keys are never checked.

| Field | Expected | Observed |
|---|---|---|
| [`values/example-env-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>FAIL: Hub local-cluster values — None of the 13 required files exist in main under values/example-env-infra/local-cluster. Missing: values/example-env-infra/local-cluster/acm.yaml, values/example-env-infra/local-cluster/acm-placements.yaml, values/example-env-infra/local-cluster/cert-manager.yaml, values/example-env-infra/local-cluster/cluster-certificates.yaml, values/example-env-infra/local-cluster/cluster-version.yaml, values/example-env-infra/local-cluster/external-dns-operator.yaml, values/example-env-infra/local-cluster/external-secrets.yaml, values/example-env-infra/local-cluster/hcp-config.yaml, values/example-env-infra/local-cluster/keycloak-oauth.yaml, values/example-env-infra/local-cluster/metallb.yaml, values/example-env-infra/local-cluster/openshift-gitops.yaml, values/example-env-infra/local-cluster/portworx.yaml, values/example-env-infra/local-cluster/user-workload-monitoring.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/example-env-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires 13 files under values/example-env-infra/local-cluster/: acm.yaml, acm-placements.yaml, cert-manager.yaml, cluster-certificates.yaml, cluster-version.yaml, external-dns-operator.yaml, external-secrets.yaml, hcp-config.yaml, keycloak-oauth.yaml, metallb.yaml, openshift-gitops.yaml, portworx.yaml, user-workload-monitoring.yaml. Configured optional components (none configured) must exist too, and the check passes only when every required and optional file is present in `main`.
Not verified: Only path existence is tested; the file contents are not read, so operator versions, values and cluster-specific names are never validated.

| Field | Expected | Observed |
|---|---|---|
| [`values/example-env-infra/local-cluster/acm.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/cert-manager.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/cluster-certificates.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/cluster-version.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/external-dns-operator.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/external-secrets.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/metallb.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/openshift-gitops.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/portworx.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/example-env-infra/local-cluster/user-workload-monitoring.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

**Required files**

| Path | Status |
|---|---|
| `values/example-env-infra/local-cluster/acm-placements.yaml` | `missing` |
| `values/example-env-infra/local-cluster/acm.yaml` | `missing` |
| `values/example-env-infra/local-cluster/cert-manager.yaml` | `missing` |
| `values/example-env-infra/local-cluster/cluster-certificates.yaml` | `missing` |
| `values/example-env-infra/local-cluster/cluster-version.yaml` | `missing` |
| `values/example-env-infra/local-cluster/external-dns-operator.yaml` | `missing` |
| `values/example-env-infra/local-cluster/external-secrets.yaml` | `missing` |
| `values/example-env-infra/local-cluster/hcp-config.yaml` | `missing` |
| `values/example-env-infra/local-cluster/keycloak-oauth.yaml` | `missing` |
| `values/example-env-infra/local-cluster/metallb.yaml` | `missing` |
| `values/example-env-infra/local-cluster/openshift-gitops.yaml` | `missing` |
| `values/example-env-infra/local-cluster/portworx.yaml` | `missing` |
| `values/example-env-infra/local-cluster/user-workload-monitoring.yaml` | `missing` |

**Additional files present**

None.

</details>

<details open>
<summary>FAIL: Hub ArgoCD applications — None of the 1 required file exist in main under apps/example-env-infra. Missing: apps/example-env-infra/keycloak-oauth.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`apps/example-env-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires apps/example-env-infra/keycloak-oauth.yaml. The check passes when that Argo CD application manifest path exists in `main`.
Not verified: Only path existence is tested; the file contents are not read, so the manifest's destination cluster and sync policy are not checked.

| Field | Expected | Observed |
|---|---|---|
| [`apps/example-env-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details>
<summary>OK: Hub Pure storage realm — The example-env-infra Pure storage realm reports subnet_vlan, subnet_prefix and s3_endpoint.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

Verifies: Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and selects the realms entry whose name equals `example-env-infra`. The check passes when subnet_vlan, subnet_prefix and s3_endpoint are all non-null.
Not verified: The three values are not validated against the hub machine network or DNS, and no Pure array is contacted.

| Field | Expected | Observed |
|---|---|---|
| `name` | `example-env-infra` | `example-env-infra` |
| `subnet_vlan` | `present` | `2321` |
| `subnet_prefix` | `present` | `10.9.15.0/24` |
| `s3_endpoint` | `present` | `s3.example-env.int.massopen.cloud` |

</details>

<details>
<summary>OK: Hub moc-aws OIDC cluster — The moc-aws OIDC cluster entry for example-env-infra is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block whose cluster_name equals `example-env-infra`. The check passes when such a block exists; its eso_writable_secret_prefixes are reported as context but nothing about them is required.
Not verified: The block's other attributes are not inspected, and the OIDC provider, IAM role and secret store are not exercised in AWS.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `example-env-infra` | `example-env-infra` |
| `eso_writable_secret_prefixes` | `not constrained by this check` | `cluster/example-env-infra/hostedcluster/` |

</details>

<details>
<summary>OK: Hub moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policies names example-env-infra in policy_name or cluster_subdomain.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and matches a block whose cluster_subdomain or policy_name names `example-env-infra` (policy_name is also tried with `-` replaced by `_`). The check passes when any block matches by name.
Not verified: The match is textual, so the certificate zone, DNS records and AWS permissions are not verified.

| Field | Expected | Observed |
|---|---|---|
| `policy entry` | `policy_name or cluster_subdomain names example-env-infra` | `cert_manager_policies` |

</details>

<details>
<summary>OK: Hub hosted-cluster secret prefix — The hub can write hosted-cluster secrets at cluster/example-env-infra/hostedcluster/.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Reads the CCI-MOC/moc-aws main.tf block whose cluster_name equals `example-env-infra` and inspects its eso_writable_secret_prefixes list. The check passes when `cluster/example-env-infra/hostedcluster/` is one of the listed prefixes.
Not verified: The rest of the hub block and the AWS-side secret store are not inspected, so an unwritable or missing store is not detected.

| Field | Expected | Observed |
|---|---|---|
| `eso_writable_secret_prefixes` | `cluster/example-env-infra/hostedcluster/` | `cluster/example-env-infra/hostedcluster/` |

</details>

<details>
<summary>OK: example-env-workload0 host inventory — The inventory contains a example-env-workload0 group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Host management: Other management (ipmi; treated as non-OpenStack).

Verifies: Parses CCI-MOC/oac-infra infra/inventory/00hosts.yaml as YAML and walks every Ansible group in every child group. The check passes when at least one group declares vars.cluster == `example-env-workload0`; the host count does not affect the state.
Not verified: Host names, node_name values, MAC addresses, boot images and group nesting are not validated here, and a matching group with zero hosts still passes.

| Field | Expected | Observed |
|---|---|---|
| `cluster_group` | `a group with vars.cluster == example-env-workload0` | `example-env-workload0` |
| `host_count` | `reported (not required)` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL | Management (bm_management) |
|---|---|---|---|---|
| `compute-0` | `MOC-R4PAC10U31-S1B` | — | `http://10.2.0.82/boot/discovery.iso` | `Other management (ipmi; treated as non-OpenStack)` |

</details>

<details open>
<summary>FAIL: example-env-workload0 boot image — A boot image URL is present, but the workload is still on the generic discovery.iso rather than the expected `example-env-infra-agent-discovery.iso`.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Verifies: Parses infra/inventory/00hosts.yaml in CCI-MOC/oac-infra and collects every boot_image_url inherited by the `example-env-workload0` host group. The check passes when exactly one URL is declared and its filename contains `example-env-workload0`, its oac-shortened name, the parent hub `example-env-infra`, or the hub's oac-shortened name; `discovery.iso` and unrecognized names do not pass.
Not verified: The URL is never fetched, so the image's existence, checksum and contents are not verified; only the filename is examined.

Status rule: The workload boot-image filename may contain the workload name `example-env-workload0`, its oac-shortened name, the parent hub name `example-env-infra`, or the hub's oac-shortened name. Unrecognized names are advisory because naming is not consistent across environments; generic `discovery.iso` remains a gap.

| Field | Expected | Observed |
|---|---|---|
| `boot_image_url` | `filename contains example-env-workload0 or example-env-infra` | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details>
<summary>OK: example-env-workload0 update-agents inputs — Every non-openstack host has the mac_addr and resource_class inputs required by infra/update-agents.yaml.</summary>

Source: CCI-MOC/oac-infra · [`infra/update-agents.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/update-agents.yaml) @ main (2222222)

Host management: Other management (ipmi; treated as non-OpenStack).

Verifies: Applies input requirements per host using the observed bm_management value. Hosts with bm_management=openstack obtain MAC addresses and resource classes from OpenStack; all other hosts require mac_addr and resource_class inventory inputs. Hardware-documentation differences are advisory only.
Not verified: Address and resource-class formats, management-system connectivity, and actual agent labels or approval are not verified. The playbook is checked only for existence.

**Agent input requirements by host**

| Field | Expected | Observed |
|---|---|---|
| `compute-0.mac_addr` | `present` | `00:11:22:33:44:55` |
| `compute-0.resource_class` | `present` | `example-env-worker` |

**Resource-class documentation comparison (advisory only)**

Documented hardware classes are reference information, not defaults or required values. Agent resource-class labels must match the NodePool selectors.

| Host | Inventory resource_class | Documented hardware class | Comparison |
|---|---|---|---|
| `compute-0` | `example-env-worker` | `example-env-worker` | `Matches documentation` |

**Agent label inputs**

| Host | bm_management | mac_addr | resource_class | Management |
|---|---|---|---|---|
| `compute-0` | `ipmi` | `00:11:22:33:44:55` | `example-env-worker` | `Other management (ipmi; treated as non-OpenStack)` |

</details>

<details open>
<summary>FAIL: Workload hosted-cluster values — None of the 1 required file exist in main under hosted-clusters/example-env-infra/example-env-workload0. Missing: hosted-clusters/example-env-infra/example-env-workload0/values.yaml. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and requires hosted-clusters/example-env-infra/example-env-workload0/values.yaml. The check passes when that path exists in `main`.
Not verified: Only path existence is tested; the file contents are not read, so the cluster name, parent hub, networking and node pools are not verified here.

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>FAIL: Workload component values — No files exist in main under values/example-env-infra/example-env-workload0; at least 1 is required. File contents are not read.</summary>

Source: CCI-MOC/oac-apps · [`values/example-env-infra/example-env-workload0`](https://github.com/CCI-MOC/oac-apps/tree/main) @ main (3333333)

Verifies: Lists the CCI-MOC/oac-apps tree and counts files under values/example-env-infra/example-env-workload0/. The check passes when at least one file exists there in `main`; there is no fixed required-file list.
Not verified: Only path existence is tested; the file contents are not read, so individual components such as hcp-config.yaml are not confirmed.

| Field | Expected | Observed |
|---|---|---|
| `values/example-env-infra/example-env-workload0` | `at least 1 file` | `0 file(s)` |

</details>

<details open>
<summary>BLOCKED: Workload API address network — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: Reads services.APIServer.ipAddress from hosted-clusters/example-env-infra/example-env-workload0/values.yaml and tests it with the ipaddress module against the hub machine network `10.20.26.0/23` from hub-images/group_vars/example-env-infra/vars.yml. The check passes when the address is inside that network.
Not verified: The address is not checked against other clusters here (see workload.address_uniqueness) and the live API endpoint is not contacted.

| Field | Expected | Observed |
|---|---|---|
| `services.APIServer.ipAddress` | `inside None` | `—` |

</details>

<details open>
<summary>BLOCKED: Workload ingress address network — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: Reads ingress.poolAddress from hosted-clusters/example-env-infra/example-env-workload0/values.yaml and requires a parseable IP address or CIDR. The check passes when the address is outside the hub machine network `10.20.26.0/23` and inside the subnet4 of the ansible-switches VLAN that matches example-env-workload0 (no VLAN matched in this run).
Not verified: Address availability, MetalLB runtime allocation and the switch configuration itself are not verified.

| Field | Expected | Observed |
|---|---|---|
| `ingress.poolAddress` | `outside None; no matching workload VLAN` | `—` |

</details>

<details open>
<summary>BLOCKED: Workload DNS base domain — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: Reads dns.records[].hostname from hosted-clusters/example-env-infra/example-env-workload0/values.yaml. The check passes when every hostname ends with the hub baseDomain `an unknown baseDomain` or hcpExternalDomain `an unknown hcpExternalDomain` taken from hosted-clusters/example-env-infra/values.yaml. A workload that declares no dns.records passes without any comparison.
Not verified: Only the suffix is compared; the records are not looked up in moc-dns and missing records are not detected.

| Field | Expected | Observed |
|---|---|---|
| `dns.records` | `hostnames under none` | `—` |

</details>

<details open>
<summary>BLOCKED: Workload node-pool host capacity — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: For each nodePools entry in the workload values file, counts inventory hosts in infra/inventory/00hosts.yaml whose fields equal the agentLabelSelector string values (resource_class also consults the documented hardware table). The check passes when every pool has at least as many matching hosts as its replicas.
Not verified: Host readiness, scheduling and non-string selector operators are not evaluated.

</details>

<details open>
<summary>BLOCKED: Workload GPU feature support — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: Reads clusterLabels.massopen.cloud/feature-gpu from the workload values file. When it is true the check passes only if at least one inventory host has gpu: true or a resource_class, flavor or documented class containing gpu, a100 or h100.
Not verified: GPU model, count and allocatable resources are not inspected, and feature-gpu false is accepted without checking that the gate is absent.

| Field | Expected | Observed |
|---|---|---|
| `clusterLabels["massopen.cloud/feature-gpu"]` | `false or at least 1 GPU host` | `—` |
| `gpu_host_count` | `at least 1 when feature-gpu is true` | `—` |

</details>

<details>
<summary>OK: Workload address uniqueness — No workload address is used by another cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ main (3333333)

Verifies: Reads every hosted-clusters/<hub>/<cluster>/values.yaml in CCI-MOC/oac-apps and collects services.APIServer.ipAddress, ingress.poolAddress, services.APIServer.externalIpAddress and ingress.externalIpAddress for each cluster. The check passes when no address used by `example-env-workload0` is also used by a different cluster.
Not verified: Addresses are compared as strings, so equivalent CIDR and bare-IP spellings are not unified; duplicates inside one cluster are covered separately by workload.address_internal_duplicates.

</details>

<details open>
<summary>BLOCKED: Workload internal address duplicates — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/example-env-infra/example-env-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/example-env-infra/example-env-workload0/values.yaml) @ main (3333333)

Verifies: Reads services.APIServer.ipAddress, ingress.poolAddress, services.APIServer.externalIpAddress and ingress.externalIpAddress from hosted-clusters/example-env-infra/example-env-workload0/values.yaml in CCI-MOC/oac-apps. Each value is parsed with the ipaddress module and compared across the four fields of that workload; the check passes when no address is used by more than one field, and reports an advisory when one is. The one exception is a shared address between exactly services.APIServer.externalIpAddress and ingress.externalIpAddress, which is allowed; any group with three or four fields that includes that pair is still reported.
Not verified: The report does not prove whether sharing an address is intentional; it only flags the duplicate inside this workload, apart from the allowed API-server and ingress external address pair. Cross-cluster duplicates are covered by workload.address_uniqueness.

</details>

<details>
<summary>OK: Workload Pure storage realm — The example-env-workload0 Pure storage realm reports subnet_vlan, subnet_prefix and s3_endpoint.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

Verifies: Reads CCI-MOC/everpure-moc ansible/group_vars/all/realms.yaml and selects the realms entry whose name equals `example-env-workload0`. The check passes when subnet_vlan, subnet_prefix and s3_endpoint are all non-null.
Not verified: The three values are not validated against the workload VLAN or DNS, and no Pure array is contacted.

| Field | Expected | Observed |
|---|---|---|
| `name` | `example-env-workload0` | `example-env-workload0` |
| `subnet_vlan` | `present` | `2322` |
| `subnet_prefix` | `present` | `10.20.28.0/24` |
| `s3_endpoint` | `present` | `s3.example-env-workload0.hcp.example-env.int.massopen.cloud` |

</details>

<details>
<summary>OK: Workload moc-aws OIDC cluster — The moc-aws OIDC cluster entry for example-env-workload0 is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws main.tf and looks for a block whose cluster_name equals `example-env-workload0`. The check passes when such a block exists; its eso_writable_secret_prefixes are reported as context but nothing about them is required.
Not verified: The block's other attributes are not inspected, and the OIDC provider, IAM role and secret store are not exercised in AWS.

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `example-env-workload0` | `example-env-workload0` |
| `eso_writable_secret_prefixes` | `not constrained by this check` | `none listed` |

</details>

<details>
<summary>OK: Workload moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policy_example_env_workload0 names example-env-workload0 in policy_name or cluster_subdomain.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

Verifies: Parses HCL blocks in CCI-MOC/moc-aws cert-manager-policies.tf and matches a block whose cluster_subdomain or policy_name names `example-env-workload0` (policy_name is also tried with `-` replaced by `_`). The check passes when any block matches by name.
Not verified: The match is textual, so the certificate zone, DNS records and AWS permissions are not verified.

| Field | Expected | Observed |
|---|---|---|
| `policy entry` | `policy_name or cluster_subdomain names example-env-workload0` | `cert_manager_policy_example_env_workload0` |

</details>

Pull requests: skipped (--no-prs)

## Recent changes

These are GitHub commit histories on main.

| Repository | Path | History |
|---|---|---|
| oac-infra | `infra/inventory/00hosts.yaml` (shared by all clusters) | [History](https://github.com/CCI-MOC/oac-infra/commits/main/infra/inventory/00hosts.yaml) |
| oac-infra | `hub-images/inventory.yml` (shared by all clusters) | [History](https://github.com/CCI-MOC/oac-infra/commits/main/hub-images/inventory.yml) |
| moc-keycloak | `main.tf` (shared by all clusters) | [History](https://github.com/CCI-MOC/moc-keycloak/commits/main/main.tf) |

## Sources

| Repository | Ref | Commit |
|---|---|---|
| `ansible-switches` | `main` | [8888888](https://github.com/CCI-MOC/ansible-switches/commit/8888888888888888888888888888888888888888) |
| `everpure-moc` | `main` | [5555555](https://github.com/CCI-MOC/everpure-moc/commit/5555555555555555555555555555555555555555) |
| `moc-aws` | `main` | [6666666](https://github.com/CCI-MOC/moc-aws/commit/6666666666666666666666666666666666666666) |
| `moc-dns` | `main` | [7777777](https://github.com/CCI-MOC/moc-dns/commit/7777777777777777777777777777777777777777) |
| `moc-keycloak` | `main` | [4444444](https://github.com/CCI-MOC/moc-keycloak/commit/4444444444444444444444444444444444444444) |
| `oac-apps` | `main` | [3333333](https://github.com/CCI-MOC/oac-apps/commit/3333333333333333333333333333333333333333) |
| `oac-infra` | `main` | [2222222](https://github.com/CCI-MOC/oac-infra/commit/2222222222222222222222222222222222222222) |


## Legend

- FAIL: A blocking check failed.
- OK: `declared_in_main` — Desired configuration is present on merged main.
- BLOCKED: `blocked` — Cannot be checked until an earlier check passes.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
