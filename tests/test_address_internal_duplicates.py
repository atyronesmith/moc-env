"""Acceptance regressions for workload address checks."""

from __future__ import annotations

import re
import unittest

from fakes import FullyConfiguredFakeGitHubClient

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.report import render_text
from moc_env.report_fields import field_rows

HUB = "bu-ist-demo-infra"
WORKLOAD0 = "bu-ist-demo-workload0"
WORKLOAD1 = "bu-ist-demo-workload1"
NEW_ID = "workload.address_internal_duplicates"


def values(
    *,
    api: str = "10.20.26.10",
    api_external: str = "10.20.29.10",
    pool: str = "10.20.28.10",
    ingress_external: str = "10.20.29.11",
) -> str:
    return f"""
clusterName: candidate
services:
  APIServer:
    ipAddress: {api}
    externalIpAddress: {api_external}
ingress:
  poolAddress: {pool}
  externalIpAddress: {ingress_external}
dns:
  records:
    - hostname: api.candidate.int.massopen.cloud
oauth:
  mocsso:
    enabled: false
  identityProviders:
    - name: htpasswd
      type: HTPasswd
nodePools:
  - name: compute
    replicas: 1
    agentLabelSelector:
      cluster: candidate
      resource_class: bu-ist-demo-worker
"""


class AddressFixture(FullyConfiguredFakeGitHubClient):
    WORKLOADS: dict[str, str] = {WORKLOAD0: values()}

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            for workload in self.WORKLOADS:
                path = f"hosted-clusters/{HUB}/{workload}/values.yaml"
                tree[path] = {"path": path}
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            for workload, text in self.WORKLOADS.items():
                if path == f"hosted-clusters/{HUB}/{workload}/values.yaml":
                    return text
        return super().get_file(repository, path, ref)


class DuplicateExternalFixture(AddressFixture):
    WORKLOADS = {
        WORKLOAD0: values(api_external="129.10.5.104", ingress_external="129.10.5.104")
    }


class CidrDuplicateFixture(AddressFixture):
    WORKLOADS = {WORKLOAD0: values(api="10.0.0.5", pool="10.0.0.5/32")}


class TripleDuplicateFixture(AddressFixture):
    WORKLOADS = {
        WORKLOAD0: values(
            api="129.10.5.104",
            api_external="129.10.5.104",
            ingress_external="129.10.5.104",
        )
    }


class DistinctFixture(AddressFixture):
    WORKLOADS = {WORKLOAD0: values()}


class SecondWorkloadDuplicateFixture(AddressFixture):
    WORKLOADS = {
        WORKLOAD0: values(),
        WORKLOAD1: values(api="10.0.0.5", pool="10.0.0.5/32"),
    }


class SharedAcrossWorkloadsFixture(AddressFixture):
    WORKLOADS = {
        WORKLOAD0: values(api_external="129.10.5.104", ingress_external="10.20.29.11"),
        WORKLOAD1: values(api_external="129.10.5.104", ingress_external="10.20.29.12"),
    }


def report_for(client, workloads=(WORKLOAD0,)) -> dict:
    environment = Environment(
        name="bu-ist-demo", issue_number=666, workload_clusters=tuple(workloads)
    )
    return StatusChecker(client=client, include_prs=False).run(environment).to_dict()


def check_for(report: dict, check_id: str, cluster: str | None = None) -> dict:
    matches = [
        check
        for check in report["checks"]
        if check["id"] == check_id and (cluster is None or check["cluster"] == cluster)
    ]
    assert len(matches) == 1, (check_id, cluster, [c["cluster"] for c in matches])
    return matches[0]


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


def result_counts(text: str) -> tuple[int, int]:
    result = next(line for line in text.splitlines() if line.startswith("RESULT:"))
    if "No deployment gaps" in result:
        return 0, 0
    match = re.search(r"RESULT: (\d+) blocking gaps.*?· (\d+) advisories", result)
    assert match, result
    return int(match.group(1)), int(match.group(2))


