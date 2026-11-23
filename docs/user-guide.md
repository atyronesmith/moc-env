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
| `moc-env list` | Discover hub and workload clusters | Yes | User cache | No |
| `moc-env status` | Show the fleet view of hub and workload clusters | Yes | User cache | No |
| `moc-env completion bash` | Print a Bash completion script | No | No | No |
| `moc-env completion zsh` | Print a Zsh completion script | No | No | No |
| `moc-env status ENV` | Inspect one environment's current configuration state | Yes | With `--output` | No |
| `moc-env status-hub ENV` | Inspect one environment's hub-cluster state | Yes | With `--output` | No |
| `moc-env status-workload ENV` | Inspect one environment's workload-cluster state | Yes | With `--output` | No |
| `moc-env charts` | Show chart groups, feature labels, per-cluster received charts, per-cluster value overrides, or a chart reference | Yes | With `--output` | No |
| `moc-env diff ENV_A ENV_B` | Compare two environments' repository structure | Yes | With `--output` | No |
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
  comparison, planning, chart inventory, and chart-values reference commands;
- Git for development and the local documentation-catalog workflow.

Optional:

- `gh` for the explicit gist targets;
- `pandoc` and `curl` for `tools/md2html.sh`.

Install and verify:

```sh
uv sync
uv run moc-env --help
```

Running `moc-env` with no arguments prints the same command catalog.

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
fine-grained personal access token or log in with GitHub CLI. When no token is
used, moc-env prints one warning with the remaining request quota after GitHub
supplies that header. Pass `--no-auth` to force unauthenticated access.
File contents are downloaded from `raw.githubusercontent.com` at the resolved
commit SHA, so they do not consume REST quota. The CLI reserves enough REST
quota for repository trees before starting, skips pull-request discovery when
unauthenticated, and stops without spending calls if the quota is too small.
If unauthenticated quota is already exhausted but the repository trees are
cached, the cached snapshots are used so a read-only report can still complete.

GitHub server errors (`5xx`) and connection failures are retried three times
with increasing delays. Pull-request lookup is optional: if it still fails,
the status report prints `Pull requests: unavailable (<reason>)` and continues
with the configuration checks. With the default `--fail-on never`, that report
exits `0`; a missing PR listing is not a configuration failure.

### GitHub response cache

GitHub-reading commands cache response bodies and ETags by URL under the
user-local cache directory, in `moc-env/github-responses.json`. Later requests
send `If-None-Match`; GitHub's uncounted `304 Not Modified` response serves the
cached body. Within one process, the same URL is never requested twice. The
cache never stores an Authorization header or token.

Raw file content pinned to a full 40-character commit SHA and a Git tree
pinned to a full commit SHA cannot change. When either has a cache entry, the
body is served from disk with no HTTP request at all. A branch name, tag,
short SHA, or pull-request ref in the SHA position is mutable and is
revalidated as usual, as is `/repos/<repo>/commits/<ref>`, so a new commit on
`main` is still seen.

Pass `--offline` to serve only cached responses; a miss fails clearly with exit
code `2`. Pass `--refresh` to ignore the disk cache and request current data;
per-process request deduplication still applies. These options are mutually
exclusive.

When any response is served from disk cache without revalidation, the report
header identifies the repository with `from cache, fetched <time>`. The time
is the original fetch time, not the report-generation time; if several cached
responses from a repository are used, the oldest fetch time is shown. A
successfully revalidated `304` response does not trigger this stale-cache
notice. Older cache entries without a recorded fetch time say `unknown`.

Every command that creates a GitHub client ends on stderr with an accounting
line in this form:

```text
GitHub API: <n> requests, <m> counted against quota, <k> from cache
```

`requests` counts HTTP attempts to both `api.github.com` and
`raw.githubusercontent.com`, including raw-file downloads. `counted against
quota` counts only non-`304` GitHub REST API responses; the `/rate_limit`
preflight is free, and immutable-SHA raw downloads do not consume REST quota.
`from cache` counts response bodies served from the local cache, including
offline reads, SHA-pinned disk hits, and successful `304` revalidation.
Commands that do not create a GitHub client, such as completion when its
environment cache is already warm, do not print this line. With `--verbose`,
the command also lists each endpoint that was counted against quota.

For a reproducible measurement, on 2026-11-17 an authenticated run was made
with an isolated response cache. The counts below are observations for those
repository snapshots, not a fixed request budget:

| Command and mode | HTTP requests | Counted against quota | From cache |
|---|---:|---:|---:|
| `status oac-prod --no-prs` (cold) | 36 | 14 | 0 |
| `status oac-prod --no-prs` (warm) | 36 | 0 | 35 |
| `diff oac-prod bu-ist-demo` (cold) | 123 | 17 | 0 |
| `diff oac-prod bu-ist-demo` (warm) | 123 | 0 | 123 |
| `diff oac-prod bu-ist-demo --offline` | 0 | 0 | 123 |

