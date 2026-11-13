# `moc-env` user guide

`moc-env` is a read-only CLI for understanding the configuration state of MOC
environments from public CCI-MOC GitHub repositories. It answers three distinct
questions:

1. What does the MOC issue request?
2. What is declared in merged repository `main` branches?
3. What exists only in an open pull request?

The tool intentionally does not claim that a cluster is deployed, healthy, or
compliant. It reports repository configuration evidence.

## When to use each command

| Command | Use it to | Reads GitHub | Writes local files | Mutates MOC |
|---|---|---:|---:|---:|
| `moc-env list` | Discover known environment names | Yes | No | No |
| `moc-env ENV` | Inspect one environment's current configuration state | Yes | With `--output` | No |
| `moc-env export-infra ENV` | Create a draft hub-cluster desired-state snapshot | Yes | With `--output` | No |
| `moc-env export-workload ENV WORKLOAD` | Create a draft workload-cluster snapshot | Yes | With `--output` | No |
| `moc-env export-environment ENV` | Create a draft Environment bundle | Yes | With `--output` | No |
| `moc-env validate FILE` | Check a desired-state document locally | No | With `--output` | No |
| `moc-env check-infra FILE` | Compare a hub-cluster document with merged `main` | Yes | With `--output` | No |
| `moc-env check-workload FILE` | Compare a workload document with merged `main` | Yes | With `--output` | No |
| `moc-env check-environment FILE` | Compare an Environment bundle with merged `main` | Yes | With `--output` | No |
| `moc-env plan-infra FILE` | Produce a read-only repository change plan | Yes | With `--output` | No |
| `moc-env refresh-doc-catalog` | Cache local MOC documentation sources | No | Yes, under cache | No |
| `moc-env discover-values` | Reconcile local values with manual documentation | No | With `--output` | No |
| `moc-env document-values` | Generate the chart-values reference | Yes | With `--output` | No |

The Makefile also has gist targets. Those are explicit external actions and
require the `gh` CLI; they are not part of the read-only inspection workflow.

## Prerequisites and setup

Required:

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/) with the committed lockfile;
- Network access to `api.github.com` for environment listing, status, export,
  comparison, planning, and chart-values reference commands;
- Git for development and the local documentation-catalog workflow.

Optional:

- `gh` for the explicit gist targets;
- `pandoc` and `curl` for `tools/md2html.sh`.

Install and verify:

```sh
uv sync
uv run moc-env --help
```

Or use Make:

```sh
make setup
make help
```

The test and packaging gate is:

```sh
make check
```

## Authentication

The CLI can read public GitHub repositories without a token, but GitHub's
unauthenticated REST quota is small. For repeated use, configure a read-only
fine-grained personal access token.

The token needs access to public repositories and these read-only permissions:

- Contents
- Issues
- Pull requests
- Metadata

Do not grant administration, workflow, interaction-limit, or write permissions.

### Resolution order

`moc-env` resolves a GitHub token in this order:

1. `GITHUB_TOKEN`
2. `GITHUB_BWS_SECRET_ID` or `MOC_ENV_BWS_SECRET_ID`
3. A Bitwarden secret UUID in macOS Keychain service
   `moc-env-github-token`
4. `bws secret get <uuid>` using a Bitwarden machine access token

If no credential is configured, the CLI continues unauthenticated. If a
credential source is explicitly selected and fails, the command fails rather
than silently trying another source.

### Direct token

```sh
export GITHUB_TOKEN="github-token"
uv run moc-env bu-ist-demo
```

Never put the token in a command-line argument or commit it to the repository.

### Selector file

Copy the example:

```sh
cp .env.example .env
```

The file may contain non-secret selectors such as:

```dotenv
GITHUB_BWS_SECRET_ID=00000000-0000-0000-0000-000000000000
BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE=example-bws-access-token
```

It must not contain `GITHUB_TOKEN` or `BWS_ACCESS_TOKEN`. Real environment
variables override `.env`.

Use another selector file:

```sh
uv run moc-env bu-ist-demo --env-file /path/to/selectors.env
```

### Bitwarden Secrets Manager

Store a GitHub token in Bitwarden Secrets Manager as a secret whose key is
`GITHUB_TOKEN`. Select it by UUID:

