# Hub Cluster and Hosted Control Plane Terminology

## Why the terminology matters

Earlier `moc-env` work used **infra cluster** as a generic label for the
cluster that hosts shared services. The clearer OpenShift terminology is:

- **Hub cluster**: the management cluster. It runs shared services such as
  ACM and hosts the control planes for hosted clusters.
- **Hosted cluster**: a cluster whose control plane runs as hosted control
  plane workloads on the hub cluster.
- **Workload cluster**: the hosted cluster from the user or application
  perspective. Its worker nodes provide the data plane where workloads run.

In a hosted control plane deployment, the control plane and data plane are
separate. The hub cluster runs the hosted control planes; the hosted cluster's
worker nodes run its workloads.

## Repository mapping

The `oac-apps` paths already reflect this model:

```text
values/<hub-cluster>/
  Values shared by hub-scoped applications.

values/<hub-cluster>/local-cluster/
  Values for components installed in the hub cluster's local cluster.

hosted-clusters/<hub-cluster>/<hosted-cluster>/values.yaml
  Values that define the hosted cluster and its node pools.

values/<hub-cluster>/<hosted-cluster>/
  Values for charts installed into that hosted workload cluster.
```

## Compatibility with existing commands

The existing `export-infra`, `check-infra`, `plan-infra`, and `InfraCluster`
names remain compatible with already-generated documents. The JSON environment
key `infra_cluster` is also unchanged for report consumers. New user-facing
check display names and documentation use **hub cluster** terminology. A later
schema migration can introduce `HubCluster`, `export-hub`, and `check-hub`
names while preserving aliases.

The planned environment bundle uses `hubCluster`:

```yaml
apiVersion: moc-env/v1alpha1
kind: Environment
metadata:
  name: bu-ist-demo
spec:
  issue: https://github.com/CCI-MOC/MOC-issues/issues/666
  hubCluster: bu-ist-demo-infra
  workloadClusters:
    - bu-ist-demo-workload0
```

## Chart inventory

`moc-env charts` maps the terminology above onto repository mechanisms:

```sh
uv run moc-env charts
uv run moc-env charts --view cluster bu-ist-demo
uv run moc-env charts --view reference
```

The summary view shows which baseline and optional feature charts each workload
cluster receives, plus the fixed charts, compliance group, and per-hub drop-ins
for each hub. The cluster view resolves the ApplicationSet and placement behind
every received chart, the feature label or `drop-in` marker, the values files
that apply, and any unmet required values. The reference view lists the hub and
workload chart groups, each optional feature and its `clusterLabels` entry, and
the settings declared by every deployed chart. It reports declared repository
configuration, not live cluster state.

## Chart-values documentation

`moc-env document-values` explains values by scope, chart, type, and source:

```sh
uv run moc-env document-values
```

The generated Markdown is environment-independent. It distinguishes hub-wide
values, hub local-cluster values, hosted-cluster-default values, hosted-cluster
values, and workload-component values. It aggregates each key across all
values files, explains its role in the deployment, and links to a representative
source file. It deliberately does not print a particular environment's current
values.

This documentation is observational. It does not replace upstream Helm chart
documentation or the review process for changing values.
