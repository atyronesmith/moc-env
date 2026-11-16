# bu-ist-demo — environment configuration status

**0 blocking gaps, 0 advisories, and 30 of 30 checks pass**

Generated 2026-11-16 12:34:56 UTC · Sources: [CCI-MOC/MOC-issues@1111111](https://github.com/CCI-MOC/MOC-issues/commit/1111111111111111111111111111111111111111) · [CCI-MOC/ansible-switches@8888888](https://github.com/CCI-MOC/ansible-switches/commit/8888888888888888888888888888888888888888) · [CCI-MOC/everpure-moc@5555555](https://github.com/CCI-MOC/everpure-moc/commit/5555555555555555555555555555555555555555) · [CCI-MOC/moc-aws@6666666](https://github.com/CCI-MOC/moc-aws/commit/6666666666666666666666666666666666666666) · [CCI-MOC/moc-dns@7777777](https://github.com/CCI-MOC/moc-dns/commit/7777777777777777777777777777777777777777) · [CCI-MOC/moc-keycloak@4444444](https://github.com/CCI-MOC/moc-keycloak/commit/4444444444444444444444444444444444444444) · [CCI-MOC/oac-apps@3333333](https://github.com/CCI-MOC/oac-apps/commit/3333333333333333333333333333333333333333) · [CCI-MOC/oac-infra@2222222](https://github.com/CCI-MOC/oac-infra/commit/2222222222222222222222222222222222222222) · MOC issue: [#666](https://github.com/CCI-MOC/MOC-issues/issues/666) (open)

## Phase summary

| Phase | HUB bu-ist-demo-infra | WORKLOAD bu-ist-demo-workload0 |
|---|---:|---:|
| 1 Host inventory entry in oac-infra | ✅ 1 hosts | ✅ 1 hosts |
| 2 Hub-image inventory entry and group variables / Obtain the agent discovery ISO from the hub's InfraEnv and publish it on the bastion | ✅ 6/6 variables | ✅ 1/1 checks |
| 3 Cluster discovery image published and referenced by the inventory / Boot nodes with the agent discovery ISO | ✅ 1/1 checks | – |
| 4 Keycloak OIDC client / Agents appear in the hub's hardware-inventory namespace | ✅ 1/1 checks | – |
| 5 GitOps values and applications in oac-apps / Label and approve agents with update-agents.yaml | ✅ 1/1 variables | ✅ 1/2 variables |
| 6 oac-apps values | – | ✅ 1/1 variables |
| 7 Shared-service prerequisites | – | ✅ 4/4 checks |

## Next actions

Nothing to do in the repositories this tool reads.

## Not checked — verify by hand

- [ ] **Configure cluster and storage networks and firewalls for bu-ist-demo-infra** (phase 1) — The four repositories read by this tool do not describe the switch, network, or firewall state required for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](docs/infra-cluster-deployment.md).
- [ ] **Store the bu-ist-demo-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/bu-ist-demo-infra/sshkey or cluster/bu-ist-demo-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Place the pull secret and SSH key under hub-images/credentials/bu-ist-demo-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for bu-ist-demo-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Run create_agent_install_media and copy the bu-ist-demo-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the four repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Bootstrap Argo CD for bu-ist-demo-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md).
- [ ] **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](docs/workload-cluster-deployment.md).
- [ ] **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](docs/workload-cluster-deployment.md).
- [ ] **Additional workload prerequisites are not yet documented upstream** (phase 7) — The upstream workload deployment guide lists observability (TBD) and ?? as open prerequisite items. Documented at [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](docs/workload-cluster-deployment.md).

## Details

<details>
<summary>✅ declared_in_main · info — bu-ist-demo-infra host inventory</summary>