```sh
export GITHUB_BWS_SECRET_ID="00000000-0000-0000-0000-000000000000"
uv run moc-env bu-ist-demo
```

Or:

```sh
uv run moc-env bu-ist-demo \
  --bws-secret-id 00000000-0000-0000-0000-000000000000
```

The UUID is neither the GitHub token nor the Bitwarden machine token.

To store the UUID in macOS Keychain:

```sh
/usr/bin/security add-generic-password -U \
  -a "$(id -un)" \
  -s moc-env-github-token \
  -T /usr/bin/security \
  -w
```

Paste the Bitwarden secret UUID at the prompt.

The Bitwarden machine access token is resolved from `BWS_ACCESS_TOKEN` or macOS
Keychain service `moc-env-bws-access-token`. Create or update that item with:

```sh
/usr/bin/security add-generic-password -U \
  -a "$(id -un)" \
  -s moc-env-bws-access-token \
  -T /usr/bin/security \
  -w
```

Paste the Bitwarden machine access token at the prompt.

## Recommended end-to-end workflow

The normal workflow is: inspect current state, export a draft, review it,
validate it, compare it with merged `main`, and optionally produce a read-only
change plan.

### 1. Discover environments

```sh
uv run moc-env list
uv run moc-env list --format json
```

Use one of the returned environment names, such as `bu-ist-demo`.

### 2. Inspect current repository state

```sh
uv run moc-env bu-ist-demo
```

Useful variants:

```sh
uv run moc-env bu-ist-demo --format json
uv run moc-env bu-ist-demo --format markdown \
  --output reports/bu-ist-demo.md
uv run moc-env bu-ist-demo --issue 666
uv run moc-env bu-ist-demo --no-prs
```

`--no-prs` avoids pull-request API calls. Progress steps are printed to stderr;
the report is printed to stdout or written with `--output`.

### 3. Export draft desired-state documents

Export the hub cluster:

```sh
uv run moc-env export-infra bu-ist-demo \
  --output desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

Export a workload cluster:

```sh
uv run moc-env export-workload bu-ist-demo workload0 \
  --output desired-state/workload-clusters/bu-ist-demo-workload0.yaml
```

Export an Environment bundle that references the hub and workloads:

```sh
uv run moc-env export-environment bu-ist-demo \
  --output desired-state/environments/bu-ist-demo.yaml
```

Exports are drafts for review. They record repository, path, ref, value, and
confidence. They do not establish deployment or health.

In this guide, “export” means extracting a deterministic snapshot from current
repository evidence into a local YAML draft.

### 4. Review and edit the YAML

Open the generated files and review:

- names and parent/child references;
- inventory hosts and boot images;
- domain and machine network;
- chart variables;
- component and application paths;
- provenance and confidence;
- explicit `present: false` or unsupported values.

Keep the source metadata intact when changing a reviewed value. If an item is
unsupported or ambiguous, leave it explicit rather than inventing a value.

### 5. Validate locally

Validate each document:

```sh
uv run moc-env validate \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml

uv run moc-env validate \
  desired-state/workload-clusters/bu-ist-demo-workload0.yaml

uv run moc-env validate \
  desired-state/environments/bu-ist-demo.yaml
```

Validation checks schema, provenance, naming, references, syntax, unknown
fields, and secret-like field names. It is local and does not call GitHub.

Write a Markdown validation report:

```sh
uv run moc-env validate \
  desired-state/environments/bu-ist-demo.yaml \
  --format markdown \
  --output reports/bu-ist-demo-environment-validation.md
```

An invalid document exits with code `2`.

### 6. Compare with merged `main`

Compare each reviewed document:

```sh
uv run moc-env check-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml

uv run moc-env check-workload \
  desired-state/workload-clusters/bu-ist-demo-workload0.yaml

uv run moc-env check-environment \
  desired-state/environments/bu-ist-demo.yaml
```

Write Markdown reports:

```sh
uv run moc-env check-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml \
  --format markdown \
  --output reports/bu-ist-demo-infra-comparison.md

uv run moc-env check-workload \
  desired-state/workload-clusters/bu-ist-demo-workload0.yaml \
  --format markdown \
  --output reports/bu-ist-demo-workload0-comparison.md

