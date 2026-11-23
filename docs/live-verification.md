# Live snapshot verification

Existing commands remain repository-only. The opt-in `capture-live` command is
the only cluster boundary; `verify-live` never invokes oc or contacts a cluster.
Environment/workload arguments select declarations, not a different oc context.
Full names and `workloadN` suffixes both work, including multiple workloads.
Both commands resolve workloads from declared inventory, using the same resolver
as status; an unknown workload lists the known workload clusters and exits 2.

```sh
uv run --locked moc-env capture-live test-env --workload workload0 \
  --out /private/tmp/synthetic-snapshot --repository-root tests/fixtures/live/repos
uv run --locked moc-env verify-live test-env --workload workload0 \
  --snapshot /private/tmp/synthetic-snapshot --repository-root tests/fixtures/live/repos
```

`capture-live` reads the current oc cluster; the example requires an appropriate
synthetic cluster session. `verify-live` is an offline snapshot comparison: it
never reads live cluster state. Use `--repository-root` for entirely local
declarations, or `--offline` for cached GitHub declarations without network
access. Without either option, it may fetch declarations from GitHub.

Snapshots of real clusters must be kept outside this repository. They can
contain identifying cluster, user, node, namespace, and object names even though
credential material and arbitrary resource payloads are excluded.

## Capture safety

Capture runs only `oc get ... -o json`, with the user's environment unchanged.
The cluster capture never reads, copies, or writes kubeconfig, cluster tokens,
passwords, or client keys. GitHub declarations use the shared credential options
and client factory, just as verify-live does; `--repository-root` bypasses GitHub
credential resolution entirely. GitHub credentials are not stored in snapshots.
It does not log in or request credential refreshes; oc uses the user's existing
authentication configuration. Missing oc and unauthorized/expired responses
produce a one-line login instruction and exit 2. Only explicit `--as USER`
causes moc-env to add an impersonation flag. Existing oc configuration remains
oc's responsibility; moc-env does not inspect it.

Only selected charts' template kinds (including local `file://` dependencies),
plus REQUIRED report kinds, are requested. Reading the required CRD inventory
resolves plural names and scope; it never triggers queries for unrelated CRD
kinds. Secrets, events, endpoints, replicasets, and replicationcontrollers are
excluded. Secrets are never requested, even if a template contains one.
Unresolvable/excluded kinds are recorded and cannot establish absence.

Identity is read with `oc get users.user.openshift.io '~' -o json`; the API URL
comes from Infrastructure status, not credential files. Every request has
`--request-timeout=30s`. The CRD list is requested once and reused in memory.
Before any snapshot write, a DNS API URL host is compared with the chart-derived
`api-internal-<clusterName>.<hcpInternalDomain>` and
`api-external-<clusterName>.<hcpExternalDomain>` names. The domains come from
`hosted-clusters/<hub>/values.yaml`; the external domain defaults to the required
internal domain. This follows the hosted-cluster chart's `hcpInternalDomain`,
`hcpExternalDomain`, `serviceHostname`, and `kubeAPIServerDNSName` helpers and the
API service comments in workload values. `clusterName` comes from the requested
workload's values. No Helm execution or runtime helper parsing is needed.
If the live host is an IP address instead, compare it only with that workload's
`services.APIServer.ipAddress` and `services.APIServer.externalIpAddress`.
No match produces a one-line error listing the live host and every declared
candidate, exits 2, and leaves the output untouched. Host matching ignores case,
a trailing dot, and the port; it performs no DNS lookup.
Unreadable Infrastructure or unavailable/invalid declared names or addresses allows
capture with `identity_verified: false` and `identity_reason` in the manifest.
If unreadable hosted-cluster values also prevent chart discovery, capture keeps
the required kinds and explicitly marks discovery incomplete in the manifest.
For a deliberate exception, `--skip-identity-check` also records an unverified
identity and the explicit skip reason. Text and Markdown verification show one
line below RESULT when identity was not verified (including older snapshots
without identity evidence); JSON retains the manifest fields.

Every object is reduced before writing, including REQUIRED kinds:

