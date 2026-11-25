from __future__ import annotations

from types import SimpleNamespace
import unittest

import yaml

from moc_env.cross_repo import _workload_value_checks
from moc_env.model import Environment


class _Client:
    def resolve_commit(self, repository: str) -> str:
        return "main"

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/ansible-switches":
            return "vlans: []\n"
        return ""

    def get_tree(self, repository: str, ref: str = "main") -> dict:
        return {}


def _run(values: dict, hosts: list[dict], documented: dict | None = None):
    workload = "bu-ist-demo-workload0"
    path = f"hosted-clusters/bu-ist-demo-infra/{workload}/values.yaml"
    infra = SimpleNamespace(
        clusters={workload: SimpleNamespace(hosts=SimpleNamespace(value=hosts))},
        hardware_resource_classes=SimpleNamespace(value=documented or {}),
    )
    apps = SimpleNamespace(paths=SimpleNamespace(value=[path]), files={path: yaml.safe_dump(values)})
    return {
        result.id: result
        for result in _workload_value_checks(
            _Client(),
            Environment(name="bu-ist-demo-infra", workload_clusters=(workload,)),
            infra,
            apps,
            {"machine_network": "10.0.0.0/8"},
            {"baseDomain": "example.test", "hcpExternalDomain": "example.test"},
            None,
        )
    }


class NodePoolSelectorRegressionTest(unittest.TestCase):
    def test_cluster_selector_requires_exact_value(self) -> None:
        for key in ("cluster", "massopen.cloud/cluster"):
            with self.subTest(key=key):
                checks = _run(
                    {"nodePools": [{"name": "compute", "replicas": 1, "agentLabelSelector": {key: "wrong-bu-ist-demo-workload0"}}]},
                    [{"cluster": "bu-ist-demo-workload0"}],
                )
                self.assertEqual(checks["workload.node_pool_hosts"].state, "value_mismatch")

    def test_exact_selector_and_zero_replicas_pass(self) -> None:
        checks = _run(
            {"nodePools": [{"name": "compute", "replicas": 0, "agentLabelSelector": {"cluster": "bu-ist-demo-workload0"}}]},
            [],
        )
        self.assertEqual(checks["workload.node_pool_hosts"].state, "declared_in_main")

    def test_exact_matching_hosts_and_numeric_string_replicas_pass(self) -> None:
        for replicas in (1, "1"):
            with self.subTest(replicas=replicas):
                checks = _run(
                    {"nodePools": [{
                        "replicas": replicas,
                        "agentLabelSelector": {"cluster": "bu-ist-demo-workload0"},
                    }]},
                    [{"cluster": "bu-ist-demo-workload0"}],
                )
                check = checks["workload.node_pool_hosts"]
                self.assertEqual(check.state, "declared_in_main")
                self.assertEqual(check.actual[0]["matching_hosts"], 1)

    def test_documented_resource_class_alias_is_still_supported(self) -> None:
        for key in ("resource_class", "openstack/resource-class"):
            with self.subTest(key=key):
                checks = _run(
                    {"nodePools": [{
                        "replicas": 1,
                        "agentLabelSelector": {key: "documented-class"},
                    }]},
                    [{"node_name": "example-node", "resource_class": "inventory-class"}],
                    {"example-node": "documented-class"},
                )
                self.assertEqual(
                    checks["workload.node_pool_hosts"].state, "declared_in_main"
                )

    def test_scalar_and_non_string_selectors_fail_without_crashing(self) -> None:
        for selector in ("scalar", ["cluster"], {"cluster": False}, {1: "one"}):
            with self.subTest(selector=selector):
                checks = _run(
                    {"nodePools": [{"replicas": 1, "agentLabelSelector": selector}]},
                    [{"cluster": "bu-ist-demo-workload0"}],
                )
                check = checks["workload.node_pool_hosts"]
                self.assertEqual(check.state, "value_mismatch")
                self.assertIn("agentLabelSelector", check.reason)

    def test_explicit_empty_pool_list_is_supported(self) -> None:
        check = _run({"nodePools": []}, [])["workload.node_pool_hosts"]
        self.assertEqual(check.state, "declared_in_main")

    def test_omitted_replicas_preserves_existing_zero_default(self) -> None:
        check = _run({"nodePools": [{"name": "compute"}]}, [])["workload.node_pool_hosts"]
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.actual[0]["replicas"], 0)

    def test_malformed_node_pools_is_reported_without_crashing(self) -> None:
        malformed_values = [
            {"nodePools": "scalar"},
            {"nodePools": {"compute": {"replicas": 1}}},
            {"nodePools": ["scalar"]},
        ]
        malformed_values.extend(
            {"nodePools": [{"replicas": value}]}
            for value in (True, -1, 1.2, float("inf"), "one", "²", "9" * 5000)
        )
        malformed_values.append({"nodePools": [{"replicas": "one", "agentLabelSelector": {"cluster": False}}]})
        for values in malformed_values:
            with self.subTest(values=values):
                check = _run(values, [])["workload.node_pool_hosts"]
                self.assertEqual(check.state, "value_mismatch")


if __name__ == "__main__":
    unittest.main()