class InternalDuplicateCheckTest(unittest.TestCase):
    def test_external_address_shared_by_api_and_ingress_is_allowed(self) -> None:
        report = report_for(DuplicateExternalFixture())
        check = check_for(report, NEW_ID, WORKLOAD0)

        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "info")
        self.assertIn("129.10.5.104", check["reason"])
        self.assertIn("allowed", check["reason"])

        actions = next_actions(render_text(report))
        matching = [action for action in actions if "129.10.5.104" in action]
        self.assertEqual(matching, [])

    def test_three_fields_sharing_external_address_is_advisory(self) -> None:
        report = report_for(TripleDuplicateFixture())
        check = check_for(report, NEW_ID, WORKLOAD0)

        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "advisory")
        self.assertIn("services.APIServer.ipAddress", check["reason"])
        self.assertIn("services.APIServer.externalIpAddress", check["reason"])
        self.assertIn("ingress.externalIpAddress", check["reason"])
        self.assertEqual(
            check["expected"],
            f"No address is used by more than one field of {WORKLOAD0}.",
        )
        self.assertEqual(
            check["actual"],
            {
                "duplicates": {
                    "129.10.5.104": [
                        "services.APIServer.ipAddress",
                        "services.APIServer.externalIpAddress",
                        "ingress.externalIpAddress",
                    ]
                }
            },
        )

    def test_cidr_and_bare_ip_are_equal(self) -> None:
        report = report_for(CidrDuplicateFixture())
        check = check_for(report, NEW_ID, WORKLOAD0)
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "advisory")
        self.assertIn("10.0.0.5", check["reason"])
        self.assertEqual(
            check["expected"],
            f"No address is used by more than one field of {WORKLOAD0}.",
        )
        self.assertEqual(
            check["actual"],
            {
                "duplicates": {
                    "10.0.0.5": [
                        "services.APIServer.ipAddress",
                        "ingress.poolAddress",
                    ]
                }
            },
        )

    def test_four_distinct_addresses_pass_with_four_rows(self) -> None:
        report = report_for(DistinctFixture())
        check = check_for(report, NEW_ID, WORKLOAD0)
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "info")
        rows = field_rows(check)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row[2] == "none" for row in rows))

    def test_only_second_workload_is_advisory_and_named_in_next(self) -> None:
        report = report_for(
            SecondWorkloadDuplicateFixture(), workloads=(WORKLOAD0, WORKLOAD1)
        )
        first = check_for(report, NEW_ID, WORKLOAD0)
        second = check_for(report, NEW_ID, WORKLOAD1)
        self.assertEqual(first["state"], "declared_in_main")
        self.assertEqual(second["state"], "value_mismatch")
        self.assertEqual(second["severity"], "advisory")

        actions = next_actions(render_text(report))
        matching = [action for action in actions if NEW_ID in action or "10.0.0.5/32" in action]
        self.assertEqual(len(matching), 1, matching)
        self.assertIn(WORKLOAD1, matching[0])

    def test_address_uniqueness_display_names_sibling_workload(self) -> None:
        report = report_for(
            SharedAcrossWorkloadsFixture(), workloads=(WORKLOAD0, WORKLOAD1)
        )
        check = check_for(report, "workload.address_uniqueness")
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "blocking")

        rows = [
            row for row in field_rows(check)
            if "129.10.5.104" in str(row[0])
        ]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn("bu-ist-demo-workload", row[0])
            self.assertIn("bu-ist-demo-workload", str(row[2]))
            self.assertNotEqual(row[2], "none")
        self.assertFalse(check["reason"].endswith("used by: ."))
        self.assertIn(WORKLOAD0, check["reason"])
        self.assertIn(WORKLOAD1, check["reason"])

    def test_next_count_equals_blocking_plus_advisory(self) -> None:
        cases = (
            (DuplicateExternalFixture(), (WORKLOAD0,)),
            (CidrDuplicateFixture(), (WORKLOAD0,)),
            (DistinctFixture(), (WORKLOAD0,)),
            (SecondWorkloadDuplicateFixture(), (WORKLOAD0, WORKLOAD1)),
            (SharedAcrossWorkloadsFixture(), (WORKLOAD0, WORKLOAD1)),
        )
        for client, workloads in cases:
            with self.subTest(client=type(client).__name__):
                report = report_for(client, workloads=workloads)
                text = render_text(report)
                blocking, advisories = result_counts(text)
                self.assertEqual(len(next_actions(text)), blocking + advisories)


if __name__ == "__main__":
    unittest.main()
