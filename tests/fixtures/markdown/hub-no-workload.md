# dizzy — environment configuration status

**10 blocking gaps, 0 advisories, and 3 of 14 checks pass; unknown: Hub moc-dns records: Hub-image variables required for DNS validation are unavailable.**

Generated 2026-11-16 12:34:56 UTC · Sources: [CCI-MOC/ansible-switches@8888888](https://github.com/CCI-MOC/ansible-switches/commit/8888888888888888888888888888888888888888) · [CCI-MOC/everpure-moc@5555555](https://github.com/CCI-MOC/everpure-moc/commit/5555555555555555555555555555555555555555) · [CCI-MOC/moc-aws@6666666](https://github.com/CCI-MOC/moc-aws/commit/6666666666666666666666666666666666666666) · [CCI-MOC/moc-keycloak@4444444](https://github.com/CCI-MOC/moc-keycloak/commit/4444444444444444444444444444444444444444) · [CCI-MOC/oac-apps@3333333](https://github.com/CCI-MOC/oac-apps/commit/3333333333333333333333333333333333333333) · [CCI-MOC/oac-infra@2222222](https://github.com/CCI-MOC/oac-infra/commit/2222222222222222222222222222222222222222) · MOC issue: not set — pass `--issue N`

## Phase summary

| Phase | HUB dizzy-infra |
|---|---:|
| 1 Host inventory entry in oac-infra | ✅ 1 hosts |
| 2 Hub-image inventory entry and group variables / Obtain the agent discovery ISO from the hub's InfraEnv and publish it on the bastion | ⚪ unknown |
| 3 Cluster discovery image published and referenced by the inventory / Boot nodes with the agent discovery ISO | ❌ none |
| 4 Keycloak OIDC client / Agents appear in the hub's hardware-inventory namespace | ❌ none |
| 5 GitOps values and applications in oac-apps / Label and approve agents with update-agents.yaml | ❌ none |
| 6 oac-apps values | – |
| 7 Shared-service prerequisites | – |

## Next actions

1. **oac-infra** — [`hub-images/group_vars/dizzy-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/tree/main): Edit CCI-MOC/oac-infra at hub-images/group_vars/&lt;hub&gt;/vars.yml and provide cluster_domain_name, base_domain, machine_network, api_ip, ingress_ip, and dns_ip.
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md)
2. **oac-infra** — [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/tree/main): Generate and publish a hub-specific discovery ISO, then replace the generic boot_image_url for every host in the hub cluster group. (after 1)
   Guide: [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md)
3. **moc-keycloak** — [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf): Edit CCI-MOC/moc-keycloak at main.tf and add the hub's OIDC client, redirect URI, and secret reference. Set cluster_name = `dizzy-infra`, openshift_redirect_uri = `https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso`, and client_secret_name = `cluster/dizzy-infra/keycloak-oidc`. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
4. **oac-apps** — [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete the hub hosted-cluster defaults file at hosted-clusters/&lt;hub&gt;/values.yaml in CCI-MOC/oac-infra. (after 2)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
5. **oac-apps** — [`values/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Create or complete values/&lt;hub&gt;/hcp-config.yaml in CCI-MOC/oac-infra for hub-wide HCP and secret-selector values. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
6. **oac-apps** — [`values/dizzy-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main): Copy the required local-cluster component files from an existing hub environment and adjust cluster-specific names and addresses. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
7. **oac-apps** — [`apps/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main): Add Argo CD application manifests for the hub after its hosted-cluster, hub-wide component, and local-cluster values are present, and reference the correct clusters. (after 4, 5, 6, 3)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
8. **everpure-moc** — [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/tree/main): Add or correct the hub realm in everpure-moc realms.yaml. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
9. **moc-aws** — [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf): Add or correct the hub entry in moc-aws local.openshift_oidc_clusters. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)
10. **moc-aws** — [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf): Add a cert-manager policy entry for the hub. (after 4)
   Guide: [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md)

## Not checked — verify by hand

- [ ] **Configure cluster and storage networks and firewalls for dizzy-infra** (phase 1) — The four repositories read by this tool do not describe the switch, network, or firewall state required for dizzy-infra. Documented at [docs/infra-cluster-deployment.md → Infrastructure Configuration](docs/infra-cluster-deployment.md).
- [ ] **Store the dizzy-infra SSH key and kubeadmin credentials in AWS Secrets Manager** (phase 2) — Secrets Manager is outside the public repositories read by this tool, so it cannot verify cluster/dizzy-infra/sshkey or cluster/dizzy-infra/kubeadmin. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Place the pull secret and SSH key under hub-images/credentials/dizzy-infra** (phase 2) — The documented credential directory is intentionally not committed, so repository state cannot prove that its files exist for dizzy-infra. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Run create_agent_install_media and copy the dizzy-infra ISO to the bastion host** (phase 3) — Running the playbook and copying the generated discovery ISO leave no trace that this tool can verify in the four repositories it reads. Documented at [docs/infra-cluster-deployment.md → Cluster Deployment](docs/infra-cluster-deployment.md).
- [ ] **Bootstrap Argo CD for dizzy-infra** (phase 5) — Running setup-gitops.sh and applying the bootstrap Helm template changes live cluster state, which this repository-only report cannot verify. Documented at [docs/infra-cluster-deployment.md → Cluster Configuration](docs/infra-cluster-deployment.md).
- [ ] **Agents visible in hardware-inventory** (phase 4) — Agent visibility in the hub's hardware-inventory namespace requires live cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](docs/workload-cluster-deployment.md).
- [ ] **Agents labelled and approved** (phase 5) — Labelling and approving agents with update-agents.yaml changes live hub cluster state that repository configuration cannot prove. Documented at [docs/workload-cluster-deployment.md → Infrastructure Configuration](docs/workload-cluster-deployment.md).
- [ ] **Additional workload prerequisites are not yet documented upstream** (phase 7) — The upstream workload deployment guide lists observability (TBD) and ?? as open prerequisite items. Documented at [docs/workload-cluster-deployment.md → Cluster Deployment and Configuration](docs/workload-cluster-deployment.md).

## Details

<details>
<summary>✅ declared_in_main · info — dizzy-infra host inventory</summary>

Finding: The inventory contains a dizzy-infra group with 1 hosts.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `found` | `—` | `Yes` |
| `host_count` | `—` | `1` |

**Observed hosts**

| Host | Node name | BMC address | Boot image URL |
|---|---|---|---|
| [`control-0`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [`MOC-R4PAC10U31-S1D`](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | [—](https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml) | — |

</details>

<details>
<summary>✅ declared_in_main · info — Hub image inventory</summary>

Finding: The hub-image inventory contains the all.children.dizzy-infra key.

Source: CCI-MOC/oac-infra · [`hub-images/inventory.yml`](https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/inventory.yml) @ 2222222

| Field | Expected | Observed |
|---|---|---|
| `found` | `—` | `Yes` |

</details>

<details open>
<summary>❌ missing · blocking — Hub image variables</summary>

Finding: The hub-image variable file is absent from main.

Source: CCI-MOC/oac-infra · [`hub-images/group_vars/dizzy-infra/vars.yml`](https://github.com/CCI-MOC/oac-infra/tree/main) @ 2222222

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
<summary>⚪ unknown · advisory — Hub moc-dns records</summary>

Finding: Hub-image variables required for DNS validation are unavailable.

Source: CCI-MOC/moc-dns · [`zonefiles/`](https://github.com/CCI-MOC/moc-dns/tree/main) @ —

| Field | Expected | Observed |
|---|---|---|
| `api` | `—` | `—` |
| `api-int` | `—` | `—` |
| `*.apps` | `—` | `—` |

</details>

<details open>
<summary>❌ missing · blocking — dizzy-infra boot image</summary>

Finding: No boot image URL is inherited by the cluster host group.

Source: CCI-MOC/oac-infra · [`infra/inventory/00hosts.yaml`](https://github.com/CCI-MOC/oac-infra/tree/main) @ 2222222

Status rule: The boot-image filename must contain the full cluster name `dizzy-infra`; generic `discovery.iso` does not satisfy this rule.

| Field | Expected | Observed |
|---|---|---|
| `value` | `Cluster-specific discovery image for dizzy-infra` | `—` |

</details>

<details open>
<summary>❌ missing · blocking — Infra OIDC client</summary>

Finding: No Keycloak OIDC client block exists for this hub.

Source: CCI-MOC/moc-keycloak · [`main.tf`](https://github.com/CCI-MOC/moc-keycloak/blob/main/main.tf) @ 4444444

| Field | Expected | Observed |
|---|---|---|
| `client` | `dizzy-infra` | `—` |
| `redirect_uri` | `https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso` | `—` |
| `secret_name` | `cluster/dizzy-infra/keycloak-oidc` | `—` |

</details>

<details open>
<summary>❌ missing · blocking — Infra hosted-cluster defaults</summary>

Finding: No merged main paths were found for the default values for hosted clusters on this hub cluster.

Source: CCI-MOC/oac-apps · [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`hosted-clusters/dizzy-infra/values.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing · blocking — Hub-wide component values</summary>

Finding: No merged main paths were found for hub-wide HCP and secret-selector values.

Source: CCI-MOC/oac-apps · [`values/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`values/dizzy-infra/hcp-config.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing · blocking — Infra local-cluster values</summary>

Finding: No merged main paths were found for the hub cluster's local operator and shared-service values.

Source: CCI-MOC/oac-apps · [`values/dizzy-infra/local-cluster`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

</details>

<details open>
<summary>❌ missing · blocking — Infra ArgoCD applications</summary>

Finding: No merged main paths were found for direct ArgoCD applications applied on the hub cluster.

Source: CCI-MOC/oac-apps · [`apps/dizzy-infra`](https://github.com/CCI-MOC/oac-apps/tree/main) @ 3333333

| Field | Expected | Observed |
|---|---|---|
| [`apps/dizzy-infra/keycloak-oauth.yaml`](https://github.com/CCI-MOC/oac-apps/tree/main) | `present` | `missing` |

</details>

<details open>
<summary>❌ missing · blocking — Hub Pure storage realm</summary>

Finding: No Pure storage realm named dizzy-infra was found.

Source: CCI-MOC/everpure-moc · [`ansible/group_vars/all/realms.yaml`](https://github.com/CCI-MOC/everpure-moc/tree/main) @ 5555555

| Field | Expected | Observed |
|---|---|---|
| `name` | `dizzy-infra` | `—` |
| `fields` | `subnet_vlan, subnet_prefix, s3_endpoint` | `—` |

</details>

<details open>
<summary>❌ missing · blocking — Hub moc-aws OIDC cluster</summary>

Finding: No moc-aws OIDC cluster entry has cluster_name dizzy-infra.

Source: CCI-MOC/moc-aws · [`main.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/main.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster_name` | `dizzy-infra` | `—` |

</details>

<details open>
<summary>❌ missing · blocking — Hub moc-aws cert-manager policy</summary>

Finding: No cert-manager policy entry names dizzy-infra.

Source: CCI-MOC/moc-aws · [`cert-manager-policies.tf`](https://github.com/CCI-MOC/moc-aws/blob/main/cert-manager-policies.tf) @ 6666666

| Field | Expected | Observed |
|---|---|---|
| `cluster` | `dizzy-infra` | `—` |

</details>

<details>
<summary>✅ declared_in_main · info — Workload address uniqueness</summary>

Finding: No workload address is used by another cluster.

Source: CCI-MOC/oac-apps · [`hosted-clusters/`](https://github.com/CCI-MOC/oac-apps/blob/main/hosted-clusters/) @ 3333333

</details>

## Pull requests

None.

## Legend

- ✅ `declared_in_main` — Desired configuration is present on merged main.
- ❌ `missing` — Required configuration was not found.
- ⚪ `unknown` — The source could not be read or parsed.

Repository-state disclaimer: this report describes repository configuration only. It does not prove live cluster synchronization, node readiness, or application health.
