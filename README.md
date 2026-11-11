# moc-env-status

`moc-env-status` is a read-only CLI that reports the **configuration state** of a
Mass Open Cloud (MOC) environment across public CCI-MOC GitHub repositories.

It intentionally does **not** claim that a cluster is deployed or healthy. Its
first release distinguishes:

- what the MOC issue requests;
- what is declared in merged repository `main` branches;
- what exists only in an open pull request.

The motivating environment is `bu-ist-demo`, tracked by
[MOC issue 666](https://github.com/CCI-MOC/MOC-issues/issues/666).

## Current scope

Milestone 1 inspects:

- `CCI-MOC/MOC-issues`
- `CCI-MOC/oac-infra`
- `CCI-MOC/moc-keycloak`
- `CCI-MOC/oac-apps`

It reports:

- MOC issue state;
- infrastructure and workload host inventory;
- hub-image variables and hardware identifiers;
- boot-image specificity;
- Keycloak OIDC client registration;
- `oac-apps` infra, local-cluster, and workload GitOps paths;
- open and merged pull requests that reference the environment.

Later milestones can add networking, DNS, AWS, storage, monitoring, billing,
access, GPU, and optional live OpenShift/Argo CD checks.

## Install and run

Using `uv`:

```sh
uv sync
uv run moc-env-status bu-ist-demo
```

Produce JSON:

```sh
uv run moc-env-status bu-ist-demo --format json
```

Produce Markdown:

```sh
uv run moc-env-status bu-ist-demo --format markdown
```

Override the associated MOC issue:

```sh
uv run moc-env-status bu-ist-demo --issue 666
```

Skip pull-request discovery:

```sh
uv run moc-env-status bu-ist-demo --no-prs
```

## GitHub authentication

The CLI works without authentication against public repositories, but GitHub's
unauthenticated REST quota is small. To use a token:

```sh
export GITHUB_TOKEN="..."
uv run moc-env-status bu-ist-demo
```

Use a fine-grained personal access token with access to public repositories and
these read-only permissions:

- Contents
- Issues
- Pull requests
- Metadata

Do not grant interaction limits, administration, workflows, or write access.

## State meanings

| State | Meaning |
|---|---|
| `requested` | The MOC issue exists and records the request |
| `missing` | No relevant configuration was found |
| `partial` | Some information exists, but required details are absent or generic |
| `pr_open` | Relevant configuration exists only in an open pull request |
| `pr_merged` | A relevant pull request has been merged |
| `declared_in_main` | Relevant configuration is present in a merged `main` branch |

The key distinction is `pr_open` versus `declared_in_main`: an open PR is not
deployed desired state.

## Exit codes

- `0`: the report was produced
- `2`: GitHub access or parsing failed

Missing configuration does not cause a non-zero exit because this is a reporting
tool, not a deployment gate.

## Development

```sh
uv sync
uv run python -m unittest discover -s tests -v
```

## Non-goals

- No infrastructure mutation
- No secret-value retrieval
- No PR creation, merge, comment, or push
- No live OpenShift/Argo CD checks in this milestone
