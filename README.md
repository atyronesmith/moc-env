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
unauthenticated REST quota is small.

### Direct token

To use a token directly:

```sh
export GITHUB_TOKEN="..."
uv run moc-env-status bu-ist-demo
```

### Bitwarden Secrets Manager

Store a secret with key `GITHUB_TOKEN`, then configure its UUID:

```sh
export GITHUB_BWS_SECRET_ID="00000000-0000-0000-0000-000000000000"
uv run moc-env-status bu-ist-demo
```

The CLI looks up the Bitwarden machine access token in this order:

1. `BWS_ACCESS_TOKEN` environment variable
2. macOS Keychain service `moc-env-status-bws-access-token`

The Keychain account defaults to the current user. Override it with
`BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT`. Override the service with
`BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE`. The secret UUID may also be supplied with
`--bws-secret-id`; the UUID is a selector, not a secret.

### macOS Keychain

If no direct token or Bitwarden secret UUID is configured, the CLI reads the
GitHub token from:

```text
service: moc-env-status-github-token
account: <current-user>
```

Create or update the item with:

```sh
/usr/bin/security add-generic-password -U \
  -a "$(id -un)" \
  -s moc-env-status-github-token \
  -T /usr/bin/security \
  -w
```

Paste the GitHub token at the prompt. Override the service or account with
`GITHUB_TOKEN_KEYCHAIN_SERVICE`, `GITHUB_TOKEN_KEYCHAIN_ACCOUNT`, or the
corresponding CLI options.

The complete resolution order is:

1. `GITHUB_TOKEN`
2. `GITHUB_BWS_SECRET_ID` / `MOC_ENV_STATUS_BWS_SECRET_ID`
3. `moc-env-status-github-token` in macOS Keychain

If that default Keychain item is absent, the CLI continues unauthenticated. If a
direct token, Bitwarden UUID, or explicit Keychain selector is configured, lookup
failures are terminal. The CLI does not silently try another credential source
after a selected source fails. No token is accepted as a command-line argument or
passed in command-line arguments to a subprocess.

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
