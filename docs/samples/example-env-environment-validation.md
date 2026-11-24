SAMPLE — generated from a synthetic fixture, not a live environment.

# Desired-State Validation

**Result:** VALID

| Field | Value |
|---|---|
| Document | `docs/samples/example-env-environment.yaml` |
| Error count | 0 |
| Warning count | 0 |
| Checks passed | 20 |
| Checks failed | 0 |
| Checks with warnings | 0 |
| Total checks | 20 |

## Check summary by category

| Category | Passed | Failed | Warnings | Total |
|---|---:|---:|---:|---:|
| Document | 5 | 0 | 0 | 5 |
| Metadata | 2 | 0 | 0 | 2 |
| Bundle | 2 | 0 | 0 | 2 |
| References | 6 | 0 | 0 | 6 |
| Network and domain | 3 | 0 | 0 | 3 |
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
| Resource kind | `kind` | Environment | 'Environment' | PASS | — |
| Schema version | `schemaVersion` | 1 | '1' | PASS | — |

### Metadata

2 of 2 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Metadata mapping | `metadata` | Mapping | Mapping | PASS | — |
| Environment name | `metadata.name` | Source object with a valid environment name | 'example-env' (inferred) | PASS | — |

### Bundle

2 of 2 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Spec mapping | `spec` | Mapping | Mapping | PASS | — |
| MOC issue reference | `spec.issue` | CCI-MOC/MOC-issues issue URL | 'https://github.com/CCI-MOC/MOC-issues/issues/666' | PASS | — |

### References

6 of 6 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Hub-cluster name | `spec.hubCluster` | 'example-env-infra' | 'example-env-infra' | PASS | — |
| Workload-cluster list | `spec.workloadClusters` | Non-empty list of workload mappings | List | PASS | — |
| Workload 0 mapping | `spec.workloadClusters[0]` | Mapping with name and parentHubCluster | Mapping | PASS | — |
| Workload 0 name | `spec.workloadClusters[0].name` | Name beginning with example-env-workload | 'example-env-workload0' | PASS | — |
| Workload 0 parent | `spec.workloadClusters[0].parentHubCluster` | 'example-env-infra' | 'example-env-infra' | PASS | — |
| Duplicate workload names | `spec.workloadClusters` | No duplicate workload names | None | PASS | — |

### Network and domain

3 of 3 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Network mapping | `spec.network` | Mapping | Mapping | PASS | — |
| Machine-network CIDR | `spec.network.machineNetwork.value` | Valid IPv4 or IPv6 CIDR | '10.20.26.0/23' | PASS | — |
| Domain syntax | `spec.domain.value` | Valid DNS name | 'example-env.int.massopen.cloud' | PASS | — |

### Security

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Secret-like field names | `document` | No fields named secret, token, password, or credential | 0 prohibited field(s) | PASS | — |

### Schema compatibility

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| Unknown fields | `document` | Only fields defined by the Environment bundle schema | 0 unknown field(s) | PASS | — |


## Interpretation

- **VALID** means the document satisfies the current desired-state schema and validation rules.
- **INVALID** means at least one error must be corrected before the document is reviewed as desired state.
- Warnings identify unknown fields or unusual content; they do not fail validation.
- This report validates repository-derived desired state only. It does not prove live cluster health or synchronization.