Finding: The inventory contains a bu-ist-demo-infra group with 1 hosts.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `found` | `—` | `Yes` |
| `host_count` | `—` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| [`control-0`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [`MOC-R4PAC10U31-S1A`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [—](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub image inventory</summary>

Finding: The hub-image inventory contains the all.children.bu-ist-demo-infra key.

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `found` | `—` | `Yes` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub image variables</summary>

Finding: All required hub-image variables are present in main.

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/bu-ist-demo-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/bu-ist-demo-infra/vars.yml) @ 2222222

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
<summary>✅ declared_in_main · info — Hub moc-dns records</summary>

Finding: All required hub DNS records match the hub-image variables.

Source: CCI-MOC/moc-dns · [`zonefiles/int.massopen.cloud.zone`](https://github.com/CCI-MOC/moc-dns/blob/main/zonefiles/int.massopen.cloud.zone) @ 7777777

| Field | Expected | Observed |
|---|---|---|
| `api.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `api-int.bu-ist-demo.int.massopen.cloud` | `10.20.27.11` | `10.20.27.11` |
| `*.apps.bu-ist-demo.int.massopen.cloud` | `10.20.27.12` | `10.20.27.12` |

</details>

<details>
<summary>✅ declared_in_main · info — bu-ist-demo-infra boot image</summary>

Finding: The boot image URL is specific to bu-ist-demo-infra.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

Status rule: The boot-image filename must contain the full cluster name `bu-ist-demo-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `value` | `Cluster-specific discovery image for bu-ist-demo-infra` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main · info — Infra OIDC client</summary>

Finding: All expected Keycloak OIDC client fields match.

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ 4444444

| Field | Expected | Observed |
|---|---|---|
| `client` | `bu-ist-demo-infra` | `bu-ist-demo-infra` |
| `redirect_uri` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` | `https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso` |
| `secret_name` | `cluster/bu-ist-demo-infra/keycloak-oidc` | `cluster/bu-ist-demo-infra/keycloak-oidc` |

</details>

<details>
<summary>✅ declared_in_main · info — Infra hosted-cluster defaults</summary>

Finding: All expected files for the default values for hosted clusters on this hub cluster are present in main.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/values.yaml) | `present` | `present` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub-wide component values</summary>

Finding: All expected files for hub-wide HCP and secret-selector values are present in main.

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`values/bu-ist-demo-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/hcp-config.yaml) | `present` | `present` |

</details>

<details>
<summary>✅ declared_in_main · info — Infra local-cluster values</summary>

Finding: All expected files for the hub cluster's local operator and shared-service values are present in main.

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/local-cluster) @ 3333333

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

</details>

<details>
<summary>✅ declared_in_main · info — Infra ArgoCD applications</summary>

Finding: All expected files for direct ArgoCD applications applied on the hub cluster are present in main.

Source: CCI-MOC/oac-apps · [`apps/bu-ist-demo-infra`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`apps/bu-ist-demo-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/apps/bu-ist-demo-infra/keycloak-oauth.yaml) | `present` | `present` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub Pure storage realm</summary>

Finding: The bu-ist-demo-infra Pure storage realm is complete.

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ 5555555

| Field | Expected | Observed |
|---|---|---|
| `name` | `bu-ist-demo-infra` | `—` |
| `fields` | `subnet_vlan, subnet_prefix, s3_endpoint` | `—` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub moc-aws OIDC cluster</summary>

Finding: The moc-aws OIDC cluster entry for bu-ist-demo-infra is present.

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-infra` | local.defaults,<br>cluster_name bu-ist-demo-infra<br>eso_writable_secret_prefixes cluster/bu-ist-demo-infra/hostedcluster/ |

</details>

<details>
<summary>✅ declared_in_main · info — Hub moc-aws cert-manager policy</summary>

Finding: The cert-manager policy entry cert_manager_policies covers bu-ist-demo-infra.

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster` | `bu-ist-demo-infra` | `cert_manager_policies` |

</details>

<details>
<summary>✅ declared_in_main · info — Hub hosted-cluster secret prefix</summary>

Finding: The hub can write hosted-cluster secrets at cluster/bu-ist-demo-infra/hostedcluster/.

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `item 0` | `cluster/bu-ist-demo-infra/hostedcluster/` | `cluster/bu-ist-demo-infra/hostedcluster/` |

</details>

<details>
<summary>✅ declared_in_main · info — bu-ist-demo-workload0 host inventory</summary>

Finding: The inventory contains a bu-ist-demo-workload0 group with 1 hosts.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `found` | `—` | `Yes` |
| `host_count` | `—` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| [`compute-0`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [`MOC-R4PAC10U31-S1B`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [—](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main · info — bu-ist-demo-workload0 boot image</summary>

Finding: The boot image URL identifies the workload or its parent hub bu-ist-demo-infra.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

Status rule: The workload boot-image filename may contain the workload name `bu-ist-demo-workload0`, its oac-shortened name, the parent hub name `bu-ist-demo-infra`, or the hub's oac-shortened name. Unrecognized names are advisory because naming is not consistent across environments; generic `discovery.iso` remains a gap.

| Field | Expected | Observed |
|---|---|---|
| `value` | `Cluster-specific discovery image for bu-ist-demo-workload0` | `http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso` |

</details>

<details>
<summary>✅ declared_in_main · info — bu-ist-demo-workload0 update-agents inputs</summary>

Finding: Every non-openstack host has the mac_addr and resource_class inputs required by infra/update-agents.yaml.

Source: CCI-MOC/oac-infra · [`infra/update-agents.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/update-agents.yaml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `host` | `mac_addr` | `compute-0` |
| `node_name` | `mac_addr` | `MOC-R4PAC10U31-S1B` |
| `bm_management` | `mac_addr` | `ipmi` |
| `mac_addr` | `mac_addr` | `00:11:22:33:44:55` |
| `resource_class` | `mac_addr` | `bu-ist-demo-worker` |
| `documented_resource_class` | `mac_addr` | `bu-ist-demo-worker` |
| `item 1` | `resource_class` | `—` |

**Agent label inputs**

| Host | bm_management | mac_addr | resource_class |
|---|---|---|---|
| `compute-0` | `ipmi` | `00:11:22:33:44:55` | `bu-ist-demo-worker` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload hosted-cluster values</summary>

Finding: All expected files for the hosted workload cluster definition are present in main.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) | `present` | `present` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload component values</summary>

Finding: All expected files for component values scoped to the workload cluster are present in main.

Source: CCI-MOC/oac-apps · [`values/bu-ist-demo-infra/bu-ist-demo-workload0`](https://github.com/CCI-MOC/oac-apps/blob/main/values/bu-ist-demo-infra/bu-ist-demo-workload0) @ 3333333

</details>

<details>
<summary>✅ declared_in_main · info — Workload API address network</summary>

Finding: The API address is inside the hub machine network.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| `ipAddress` | `10.20.26.10` | `10.20.26.10` |
| `machine_network` | `10.20.26.0/23` | `10.20.26.10` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload ingress address network</summary>

Finding: The ingress pool address is on the expected network.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| `poolAddress` | `10.20.28.10` | `10.20.28.10` |
| `machine_network` | `10.20.26.0/23` | `10.20.28.10` |
| `vlan_subnet` | `10.20.28.0/24` | `10.20.28.10` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload DNS base domain</summary>

Finding: All DNS record hostnames use the hub base domain.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| `baseDomain` | `int.massopen.cloud` | `api.bu-ist-demo-workload0.int.massopen.cloud` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload node-pool host capacity</summary>

Finding: Every node pool has enough matching inventory hosts.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `name` | `compute` | `compute` |
| `replicas` | `1` | `1` |
| `cluster` | `bu-ist-demo-workload0` | `—` |
| `resource_class` | `bu-ist-demo-worker` | `—` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload GPU feature support</summary>

Finding: GPU configuration is consistent with the inventory.

Source: CCI-MOC/oac-apps · [`hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| `feature-gpu` | `false` | `—` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload address uniqueness</summary>

Finding: No workload address is used by another cluster.

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| `10.20.26.10` | `—` | `bu-ist-demo-workload0, services.APIServer.ipAddress` |
| `10.20.28.10` | `—` | `bu-ist-demo-workload0, ingress.poolAddress` |
| `10.20.29.10` | `—` | `bu-ist-demo-workload0, services.APIServer.externalIpAddress, bu-ist-demo-workload0, ingress.externalIpAddress` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload Pure storage realm</summary>

Finding: The bu-ist-demo-workload0 Pure storage realm is complete.

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/blob/main/ansible/group_vars/all/realms.yaml) @ 5555555

| Field | Expected | Observed |
|---|---|---|
| `name` | `bu-ist-demo-workload0` | `—` |
| `fields` | `subnet_vlan, subnet_prefix, s3_endpoint` | `—` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload moc-aws OIDC cluster</summary>

Finding: The moc-aws OIDC cluster entry for bu-ist-demo-workload0 is present.

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-workload0` | local.defaults,<br>cluster_name bu-ist-demo-workload0 |

</details>

<details>
<summary>✅ declared_in_main · info — Workload moc-aws cert-manager policy</summary>

Finding: The cert-manager policy entry cert_manager_policy_bu_ist_demo_workload0 covers bu-ist-demo-workload0.

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster` | `bu-ist-demo-workload0` | `cert_manager_policy_bu_ist_demo_workload0` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload Keycloak OIDC client</summary>

Finding: The Keycloak OIDC client for bu-ist-demo-workload0 matches.

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ 4444444

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `bu-ist-demo-workload0` | `bu-ist-demo-workload0` |
| `openshift_redirect_uri` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` | `https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso` |
| `client_secret_name` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` | `cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc` |

</details>

<details>
<summary>📝 requested · info — MOC issue</summary>

Finding: Issue #666 is open and records the environment request.

Source: CCI-MOC/MOC-issues · [`issues/666`](https://github.com/CCI-MOC/MOC-issues/issues/666) @ 1111111

| Field | Expected | Observed |
|---|---|---|
| `value` | `Open issue recording the environment request` | `open` |

</details>

## Pull requests

None.

## Legend

- 📝 `requested` — The MOC issue records the request.
- ✅ `declared_in_main` — Desired configuration is present on merged main.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