uv run moc-env check-environment \
  desired-state/environments/bu-ist-demo.yaml \
  --format markdown \
  --output reports/bu-ist-demo-environment-comparison.md
```

Hard differences exit with code `1`. An open PR by itself exits with code `0`
because it is evidence of work in progress, not a comparison failure.

### 7. Produce a read-only change plan

After the desired state validates, plan the repository changes:

```sh
uv run moc-env plan-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml
```

Write JSON or Markdown:

```sh
uv run moc-env plan-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml \
  --format json

uv run moc-env plan-infra \
  desired-state/infra-clusters/bu-ist-demo-infra.yaml \
  --format markdown \
  --output reports/bu-ist-demo-infra-plan.md
```

The plan maps:

| Comparison result | Planned operation |
|---|---|
| `missing_from_main` | `create` |
| `value_mismatch` | `update` |
| `unexpected_in_main` | `delete` |
| `unsupported_check` or `ambiguous` | `manual_review` |

Each planned operation records repository, base ref, branch, path, field,
operation, desired value, current value, reason, and dependencies. The default
uses one deterministic branch per repository.

`plan-infra` is read-only. It does not create branches, commits, worktrees,
pushes, pull requests, comments, approvals, or merges. A successfully produced
plan exits with code `0`, even when changes are planned. Matches and open PRs
are not converted into repository operations.

## Chart-values documentation workflow

The documentation tools use a local clone of `oac-apps` and a local cache.

### 1. Refresh cached source documents

```sh
uv run moc-env refresh-doc-catalog
```

By default, this expects local repository clones under `../MOC`. Override the
root and cache:

```sh
uv run moc-env refresh-doc-catalog \
  --repository-root /path/to/MOC \
  --cache-root .cache/doc-catalog
```

The command records repository HEADs, content hashes, cached documents, and
extracts under `.cache/doc-catalog/`. It reads local Git clones and does not
fetch or mutate them.

### 2. Reconcile discovered values

```sh
uv run moc-env discover-values \
  --repository-root /path/to/MOC
```

The report identifies:

- variables that need manual definitions;
- manual entries with no current repository occurrence;
- changed or missing evidence;
- default conflicts;
- unsupported YAML files.

Write a report:

```sh
uv run moc-env discover-values \
  --output reports/chart-values-discovery.md
