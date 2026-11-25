"""Offline classification and rendering acceptance tests for node-pool hosts."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import yaml

from moc_env.cross_repo import _workload_value_checks
from moc_env.model import Environment, StatusReport
from moc_env.observed import parse_hardware_resource_classes
from moc_env.phases import annotate_and_sort_checks
from moc_env.report import render_markdown, render_text


WORKLOAD = "aurora-workload0"
REQUIRED = "forge-accelerator"
ENVIRONMENT = Environment(name="aurora", workload_clusters=(WORKLOAD,))


class RepositoryInputs:
    def resolve_commit(self, repository, ref="main"):
        return "a" * 40

    def get_file(self, repository, path, ref="main"):
        return "vlans: []\n"

    def get_tree(self, repository, ref="main"):
        return {}


def host(name="aurora-node-1", **fields):
    return {"node_name": name, "cluster": WORKLOAD, "bm_management": "openstack", **fields}


def pool(name="accelerators", replicas=1, required=REQUIRED):
    return {
        "name": name,
        "replicas": replicas,
        "agentLabelSelector": {
            "massopen.cloud/cluster": WORKLOAD,
            "openstack/resource-class": required,
        },
    }


def capacity_check(hosts, documented=None, pools=None):
    path = f"hosted-clusters/aurora-infra/{WORKLOAD}/values.yaml"
    hardware_table = "| Node Name | Resource Class |\n|---|---|\n" + "".join(
        f"| {name} | {value} |\n" for name, value in (documented or {}).items()
    )
    infra = SimpleNamespace(
        clusters={WORKLOAD: SimpleNamespace(hosts=SimpleNamespace(value=hosts))},
        hardware_resource_classes=SimpleNamespace(
            value=parse_hardware_resource_classes(hardware_table)
        ),
    )
    apps = SimpleNamespace(
        paths=SimpleNamespace(value=[path]),
        files={path: yaml.safe_dump({"nodePools": pools if pools is not None else [pool()]})},
    )
    checks = _workload_value_checks(
        RepositoryInputs(), ENVIRONMENT, infra, apps,
        {"machine_network": "192.0.2.0/24"},
        {"baseDomain": "aurora.example.test", "hcpExternalDomain": "aurora.example.test"},
        None,
    )
    return next(check for check in checks if check.id == "workload.node_pool_hosts")


def rendered_report(check):
    annotate_and_sort_checks([check])
    report = StatusReport(
        environment=ENVIRONMENT, checks=[check], overall_state=check.state,
    ).to_dict()
    return render_text(report), render_text(report, details=True), render_markdown(report)


class NodePoolResourceClassTest(unittest.TestCase):
    def assert_unknown_output(self, check, unclassified):
        self.assertEqual(check.state, "unknown")
        self.assertNotEqual(check.severity, "blocking")
        self.assertEqual(check.actual[0]["unclassified_hosts"], unclassified)
        for output in rendered_report(check):
            with self.subTest(output=output[:30]):
                self.assertIn("UNKNOWN", output)
                self.assertIn("0 blocking gaps", output)
                self.assertIn("accelerators", output)
                self.assertIn(REQUIRED, output)
                self.assertIn("CCI-MOC/oac-infra", output)
                self.assertIn("infra/inventory/00hosts.yaml", output)
                self.assertIn("docs/hardware-and-network-configuration.md", output)
                self.assertIn("no resource_class", output.lower())
                self.assertIn("no documented class", output.lower())
                self.assertIn(f"{unclassified} hosts matched the cluster selector", output)
                self.assertIn("held in OpenStack", output)
                self.assertIn("not recorded in the repositories", output)
                lines = output.splitlines()
                for index, line in enumerate(lines):
                    if "UNKNOWN" not in line or line.startswith("- UNKNOWN:"):
                        continue
                    # Summary, phase and detailed UNKNOWN markers must each
                    # carry the explanation on that line or directly below it.
                    adjacent = " ".join(lines[index:index + 2])
                    self.assertIn("accelerators", adjacent)
                    self.assertIn(REQUIRED, adjacent)

    def test_inventory_equal_matches_on_inventory_basis(self):
        check = capacity_check([host(resource_class=REQUIRED)])
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.actual[0]["matching_hosts"], 1)
        self.assertEqual(check.actual[0]["basis"], "inventory")
        self.assertIn("1 (basis: inventory)", rendered_report(check)[1])

    def test_inventory_mismatch_cannot_be_overridden_by_documentation(self):
        for inventory_class in ("other-accelerator", "accelerator"):
            with self.subTest(inventory_class=inventory_class):
                check = capacity_check(
                    [host(resource_class=inventory_class)],
                    {"aurora-node-1": "accelerator"},
                )
                self.assertEqual(check.state, "value_mismatch")
                self.assertEqual(check.actual[0]["matching_hosts"], 0)
                self.assertEqual(check.actual[0]["basis"], "inventory")

    def test_documented_exact_or_hyphen_suffix_matches(self):
        for documented in (REQUIRED, "accelerator"):
            with self.subTest(documented=documented):
                check = capacity_check([host()], {"aurora-node-1": documented})
                self.assertEqual(check.state, "declared_in_main")
                self.assertEqual(check.actual[0]["matching_hosts"], 1)
                self.assertEqual(check.actual[0]["basis"], "documented class")
                self.assertIn("1 (basis: documented class)", rendered_report(check)[1])

    def test_documented_substrings_or_nonfinal_tokens_do_not_match(self):
        for required in ("forgeaccelerator", "forge-accelerator-extra", "forge-accelerators"):
            with self.subTest(required=required):
                check = capacity_check(
                    [host()], {"aurora-node-1": "accelerator"},
                    [pool(required=required)],
                )
                self.assertEqual(check.state, "value_mismatch")
                self.assertEqual(check.severity, "blocking")
                self.assertEqual(check.actual[0]["matching_hosts"], 0)

    def test_missing_both_classes_is_unknown_in_all_renderers(self):
        check = capacity_check([host(), host("aurora-node-2")])
        self.assertIsNone(check.actual[0]["matching_hosts"])
        self.assert_unknown_output(check, 2)
        self.assertIn("matching count undetermined", rendered_report(check)[1])

    def test_partial_classification_reports_known_count_and_unknown_remainder(self):
        check = capacity_check(
            [host(resource_class=REQUIRED), host("aurora-node-2")],
            pools=[pool(replicas=2)],
        )
        self.assert_unknown_output(check, 1)
        self.assertEqual(check.actual[0]["matching_hosts"], 1)
        self.assertEqual(check.actual[0]["classified_hosts"], 1)
        self.assertEqual(check.actual[0]["basis"], "inventory")
        for output in rendered_report(check):
            self.assertIn("1 confirmed matching hosts", output)

    def test_enough_confirmed_matches_pass_with_unclassified_candidates_noted(self):
        check = capacity_check([host(resource_class=REQUIRED), host("aurora-node-2")])
        self.assertEqual(check.state, "declared_in_main")
        for output in rendered_report(check)[1:]:
            self.assertIn("Note: 1 unclassified hosts (aurora-node-2)", output)
            self.assertNotIn("UNKNOWN", output)

    def test_two_confirmed_one_unclassified_for_five_is_blocking(self):
        check = capacity_check(
            [host(f"aurora-node-{i}", resource_class=REQUIRED) for i in range(2)]
            + [host("aurora-node-unclassified")],
            pools=[pool(replicas=5)],
        )
        self.assertEqual(check.state, "value_mismatch")
        self.assertEqual(check.severity, "blocking")
        self.assertIn("2 confirmed matching hosts; 1 unclassified hosts", check.reason)
        self.assertIn("short even if every unclassified host matched", check.reason)
        for output in rendered_report(check):
            self.assertIn("2 confirmed matching hosts; 1 unclassified hosts", " ".join(output.split()))
            self.assertNotIn("UNKNOWN", output)

    def test_four_confirmed_one_unclassified_for_five_is_unknown(self):
        check = capacity_check(
            [host(f"aurora-node-{i}", resource_class=REQUIRED) for i in range(4)]
            + [host("aurora-node-unclassified")],
            pools=[pool(replicas=5)],
        )
        self.assert_unknown_output(check, 1)
        self.assertEqual(check.actual[0]["matching_hosts"], 4)

    def test_determined_pools_report_zero_when_all_candidates_are_unclassified(self):
        for replicas, state in ((0, "declared_in_main"), (2, "value_mismatch")):
            with self.subTest(replicas=replicas):
                check = capacity_check([host()], pools=[pool(replicas=replicas)])
                self.assertEqual(check.state, state)
                self.assertEqual(check.actual[0]["matching_hosts"], 0)
                self.assertEqual(check.actual[0]["unclassified_hosts"], 1)
                self.assertNotIn("matching count undetermined", rendered_report(check)[1])

    def test_non_openstack_missing_inventory_class_does_not_use_documentation(self):
        for management in ("bmc", "redfish", None):
            with self.subTest(management=management):
                candidate = host(bm_management=management)
                if management is None:
                    candidate.pop("bm_management")
                check = capacity_check([candidate], {"aurora-node-1": "accelerator"})
                self.assertEqual(check.state, "value_mismatch")
                self.assertEqual(check.severity, "blocking")
                self.assertEqual(check.actual[0]["matching_hosts"], 0)
                self.assertEqual(check.actual[0]["unclassified_hosts"], 0)
                self.assertIn("workload.agent_labels_inputs", check.reason)
                self.assertNotIn("OpenStack", check.reason)
                self.assertNotIn("OpenStack", check.next_action)
                for output in rendered_report(check)[1:]:
                    self.assertIn("aurora-node-1: no resource_class in the inventory", output)
                    self.assertIn("update-agents.yaml will not label it", output)
                    self.assertIn("workload.agent_labels_inputs", output)
                    self.assertNotIn("OpenStack", output)
                    self.assertNotIn("UNKNOWN", output)

    def test_four_classified_matching_hosts_for_five_is_blocking_on_either_basis(self):
        for basis in ("inventory", "documented class"):
            with self.subTest(basis=basis):
                hosts = [
                    host(f"aurora-node-{i}", **({"resource_class": REQUIRED} if basis == "inventory" else {}))
                    for i in range(4)
                ]
                documented = {item["node_name"]: "accelerator" for item in hosts}
                check = capacity_check(hosts, documented, [pool(replicas=5)])
                self.assertEqual(check.state, "value_mismatch")
                self.assertEqual(check.severity, "blocking")
                self.assertEqual(check.actual[0]["matching_hosts"], 4)
                self.assertEqual(check.actual[0]["basis"], basis)
                self.assertEqual(check.actual[0]["unclassified_hosts"], 0)

    def test_unknown_host_in_other_cluster_is_not_a_candidate(self):
        check = capacity_check([
            host(resource_class=REQUIRED), host("aurora-node-2", cluster="other-aurora-workload0"),
        ])
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.actual[0]["unclassified_hosts"], 0)

    def test_mixed_bases_are_recorded(self):
        check = capacity_check(
            [host(resource_class=REQUIRED), host("aurora-node-2")],
            {"aurora-node-2": "accelerator"}, [pool(replicas=2)],
        )
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.actual[0]["matching_hosts"], 2)
        self.assertEqual(check.actual[0]["basis"], "documented class, inventory")

    def test_basis_describes_matches_not_other_classified_hosts(self):
        check = capacity_check(
            [host(resource_class="other-class"), host("aurora-node-2")],
            {"aurora-node-2": "accelerator"},
        )
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.actual[0]["matching_hosts"], 1)
        self.assertEqual(check.actual[0]["basis"], "documented class")
