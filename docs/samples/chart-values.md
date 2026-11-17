SAMPLE — generated from a synthetic fixture, not a live environment.

# 📘 Chart Configuration Reference

> **Generated documentation.** This file is produced by `moc-env document-values`. Edit `docs/variables/*.yaml` and `docs/sources.yaml`; do not edit the generated Markdown directly.

This guide explains how `CCI-MOC/oac-apps` organizes Helm chart values across the deployment. It is intentionally independent of a particular environment: it documents the purpose and placement of configuration keys, not the current value assigned to any environment.

| Field | Value |
|---|---|
| Source repository | `CCI-MOC/oac-apps` |
| Source ref | `main` |
| Values files | 17 |
| Unique keys | 23 |

## Deployment model

The hub cluster is the management cluster. It runs shared services and hosts control planes for workload clusters. A hosted workload cluster therefore has two important halves: its control plane runs on the hub, while its worker nodes provide the workload data plane.

## Scope summary

| Scope | Layer | Path pattern | Files | Keys |
|---|---|---|---:|---:|
| `hub-wide` | Hub cluster | `values/{hub-cluster}/*.yaml` | 1 | 0 |
| `hub-local-cluster` | Hub local cluster | `values/{hub-cluster}/local-cluster/*.yaml` | 13 | 0 |
| `hosted-cluster-defaults` | Hosted clusters under a hub | `hosted-clusters/{hub-cluster}/*.yaml` | 1 | 2 |
| `hosted-cluster` | Hosted control plane and data plane | `hosted-clusters/{hub-cluster}/{workload-cluster}/values.yaml` | 1 | 21 |
| `workload-components` | Hosted workload cluster | `values/{hub-cluster}/{workload-cluster}/*.yaml` | 1 | 0 |

## Manual topics

Manual topics carry the reviewed explanation for each variable. Discovery adds the charts, types, file counts, and scopes where that key currently appears. Source references use compact links; the appendix lists each referenced document once.

## Hosted Cluster DNS and Addressing

Hosted clusters use two DNS facings. The internal facing carries control-plane and router names that must be reachable from the hub and in-cluster callers. The external facing carries names that must be reachable from outside the hub, usually through a firewall or NAT boundary. The chart creates two hub-wide wildcard records and, when automatic DNS generation is enabled, explicit records for the API server and guest-cluster ingress. ExternalDNS is configured separately to publish those records into the supported DNS provider.

