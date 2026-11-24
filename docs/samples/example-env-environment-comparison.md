SAMPLE — generated from a synthetic fixture, not a live environment.

# Environment Desired-State Comparison

## `example-env` — MATCHES MAIN

This report compares reviewed desired state with merged repository `main`. It does not claim live cluster health.

## Summary

| State | Count |
|---|---:|
| MATCH `matches_main` | 14 |

## Detailed comparison

| Category | Field | Desired | Current | State | Reason |
|---|---|---|---|---|---|
| Metadata | `metadata.name.value` | `example-env` | `example-env` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Bundle | `spec.issue.value` | `https://github.com/CCI-MOC/MOC-issues/issues/666` | `https://github.com/CCI-MOC/MOC-issues/issues/666` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| References | `spec.hubCluster.value` | `example-env-infra` | `example-env-infra` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| References | `spec.hubCluster.inventoryPresent` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Network and domain | `spec.network.machineNetwork.value` | `10.20.26.0/23` | `10.20.26.0/23` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Network and domain | `spec.domain.value` | `example-env.int.massopen.cloud` | `example-env.int.massopen.cloud` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| References | `spec.workloadClusters[0].name.value` | `example-env-workload0` | `example-env-workload0` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| References | `spec.workloadClusters[0].parentHubCluster.value` | `example-env-infra` | `example-env-infra` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| References | `spec.workloadClusters[0].inventoryPresent` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| GitOps | `spec.workloadClusters[0].gitOps.hostedClusterValues` | `hosted-clusters/example-env-infra/example-env-workload0/values.yaml` | `True` | MATCH `matches_main` | The expected GitOps path is present in merged main. |
| GitOps | `spec.workloadClusters[0].gitOps.componentValues` | `values/example-env-infra/example-env-workload0/` | `True` | MATCH `matches_main` | The expected GitOps path is present in merged main. |
| GitOps | `spec.workloadClusters[0].gitOps.applications` | `apps/example-env-infra/example-env-workload0/` | `True` | MATCH `matches_main` | The expected GitOps path is present in merged main. |
| GitOps | `spec.gitOps.sourceRepository.value` | `CCI-MOC/oac-apps` | `CCI-MOC/oac-apps` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Pull requests | `relevant_pull_requests` | `No relevant open pull requests` | `{"matching_pr_count": 0, "open_pr_count": 0}` | MATCH `matches_main` | No relevant pull requests are open. |
