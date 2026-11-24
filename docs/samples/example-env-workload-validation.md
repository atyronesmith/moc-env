SAMPLE — generated from a synthetic fixture, not a live environment.

# Desired-State Validation

**Result:** VALID

| Field | Value |
|---|---|
| Document | `docs/samples/example-env-workload0.yaml` |
| Error count | 0 |
| Warning count | 0 |
| Checks passed | 1 |
| Checks failed | 0 |
| Checks with warnings | 0 |
| Total checks | 1 |

## Check summary by category

| Category | Passed | Failed | Warnings | Total |
|---|---:|---:|---:|---:|
| Document | 1 | 0 | 0 | 1 |

## Detailed checks

### Document

1 of 1 checks passed.

| Check | Path | Expected | Actual | Result | Detail |
|---|---|---|---|---|---|
| YAML parsing and duplicate keys | `document` | Parseable YAML without duplicate mapping keys | Valid | PASS | — |


## Interpretation

- **VALID** means the document satisfies the current desired-state schema and validation rules.
- **INVALID** means at least one error must be corrected before the document is reviewed as desired state.
- Warnings identify unknown fields or unusual content; they do not fail validation.
- This report validates repository-derived desired state only. It does not prove live cluster health or synchronization.
