# bu-ist-demo — environment configuration status

**8 blocking gaps, 0 advisories, and 16 of 29 checks pass; 5 checks blocked until Create the missing hosted-cluster values file from the closest existing environment; set the cluster name, parent hub, networking, and node pools before adding components.**

Generated 2026-11-16 12:34 UTC · MOC issue: [#666](https://github.com/CCI-MOC/MOC-issues/issues/666) (open) · Pull requests skipped because this run is unauthenticated; use --prs

## Phase summary

### Hub phases

| Phase | HUB bu-ist-demo-infra |
|---|---:|
| 1 Host inventory entry | ✅ 1/1 checks |
| 2 Hub image inventory and vars | ✅ 3/3 checks |
| 3 Discovery image reference | 🟡 0/1 checks |
| 4 Keycloak OIDC client | ✅ 1/1 checks |
| 5 GitOps values and apps | ❌ 4/8 checks |

### Workload phases

| Phase | WORKLOAD bu-ist-demo-workload0 |
|---|---:|
| 1 Host inventory entry | ✅ 1/1 checks |
| 2 Hub agent discovery ISO | 🟡 0/1 checks |
| 3 Agent ISO boot | – |
| 4 Agent visibility | – |
| 5 Agent labels and approval | ✅ 1/1 checks |
| 6 oac-apps values | ❌ 0/7 checks, 5 blocked |
| 7 Shared-service prerequisites | ✅ 3/3 checks |

## Next actions

1. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml): Generate and publish a hub-specific discovery ISO, then replace the generic boot_image_url for every host in the hub cluster group.
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment)
2. **oac-apps** — [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete the hub hosted-cluster defaults file at hosted-clusters/bu-ist-demo-infra/values.yaml in CCI-MOC/oac-infra. (after 1)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
3. **oac-apps** — [`values/bu-ist-demo-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main): Copy the required local-cluster component files from an existing hub environment and adjust cluster-specific names and addresses. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
4. **oac-apps** — [`values/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete values/bu-ist-demo-infra/hcp-config.yaml in CCI-MOC/oac-infra for hub-wide HCP and secret-selector values. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
5. **oac-apps** — [`apps/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Add Argo CD application manifests for the hub after its hosted-cluster, hub-wide component, and local-cluster values are present, and reference the correct clusters. (after 2, 4, 3)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration)
6. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml): Generate and publish the parent hub's agent discovery ISO, then replace the generic boot_image_url for every host in the workload cluster group. (after 1)
   Guide: [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration)
7. **oac-apps** — [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): Create the missing hosted-cluster values file from the closest existing environment; set the cluster name, parent hub, networking, and node pools before adding components. (after 2)
   Guide: [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#cluster-deployment-and-configuration)
8. **oac-apps** — [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/tree/main): Create the workload component-values directory, starting with hcp-config.yaml and only the shared components this workload needs. (after 7)
   Guide: [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#cluster-deployment-and-configuration)

## Not checked — verify by hand

- [ ] **Configure cluster and storage networks and firewalls for bu-ist-demo-infra** (phase 1) — The repositories read by this tool do not describe the switch, network, or firewall state required for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#infrastructure-configuration).
- [ ] **Store the bu-ist-demo-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/bu-ist-demo-infra/sshkey or cluster/bu-ist-demo-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Place the pull secret and SSH key under hub-images/credentials/bu-ist-demo-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Run create_agent_install_media and copy the bu-ist-demo-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-deployment).
- [ ] **Bootstrap Argo CD for bu-ist-demo-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/infra-cluster-deployment.md#cluster-configuration).
- [ ] **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).
- [ ] **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](https://github.com/CCI-MOC/oac-apps/blob/main/docs/workload-cluster-deployment.md#infrastructure-configuration).

## Details

<details>
<summary>✅ declared_in_main bu-ist-demo-infra host inventory — The inventory contains a bu-ist-demo-infra group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Observed |
|---|---|
| `cluster_group` | `bu-ist-demo-infra` |
| `host_count` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| `control-0` | `MOC-R4PAC10U31-S1A` | — | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main Hub image inventory — The hub-image inventory contains the all.children.bu-ist-demo-infra key.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ 2222222

| Field | Observed |
|---|---|
| `inventory_key` | `bu-ist-demo-infra` |

</details>

<details>
<summary>✅ declared_in_main Hub image variables — All required hub-image variables are present in main.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/bu-ist-demo-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/bu-ist-demo-infra/vars.yml) @ 2222222

| Field | Observed |
|---|---|
| `cluster_domain_name` | `bu-ist-demo` |
| `base_domain` | `int.massopen.cloud` |
| `machine_network` | `10.20.26.0/23` |
| `api_ip` | `10.20.27.11` |
| `ingress_ip` | `10.20.27.12` |
| `dns_ip` | `8.8.8.8` |

</details>

<details>
<summary>✅ declared_in_main Hub moc-dns records — All required hub DNS records in zonefiles/int.massopen.cloud.zone match the hub-image variables.</summary>

Source: CCI-MOC/moc-dns · [`zonefiles/int.massopen.cloud.zone`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/int.massopen.cloud.zone) @ 7777777

| Field | Observed |
|---|---|
| `api.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` |
| `api-int.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` |
| `*.apps.bu-ist-demo.int.massopen.cloud` | `10.20.27.12` |

</details>

<details open>
<summary>🟡 partial bu-ist-demo-infra boot image — A boot image URL is present, but it points to the generic discovery.iso rather than a cluster-specific image.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

Status rule: The boot-image filename must contain the full cluster name `bu-ist-demo-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `value` | `Cluster-specific discovery image for bu-ist-demo-infra` | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main Hub OIDC client — All expected Keycloak OIDC client fields match.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ 4444444

| Field | Observed |
|---|---|
| `client` | `bu-ist-demo-infra` |
| `redirect_uri` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` |
| `secret_name` | `cluster/bu-ist-demo-infra/keycloak-oidc` |

</details>

<details open>
<summary>❌ missing Hub hosted-cluster defaults — No merged main paths were found for the default values for hosted clusters on this hub cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing Hub-wide component values — No merged main paths were found for hub-wide HCP and secret-selector values.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`values/bu-ist-demo-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing Hub local-cluster values — No merged main paths were found for the hub cluster's local operator and shared-service values.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`values/bu-ist-demo-infra/local-cluster/acm.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/cert-manager.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-version.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/external-secrets.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/metallb.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/portworx.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |
| [`values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

**Required files**

| Path | Status |
|---|---|
| `values/bu-ist-demo-infra/local-cluster/acm-placements.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/acm.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/cert-manager.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/cluster-version.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/external-secrets.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/hcp-config.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/metallb.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/portworx.yaml` | `missing` |
| `values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml` | `missing` |

**Additional files present**

None.

</details>

<details open>
<summary>❌ missing Hub ArgoCD applications — No merged main paths were found for direct ArgoCD applications applied on the hub cluster.</summary>

Source: CCI-MOC/oac-apps · [`apps/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`apps/bu-ist-demo-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details>
<summary>✅ declared_in_main Hub Pure storage realm — The bu-ist-demo-infra Pure storage realm is complete.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ 5555555

| Field | Observed |
|---|---|
| `subnet_vlan` | `2321` |
| `subnet_prefix` | `10.9.15.0/24` |
| `s3_endpoint` | `s3.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>✅ declared_in_main Hub moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-infra is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Observed |
|---|---|
| `cluster_name` | `bu-ist-demo-infra` |
| `eso_writable_secret_prefixes` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>✅ declared_in_main Hub moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policies covers bu-ist-demo-infra.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ 6666666

| Field | Observed |
|---|---|
| `cluster` | `cert_manager_policies` |

</details>

<details>
<summary>✅ declared_in_main Hub hosted-cluster secret prefix — The hub can write hosted-cluster secrets at cluster/bu-ist-demo-infra/hostedcluster/.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Observed |
|---|---|
| `eso_writable_secret_prefix` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>✅ declared_in_main bu-ist-demo-workload0 host inventory — The inventory contains a bu-ist-demo-workload0 group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Observed |
|---|---|
| `cluster_group` | `bu-ist-demo-workload0` |
| `host_count` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| `compute-0` | `MOC-R4PAC10U31-S1B` | — | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details open>
<summary>🟡 partial bu-ist-demo-workload0 boot image — A boot image URL is present, but the workload is still on the generic discovery.iso rather than the expected `bu-ist-demo-infra-agent-discovery.iso`.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

Status rule: The workload boot-image filename may contain the workload name `bu-ist-demo-workload0`, its oac-shortened name, the parent hub name `bu-ist-demo-infra`, or the hub's oac-shortened name. Unrecognized names are advisory because naming is not consistent across environments; generic `discovery.iso` remains a gap.

| Field | Expected | Observed |
|---|---|---|
| `value` | `Cluster-specific discovery image for bu-ist-demo-workload0` | `http://10.2.0.82/boot/discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main bu-ist-demo-workload0 update-agents inputs — Every non-openstack host has the mac_addr and resource_class inputs required by infra/update-agents.yaml.</summary>

Source: CCI-MOC/oac-infra · [`infra/update-agents.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/update-agents.yaml) @ 2222222

| Field | Observed |
|---|---|
| `host` | `compute-0` |
| `node_name` | `MOC-R4PAC10U31-S1B` |
| `bm_management` | `ipmi` |
| `mac_addr` | `00:11:22:33:44:55` |
| `resource_class` | `bu-ist-demo-worker` |
| `documented_resource_class` | `bu-ist-demo-worker` |
| `item 1` | `—` |

**Agent label inputs**

| Host | bm_management | mac_addr | resource_class |
|---|---|---|---|
| `compute-0` | `ipmi` | `00:11:22:33:44:55` | `bu-ist-demo-worker` |

</details>

<details open>
<summary>❌ missing Workload hosted-cluster values — No merged main paths were found for the hosted workload cluster definition.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing Workload component values — No merged main paths were found for component values scoped to the workload cluster.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

</details>

<details open>
<summary>• blocked Workload API address network — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

</details>

<details open>
<summary>• blocked Workload ingress address network — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

</details>

<details open>
<summary>• blocked Workload DNS base domain — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

</details>

<details open>
<summary>• blocked Workload node-pool host capacity — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

</details>

<details open>
<summary>• blocked Workload GPU feature support — Blocked until Workload hosted-cluster values is complete.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

</details>

<details>
<summary>✅ declared_in_main Workload address uniqueness — No workload address is used by another cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ 3333333

</details>

<details>
<summary>✅ declared_in_main Workload Pure storage realm — The bu-ist-demo-workload0 Pure storage realm is complete.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ 5555555

| Field | Observed |
|---|---|
| `subnet_vlan` | `2322` |
| `subnet_prefix` | `10.20.28.0/24` |
| `s3_endpoint` | `s3.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>✅ declared_in_main Workload moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-workload0 is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Observed |
|---|---|
| `cluster_name` | `bu-ist-demo-workload0` |
| `eso_writable_secret_prefixes` | `—` |

</details>

<details>
<summary>✅ declared_in_main Workload moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policy_bu_ist_demo_workload0 covers bu-ist-demo-workload0.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ 6666666

| Field | Observed |
|---|---|
| `cluster` | `cert_manager_policy_bu_ist_demo_workload0` |

</details>

<details>
<summary>📝 requested MOC issue — Issue #666 is open and records the environment request.</summary>

Source: CCI-MOC/MOC-issues · [`issues/666`](https://github.com/CCI-MOC/MOC-issues/issues/666) @ 1111111

| Field | Observed |
|---|---|
| `value` | `open` |

</details>

## Pull requests

**0 open PRs touch this environment.**

None.

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

- 📝 `requested` — The MOC issue records the request.
- ✅ `declared_in_main` — Desired configuration is present on merged main.
- 🟡 `partial` — Some required configuration is present.
- ❌ `missing` — Required configuration was not found.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
