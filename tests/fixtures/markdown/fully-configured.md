# bu-ist-demo — environment configuration status

**No deployment gaps in repository configuration.**

Generated 2026-11-16 12:34 UTC · MOC issue: [#666](https://github.com/CCI-MOC/MOC-issues/issues/666) (open)

## Phase summary

### Hub phases

| Phase | HUB bu-ist-demo-infra |
|---|---:|
| 1 Host inventory entry | ✅ 1/1 checks |
| 2 Hub image inventory and vars | ✅ 3/3 checks |
| 3 Discovery image reference | ✅ 1/1 checks |
| 4 Keycloak OIDC client | ✅ 1/1 checks |
| 5 GitOps values and apps | ✅ 8/8 checks |

### Workload phases

| Phase | WORKLOAD bu-ist-demo-workload0 |
|---|---:|
| 1 Host inventory entry | ✅ 1/1 checks |
| 2 Hub agent discovery ISO | ✅ 1/1 checks |
| 3 Agent ISO boot | verify by hand |
| 4 Agent visibility | verify by hand |
| 5 Agent labels and approval | ✅ 1/1 checks |
| 6 oac-apps values | ✅ 7/7 checks |
| 7 Shared-service prerequisites | ✅ 4/4 checks |

## Next actions

Nothing to do in the repositories this tool reads.

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
<summary>✅ bu-ist-demo-infra host inventory — The inventory contains a bu-ist-demo-infra group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

| Field | Observed |
|---|---|
| `cluster_group` | `bu-ist-demo-infra` |
| `host_count` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| `control-0` | `MOC-R4PAC10U31-S1A` | — | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ Hub image inventory — The hub-image inventory contains the all.children.bu-ist-demo-infra key.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ main (2222222)

| Field | Observed |
|---|---|
| `inventory_key` | `bu-ist-demo-infra` |

</details>

<details>
<summary>✅ Hub image variables — All required hub-image variables are present in main.</summary>

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/bu-ist-demo-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/bu-ist-demo-infra/vars.yml) @ main (2222222)

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
<summary>✅ Hub moc-dns records — All required hub DNS records in zonefiles/int.massopen.cloud.zone match the hub-image variables.</summary>

Source: CCI-MOC/moc-dns · [`zonefiles/int.massopen.cloud.zone`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/int.massopen.cloud.zone) @ main (7777777)

| Field | Observed |
|---|---|
| `api.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` |
| `api-int.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` |
| `*.apps.bu-ist-demo.int.massopen.cloud` | `10.20.27.12` |

</details>

<details>
<summary>✅ bu-ist-demo-infra boot image — The boot image URL is specific to bu-ist-demo-infra.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Status rule: The boot-image filename must contain the full cluster name `bu-ist-demo-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Observed |
|---|---|
| `boot_image_url` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ Hub OIDC client — All expected Keycloak OIDC client fields match.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

| Field | Observed |
|---|---|
| `client` | `bu-ist-demo-infra` |
| `redirect_uri` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` |
| `secret_name` | `cluster/bu-ist-demo-infra/keycloak-oidc` |

</details>

<details>
<summary>✅ Hub hosted-cluster defaults — All expected files for the default values for hosted clusters on this hub cluster are present in main.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) | `present` |

</details>

<details>
<summary>✅ Hub-wide component values — All expected files for hub-wide HCP and secret-selector values are present in main.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra) @ main (3333333)

| Field | Observed |
|---|---|
| [`values/bu-ist-demo-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/hcp-config.yaml) | `present` |

</details>

<details>
<summary>✅ Hub local-cluster values — All expected files for the hub cluster's local operator and shared-service values are present in main.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster) @ main (3333333)

| Field | Observed |
|---|---|
| [`values/bu-ist-demo-infra/local-cluster/acm.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/acm.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/acm-placements.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/acm-placements.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cert-manager.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cert-manager.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cluster-certificates.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/cluster-version.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/cluster-version.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/external-dns-operator.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/external-secrets.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/external-secrets.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/hcp-config.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/metallb.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/metallb.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/openshift-gitops.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/portworx.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/portworx.yaml) | `present` |
| [`values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster/user-workload-monitoring.yaml) | `present` |

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
<summary>✅ Hub ArgoCD applications — All expected files for direct ArgoCD applications applied on the hub cluster are present in main.</summary>

Source: CCI-MOC/oac-apps · [`apps/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra) @ main (3333333)