- All kinds: apiVersion, kind, name, namespace, tracking-id annotation.
- Pods: nodeName, phase, condition type/status, and container
  name/ready/restartCount, including init and ephemeral containers.
- Nodes: condition type/status.
- ResourceQuotas: spec.hard.
- DataScienceClusters: spec.components.
- HardwareProfiles: spec.identifiers, spec.scheduling, disabled annotation.
- ClusterVersions: status.desired.version.

Environment variables, Application Helm values, last-applied annotations, and
arbitrary specs/status are not retained. Snapshot directories are mode 0700;
JSON files are created mode 0600. Capture requires a new or empty directory and
refuses overwrites. Forbidden and other failures get per-kind files and manifest
entries. Interrupted captures are incomplete without the final manifest.

The manifest records time, user, API URL (or explicit read errors), requested
impersonation, cluster identity verification, coverage, unresolved kinds, and the
complete exact command argv. A snapshot is a manifest plus reduced per-kind JSON
files, not a cluster backup, full resource export, or copy of repository inputs.

## Verification

The existing ApplicationSet/placement resolver selects charts and value files.
Values are layered in declared order over defaults. Static template group/kind
pairs and local dependencies determine coverage; Helm is never executed.

Chart verdicts:

- Enabled with a self-referencing tracked object: `match`.
- Disabled with tracked objects: `drift`.
- Enabled with none, and every template kind readable: `drift`.
- Enabled with none, and a kind unread/missing/unresolvable: `unverifiable`.
- Disabled with readable absence: `expected-absent`, citing disabling file/line.

Across the report, `match` means the checked evidence agrees with declarations;
`drift` means an observed difference or proven missing required object;
`expected-absent` means a deliberately disabled/removed object is absent; and
`unverifiable` means the available evidence cannot establish the result.

Tracking uses the format confirmed from real read-only data:
`application:api-group/Kind:namespace/name`. Core groups and cluster-scoped
namespaces are empty. Application names must equal `<cluster>-<chart>` and
group/kind/namespace/name must refer to the object itself. Copied annotations on
controller children do not count. Chart matches prove presence, not full
manifest equality or successful reconciliation.

Node identities compare case-insensitively. Quotas merge defaults and overrides;
equivalent Kubernetes quantities compare numerically. RHOAI checks the selected
major's component states and hardware-profile identifiers, scheduling, namespace,
and enabled annotation. Pod health ignores Succeeded pods and groups non-Ready
or >50-restart pods by node.

Each row has one verdict. Text/Markdown matches contain only name/verdict;
drift rows show only differences, and absent objects say `live: missing`.
JSON retains structured evidence. Common CLI helpers handle formats, extension
inference, and output. A wrong-workload snapshot yields a one-line error and
exit 2 before chart comparisons. Other runs exit 0 for match/expected-absent only,
1 for drift/unverifiable, and 2 for invalid inputs or failed repository reads.

## Synthetic offline fixtures

No upstream exports are retained. Fixture trees are hand-written, with invented
environment/node/project names, documentation-range API addresses (`192.0.2.0/24`),
and `.invalid` domains, with no real host addresses, emails, or UUIDs. The
host inventory has only two workload groups and host identity; the hub inventory
declares only `test-env-infra`. Real chart names are
retained to exercise structure. Checked-in inputs do not depend on upstream.

```sh
uv run --locked moc-env verify-live test-env --workload workload0 \
  --snapshot tests/fixtures/live/workload0 \
  --repository-root tests/fixtures/live/repos
uv run --locked moc-env verify-live test-env --workload workload1 \
  --snapshot tests/fixtures/live/workload1 \
  --repository-root tests/fixtures/live/repos
```

Both exit 1 intentionally. Four workload0 charts match, including an
operator-library chart. The missing node, Forbidden DNS, and restarting pod are
intentional. Workload1 enables jobset but has no tracked objects. The quota16
overlay changes only a tenant GPU quota. Defaults also declare a PVC count of
20, beyond the seven explicitly overridden quota keys.

Without `--repository-root`, declarations use the existing GitHub reader; local
trees allow fully offline verification. Local synthetic sources are labeled
`local-unversioned`, never with misleading upstream SHAs.
