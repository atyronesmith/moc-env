# `moc-env-status` roadmap

## Direction

`moc-env-status` remains one CLI with separate infra-cluster and workload-cluster
check suites. The implementation moves through three connected capabilities:

1. **Observe** current repository configuration.
2. **Declare** reviewed desired state in YAML.
3. **Converge** by planning and, only after explicit action, generating PRs.

Ordinary status, export, check, plan, and local-generation commands must not
push, create PRs, approve, merge, comment, or force-push anything.

## Dependency policy

The runtime is standard-library Python plus **PyYAML**. PyYAML is approved for
repository YAML parsing and is locked with `uv.lock`. Any additional runtime
dependency requires an explicit design decision; prefer extending the existing
model and renderers first.

## Phase 0 — stabilize the current foundation

**Status:** complete

The first stabilization slice:

- introduced a normalized `InfraObservation` model;
- moved `oac-infra` repository reads and YAML normalization out of check
  generation;
- moved the offline GitHub fixture into a reusable test module;
- added CLI dispatch tests for `list`, text, JSON, Markdown, and output files;
- added an observation-reader test for inventory, hub inventory, and hub
  variables;
- verified that live `bu-ist-demo` stdout remains byte-for-byte unchanged.

Remaining Phase 0 hardening can be done incrementally:

- move issue, Keycloak, `oac-apps`, and pull-request reads behind normalized
  observation models;
- add no-network tests for all check branches, especially missing and partial
  repository files;
- add parser tests for all supported YAML shapes.

## Phase 1 — complete the observed-state model

Extend the normalized model before adding export commands:

```text
GitHub repositories
  → repository readers
  → ObservedInfraCluster
  → check suite
  → status report
```

Add:

- issue observation;
- Keycloak OIDC observation;
- `oac-apps` path and pull-request observations;
- `ObservedWorkloadCluster`;
- `ObservedEnvironment`;
- source provenance for every extracted value.

Every observation field should distinguish `exact`, `inferred`, and
`unsupported` extraction confidence.

## Phase 2 — `export-infra`

Add a deterministic read-only exporter:

```sh
uv run moc-env-status export-infra bu-ist-demo
uv run moc-env-status export-infra bu-ist-demo \
  --output desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

The generated `InfraCluster` YAML is a draft normalized snapshot of repository
state, not a claim that a cluster is deployed. It must:

- sort and render fields deterministically;
- preserve source provenance;
- mark inferred values;
- represent unsupported or ambiguous fields explicitly;
- omit timestamps unless explicitly requested.

## Phase 3 — desired-state validation

Add:

```sh
uv run moc-env-status validate desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

Validate:

- required metadata;
- required network and domain fields;
- IP and CIDR syntax;
- environment and infra-cluster naming consistency;
- duplicate keys;
- unknown fields, warning rather than silently accepting them;
- secret-like fields, rejecting them.

## Phase 4 — `check-infra`

Compare reviewed desired state to current merged repository state:

```sh
uv run moc-env-status check-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

Comparison states:

- `matches_main`
- `missing_from_main`
- `value_mismatch`
- `unexpected_in_main`
- `unsupported_check`
- `ambiguous`
- `pr_open`

A YAML exported from current state should report supported fields as matching.
Changing one desired value should produce exactly one `value_mismatch`.

## Phase 5 — workload export

Add:

```sh
uv run moc-env-status export-workload bu-ist-demo workload0
```

Extract:

- workload host group and host count;
- boot image;
- machine inventory;
- hosted-cluster values;
- workload component values;
- workload applications;
- references to the parent infra cluster.

Missing values must remain explicit; they must not disappear from the YAML.

## Phase 6 — `check-workload`

Add:

```sh
uv run moc-env-status check-workload \
  desired-state/workload-clusters/bu-ist-demo-workload0.yaml
```

Cross-check:

- referenced infra cluster exists;
- names are consistent;
- networks are compatible;
- boot image is cluster-specific;
- hosted-cluster and component values exist;
- applications reference the correct infra and workload clusters;
- identity and domain references are consistent.

## Phase 7 — environment bundles

Add one environment YAML that references one infra cluster and one or more
workload clusters:

```yaml
apiVersion: moc.org/v1alpha1
kind: Environment
metadata:
  name: bu-ist-demo
spec:
  issue: https://github.com/CCI-MOC/MOC-issues/issues/666
  infraCluster: bu-ist-demo-infra
  workloadClusters:
    - bu-ist-demo-workload0
```

Then validate and check the complete environment.

## Phase 8 — change planning

Planning remains read-only:

```sh
uv run moc-env-status plan-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

The plan identifies each repository, branch, changed path, operation, reason,
and dependency. For same-repository review sequencing, support optional stacked
branches:

```text
main
 └── add-bu-ist-demo-infra-inventory
      └── add-bu-ist-demo-infra-hub-values
           └── add-bu-ist-demo-infra-gitops
```

Stacking is optional; the default is one branch per repository.

## Phase 9 — local change generation

Generate local branches without pushing:

```sh
uv run moc-env-status generate-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml \
  --output-worktree generated-changes
```

Output:

```text
generated-changes/
  oac-infra/
  moc-keycloak/
  oac-apps/
```

Each repository contains a deterministic local branch and commit. The command
must not push or create PRs.

## Phase 10 — local plan validation

Add:

```sh
uv run moc-env-status validate-plan generated-changes
```

Validate:

- YAML syntax;
- Terraform format where applicable;
- desired-state schemas;
- whitespace and Git diffs;
- repository tests where available;
- cross-repository consistency;
- generated PR bodies.

## Phase 11 — publish coordinated PR sets

Only this phase mutates GitHub:

```sh
uv run moc-env-status publish-plan generated-changes \
  --draft \
  --create-prs
```

It pushes local branches and creates draft PRs. It must never approve, merge,
close, reopen, or force-push a PR. Each PR links the MOC issue, desired-state
source, changed files, validation results, and related PRs in dependency order.

## Phase 12 — operational hardening

Add:

- repository response caching and `--refresh`;
- rate-limit retry and backoff;
- bounded concurrent repository reads;
- separate read and write credential scopes;
- dry-run output for every mutating command;
- report snapshots;
- hosted CI;
- user documentation for credentials, schemas, status, export, checking, and
  PR generation.