The warm status run's one non-cached request was the free `/rate_limit`
preflight; `diff` does not make that preflight. Offline mode performs no
credential lookup or quota preflight and fails with code `2` on any cache miss.
Use the final accounting line, rather than an old rule-of-thumb quota estimate,
when planning a run.

The token needs access to public repositories and these read-only permissions:

- Contents
- Issues
- Pull requests
- Metadata

Do not grant administration, workflow, interaction-limit, or write permissions.

### Resolution order

`moc-env` resolves a GitHub token in this order:

1. `GITHUB_TOKEN`
2. An explicitly configured Bitwarden selector
3. `gh auth token` when GitHub CLI is installed and logged in
4. The default Bitwarden secret UUID item in macOS Keychain service
   `moc-env-github-token`
5. Unauthenticated access

Unavailable optional steps are skipped silently. If a direct token or explicitly
selected Bitwarden source fails, the command fails rather than silently trying
another source.

### Direct token

```sh
export GITHUB_TOKEN="github-token"
uv run moc-env status bu-ist-demo
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
uv run moc-env status bu-ist-demo --env-file /path/to/selectors.env
```

### Bitwarden Secrets Manager

Store a GitHub token in Bitwarden Secrets Manager as a secret whose key is
`GITHUB_TOKEN`. Select it by UUID:

```sh
export GITHUB_BWS_SECRET_ID="00000000-0000-0000-0000-000000000000"
uv run moc-env status bu-ist-demo
```

Or:

```sh
uv run moc-env status bu-ist-demo \
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

### 1. Discover environment clusters

```sh
uv run moc-env list
uv run moc-env list --format json
```

The output includes one row for each hub and workload cluster. Each row records
the environment base name, full cluster name, `hub` or `workload` type, source
path, and environment-level status command.

Use the environment base name from the `environment` field, such as
`bu-ist-demo`. Each row's `status_command` selects the matching scoped command:
`moc-env status-hub ENV` for a hub row and `moc-env status-workload ENV` for a
workload row. Use `moc-env status ENV` for the environment-level report that
includes both scopes.

### 2. Inspect current repository state

List the fleet first:

```sh
uv run moc-env status
```

Then inspect one environment:

```sh
uv run moc-env status bu-ist-demo
```

Useful variants:

```sh
uv run moc-env status bu-ist-demo --format json
uv run moc-env status bu-ist-demo --format markdown \
  --output reports/bu-ist-demo.md
uv run moc-env status bu-ist-demo --issue 666
uv run moc-env status bu-ist-demo --no-prs
uv run moc-env status bu-ist-demo --prs
uv run moc-env status bu-ist-demo --details
uv run moc-env status bu-ist-demo --fail-on blocking
```

For the four supported Terraform gaps (hub hosted-secret prefixes, workload
moc-aws OIDC and cert-manager entries, and workload Keycloak clients), next
actions include suggested HCL copied from the observed upstream file. Text shows
the code with `--details`; Markdown always includes it; JSON exposes `suggestion`
or a null suggestion with `suggestion_skipped_reason`. Locations link to the
commit in Sources. Suggestions are replayed against the same check in memory
before display, but are not applied and no Terraform plan is run. An incomplete
open PR is identified when the suggestion corrects its block. moc-env never
writes to another repository or opens a PR.

Run a hub-scoped report:

```sh
uv run moc-env status-hub bu-ist-demo
```

Run a workload-scoped report:

```sh
uv run moc-env status-workload bu-ist-demo
```

Compare two environments:

```sh
uv run moc-env diff bu-ist-demo oac-prod
```

`--no-prs` avoids pull-request API calls. When unauthenticated, pull-request
discovery is also skipped by default to preserve REST quota; `--prs` forces it.
`--details` appends the full check ledger after the summary. `--fail-on` controls the status exit code: `never`
(the default) always returns `0` after a successful report, `blocking` returns
`1` when any blocking gap exists, and `advisory` returns `1` when any advisory
or blocking gap exists. Progress steps are printed to stderr; the report is
printed to stdout or written with `--output`.

When a command accepts both `--format` and `--output`, an omitted `--format`
is inferred from the output file extension: `.md` and `.markdown` mean
Markdown, `.json` means JSON, and `.txt` means text. Other extensions keep the
command's usual default. If the extension names a format the command does not
support, moc-env keeps the default and prints a warning naming the file. An
explicit `--format` always wins.

### Chart inventory and reference

`moc-env charts` reads every chart placement, feature label, and values file it
can determine from `oac-apps`. It has five views:

| View | Command | Contents |
|---|---|---|
| `summary` (default) | `moc-env charts` | Workload and hub matrices, feature and group chart lists, and charts not deployed by GitOps |
| `cluster` | `moc-env charts --view cluster ENV` | One section per cluster with its ApplicationSet, placement, feature label, values files, and unmet required values |
| `overrides` | `moc-env charts --view overrides ENV` | One section per cluster with only the chart values that differ from the chart defaults, plus counts of restated values |
| `reference` | `moc-env charts --view reference` | Hub and workload chart groups, optional features with their labels, and one values table per deployed chart |
| `page` | `moc-env charts --view page` | One Markdown page combining the summary tables, the per-cluster changed and added values, and the per-chart values reference |

Limit the inventory to one environment or workload:

```sh
uv run moc-env charts bu-ist-demo
uv run moc-env charts bu-ist-demo --workload workload0 --view cluster
uv run moc-env charts bu-ist-demo --workload workload0 --view overrides
```

With no environment, `moc-env charts` covers deployment clusters only. The
deployment hubs are configured in `src/moc_env/data/environments.yaml`:

```yaml
cluster_scope:
  deployment_hub_patterns:
    - "compliant-*"
    - "oac-*"
