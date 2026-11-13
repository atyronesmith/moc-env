# `moc-env` roadmap

## Direction

`moc-env` remains one CLI with separate hub-cluster and hosted-workload-cluster
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

The deferred Phase 0 hardening is also complete:

- move issue, Keycloak, `oac-apps`, and pull-request reads behind normalized
  observation models;
- add no-network tests for check branches covering declared, missing, and
  partial repository state;
- add parser tests for supported inventory roots and unsupported YAML shapes.

## Phase 1 — complete the observed-state model

**Status:** complete

Extend the normalized model before adding export commands:

```text
GitHub repositories
  → repository readers
  → ObservedInfraCluster
  → check suite
  → status report
```

Implemented:

- issue observation;
- Keycloak OIDC observation;
- `oac-apps` path and pull-request observations;
- `ObservedWorkloadCluster`;
- `ObservedEnvironment`;
- source provenance for every extracted value.

Every observation field should distinguish `exact`, `inferred`, and
`unsupported` extraction confidence.

The completed model uses `SourceValue` for repository-extracted structural
fields as well as scalar values. Requested cluster names are marked `inferred`;
values extracted from a supported YAML shape are marked `exact`; values that
cannot be extracted from an unsupported YAML shape are represented explicitly
and marked `unsupported`.

## Phase 2 — `export-infra`

**Status:** complete

Add a deterministic read-only exporter:

```sh
uv run moc-env export-infra bu-ist-demo
uv run moc-env export-infra bu-ist-demo \
  --output desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

The generated `InfraCluster` YAML is a draft normalized snapshot of repository
state, not a claim that a cluster is deployed. It must:

- sort and render fields deterministically;
- preserve source provenance;
- mark inferred values;
- represent unsupported or ambiguous fields explicitly;
- omit timestamps unless explicitly requested.

The exporter emits a versioned `moc-env/v1alpha1` `InfraCluster` document.
Every repository-derived field retains its repository/path/ref provenance and
extraction confidence. Derived environment, cluster, path, and domain values
are marked `inferred`; ambiguous boot-image selections and values from
unsupported YAML shapes are represented with null values and `unsupported`
confidence. Output is sorted deterministically and contains no generation
timestamp.

## Phase 3 — desired-state validation

**Status:** complete

Add:

```sh
uv run moc-env validate desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

Validate:

- required metadata;
- required network and domain fields;
- IP and CIDR syntax;
- environment and hub-cluster naming consistency;
- duplicate keys;
- unknown fields, warning rather than silently accepting them;
- secret-like fields, rejecting them.

Validation is local and read-only. It accepts the Phase 2 `InfraCluster` export
schema, rejects duplicate YAML keys and secret-like field names, checks naming
and domain consistency, validates IP and CIDR syntax, and rejects unsupported
required values. Unknown fields produce warnings without failing validation.
Validation results retain a detailed per-check ledger. Text, JSON, and
standalone Markdown output are available; invalid documents return exit code 2.

## Phase 4 — `check-infra`

**Status:** complete

Compare reviewed desired state to current merged repository state:

```sh
uv run moc-env check-infra \
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

The comparison validates the desired-state document first, reads the current
`oac-infra` observation, and optionally reads relevant `oac-apps` pull
requests. It compares supported metadata, inventory, hub inventory, domain,
network, cluster, host, and boot-image fields. Text, JSON, and Markdown output
are available. Hard differences return exit code 1; an open relevant pull
request without a hard difference returns exit code 0.

## Phase 5 — workload export

**Status:** complete

Add:

```sh
uv run moc-env export-workload bu-ist-demo workload0
```

Extract:

- workload host group and host count;
- boot image;
- machine inventory;
- hosted-cluster values;
- workload component values;
- workload applications;
- references to the parent hub cluster.

Missing values must remain explicit; they must not disappear from the YAML.

The exporter emits a versioned `moc-env/v1alpha1` `WorkloadCluster` document.
It records the parent hub cluster, host group and count, machine inventory,
boot image, hosted-cluster values, component values, application paths, and
repository/path/ref provenance. Missing GitOps scopes remain explicit with
`present: false`; ambiguous boot-image selections are represented with an
unsupported selected value. Output is deterministic and contains no generation
timestamp.

## Phase 6 — `check-workload`

**Status:** complete

Add:

```sh
uv run moc-env check-workload \
  desired-state/workload-clusters/bu-ist-demo-workload0.yaml
