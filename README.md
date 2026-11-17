# moc-env

`moc-env` is a read-only Python CLI that reports the repository configuration
state of Mass Open Cloud environments by reading public CCI-MOC GitHub
repositories. It distinguishes what an issue requests, what is declared in
merged `main` branches, and what exists only in an open pull request. It does
not claim that a cluster is deployed, healthy, or compliant, and it does not
mutate GitHub or connect to a live cluster.

## Quickstart

Install the locked environment and verify the command:

```sh
uv sync
uv run moc-env --help
```

List every discovered hub and workload cluster:

```sh
uv run moc-env status
```

Inspect one environment:

```sh
uv run moc-env status bu-ist-demo
```

Read the report from top to bottom: the `RESULT` line gives the number of
blocking and advisory gaps, the phase table shows where each scope stands, and
`NEXT` lists repository actions in dependency order. The
[Reading a status report](docs/user-guide.md#reading-a-status-report) section
explains each part with a complete example.

## Sample text report

```text
bu-ist-demo · hub + workload · repo config as of 2026-11-16 12:34:56 UTC
MOC-issues@1111111  ansible-switches@8888888  everpure-moc@5555555  moc-aws@6666666
moc-dns@7777777  moc-keycloak@4444444  oac-apps@3333333  oac-infra@2222222  issue #666 (open)

RESULT: 8 blocking gaps (workload 3) · 0 advisories · 16 of 29 checks pass
UNKNOWN: Workload API address network: hosted-clusters/bu-ist-demo-infra/bu-ist-demo-…

PHASE                        HUB bu-ist-demo-infra           WORKLOAD bu-ist-demo-workload0
1 Host inventory entry in…   ✅ 1 hosts                       ✅ 1 hosts
2 Hub-image inventory entry… ✅ 6/6 variables                 🟡 partial
3 Cluster discovery image…   🟡 partial                       –
4 Keycloak OIDC client /…    ✅ 1/1 checks                    –
5 GitOps values and…         ❌ none                          ✅ 1/2 variables
6 oac-apps values            –                               ⚪ unknown
7 Shared-service…            –                               ✅ 3/3 checks

NEXT
  1. [oac-infra] Generate and publish the parent hub's agent discovery ISO, then replace the
  generic boot_image_url for every host in the workload cluster group. (after 2)
       guide: docs/workload-cluster-deployment.md → Infrastructure Configuration
  2. [oac-infra] Generate and publish a hub-specific discovery ISO, then replace the generic
  boot_image_url for every host in the hub cluster group.
       guide: docs/infra-cluster-deployment.md → Cluster Deployment

NOT CHECKED — verify by hand:
  Configure cluster and storage networks and firewalls for bu-ist-demo-infra; Store the
  bu-ist-demo-infra SSH key and kubeadmin credentials in AWS Secrets Manager; Place the pull
  secret and SSH key under hub-images/credentials/bu-ist-demo-infra

Details:  moc-env status bu-ist-demo --details
Markdown: moc-env status bu-ist-demo --format markdown --output report.md
```

## Authentication

- Public repositories can be read without a token, but GitHub allows only 60 unauthenticated REST requests per hour.
- For repeated use, set a read-only `GITHUB_TOKEN` or log in with GitHub CLI.
- Detailed Bitwarden Secrets Manager and macOS Keychain setup is in the [user guide](docs/user-guide.md#authentication).
- A token needs only public-repository read access to contents, issues, pull requests, and metadata.
- Never place a token in a command-line argument or commit it to the repository.

## Documentation

- [User guide](docs/user-guide.md) — setup, authentication, workflows, report interpretation, options, and troubleshooting.
- [Roadmap](docs/roadmap.md) — milestone history and future desired-state work.
- [Hub-cluster terminology](docs/hub-cluster-terminology.md) — hub, hosted, workload, and compatibility naming.

Developers can run the full test and packaging gate with `make check`, and regenerate the
offline sample reports with `make sample-reports`.
