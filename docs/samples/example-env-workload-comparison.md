SAMPLE — generated from a synthetic fixture, not a live environment.

# Workload Desired-State Comparison

## `example-env` — DIFFERENCES FOUND

This report compares reviewed desired state with merged repository `main`. It does not claim live cluster health.

## Summary

| State | Count |
|---|---:|
| MATCH `matches_main` | 17 |
| MISMATCH `value_mismatch` | 4 |

## Detailed comparison

| Category | Field | Desired | Current | State | Reason |
|---|---|---|---|---|---|
| Metadata | `metadata.environment.value` | `example-env` | `example-env` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Metadata | `metadata.name.value` | `example-env-workload0` | `example-env-workload0` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Metadata | `metadata.parentInfraCluster.value` | `example-env-infra` | `example-env-infra` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Parent references | `metadata.parentInfraCluster` | `example-env-infra` | `present` | MATCH `matches_main` | The referenced parent hub cluster exists in merged main. |
| Parent references | `spec.parent.domain.value` | `example-env.int.massopen.cloud` | `example-env.int.massopen.cloud` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Parent references | `spec.parent.network.machineNetwork.value` | `10.20.26.0/23` | `10.20.26.0/23` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `metadata.name` | `example-env-workload0` | `present` | MATCH `matches_main` | The workload cluster exists in the current inventory. |
| Inventory | `spec.inventory.groupPresent.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.hostCount.value` | `1` | `1` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.hosts.value` | `[{"bm_management": "ipmi", "boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-workload0", "mac_addr": "00:11:22:33:44:55", "name": "compute-0", "node_name": "MOC-R4PAC10U31-S1B", "resource_class": "example-env-worker"}]` | `[{"bm_management": "ipmi", "boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-workload0", "mac_addr": "00:11:22:33:44:55", "name": "compute-0", "node_name": "MOC-R4PAC10U31-S1B", "resource_class": "example-env-worker"}]` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.bootImage.selected.value` | `http://10.2.0.82/boot/discovery.iso` | `http://10.2.0.82/boot/discovery.iso` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.bootImage.selected.clusterSpecific` | `True` | `False` | MISMATCH `value_mismatch` | The selected boot image does not identify the workload cluster. |
| GitOps references | `spec.gitOps.hostedClusterValues.path.value` | `hosted-clusters/example-env-infra/example-env-workload0/values.yaml` | `hosted-clusters/example-env-infra/example-env-workload0/values.yaml` | MATCH `matches_main` | The hosted-cluster path references the correct infra and workload clusters. |
| GitOps presence | `spec.gitOps.hostedClusterValues.present` | `True` | `True` | MATCH `matches_main` | The hosted-cluster values file exists in merged main. |
| GitOps references | `spec.gitOps.componentValues.prefix.value` | `values/example-env-infra/example-env-workload0/` | `values/example-env-infra/example-env-workload0/` | MATCH `matches_main` | The component-value prefix references the correct clusters. |
| GitOps presence | `spec.gitOps.componentValues.paths.value` | `[]` | `["values/example-env-infra/example-env-workload0/cert-manager.yaml"]` | MISMATCH `value_mismatch` | The reviewed desired value differs from merged main. |
| GitOps presence | `spec.gitOps.componentValues.present` | `True` | `True` | MATCH `matches_main` | Workload component values exist in merged main. |
| GitOps references | `spec.gitOps.applications.prefix.value` | `apps/example-env-infra/example-env-workload0/` | `apps/example-env-infra/example-env-workload0/` | MATCH `matches_main` | The application prefix references the correct clusters. |
| GitOps presence | `spec.gitOps.applications.paths.value` | `[]` | `["apps/example-env-infra/example-env-workload0/example.yaml"]` | MISMATCH `value_mismatch` | The reviewed desired value differs from merged main. |
| GitOps presence | `spec.gitOps.applications.present` | `False` | `True` | MISMATCH `value_mismatch` | The reviewed desired value differs from merged main. |
| Pull requests | `relevant_pull_requests` | `No relevant open pull requests` | `{"matching_pr_count": 0, "open_pr_count": 0}` | MATCH `matches_main` | No relevant pull requests are open. |
