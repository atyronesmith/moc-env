"""Acceptance regressions for explicit per-workload check identity."""

from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from fakes import MultiWorkloadFakeGitHubClient

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.report import (
    _action_description,
    _dependency_action_numbers,
    _phase_cell,
    _sorted_actions,
    _workload_checks,
    render_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TwoWorkloadBootImageClient(MultiWorkloadFakeGitHubClient):
    """Two workloads: workload0 gets a blocking boot gap, workload1 advisory."""

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            return """
all:
  children:
    oac_dev_clusters:
      children:
        oac_dev_infra:
          vars:
            cluster: oac-dev-infra
          children:
            controller:
              hosts:
                control-0:
                  node_name: MOC-R4PAC10U31-S1A
        oac_dev_workload0:
          vars:
            cluster: oac-dev-workload0
          children:
            compute:
              vars:
                boot_image_url: http://10.2.0.82/boot/discovery.iso
              hosts:
                compute-0:
                  node_name: MOC-R4PAC10U31-S1B
        oac_dev_workload1:
          vars:
            cluster: oac-dev-workload1
          children:
            compute:
              vars:
                boot_image_url: http://10.2.0.82/boot/dev-workload-agent.iso
              hosts:
                compute-1:
                  node_name: MOC-R4PAC10U31-S1C
"""
        return super().get_file(repository, path, ref)


def two_workload_report() -> dict:
    environment = Environment(
        name="oac-dev",
        workload_clusters=("oac-dev-workload0", "oac-dev-workload1"),
    )
    return StatusChecker(TwoWorkloadBootImageClient()).run(environment).to_dict()


def result_counts(text: str) -> tuple[int, int]:
    result = next(line for line in text.splitlines() if line.startswith("RESULT:"))
    if "No deployment gaps" in result:
        return 0, 0
    match = re.search(r"RESULT: (\d+) blocking gaps.*?· (\d+) advisories", result)
    if match is None:
        raise AssertionError(f"unexpected RESULT line: {result}")
    return int(match.group(1)), int(match.group(2))


def next_actions(text: str) -> list[str]:
    if "\nNEXT\n" not in text:
        return []
    section = text.split("\nNEXT\n", 1)[1].split("\nNOT CHECKED", 1)[0]
    actions: list[str] = []
    current: list[str] | None = None
    for line in section.splitlines():
        if re.match(r"^  \d+\. ", line):
            if current is not None:
                actions.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        actions.append("\n".join(current))
    return actions


class MultiWorkloadReportIdentityTest(unittest.TestCase):
    def test_next_includes_both_workload_boot_image_gaps_by_cluster(self) -> None:
        report = two_workload_report()
        boot_checks = [
            check for check in report["checks"]
            if check["id"] == "workload.boot_image"
        ]
        self.assertEqual(len(boot_checks), 2)
        self.assertEqual(
            {check["cluster"] for check in boot_checks},
            {"oac-dev-workload0", "oac-dev-workload1"},
        )
        self.assertEqual(
            {check["cluster"]: check["severity"] for check in boot_checks},
            {"oac-dev-workload0": "blocking", "oac-dev-workload1": "advisory"},
        )

        actions = next_actions(render_text(report))
        boot_actions = [action for action in actions if "agent discovery ISO" in action]
        self.assertEqual(len(boot_actions), 2)
        self.assertIn("oac-dev-workload0", "\n".join(boot_actions))
        self.assertIn("oac-dev-workload1", "\n".join(boot_actions))

    def test_next_action_count_matches_result_gap_count_for_every_fixture(self) -> None:
        fixtures = sorted(FIXTURES.glob("*status*.json"))
        fixtures += sorted((FIXTURES / "text").glob("*.txt"))
        for path in fixtures:
            with self.subTest(fixture=path.name):
                if path.suffix == ".json":
                    text = render_text(json.loads(path.read_text(encoding="utf-8")))
                else:
                    text = path.read_text(encoding="utf-8")
                blocking, advisories = result_counts(text)
                self.assertEqual(
                    len(next_actions(text)),
                    blocking + advisories,
                    path.name,
                )

    def test_phase_table_attributes_node_pool_gap_only_to_its_workload(self) -> None:
        checks = [
            {
                "id": "workload.node_pool_hosts",
                "cluster": "oac-dev-workload0",
                "scope": "workload",
                "phase": 6,
                "state": "value_mismatch",
                "severity": "blocking",
                "check": "Workload node-pool host capacity",
                "path": "infra/inventory/00hosts.yaml",
                "reason": "At least one node pool lacks matching inventory hosts.",
                "actual": [{"name": "compute", "replicas": 3, "matching_hosts": 0}],
                "expected": [{"name": "compute", "replicas": 3}],
                "evidence": {},
            },
            {
                "id": "workload.node_pool_hosts",
                "cluster": "oac-dev-workload1",
                "scope": "workload",
                "phase": 6,
                "state": "declared_in_main",
                "severity": "info",
                "check": "Workload node-pool host capacity",
                "path": "infra/inventory/00hosts.yaml",
                "reason": "Every node pool has enough matching inventory hosts.",
                "actual": [{"name": "compute", "replicas": 2, "matching_hosts": 2}],
                "expected": [{"name": "compute", "replicas": 2}],
                "evidence": {},
            },
        ]
        workload0 = _workload_checks(checks, "oac-dev-workload0")
        workload1 = _workload_checks(checks, "oac-dev-workload1")
        self.assertEqual(len(workload0), 1)
        self.assertEqual(len(workload1), 1)
        self.assertTrue(_phase_cell(workload0, ascii_mode=True).startswith("[fail]"))
        self.assertTrue(_phase_cell(workload1, ascii_mode=True).startswith("[ok]"))
        self.assertIn(
            "0/1 checks",
            _phase_cell(workload0, ascii_mode=True),
        )

    def test_workload_check_clusters_partition_every_workload_check(self) -> None:
        report = two_workload_report()
        workloads = report["environment"]["workload_clusters"]
        workload_checks = [
            check for check in report["checks"] if check["scope"] == "workload"
        ]
        self.assertTrue(workload_checks)
        for check in workload_checks:
            self.assertIn(check.get("cluster"), workloads, check["id"])
        columns = {
            workload: {id(check) for check in _workload_checks(report["checks"], workload)}
            for workload in workloads
        }
        for workload in workloads:
            self.assertTrue(columns[workload], workload)
        first, second = (columns[workload] for workload in workloads)
        self.assertFalse(first & second)
        self.assertEqual(
            first | second,
            {id(check) for check in workload_checks},
        )

    def test_workload_actions_name_their_cluster(self) -> None:
        report = two_workload_report()
        workload_gaps = [
            check
            for check in report["checks"]
            if check["scope"] == "workload"
            and check["severity"] in {"blocking", "advisory"}
            and check["state"] not in {"declared_in_main", "requested", "pr_merged", "unknown", "blocked"}
        ]
        self.assertTrue(workload_gaps)
        for check in workload_gaps:
            self.assertIn(check["cluster"], _action_description(check, report))

    def test_dependencies_prefer_same_cluster_then_hub(self) -> None:
        hub = "oac-dev-infra"
        check = {
            "id": "workload.node_pool_hosts",
            "cluster": "oac-dev-workload1",
            "blocked_by": ["workload.inventory"],
        }
        action_numbers = {
            ("workload.inventory", "oac-dev-workload0"): 4,
            ("workload.inventory", "oac-dev-workload1"): 5,
            ("workload.inventory", hub): 2,
        }
        self.assertEqual(
            _dependency_action_numbers(check, action_numbers, hub),
            ["5"],
        )
        check["cluster"] = "oac-dev-workload0"
        self.assertEqual(
            _dependency_action_numbers(check, action_numbers, hub),
            ["4"],
        )
        check["cluster"] = hub
        self.assertEqual(
            _dependency_action_numbers(check, action_numbers, hub),
            ["2"],
        )

    def test_hub_dependency_orders_both_workload_actions(self) -> None:
        hub = "oac-dev-infra"
        gaps = [
            {
                "id": "hub.boot_image",
                "cluster": hub,
                "scope": "hub",
                "severity": "blocking",
                "phase": 3,
                "check": "Hub boot image",
                "blocked_by": [],
            },
            *[
                {
                    "id": "workload.boot_image",
                    "cluster": workload,
                    "scope": "workload",
                    "severity": "blocking",
                    "phase": 2,
                    "check": f"{workload} boot image",
                    "blocked_by": ["hub.boot_image"],
                }
                for workload in ("oac-dev-workload0", "oac-dev-workload1")
            ],
        ]
        ordered = _sorted_actions(gaps, hub)
        self.assertEqual(ordered[0]["cluster"], hub)
        self.assertEqual(
            {check["cluster"] for check in ordered[1:]},
            {"oac-dev-workload0", "oac-dev-workload1"},
        )


if __name__ == "__main__":
    unittest.main()
