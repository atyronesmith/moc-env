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

Using the Makefile:

```sh
make help
make setup
make test
make run ENV=bu-ist-demo
make run-json ENV=bu-ist-demo
make run-no-prs ENV=bu-ist-demo
make report-markdown ENV=bu-ist-demo
make check
```

Common variables:

```sh
make run ENV=bu-ist-demo FORMAT=markdown
make run ARGS="--issue 666"
make run-no-prs ENV=bu-ist-demo
```

`make check` runs the unit tests, byte-compilation, Git whitespace check, and
package build.

Generate a verbose Markdown report:

```sh
make report-markdown ENV=bu-ist-demo
```

The default destination is `reports/bu-ist-demo.md`. Override it with:

```sh
make report-markdown ENV=bu-ist-demo OUTPUT=/tmp/bu-ist-demo.md
```

The CLI prints each inspection step to stderr, including the action, repository,
and source path. Partial results include a reason plus explicit present and
missing values.

Produce JSON:

```sh
uv run moc-env-status bu-ist-demo --format json
```

Produce Markdown:

```sh
uv run moc-env-status bu-ist-demo --format markdown
```

Write Markdown directly to a file:

```sh
uv run moc-env-status bu-ist-demo --format markdown --output reports/bu-ist-demo.md
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

### Local selector file

Copy `.env.example` to `.env`:

```sh
cp .env.example .env
```

Then set the non-secret selectors:

```dotenv
GITHUB_BWS_SECRET_ID=00000000-0000-0000-0000-000000000000
BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE=jira-bws-access-token
```

`.env` is Git-ignored. It may contain only selector values such as UUIDs and
Keychain service/account names. It must not contain `GITHUB_TOKEN` or
`BWS_ACCESS_TOKEN`. Real environment variables override `.env` values.

Use another file with:

```sh
uv run moc-env-status bu-ist-demo --env-file /path/to/selectors.env
```

### Direct token

To use a token directly:

```sh
export GITHUB_TOKEN="..."
uv run moc-env-status bu-ist-demo
```

### Bitwarden Secrets Manager

Store the GitHub personal access token in Bitwarden Secrets Manager as a secret
with key `GITHUB_TOKEN`. Then select that secret by its UUID.

Provide the UUID directly:

```sh
export GITHUB_BWS_SECRET_ID="00000000-0000-0000-0000-000000000000"
uv run moc-env-status bu-ist-demo
```

Or pass it as a selector:

```sh
uv run moc-env-status bu-ist-demo \
  --bws-secret-id 00000000-0000-0000-0000-000000000000
```

The UUID is not the GitHub token and is not the Bitwarden machine access token.

### macOS Keychain-stored Bitwarden UUID

If no direct token or UUID environment variable is configured, the CLI reads the
Bitwarden secret UUID from:

```text
service: moc-env-status-github-token
account: <current-user>
```

The service name is retained for compatibility with the existing local item, but
its value must be the **Bitwarden secret UUID**, not a GitHub token.

Create or update the UUID item with:

```sh
/usr/bin/security add-generic-password -U \
  -a "$(id -un)" \
  -s moc-env-status-github-token \
  -T /usr/bin/security \
  -w
```

Paste the Bitwarden secret UUID at the prompt.

Override the UUID item's service or account with:

```text
GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE
GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT
```

The equivalent CLI options are:

```text
--bws-secret-id-keychain-service
--bws-secret-id-keychain-account
```

### Bitwarden machine access token

To read the selected secret, the CLI needs a Bitwarden machine access token. It
looks for that token in this order:

1. `BWS_ACCESS_TOKEN` environment variable
2. macOS Keychain service `moc-env-status-bws-access-token`

Create or update the machine-token item with:

```sh
/usr/bin/security add-generic-password -U \
  -a "$(id -un)" \
  -s moc-env-status-bws-access-token \
  -T /usr/bin/security \
  -w
```

Paste the Bitwarden machine access token at the prompt. Override its account or
service with `BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT` or
`BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE`.

The complete resolution order is:

1. `GITHUB_TOKEN`
2. `GITHUB_BWS_SECRET_ID` / `MOC_ENV_STATUS_BWS_SECRET_ID`
3. Bitwarden secret UUID from `moc-env-status-github-token` in macOS Keychain
4. `bws secret get <uuid>` using the Bitwarden machine access token

The GitHub token itself is never stored in macOS Keychain. If the default UUID
Keychain item is absent and no direct credential is configured, the CLI continues
unauthenticated. If a direct token, UUID selector, or explicit Keychain selector
is configured, lookup failures are terminal. The CLI does not silently try
another credential source after a selected source fails. No token is accepted as
a command-line argument or passed in command-line arguments to a subprocess.

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
