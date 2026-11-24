SAMPLE — generated from a synthetic fixture, not a live environment.

# Hub Desired-State Comparison

## `example-env` — MATCHES MAIN

This report compares reviewed desired state with merged repository `main`. It does not claim live cluster health.

## Summary

| State | Count |
|---|---:|
| MATCH `matches_main` | 21 |

## Detailed comparison

| Category | Field | Desired | Current | State | Reason |
|---|---|---|---|---|---|
| Metadata | `metadata.environment.value` | `example-env` | `example-env` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Metadata | `metadata.name.value` | `example-env-infra` | `example-env-infra` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.present.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Hub inventory | `spec.hubInventory.present.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Hub inventory | `spec.hubInventory.inventoryPresent.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Hub inventory | `spec.hubInventory.clusterKeyPresent.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.present.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.cluster_domain_name.value` | `example-env` | `example-env` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.base_domain.value` | `int.massopen.cloud` | `int.massopen.cloud` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.machine_network.value` | `10.20.26.0/23` | `10.20.26.0/23` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.api_ip.value` | `10.20.27.11` | `10.20.27.11` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.ingress_ip.value` | `10.20.27.12` | `10.20.27.12` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Variables | `spec.variables.fields.dns_ip.value` | `8.8.8.8` | `8.8.8.8` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Domain | `spec.domain.value` | `example-env.int.massopen.cloud` | `example-env.int.massopen.cloud` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-infra.name.value` | `example-env-infra` | `example-env-infra` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-infra.groupPresent.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-infra.hosts.value` | `[{"boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-infra", "name": "control-0", "node_name": "MOC-R4PAC10U31-S1A"}]` | `[{"boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-infra", "name": "control-0", "node_name": "MOC-R4PAC10U31-S1A"}]` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-infra.bootImage.selected.value` | `http://10.2.0.82/boot/discovery.iso` | `http://10.2.0.82/boot/discovery.iso` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-workload0.name.value` | `example-env-workload0` | `example-env-workload0` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-workload0.groupPresent.value` | `True` | `True` | MATCH `matches_main` | The reviewed desired value matches merged main. |
| Inventory | `spec.inventory.clusters.example-env-workload0.hosts.value` | `[{"bm_management": "ipmi", "boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-workload0", "mac_addr": "00:11:22:33:44:55", "name": "compute-0", "node_name": "MOC-R4PAC10U31-S1B", "resource_class": "example-env-worker"}]` | `[{"bm_management": "ipmi", "boot_image_url": "http://10.2.0.82/boot/discovery.iso", "cluster": "example-env-workload0", "mac_addr": "00:11:22:33:44:55", "name": "compute-0", "node_name": "MOC-R4PAC10U31-S1B", "resource_class": "example-env-worker"}]` | MATCH `matches_main` | The reviewed desired value matches merged main. |
