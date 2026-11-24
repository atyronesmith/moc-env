SAMPLE — generated from a synthetic fixture, not a live environment.

# Desired-State Validation

**Result:** VALID

| Field | Value |
|---|---|
| Document | `docs/samples/example-env-infra.yaml` |
| Error count | 0 |
| Warning count | 0 |
| Checks passed | 33 |
| Checks failed | 0 |
| Checks with warnings | 0 |
| Total checks | 33 |

## Check summary by category

| Category | Passed | Failed | Warnings | Total |
|---|---:|---:|---:|---:|
| Document | 5 | 0 | 0 | 5 |
| Metadata | 6 | 0 | 0 | 6 |
| Specification | 1 | 0 | 0 | 1 |
| Inventory | 4 | 0 | 0 | 4 |
| Network and domain | 15 | 0 | 0 | 15 |
| Security | 1 | 0 | 0 | 1 |
| Schema compatibility | 1 | 0 | 0 | 1 |

## Detailed checks

### Document

5 of 5 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| YAML parsing and duplicate keys | `document` | Parseable YAML without duplicate mapping keys | Valid | PASS | — |
| YAML document shape | `document` | Mapping | Mapping | PASS | — |
| API version | `apiVersion` | moc-env/v1alpha1 | 'moc-env/v1alpha1' | PASS | — |
| Resource kind | `kind` | InfraCluster | 'InfraCluster' | PASS | — |
| Schema version | `schemaVersion` | 1 | '1' | PASS | — |

### Metadata

6 of 6 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Metadata mapping | `metadata` | Mapping | Mapping | PASS | — |
| Infra-cluster metadata | `metadata.name` | Source object with cluster name | 'example-env-infra' (inferred) | PASS | — |
| Environment metadata | `metadata.environment` | Source object with environment name | 'example-env' (inferred) | PASS | — |
| Infra-cluster name format | `metadata.name.value` | Valid DNS-like cluster name | 'example-env-infra' | PASS | — |
| Environment name format | `metadata.environment.value` | Valid DNS-like environment name | 'example-env' | PASS | — |
| Environment and infra naming | `metadata` | ENVIRONMENT-infra ('example-env-infra') | 'example-env-infra' | PASS | — |

### Specification

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Specification mapping | `spec` | Mapping | Mapping | PASS | — |

### Inventory

4 of 4 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Inventory mapping | `spec.inventory` | Mapping | Mapping | PASS | — |
| Inventory cluster mapping | `spec.inventory.clusters` | Mapping of cluster names | Mapping | PASS | — |
| Expected inventory cluster | `spec.inventory.clusters` | 'example-env-infra' | present | PASS | — |
| Inventory cluster name | `spec.inventory.clusters.example-env-infra.name.value` | 'example-env-infra' | 'example-env-infra' | PASS | — |

### Network and domain

15 of 15 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Variables mapping | `spec.variables` | Mapping | Mapping | PASS | — |
| Variable fields mapping | `spec.variables.fields` | Mapping of required fields | Mapping | PASS | — |
| Required field: cluster_domain_name | `spec.variables.fields.cluster_domain_name` | Source object with value, provenance, and confidence | 'example-env' (exact) | PASS | — |
| Required field: base_domain | `spec.variables.fields.base_domain` | Source object with value, provenance, and confidence | 'int.massopen.cloud' (exact) | PASS | — |
| Required field: machine_network | `spec.variables.fields.machine_network` | Source object with value, provenance, and confidence | '10.20.26.0/23' (exact) | PASS | — |
| Required field: api_ip | `spec.variables.fields.api_ip` | Source object with value, provenance, and confidence | '10.20.27.11' (exact) | PASS | — |
| Required field: ingress_ip | `spec.variables.fields.ingress_ip` | Source object with value, provenance, and confidence | '10.20.27.12' (exact) | PASS | — |
| Required field: dns_ip | `spec.variables.fields.dns_ip` | Source object with value, provenance, and confidence | '8.8.8.8' (exact) | PASS | — |
| Machine network CIDR syntax | `spec.variables.fields.machine_network.value` | Valid IPv4 or IPv6 CIDR | '10.20.26.0/23' | PASS | — |
| api_ip syntax | `spec.variables.fields.api_ip.value` | Valid IPv4 or IPv6 address | '10.20.27.11' | PASS | — |
| ingress_ip syntax | `spec.variables.fields.ingress_ip.value` | Valid IPv4 or IPv6 address | '10.20.27.12' | PASS | — |
| dns_ip syntax | `spec.variables.fields.dns_ip.value` | Valid IPv4 or IPv6 address | '8.8.8.8' | PASS | — |
| cluster_domain_name syntax | `spec.variables.fields.cluster_domain_name.value` | Valid DNS name | 'example-env' | PASS | — |
| base_domain syntax | `spec.variables.fields.base_domain.value` | Valid DNS name | 'int.massopen.cloud' | PASS | — |
| Domain consistency | `spec.domain.value` | cluster_domain_name.base_domain ('example-env.int.massopen.cloud') | 'example-env.int.massopen.cloud' | PASS | — |

### Security

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Secret-like field names | `document` | No fields named secret, token, password, or credential | 0 prohibited field(s) | PASS | — |

### Schema compatibility

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Unknown fields | `document` | Only fields defined by schema version 1 | 0 unknown field(s) | PASS | — |


## Interpretation

- **VALID** means the document satisfies the current desired-state schema and validation rules.
- **INVALID** means at least one error must be corrected before the document is reviewed as desired state.
- Warnings identify unknown fields or unusual content; they do not fail validation.
- This report validates repository-derived desired state only. It does not prove live cluster health or synchronization.