```

Hubs whose names match a pattern are deployment hubs, and a workload cluster
takes the class of its hub. The summary and cluster views name any test
clusters they left out. Pass `--all-clusters` to include every hub and
workload cluster, or name an environment to show that environment whatever its
class. `--all-clusters` ends the view with a line naming the test clusters it
showed.

The summary view prints `x` marks in the cluster matrices and lists the charts
each feature, hub group, or add-on installs. "Charts not deployed by GitOps"
lists whole-repository charts that no ApplicationSet or drop-in installs; the
library section lists dependency-only charts. These are repository facts, not
live cluster state.

Generate the Markdown reference and optionally restrict only its chart tables:

```sh
uv run moc-env charts --view reference \
  --output reports/chart-reference.md
uv run moc-env charts --view reference \
  --chart hcp-config --chart hosted-ingress --chart metallb \
  --output reports/chart-reference-sample.md
```

`--chart` is repeatable. In the reference view it limits the Chart reference
entries; the hub, workload, feature, baseline, and drop-in lists still describe
the full repository. A filtered reference report states `Showing N of M
deployed charts (filtered with --chart)`, and its footer separates those
omitted by the filter from undeployed and library charts. In the overrides
view, `--chart` limits the charts compared for each cluster.

The overrides view takes each chart's value files from the manifest that
deploys it: the `valueFiles` entries in hub and managed ApplicationSet
templates, and the `spec.source.helm.valueFiles` entries in hub drop-ins under
`apps/<hub>/`. It compares those layers with the chart's own `values.yaml` and
reports only changed and added keys, plus a count of keys restated at their
defaults. A drop-in is identified by `spec.source.path` (`charts/<name>`), not
by its file name.

Charts are not compared when their value files resolve outside `values/`, when
an entry cannot be resolved from its template, when a template has no
`valueFiles` entries, or when a drop-in is not an Application with a `charts/`
source path. The text and Markdown reports give that reason beside each chart;
JSON reports it as `{"chart", "reason"}`. This view does not cover Helm
parameters set inside an ApplicationSet, defaults supplied by a chart
dependency, kustomize applications, or the hosted-cluster chart itself.

Reference output is deterministic. The header includes a `Generated by:` code
block with the normalized `moc-env` command and shell-quoted arguments, so the
report can be reproduced without recording a timestamp. Use repeatable
`--ref REPO=REF` options, for example `--ref oac-apps=pull/246/head`, to read a
non-default ref; the footer records the resolved commit.

The page view produces a single Markdown document a reader can generate on
demand. It has YAML front matter with the title `oac-apps charts and values by
cluster`, no level-one heading, and four sections: which clusters get which
charts, the values set for each cluster, the chart values reference, and the
page's coverage limits. Values and file paths are code spans so typographic
Markdown processing keeps them literal, and every chart link targets exactly
one chart heading. If any value contains Liquid syntax (`{{` or `{%`), the page
wraps its body in `{% raw %}` and `{% endraw %}` tags.

`--view page` supports Markdown only: omitting `--format` renders Markdown and
`--format markdown` is accepted, while `--format text` and `--format json` stop
with an error. `--chart` and `--workload` are also rejected because the page
always describes the selected deployment clusters in full. Cluster selection
is the same as for the other views, including `--all-clusters` and a named
environment, and `--output page.md` writes the page to a file. The page records
the resolved commit instead of a generation date, so the same `oac-apps` commit
and arguments produce identical bytes.

Each chart table uses the chart's own `values.yaml`:

- `Key` is the dotted setting path.
- `Default` is the declared default; `(section)` marks a mapping with child
  rows, and `(commented out)` marks a commented-out key block.
- `Required` is `yes` for an unconditional Helm `required` call, or
  `conditional (when ...)` when the enclosing `if`, `with`, or `range`
  expression is known.
- `Description` is the comment beside the key. Blank means upstream has no
  comment, not that the setting is unimportant.

Blocks following a key are rendered as `Example for <key>`. A comment block
that parses as YAML with a single top-level key absent from `values.yaml` is
treated as a commented-out key: it receives a table row with the default
`(commented out)` and is rendered as an example. Comments that are not key
examples remain under `Other comments in values.yaml`. Text inside fenced code
blocks is not rewritten.

In Markdown, repository text is HTML-escaped outside code spans, path
placeholders are code-spanned, and the tables use backticked keys and defaults.
The hub section defines the ApplicationSet arrow and explains that per-hub
drop-ins are Applications checked in under `apps/<hub>/`.

After writing a reference report, moc-env prints a warning to stderr for every
required or conditional key whose `Description` is blank, grouped by chart and
limited to the charts shown. These are upstream documentation gaps; the
generator does not invent descriptions.

The reference defaults to Markdown. The summary, cluster, and overrides views
default to text. All four views support `--format text`, `--format markdown`,
and `--format json`.

## Reading a status report

The example below is the current text renderer's output for the synthetic
`example-env` fixture. Run `make sample-reports` to regenerate it as
`docs/samples/example-env.txt`. Every generated sample starts with a banner
that identifies it as synthetic.

```text
example-env · hub + workload · repo config as of 2026-11-16 12:34 UTC

RESULT: 8 blocking gaps (workload 3) · 0 advisories · 15 of 28 checks pass
5 checks blocked by action 7
Pull requests: skipped (--no-prs)


HUB PHASES
PHASE                        HUB example-env-infra
1 Host inventory entry       ✅ 1/1 checks
2 Hub image inventory and…   ✅ 3/3 checks
3 Discovery image reference  🟡 0/1 checks
4 Keycloak OIDC client       ✅ 1/1 checks
5 GitOps values and apps     ❌ 4/8 checks

WORKLOAD PHASES
PHASE                        WORKLOAD example-env-workload0
1 Host inventory entry       ✅ 1/1 checks
2 Hub agent discovery ISO    🟡 0/1 checks
3 Agent ISO boot             verify by hand
4 Agent visibility           verify by hand
5 Agent labels and approval  ✅ 1/1 checks
6 oac-apps values            ❌ 0/7 checks, 5 blocked
7 Shared-service…            ✅ 3/3 checks

NEXT
  1. [oac-infra] Generate and publish a hub-specific discovery ISO, then replace the generic
  boot_image_url for every host in the hub cluster group. boot_image_url is
  http://10.2.0.82/boot/discovery.iso; expected cluster_specific_image
  example-env-infra-agent-discovery.iso.
       guide: docs/infra-cluster-deployment.md → Cluster Deployment
  2. [oac-apps] Create or complete the hub hosted-cluster defaults file at
  hosted-clusters/example-env-infra/values.yaml in CCI-MOC/oac-infra.
  hosted-clusters/example-env-infra/values.yaml is missing; expected present. (after 1)
       guide: docs/infra-cluster-deployment.md → Cluster Configuration
  3. [oac-apps] Copy the required local-cluster component files from an existing hub environment
  and adjust cluster-specific names and addresses.
  values/example-env-infra/local-cluster/acm.yaml is missing; expected present.
  values/example-env-infra/local-cluster/acm-placements.yaml is missing; expected present.
  values/example-env-infra/local-cluster/cert-manager.yaml is missing; expected present.
  values/example-env-infra/local-cluster/cluster-certificates.yaml is missing; expected present.
  values/example-env-infra/local-cluster/cluster-version.yaml is missing; expected present.
  values/example-env-infra/local-cluster/external-dns-operator.yaml is missing; expected
  present. values/example-env-infra/local-cluster/external-secrets.yaml is missing; expected
  present. values/example-env-infra/local-cluster/hcp-config.yaml is missing; expected present.
  values/example-env-infra/local-cluster/keycloak-oauth.yaml is missing; expected present.
  values/example-env-infra/local-cluster/metallb.yaml is missing; expected present.
  values/example-env-infra/local-cluster/openshift-gitops.yaml is missing; expected present.
  values/example-env-infra/local-cluster/portworx.yaml is missing; expected present.
  values/example-env-infra/local-cluster/user-workload-monitoring.yaml is missing; expected
  present. (after 2)
       guide: docs/infra-cluster-deployment.md → Cluster Configuration
  4. [oac-apps] Create or complete values/example-env-infra/hcp-config.yaml in CCI-MOC/oac-infra
  for hub-wide HCP and secret-selector values. values/example-env-infra/hcp-config.yaml is
  missing; expected present. (after 2)
       guide: docs/infra-cluster-deployment.md → Cluster Configuration
  5. [oac-apps] Add Argo CD application manifests for the hub after its hosted-cluster, hub-wide
  component, and local-cluster values are present, and reference the correct clusters.
  apps/example-env-infra/keycloak-oauth.yaml is missing; expected present. (after 2, 4, 3)
       guide: docs/infra-cluster-deployment.md → Cluster Configuration
  6. [oac-infra] Generate and publish the parent hub's agent discovery ISO, then replace the
  generic boot_image_url for every host in the workload cluster group. boot_image_url is
  http://10.2.0.82/boot/discovery.iso; expected cluster_specific_image
  example-env-infra-agent-discovery.iso. (after 1)
       guide: docs/workload-cluster-deployment.md → Infrastructure Configuration
  7. [oac-apps] Create the missing hosted-cluster values file from the closest existing
  environment; set the cluster name, parent hub, networking, and node pools before adding
  components. hosted-clusters/example-env-infra/example-env-workload0/values.yaml is missing;
  expected present. (after 2)
       guide: docs/workload-cluster-deployment.md → Cluster Deployment and Configuration
  8. [oac-apps] Create the workload component-values directory, starting with hcp-config.yaml
  and only the shared components this workload needs. matched_file_count is 0; expected At least
  one matching path. (after 7)
       guide: docs/workload-cluster-deployment.md → Cluster Deployment and Configuration

NOT CHECKED — verify by hand:
  Configure cluster and storage networks and firewalls for example-env-infra; Store the
  example-env-infra SSH key and kubeadmin credentials in AWS Secrets Manager; Place the pull
  secret and SSH key under hub-images/credentials/example-env-infra; Run
  create_agent_install_media and copy the example-env-infra ISO to the bastion host; Bootstrap
  Argo CD for example-env-infra; Agents visible in hardware-inventory; Agents labelled and
  approved

Sources
Repository                 Ref      Commit
CCI-MOC/ansible-switches    main     8888888
CCI-MOC/everpure-moc        main     5555555
CCI-MOC/moc-aws             main     6666666
CCI-MOC/moc-dns             main     7777777
CCI-MOC/moc-keycloak        main     4444444
CCI-MOC/oac-apps            main     3333333
CCI-MOC/oac-infra           main     2222222

Details:  moc-env status example-env --details
Markdown: moc-env status example-env --format markdown --output report.md
```

The first line identifies the environment, report scope, and the UTC minute at
which repository state was read. The `Sources` table at the end records each
repository ref and SHA. Treat the report as evidence at those snapshots, not as
continuously monitored state.

`RESULT` is the first answer: how many blocking gaps exist, how many are
advisory, and how many checks pass. For an environment report, the parenthetical
workload count shows how many blocking gaps belong to workload scopes. An
`UNKNOWN` line names at most two checks whose evidence was absent or could not
be normalized, then reports how many more exist. `N checks blocked by action K`
points to the numbered action that must be completed before dependent checks
can run; blocked checks are not unknown and are not counted as gaps.

Pull requests are context, not a check. They do not affect pass/gap counts,
severity, or next actions; the pull-request section states how many open PRs
touch the environment and lists them separately. If lookup is skipped or
unavailable, only the corresponding `Pull requests: ...` line is printed, not
an unverified `0 open PRs` count.

When PR inspection is enabled, changed-file overlap only selects a PR as a
candidate. For each candidate, `moc-env` replays the relevant check at
`pull/<number>/head` and compares its normalized expected/observed fields:

- `fixed by open PR oac-apps#246` means the replay changed the check to a
  passing state;
- `open PR oac-apps#246 touches this but the check still fails there: ...`
  means the replay still has the listed failing fields.

An overlapping file alone never produces a “fixed” annotation. A PR whose head
is already the selected source through `--ref REPO=REF` is excluded from
self-annotation. These annotations are review evidence only: they do not alter
the report's pass/gap counts and do not claim that a PR was merged or that a
live cluster changed. PR heads are mutable, so record the resolved SHA when a
review result matters.

For example, on 2026-11-17 `oac-apps` `pull/246/head` had advanced to
`071b4677139a893845ffa2ee70e81aad561db32b`, a child of
`625765a730e30a689f3e7e78886b7877f05bc9c8`, and the newer head fixed four
address/DNS issues present in the earlier snapshot. An authenticated live-head
`status bu-ist-demo --ref oac-apps=pull/246/head --prs --details` run reported 5
blocking and 2 advisory gaps; the explicitly pinned
`--ref oac-apps=625765a730e30a689f3e7e78886b7877f05bc9c8` run reported 9
blocking and 2 advisory gaps. Treat these as snapshot-specific observations;
do not present the pinned 9/2 result as the current live result.

Hub and workload phases are rendered as separate tables so each scope keeps its
own numbering and titles. Each cell counts every check in that phase as
`passing/total checks`; unknown and blocked counts are shown separately. The
worst known state sets the symbol, but unknown checks never hide the passes.
`verify by hand` identifies a phase whose steps cannot be verified from the
repositories.

`NEXT` is the work list. Actions are sorted topologically so no action appears
before one it depends on; within that order, hub actions precede workload
actions and blocking actions precede advisories. `(after N)` records an
explicit dependency, and Markdown guide links point to the upstream
documentation section. Each action includes the check's observed and expected
values; advisory actions are marked `(advisory)`. For example, a copied API
address names both the observed address and the hub machine network it must
be inside. Duplicate-address actions list the conflicting addresses and the
other clusters using them. The list contains repository actions only.

`NOT CHECKED` names required deployment steps that cannot be proven from the
public repositories, such as live cluster state and credentials stored outside
Git. The final lines give the commands for full details and a Markdown file.
Use `--details` when you need one row per field with separate expected and
observed columns, source paths, and reasons. Source lines include the commit
SHA and actual ref read; URLs use that ref, including `--ref` overrides.

### Workload value checks

`workload.dns_base_domain` checks every explicit `dns.records` hostname against
`baseDomain` or `hcpExternalDomain` from
`hosted-clusters/<hub>/values.yaml`. It does not use the hub-image
`base_domain`. For `bu-ist-demo`, the hosted domain is
`hcp.bu-ist-demo.int.massopen.cloud`; a copied hostname such as
`s3.bu-ist-demo-workload0.hcp.oac.int.massopen.cloud` is a blocking gap.

`workload.gpu_without_hosts` reads
`clusterLabels["massopen.cloud/feature-gpu"]`. A value of `"true"` with no GPU
hosts in that workload's inventory produces an advisory gap, not a blocking
gap. A top-level `feature-gpu` value is not the cluster label.
GPU inventory evidence includes an explicit `gpu: true` flag or GPU/A100/H100
resource-class or flavor descriptors, including node resource classes recorded
in the upstream hardware documentation. Hosts from another cluster do not
satisfy the check.

`workload.ingress_address_network` selects the workload VLAN by its full
environment/workload name, not a generic `WORKLOAD` or `PRODUCTION` substring.
The `BU-IST-DEMO-WORKLOAD` VLAN supplies `10.20.28.0/23`; documented naming
variants such as `OAC-PRODUCTION-WORKLOAD0` are also recognized. If no VLAN
matches, the report says so and checks only that the ingress address is
outside the hub machine network.

### 3. Enable shell completion

`moc-env list` writes its cluster results to a user-local cache outside the
repository. The default location follows XDG:

```text
${XDG_CACHE_HOME:-$HOME/.cache}/moc-env/environment-clusters.json
```

Shell completion reads that cache. If the cache is empty, the first
environment-name completion refreshes it from GitHub; later Tab presses use the
local cache and do not call GitHub. Run `moc-env list` again when you want to
refresh it explicitly.

Set `MOC_ENV_CACHE_DIR` to use a different cache directory.

Bash:

```sh
make completion-init
```

Zsh:

```sh
make completion-init
```

`completion-init` detects the shell from `SHELL`, appends an idempotent
completion block to `~/.bashrc` or `~/.zshrc`, adds this checkout's `.venv/bin`
to `PATH`, and registers completion for `moc-env`. Run `source ~/.bashrc` or
`source ~/.zshrc` (or start a new shell) after initialization.

For a non-default startup file, run
`make completion-init COMPLETION_RC=/path/to/rc-file`. The managed block sets
`MOC_ENV_COMPLETION_COMMAND` and `PATH` to this checkout's virtual environment,
so both the command and completion work outside the repository directory. If
completion returns nothing, check network access or run `moc-env list` to see
the GitHub error directly.

Use `moc-env` rather than `uv run moc-env` after initialization. Shell
completion is attached to the command name `moc-env`; with
`uv run moc-env`, the shell asks `uv` for completion instead.

Completion supplies top-level command names and follows each command's parser
definition. Tab offers environment names wherever a command accepts one,
including both arguments of `diff`, the optional environment of the `status`
commands, and the environment arguments of the `export-*` commands. It also
supplies workload-cluster names for `export-workload` and the
`status-workload --workload` option. After a command name, Tab also offers that
command's options, taken from the same parser that renders `--help`; options
with a fixed choice list, such as `--format`, complete their values as well.
File-valued arguments such as `--output`, `--env-file`, `--repository-root`,
and `--cache-root` use normal filesystem completion, as do the YAML path
arguments of `validate`, `check-infra`, `check-workload`,
`check-environment`, and `plan-infra`.

### 4. Export draft desired-state documents

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

### 5. Review and edit the YAML

Open the generated files and review:

- names and parent/child references;
- inventory hosts and boot images;
- non-OpenStack host `mac_addr` and `resource_class` inputs used by
  `infra/update-agents.yaml`;
- `resource_class` values against `docs/hardware-and-network-configuration.md`
  when the host's node name appears in that document's resource-class table;
- domain and machine network;
- chart variables;
- component and application paths;
- provenance and confidence;
- explicit `present: false` or unsupported values.

Keep the source metadata intact when changing a reviewed value. If an item is
unsupported or ambiguous, leave it explicit rather than inventing a value.

### 6. Validate locally

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

### 7. Compare with merged `main`

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

### 8. Produce a read-only change plan

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

This workflow generates the broader, topic-first values guide from manual
definitions plus discovery. For the per-chart tables built directly from each
chart's `values.yaml`, use `moc-env charts --view reference` described in
[Chart inventory and reference](#chart-inventory-and-reference). The
documentation tools here use a local clone of `oac-apps` and a local cache.

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
make sample-reports
```

Desired-state targets:

```sh
make export-infra-file ENV=bu-ist-demo \
  OUTPUT=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make export-workload-file ENV=bu-ist-demo WORKLOAD=workload0 \
  OUTPUT=desired-state/workload-clusters/bu-ist-demo-workload0.yaml
make validate FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make validate-markdown FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make check-infra FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make check-infra-markdown FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make plan-infra FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make plan-infra-markdown FILE=desired-state/infra-clusters/bu-ist-demo-infra.yaml
make check-workload FILE=desired-state/workload-clusters/bu-ist-demo-workload0.yaml
make check-workload-markdown FILE=desired-state/workload-clusters/bu-ist-demo-workload0.yaml
```

`NO_PRS=1` adds `--no-prs` to the `make run`, `make run-json`, and
`make run-markdown` status targets. For check or plan targets, pass
`ARGS="--no-prs"` explicitly.

`make sample-reports` regenerates the offline `example-env` status, export,
validation, comparison, plan, and chart-values samples under `docs/samples/`
with synthetic fixtures and a fixed clock. It does not call GitHub.

## Output and exit codes

Most commands support `--format` and `--output`:

- fleet status and environment lists: text, JSON;
- environment status reports: text, JSON, Markdown;
- validation reports: text, JSON, Markdown;
- comparison reports: text, JSON, Markdown;
- change plans: text, JSON, Markdown;
- documentation refresh: text, JSON;
- discovery reports: text, JSON, Markdown;
- chart inventory and reference: text, JSON, Markdown (reference defaults to Markdown);
- chart-values reference: Markdown;
- exports: YAML.

Status-specific options:

| Option | Effect |
|---|---|
| `--details` | Appends the full per-check ledger to the text report |
| `--fail-on never` | Returns `0` after a successful report, even with gaps (default) |
| `--fail-on blocking` | Returns `1` when any check has `blocking` severity |
| `--fail-on advisory` | Returns `1` when any check has `advisory` or `blocking` severity |

`moc-env diff ENV_A ENV_B` always exits `0` after successfully rendering a
comparison. It reports checks, files, components, and structural facts; it does
not compare addresses, cluster-specific names, or MAC addresses.

To compare a reference environment on `main` with proposed changes for the
second environment, pass repeatable `--ref REPO=REF` overrides:

```sh
moc-env diff oac-prod bu-ist-demo --ref oac-apps=pull/246/head \
  --format markdown --output reports/oac-prod-vs-bu-ist-demo-pr246.md
```

These overrides apply only to `ENV_B`; `ENV_A` remains on `main`. The Markdown
report records the refs and commit snapshots for each environment separately.
It compares repository configuration, not live cluster health; differences
can reflect legitimate environment-specific choices rather than defects.

File paths are normalized before comparison: hub names become `<hub>` and
workload names become `<workload>`. Equivalent environment-specific layouts
therefore do not appear as differences. Remaining file differences are printed
one path per line. Structural values use plain text, for example
`bmc 3, openstack 7`, rather than Python dictionary or tuple representations.

The `hosted_cluster_zone_delegation` fact names where hosted-zone delegation
records are declared, such as `moc-dns zonefile` or
`moc-aws hosted-zones.tf`. `hosted_cluster_wildcard_records` separately locates
the `*.hcp` / `*.hcp-int` wildcard declarations. A zone name or zone creation
alone is not evidence of delegation or wildcard records. If no declaration is
found, the fact says `not found in any repository`; unreadable evidence is
reported as unavailable.

GitHub-reading commands also accept the mutually exclusive `--offline` and
`--refresh` cache options described in [Authentication](#authentication).
`--no-prs` is available for status, comparison, and planning commands.

Exit codes:

| Result | Code |
|---|---:|
| Successful report, diff, export, plan, validation, or comparison without hard differences | `0` |
| Hard desired-state comparison difference, or a status gap matching `--fail-on` | `1` |
| Invalid input, GitHub failure, offline cache miss, parse failure, or output-file failure | `2` |

With the default `--fail-on never`, missing configuration in a status report
does not cause a non-zero exit. This remains a reporting tool, not a deployment
gate; `--fail-on` is an explicit opt-in for automation.

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
| `unknown` | Evidence was absent or could not be normalized into an expected value |
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

## Severity and phases

Every status check has one severity:

| Severity | Meaning |
|---|---|
| `blocking` | The gap prevents the environment from progressing to the next repository-configuration phase |
| `advisory` | The gap is worth reviewing, but it does not block the overall configuration state |
| `info` | The check passed or records supporting information without a gap |

The report's phase numbers follow the upstream deployment guides. Phase `0` is
the environment request. Hub phases `1–5` cover inventory, hub-image variables,
discovery images, OIDC, and GitOps values. Workload phases `1–7` cover
inventory, discovery ISO, booting, agent visibility, agent labelling, `oac-apps`
values, and shared-service prerequisites. A phase can contain checks that pass,
are partial, are missing, or are unknown.

The JSON `current_phase` value is the lowest phase with a blocking gap. For an
environment report it is a hub/workload mapping; scoped reports return one
value. The text and Markdown `NEXT` lists respect dependencies first, then
prefer hub before workload actions, blocking before advisory actions, and
earlier phases within those groups.

Overall status states are:

| Report | Overall state | Meaning |
|---|---|---|
| Status | `CONFIGURATION IN PROGRESS` | At least one blocking gap exists |
| Status | `DECLARED IN MAIN` | Checks exist and none are blocking |
| Status | `NOT CONFIGURED` | No checks were produced |
| Comparison | `DIFFERENCES FOUND` | At least one hard difference exists |
| Comparison | `CONFIGURATION IN PROGRESS` | No hard difference, but relevant work is open in a PR |
| Comparison | `MATCHES MAIN` | Reviewed desired state matches merged `main` |

## Troubleshooting

### GitHub rate limits

Set `GITHUB_TOKEN` or run `gh auth login`; these are the quickest fixes. The CLI
reports the reset time and exits with code `2`.

### No known issue number

Issue numbers come from the packaged `moc_env/data/environments.yaml` registry.
If the environment has no registry entry, pass the issue explicitly:

```sh
uv run moc-env status example-env --issue 123
```

The same registry defines default and per-environment required and optional
local-cluster components, plus an optional Keycloak client-name override. An
environment may also list `deferred` checks with a reason, optional cluster,
and optional `until` date. A workload check in a multi-workload environment
must name its cluster. Active deferrals are reported under a Deferred heading
and excluded from blocking and advisory counts; once `until` passes, the gap
counts again and the report says the deferral expired. A deferred entry whose
check now passes is reported as resolved so it can be removed from the
registry. The
overall status is driven only by `blocking` gaps; `advisory` gaps are counted
separately and do not make an environment partially configured.

Report metadata records when the report was generated, the tool version, the
sanitized command, the repository refs and SHAs read, whether GitHub requests
were authenticated, and the remaining GitHub rate limit when GitHub supplies
it. In JSON, each check has normalized `expected`, `observed`, and `gaps`
arrays; the older `expected`, `present`, `missing`, and `actual` fields are
retained temporarily for compatibility.

Pull-request discovery covers `oac-apps`, `oac-infra`, and `moc-keycloak`.
Reports record the repository for each PR and group rendered PR tables by
repository.

### Pull-request calls are too expensive

Use `--no-prs` for status, comparison, or planning commands when PR state is
not required.

### Chart reference warns about missing descriptions

The warning lists required or conditional keys whose upstream `values.yaml`
has no comment. It is an upstream documentation gap, not a rendering failure.
Fix it by adding a comment beside the key in `oac-apps`; moc-env does not
invent descriptions. Use `--chart NAME` to focus the reference and warning on
one or more charts.

### A chart key appears as "(commented out)" or "(section)"

`(commented out)` means an unassigned comment block parses as YAML with a
top-level key that is absent from the active `values.yaml`; the original block
is shown under `Example for <key>`. `(section)` means the key is a mapping with
child rows, so it has no scalar default of its own. Neither marker changes the
chart or the upstream file.

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

## Safety boundaries

Current commands do not:

- mutate MOC repositories;
- create branches, commits, worktrees, or pull requests;
- approve, merge, close, comment on, or force-push a PR;
- connect to a live OpenShift or Argo CD cluster;
- claim deployment, health, or compliance.

The only external publishing actions are the explicit `make report-gist-*`
targets, which use `gh` and require deliberate invocation.