| Field | Observed |
|---|---|
| [`apps/bu-ist-demo-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra/keycloak-oauth.yaml) | `present` |

</details>

<details>
<summary>✅ Hub Pure storage realm — The bu-ist-demo-infra Pure storage realm is complete.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

| Field | Observed |
|---|---|
| `name` | `bu-ist-demo-infra` |
| `subnet_vlan` | `2321` |
| `subnet_prefix` | `10.9.15.0/24` |
| `s3_endpoint` | `s3.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>✅ Hub moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-infra is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

| Field | Observed |
|---|---|
| `cluster_name` | `bu-ist-demo-infra` |
| `eso_writable_secret_prefixes` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>✅ Hub moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policies covers bu-ist-demo-infra.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

| Field | Observed |
|---|---|
| `policy entry` | `cert_manager_policies` |

</details>

<details>
<summary>✅ Hub hosted-cluster secret prefix — The hub can write hosted-cluster secrets at cluster/bu-ist-demo-infra/hostedcluster/.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

| Field | Observed |
|---|---|
| `eso_writable_secret_prefixes` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>✅ bu-ist-demo-workload0 host inventory — The inventory contains a bu-ist-demo-workload0 group with 1 hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

| Field | Observed |
|---|---|
| `cluster_group` | `bu-ist-demo-workload0` |
| `host_count` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| `compute-0` | `MOC-R4PAC10U31-S1B` | — | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ bu-ist-demo-workload0 boot image — The boot image URL identifies the workload or its parent hub bu-ist-demo-infra.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

Status rule: The workload boot-image filename may contain the workload name `bu-ist-demo-workload0`, its oac-shortened name, the parent hub name `bu-ist-demo-infra`, or the hub's oac-shortened name. Unrecognized names are advisory because naming is not consistent across environments; generic `discovery.iso` remains a gap.

| Field | Observed |
|---|---|
| `boot_image_url` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ bu-ist-demo-workload0 update-agents inputs — Every non-openstack host has the mac_addr and resource_class inputs required by infra/update-agents.yaml.</summary>

Source: CCI-MOC/oac-infra · [`infra/update-agents.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/update-agents.yaml) @ main (2222222)

| Field | Observed |
|---|---|
| `compute-0.mac_addr` | `00:11:22:33:44:55` |
| `compute-0.resource_class` | `bu-ist-demo-worker` |

**Agent label inputs**

| Host | bm_management | mac_addr | resource_class |
|---|---|---|---|
| `compute-0` | `ipmi` | `00:11:22:33:44:55` | `bu-ist-demo-worker` |

</details>

<details>
<summary>✅ Workload hosted-cluster values — All expected files for the hosted workload cluster definition are present in main.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) | `present` |

</details>

<details>
<summary>✅ Workload component values — All expected files for component values scoped to the workload cluster are present in main.</summary>

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/bu-ist-demo-workload0) @ main (3333333)

| Field | Observed |
|---|---|
| `matched_file_count` | `1` |

</details>

<details>
<summary>✅ Workload API address network — The API address is inside the hub machine network.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| `services.APIServer.ipAddress` | `10.20.26.10` |

</details>

<details>
<summary>✅ Workload ingress address network — The ingress pool address is on the expected network. Selected VLAN BU-IST-DEMO-WORKLOAD0 (10.20.28.0/24).</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| `ingress.poolAddress` | `10.20.28.10` |

</details>

<details>
<summary>✅ Workload DNS base domain — All DNS record hostnames use the hub hosted-cluster domains.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| `dns.records[0].hostname` | `api.bu-ist-demo-workload0.int.massopen.cloud` |

</details>

<details>
<summary>✅ Workload node-pool host capacity — Every node pool has enough matching inventory hosts.</summary>

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ main (2222222)

| Field | Observed |
|---|---|
| `nodePools.compute.matching_hosts` | `1` |

</details>

<details>
<summary>✅ Workload GPU feature support — GPU configuration is consistent with the inventory.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ main (3333333)

| Field | Observed |
|---|---|
| `clusterLabels["massopen.cloud/feature-gpu"]` | `false` |
| `gpu_host_count` | `0` |

</details>

<details>
<summary>✅ Workload address uniqueness — No workload address is used by another cluster.</summary>

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ main (3333333)

| Field | Observed |
|---|---|
| `10.20.26.10` | `bu-ist-demo-workload0: services.APIServer.ipAddress` |
| `10.20.28.10` | `bu-ist-demo-workload0: ingress.poolAddress` |
| `10.20.29.10` | `bu-ist-demo-workload0: services.APIServer.externalIpAddress; bu-ist-demo-workload0: ingress.externalIpAddress` |

</details>

<details>
<summary>✅ Workload Pure storage realm — The bu-ist-demo-workload0 Pure storage realm is complete.</summary>

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ main (5555555)

| Field | Observed |
|---|---|
| `name` | `bu-ist-demo-workload0` |
| `subnet_vlan` | `2322` |
| `subnet_prefix` | `10.20.28.0/24` |
| `s3_endpoint` | `s3.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud` |

</details>

<details>
<summary>✅ Workload moc-aws OIDC cluster — The moc-aws OIDC cluster entry for bu-ist-demo-workload0 is present.</summary>

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ main (6666666)

| Field | Observed |
|---|---|
| `cluster_name` | `bu-ist-demo-workload0` |
| `eso_writable_secret_prefixes` | `—` |

</details>

<details>
<summary>✅ Workload moc-aws cert-manager policy — The cert-manager policy entry cert_manager_policy_bu_ist_demo_workload0 covers bu-ist-demo-workload0.</summary>

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ main (6666666)

| Field | Observed |
|---|---|
| `policy entry` | `cert_manager_policy_bu_ist_demo_workload0` |

</details>

<details>
<summary>✅ Workload Keycloak OIDC client — The Keycloak OIDC client for bu-ist-demo-workload0 matches.</summary>

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ main (4444444)

| Field | Observed |
|---|---|
| `cluster_name` | `bu-ist-demo-workload0` |
| `openshift_redirect_uri` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` |
| `client_secret_name` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` |

</details>

<details>
<summary>📝 MOC issue — Issue #666 is open and records the environment request.</summary>

Source: CCI-MOC/MOC-issues · [`issues/666`](https://github.com/CCI-MOC/MOC-issues/issues/666) @ main (1111111)

| Field | Observed |
|---|---|
| `issue_state` | `open` |

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

- 📝 `requested` — The MOC issue records the request.
- ✅ `declared_in_main` — Desired configuration is present on merged main.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