### Hub-level domains

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `hcpInternalDomain` | Required | `—` | [DNS-1](#sources), [HCP-1](#sources) |
| `hcpExternalDomain` | Optional | `hcpInternalDomain` | [DNS-1](#sources), [HCP-1](#sources) |
| `baseDomain` | Required | `—` | [DNS-1](#sources), [HCP-1](#sources) |

#### `hcpInternalDomain`

Required per-hub domain used for internal-facing hosted-control-plane names, including the internal API server name and the Konnectivity and Ignition route hostnames.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `hcpExternalDomain`, `baseDomain` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

#### `hcpExternalDomain`

Optional per-hub domain used for externally reachable hosted-control-plane names, including the external API server name and browser-facing OAuth hostname. When unset, it inherits hcpInternalDomain. Set it only when internal and external names must resolve to different addresses.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster-defaults`. Types: `str`. Values files: 1. Scopes: `hosted-cluster-defaults`. |
| Related keys | `hcpInternalDomain`, `baseDomain` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

#### `baseDomain`

Parent DNS domain used for the guest cluster’s application ingress wildcard. The chart derives the wildcard as *.apps.<clusterName>.<baseDomain> unless an explicit ingress hostname is supplied.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster-defaults`. Types: `str`. Values files: 1. Scopes: `hosted-cluster-defaults`. |
| Related keys | `hcpInternalDomain`, `hcpExternalDomain` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

### Hosted-cluster DNS generation

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `dns.enabled` | Optional | `—` | [HCP-1](#sources) |
| `dns.autoGenerate` | Optional | `—` | [DNS-1](#sources), [HCP-1](#sources) |

#### `dns.enabled`

Enables DNS record generation for the hosted cluster. When false, the chart does not create automatic records or process manual dns.records.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.autoGenerate`, `dns.records` |
| Source(s) | [HCP-1](#sources) |

#### `dns.autoGenerate`

Enables automatic shadow-Service DNS records for the API server and guest-cluster ingress. This creates explicit records for the internal and external API names and the application ingress wildcard, overriding the corresponding hub-wide wildcards.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.enabled`, `services.APIServer.ipAddress`, `services.APIServer.externalIpAddress`, `ingress.ipAddress`, `ingress.externalIpAddress` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

### Manual DNS records

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `dns.records[].name` | Required | `—` | [HCP-1](#sources) |
| `dns.records[].hostname` | Required | `—` | [HCP-1](#sources) |
| `dns.records[].target` | Required | `—` | [HCP-1](#sources) |
| `dns.records[].targets` | Optional | `—` | [HCP-1](#sources) |

#### `dns.records[].name`

Unique identifier for a manual DNS record entry. The chart uses it to build the generated shadow Service name.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.records[].hostname`, `dns.records[].target` |
| Source(s) | [HCP-1](#sources) |

#### `dns.records[].hostname`

DNS hostname published by the manual record. ExternalDNS reads this from the external-dns.alpha.kubernetes.io/hostname annotation.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster`. Types: `str`. Values files: 1. Scopes: `hosted-cluster`. |
| Related keys | `dns.records[].name`, `dns.records[].target` |
| Source(s) | [HCP-1](#sources) |

#### `dns.records[].target`

Single IP address or hostname target for a manual DNS record. Specify either target or targets, not both.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.records[].targets`, `dns.records[].hostname` |
| Source(s) | [HCP-1](#sources) |

#### `dns.records[].targets`

List of target values for a manual DNS record. The chart joins them into a comma-separated annotation. Specify either target or targets, not both.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.records[].target` |
| Source(s) | [HCP-1](#sources) |

### ExternalDNS operator

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `externaldns[].name` | Required | `—` | [EDNS-1](#sources) |
| `externaldns[].credentials` | Required | `—` | [EDNS-1](#sources) |
| `externaldns[].externalSecret.remoteKey` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].externalSecret.secretStore` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].externalSecret.secretStoreType` | Optional | `ClusterSecretStore` | [EDNS-1](#sources) |
| `externaldns[].domains[].filterType` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].domains[].matchType` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].domains[].name` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].hostnameAnnotation` | Optional | `Allow` | [EDNS-1](#sources) |
| `externaldns[].labelFilter.matchLabels` | Optional | `—` | [EDNS-1](#sources) |
| `externaldns[].zones` | Optional | `—` | [EDNS-1](#sources) |

#### `externaldns[].name`

Name assigned to the generated ExternalDNS resource.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains`, `externaldns[].zones` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].credentials`

Name of the Secret containing provider credentials used by ExternalDNS. When externalSecret is configured, the chart creates that Secret from the external secret store.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].externalSecret.remoteKey`, `externaldns[].externalSecret.secretStore` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].externalSecret.remoteKey`

Remote key in the external secret store that contains the ExternalDNS provider credentials.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].credentials`, `externaldns[].externalSecret.secretStore` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].externalSecret.secretStore`

Name of the ExternalSecret store used to retrieve the ExternalDNS provider credentials.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].externalSecret.remoteKey`, `externaldns[].externalSecret.secretStoreType` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].externalSecret.secretStoreType`

Kind of ExternalSecret store used for the ExternalDNS provider credentials. Defaults to ClusterSecretStore.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].externalSecret.secretStore` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].domains[].filterType`

Whether the domain entry includes or excludes matching DNS names.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains[].matchType`, `externaldns[].domains[].name` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].domains[].matchType`

Match strategy applied to the domain filter, such as exact matching.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains[].filterType`, `externaldns[].domains[].name` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].domains[].name`

DNS domain included or excluded by the ExternalDNS domain filter.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains[].filterType`, `externaldns[].domains[].matchType` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].hostnameAnnotation`

Controls whether ExternalDNS uses the external-dns.alpha.kubernetes.io/hostname annotation on source Services. The hosted-cluster chart relies on this annotation to publish DNS names.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `dns.records[].hostname` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].labelFilter.matchLabels`

Labels used to select which source Services ExternalDNS considers. The hosted-cluster chart labels generated DNS shadow Services with massopen.cloud/external-dns.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains` |
| Source(s) | [EDNS-1](#sources) |

#### `externaldns[].zones`

Provider-specific DNS zone identifiers, such as Route 53 hosted-zone IDs, that ExternalDNS may manage.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `externaldns[].domains` |
| Source(s) | [EDNS-1](#sources) |

### Hosted-cluster service addressing

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `services.APIServer.ipAddress` | Optional | `—` | [DNS-1](#sources), [HCP-1](#sources) |
| `services.APIServer.externalIpAddress` | Optional | `—` | [DNS-1](#sources), [HCP-1](#sources) |
| `ingress.ipAddress` | Optional | `—` | [DNS-1](#sources), [HCP-1](#sources) |
| `ingress.externalIpAddress` | Optional | `—` | [DNS-1](#sources), [HCP-1](#sources) |

#### `services.APIServer.ipAddress`

Internal LoadBalancer IP for the hosted-cluster API server. When DNS auto-generation is enabled, it becomes the target of the internal api-internal-<cluster> record and the MetalLB pool address.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster`. Types: `str`. Values files: 1. Scopes: `hosted-cluster`. |
| Related keys | `services.APIServer.externalIpAddress`, `hcpInternalDomain`, `dns.autoGenerate` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

#### `services.APIServer.externalIpAddress`

External firewall IP for the hosted-cluster API server. When DNS auto-generation is enabled, it becomes the target of the external api-external-<cluster> record and the kubeAPIServerDNSName.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster`. Types: `str`. Values files: 1. Scopes: `hosted-cluster`. |
| Related keys | `services.APIServer.ipAddress`, `hcpExternalDomain`, `dns.autoGenerate` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

#### `ingress.ipAddress`

Internal fallback target for the guest-cluster application ingress wildcard. Use it when the guest router is not externally reachable.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `ingress.externalIpAddress`, `baseDomain` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

#### `ingress.externalIpAddress`

Externally reachable IP for the guest-cluster application ingress wildcard. When set, it takes precedence over ingress.ipAddress.

| Field | Value |
|---|---|
| Chart discovery | Charts: `hosted-cluster`. Types: `str`. Values files: 1. Scopes: `hosted-cluster`. |
| Related keys | `ingress.ipAddress`, `baseDomain` |
| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |

### Spoke-cluster addressing

| Key | Required | Default or fallback | Source(s) |
|---|---|---|---|
| `apiVIP` | Optional | `—` | [HCP-1](#sources) |
| `ingressVIP` | Optional | `—` | [HCP-1](#sources) |

#### `apiVIP`

Reserved virtual IP for a spoke cluster’s API endpoint. This is used by the spoke-cluster chart rather than the hosted-cluster chart.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `ingressVIP` |
| Source(s) | [HCP-1](#sources) |

#### `ingressVIP`

Reserved virtual IP for a spoke cluster’s ingress router. This is used by the spoke-cluster chart rather than the hosted-cluster chart.

| Field | Value |
|---|---|
| Chart discovery | Not currently observed in merged `main`; this entry documents supported chart input. |
| Related keys | `apiVIP` |
| Source(s) | [HCP-1](#sources) |

## Uncurated variables

These variables do not yet have a manual definition. They are shown with repository-derived facts and a provisional chart-based description until a reviewed manual entry is added.

### hosted-cluster

The primary definition of one hosted workload cluster. Its hosted control plane runs on the hub; these values describe the cluster and its node pools.

**Path pattern:** `hosted-clusters/{hub-cluster}/{workload-cluster}/values.yaml`

| Key | Charts | Type | Files | What it controls |
|---|---|---|---:|---|
| `clusterName` | `hosted-cluster` | `str` | 1 | Name assigned to the hosted cluster. |
| `dns` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `dns`. |
| `dns.records` | `hosted-cluster` | `list` | 1 | The hosted workload cluster and its node pools. This key controls `records`. |
| `feature-gpu` | `hosted-cluster` | `str` | 1 | The hosted workload cluster and its node pools. This key controls `feature-gpu`. |
| `ingress` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `ingress`. |
| `ingress.poolAddress` | `hosted-cluster` | `str` | 1 | Address pool used for ingress. |
| `nodePools` | `hosted-cluster` | `list` | 1 | The hosted workload cluster and its node pools. This key controls `nodePools`. |
| `nodePools[].agentLabelSelector` | `hosted-cluster` | `dict` | 1 | Hosted-cluster node-pool settings: node selection, sizing, storage, and update behavior. |
| `nodePools[].agentLabelSelector.cluster` | `hosted-cluster` | `str` | 1 | Hosted-cluster node-pool settings: node selection, sizing, storage, and update behavior. |
| `nodePools[].agentLabelSelector.resource_class` | `hosted-cluster` | `str` | 1 | Hosted-cluster node-pool settings: node selection, sizing, storage, and update behavior. |
| `nodePools[].name` | `hosted-cluster` | `str` | 1 | Hosted-cluster node-pool settings: node selection, sizing, storage, and update behavior. |
| `nodePools[].replicas` | `hosted-cluster` | `int` | 1 | Hosted-cluster node-pool settings: node selection, sizing, storage, and update behavior. |
| `oauth` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `oauth`. |
| `oauth.mocsso` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `mocsso`. |
| `oauth.mocsso.enabled` | `hosted-cluster` | `bool` | 1 | Enables the MOC single sign-on OAuth provider. |
| `services` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `services`. |
| `services.APIServer` | `hosted-cluster` | `dict` | 1 | The hosted workload cluster and its node pools. This key controls `APIServer`. |

## How to use this guide

- Choose the scope that matches the deployment layer you are changing.
- Use the path pattern to locate the relevant values file.
- Read the cited source and the upstream chart documentation together.
- Keep secret material in an external-secret store; only reference its key here.
- Do not copy an environment's values blindly. Values are examples of usage, not portable defaults.

This reference is generated read-only from merged `main`. It does not prove that a chart is installed, healthy, or current in any cluster.

## Sources

| ID | Source | Repository | Path | Ref |
|---|---|---|---|---|
| `DNS-1` | [Hosted Cluster Address and DNS Design](https://github.com/CCI-MOC/oac-apps/blob/ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3/docs/superpowers/specs/2026-08-28-hosted-cluster-address-dns-design.md) | `CCI-MOC/oac-apps` | `docs/superpowers/specs/2026-08-28-hosted-cluster-address-dns-design.md` | `ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3` |
| `EDNS-1` | [External DNS Operator Chart Defaults](https://github.com/CCI-MOC/oac-apps/blob/ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3/charts/external-dns-operator/values.yaml) | `CCI-MOC/oac-apps` | `charts/external-dns-operator/values.yaml` | `ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3` |
| `HCP-1` | [Hosted Cluster Chart Defaults](https://github.com/CCI-MOC/oac-apps/blob/ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3/charts/hosted-cluster/values.yaml) | `CCI-MOC/oac-apps` | `charts/hosted-cluster/values.yaml` | `ba0c0e8c47855e65edb85b80f9d904ee6b1e17b3` |