```

Cross-check:

- referenced hub cluster exists;
- names are consistent;
- networks are compatible;
- boot image is cluster-specific;
- hosted-cluster and component values exist;
- applications reference the correct infra and workload clusters;
- identity and domain references are consistent.

The workload check validates the document structure, reads current `oac-infra`
and `oac-apps` observations, and compares the workload against its parent.
It checks parent existence, naming, parent domain and machine-network
references, inventory and host count, boot-image specificity, hosted-cluster
and component values, application path references, and relevant pull requests.
Application absence is valid when desired state records it as absent. Text,
JSON, and Markdown output are available; hard differences return exit code 1.

## Chart-values documentation

**Status:** complete

The next documentation milestone is captured in
[chart-values-documentation-plan.md](chart-values-documentation-plan.md). It
separates human-authored variable explanations from refreshable repository
discovery and assembles the final guide from both layers.

Add a read-only command that explains how values are organized in `oac-apps`:

```sh
uv run moc-env document-values
```

The command reads all merged-`main` values files and generates an
environment-independent Markdown reference for five scopes:

- hub-wide values;
- hub local-cluster values;
- hosted-cluster-default values;
- hosted-cluster values;
- workload-component values.

Keys are aggregated across environments. Manual definitions provide the
reviewed narrative, defaults, relationships, and evidence; discovery adds the
scopes, charts, types, and file counts where each key currently appears.
Source references use compact in-document links and a single source appendix
rather than per-variable URLs. Variables without manual definitions remain in an
uncurated section. List-valued settings are expanded with `[]` keys, so fields
inside repeated objects such as node pools and DNS records are documented
individually. The guide does not print an environment's current values.
Unsupported YAML shapes remain explicit, and the guide does not replace
upstream Helm chart documentation.

The local documentation catalog can be refreshed from the clones under
`../MOC`:

```sh
uv run moc-env refresh-doc-catalog
```

The refresh records each source’s repository HEAD SHA, content hash, and cached
document text under `.cache/doc-catalog/`. Manual definitions are not modified.

Manual definitions can also be reconciled with the local `oac-apps` clone:

```sh
uv run moc-env discover-values
```

The discovery report identifies variables without manual definitions, manual
entries without current occurrences, changed or missing evidence, default
conflicts, and unsupported YAML files. Manual definitions are never overwritten.

## Phase 7 — environment bundles

**Status:** complete

Add one environment YAML that references one hub cluster and one or more
workload clusters:

```yaml
apiVersion: moc-env/v1alpha1
kind: Environment
metadata:
  name: bu-ist-demo
spec:
  issue: https://github.com/CCI-MOC/MOC-issues/issues/666
  hubCluster: bu-ist-demo-infra
  workloadClusters:
    - name: bu-ist-demo-workload0
      parentHubCluster: bu-ist-demo-infra
  domain: bu-ist-demo.int.massopen.cloud
  network:
    machineNetwork: 10.20.26.0/23
```

Export the draft bundle, validate it, and compare it with merged `main`:

```sh
uv run moc-env export-environment bu-ist-demo
uv run moc-env validate desired-state/environments/bu-ist-demo.yaml
uv run moc-env check-environment \
  desired-state/environments/bu-ist-demo.yaml
```

Validation checks the document schema, source provenance, issue URL, hub and
workload naming, parent-child references, duplicate workloads, domain syntax,
machine-network CIDR, unknown fields, and secret-like field names. Comparison
cross-checks those references against current issue, inventory, domain,
network, and GitOps observations. Text, JSON, and Markdown reports are
available.

## Phase 8 — change planning

**Status:** complete

Planning remains read-only:

```sh
uv run moc-env plan-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

The plan identifies each repository, branch, changed path, operation, reason,
and dependency. It maps comparison differences to `create`, `update`, `delete`,
and `manual_review` operations, derives repository and path targets from
desired-state provenance, and uses one deterministic branch per repository by
default. Text, JSON, and Markdown output are available. Matches and open pull
requests do not become repository-change operations.

For same-repository review sequencing, a later enhancement can support optional
stacked branches:

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
uv run moc-env generate-infra \
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
uv run moc-env validate-plan generated-changes
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
uv run moc-env publish-plan generated-changes \
  --draft \
  --create-prs
```

It pushes local branches and creates draft PRs. It must never approve, merge,
close, reopen, or force-push a PR. Each PR links the MOC issue, desired-state
source, changed files, validation results, and related PRs in dependency order.

## Phase 12 — operational hardening

**Status:** partial

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

The current [user guide](user-guide.md) documents credentials and every
implemented command through Phase 8. Hosted CI exists but currently fails on
Linux because four credential tests assume the macOS Keychain executable.