```

### 3. Add or review manual definitions

Manual definitions live in `docs/variables/*.yaml`. A definition provides the
reviewed explanation, topic, default, relationships, warnings, and source IDs.
Sources are registered in `docs/sources.yaml`.

Discovery never edits manual definitions.

### 4. Generate the reference

```sh
uv run moc-env document-values \
  --output reports/chart-values.md
```

Optionally render a standalone HTML page:

```sh
tools/md2html.sh \
  reports/chart-values.md \
  reports/chart-values.html \
  "Chart Configuration Reference"
```

The HTML helper requires `pandoc` and `curl`. It downloads the GitHub Markdown
stylesheet once into `.cache/github-markdown.css`.

## Make targets

Common targets:

```sh
make setup
make test
make check
make list
make run ENV=bu-ist-demo
make run-json ENV=bu-ist-demo
make run-no-prs ENV=bu-ist-demo
make report-markdown ENV=bu-ist-demo
```

Desired-state targets:

```sh
make export-infra ENV=bu-ist-demo
make export-workload ENV=bu-ist-demo WORKLOAD=workload0
make validate ENV=bu-ist-demo
make validate-markdown ENV=bu-ist-demo
make check-infra ENV=bu-ist-demo
make check-infra-markdown ENV=bu-ist-demo
make plan-infra ENV=bu-ist-demo
make plan-infra-markdown ENV=bu-ist-demo
make check-workload ENV=bu-ist-demo WORKLOAD=workload0
make check-workload-markdown ENV=bu-ist-demo WORKLOAD=workload0
```

`NO_PRS=1` adds `--no-prs` to the `make run`, `make run-json`, and
`make run-markdown` status targets. For check or plan targets, pass
`ARGS="--no-prs"` explicitly.

## Output and exit codes

Most commands support `--format` and `--output`:

- status reports: text, JSON, Markdown;
- validation reports: text, JSON, Markdown;
- comparison reports: text, JSON, Markdown;
- change plans: text, JSON, Markdown;
- documentation refresh: text, JSON;
- discovery reports: text, JSON, Markdown;
- exports: YAML.

Exit codes:

| Result | Code |
|---|---:|
| Successful report, export, validation, comparison without hard differences, or plan | `0` |
| Hard desired-state comparison difference | `1` |
| Invalid input, GitHub failure, parse failure, or output-file failure | `2` |

Missing configuration in a status report does not cause a non-zero exit. This is
a reporting tool, not a deployment gate.

## Files and directories

| Path | Purpose |
|---|---|
| `desired-state/infra-clusters/` | Reviewed hub-cluster YAML documents |
| `desired-state/workload-clusters/` | Reviewed workload-cluster YAML documents |
| `desired-state/environments/` | Reviewed Environment bundles |
| `reports/` | Generated Markdown, JSON, HTML, and comparison artifacts |
| `docs/variables/` | Manual chart-value definitions |
| `docs/sources.yaml` | Registered documentation sources and stable source IDs |
| `.cache/doc-catalog/` | Local documentation catalog, extracts, and values cache |
| `.cache/github-markdown.css` | Downloaded stylesheet used by `tools/md2html.sh` |
| `tools/md2html.sh` | Standalone HTML renderer for the chart-values guide |

Generated files under `reports/` are artifacts for review. They are not proof
of deployment or health.

## State meanings

| State | Meaning |
|---|---|
| `requested` | The MOC issue exists and records the request |
| `missing` | No relevant configuration was found |
| `partial` | Some information exists, but required details are absent or generic |
| `pr_open` | Relevant configuration exists only in an open pull request |
| `pr_merged` | A relevant pull request has been merged |
| `declared_in_main` | Relevant configuration is present in a merged `main` branch |

Desired-state comparisons also use:

| State | Meaning |
|---|---|
| `matches_main` | Reviewed desired value matches merged `main` |
| `missing_from_main` | Desired value is absent from merged `main` |
| `value_mismatch` | Desired and current values differ |
| `unexpected_in_main` | Current repository has a value the desired state omits |
| `unsupported_check` | Desired or observed value is not supported |
| `ambiguous` | Current evidence supports more than one value |

Open pull requests are not treated as merged desired state.

## Troubleshooting

### GitHub rate limits

Use `GITHUB_TOKEN` or the Bitwarden selector workflow. The CLI reports the
GitHub API error and exits with code `2`.

### No known issue number

If the environment is not built into the known-issue map, pass it explicitly:

```sh
uv run moc-env example-env --issue 123
```

### Pull-request calls are too expensive

Use `--no-prs` for status, comparison, or planning commands when PR state is
not required.

### Local documentation repository not found

`refresh-doc-catalog` and `discover-values` expect local clones under `../MOC`
by default. Pass `--repository-root /path/to/MOC`.

### Desired-state validation fails

Read the validation report. Common causes are naming mismatches, missing
provenance, duplicate keys, invalid IP/CIDR values, unsupported required values,
and secret-like field names.

### Comparison reports differences

Inspect desired and current values in the report. An open PR is reported
separately and is not treated as a hard difference by itself.

### Planning cannot determine provenance

`plan-infra` derives repository and path from desired-state provenance. Keep
source metadata intact when editing exported YAML.

### Hosted CI currently fails on Linux

The GitHub Actions `Check` workflow uses Ubuntu. Four current credential tests
assume the macOS `/usr/bin/security` executable and therefore fail with
`macOS Keychain utility is unavailable`. The full suite and `make check` pass on
macOS. The pending fix is to make those tests platform-independent or inject
the Keychain executable path.

## Safety boundaries

Current commands do not:

- mutate MOC repositories;
- create branches, commits, worktrees, or pull requests;
- approve, merge, close, comment on, or force-push a PR;
- connect to a live OpenShift or Argo CD cluster;
- claim deployment, health, or compliance.

The only external publishing actions are the explicit `make report-gist-*`
targets, which use `gh` and require deliberate invocation.
