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

The existing `export-infra`, `check-infra`, and `InfraCluster` names remain
compatible with already-generated documents. New user-facing documentation
uses **hub cluster** terminology. A later schema migration can introduce
`HubCluster`, `export-hub`, and `check-hub` names while preserving aliases.

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
