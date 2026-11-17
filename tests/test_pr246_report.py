"""Offline end-to-end regressions for the copied values in oac-apps PR 246."""

from __future__ import annotations

import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.report import render_markdown, render_text

from fakes import FullyConfiguredFakeGitHubClient


FIXTURES = Path(__file__).parent / "fixtures"
WORKLOAD_PATH = "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
DEFAULTS_PATH = "hosted-clusters/bu-ist-demo-infra/values.yaml"
DEV_PATH = "hosted-clusters/oac-dev-infra/oac-dev-workload0/values.yaml"


class Pr246ReportClient(FullyConfiguredFakeGitHubClient):
    """Exact values at 625765a, with synthetic offline surrounding repositories.

    The workload fixture is copied byte-for-byte from:
    https://github.com/CCI-MOC/oac-apps/blob/625765a/
    hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml
    """

    SOURCE_SHAS = {
        **FullyConfiguredFakeGitHubClient.SOURCE_SHAS,
        "CCI-MOC/oac-apps": "625765a" + "0" * 33,
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree[DEV_PATH] = {"path": DEV_PATH}
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            if path in {WORKLOAD_PATH, DEV_PATH}:
                text = (FIXTURES / "pr246-workload-values.yaml").read_text(encoding="utf-8")
                return text if path == WORKLOAD_PATH else text.replace(
                    "bu-ist-demo-workload0", "oac-dev-workload0"
                )
            if path == DEFAULTS_PATH:
                return (
                    "baseDomain: hcp.bu-ist-demo.int.massopen.cloud\n"
                    "managementCluster: bu-ist-demo-infra\n"
                    "hcpInternalDomain: hcp-int.bu-ist-demo.int.massopen.cloud\n"
                    "hcpExternalDomain: hcp.bu-ist-demo.int.massopen.cloud\n"
                )
        if repository == "CCI-MOC/ansible-switches" and path == "group_vars/all/vlans.yaml":
            return (
                "vlans:\n"
                "  - name: OAC-PRODUCTION-WORKLOAD0\n"
                "    subnet4: 10.20.12.0/23\n"
                "  - name: BU-IST-DEMO-WORKLOAD\n"
                "    subnet4: 10.20.28.0/23\n"
            )
        return super().get_file(repository, path, ref)


class Pr246ReportingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = StatusChecker(
            Pr246ReportClient(refs={"CCI-MOC/oac-apps": "pull/246/head"}),
            include_prs=False,
            clock=lambda: datetime(2026, 11, 17, 12, 34, tzinfo=timezone.utc),
            tool_version="test",
        ).run(Environment(name="bu-ist-demo", issue_number=666)).to_dict()

    def test_actions_include_copied_address_observed_and_required_network(self) -> None:
        for rendered in (render_text(self.report), render_markdown(self.report)):
            with self.subTest(format=rendered[:30]):
                compact = " ".join(rendered.split())
                self.assertIn(
                    "services.APIServer.ipAddress is 10.20.3.13; it must be inside 10.20.26.0/23",
                    compact,
                )
                self.assertIn("ingress.poolAddress is 10.20.7.10/32", compact)
                self.assertIn("inside 10.20.28.0/23", compact)

    def test_duplicate_action_names_all_copied_addresses_and_other_cluster(self) -> None:
        for rendered in (render_text(self.report), render_markdown(self.report)):
            with self.subTest(format=rendered[:30]):
                compact = " ".join(rendered.split())
                self.assertRegex(
                    compact,
                    r"10\.20\.3\.13, 10\.20\.7\.10/32, 129\.10\.5\.101(?:,| and) 129\.10\.5\.102 "
                    r"are also used by oac-dev-workload0",
                )

    def test_gpu_advisory_is_an_action_with_label_and_host_count(self) -> None:
        text = render_text(self.report)
        next_section = text.split("NEXT", 1)[1].split("NOT CHECKED", 1)[0]
        compact = " ".join(next_section.split())
        self.assertIn("(advisory)", compact)
        self.assertIn('clusterLabels["massopen.cloud/feature-gpu"] is true', compact)
        self.assertIn("gpu_host_count is 0", compact)

    def test_details_use_fields_actual_refs_and_source_shas(self) -> None:
        text = render_text(self.report, details=True)
        details = text.split("DETAILED CHECKS", 1)[1]
        self.assertIn("Field", details)
        self.assertIn("Expected", details)
        self.assertIn("Observed", details)
        for field in (
            "services.APIServer.ipAddress", "ingress.poolAddress",
            "dns.records[0].hostname", "gpu_host_count",
        ):
            self.assertIn(field, details)
        self.assertNotRegex(details, r"(?m)^\s+value\s{2,}")
        self.assertNotIn("('oac-dev-workload0',", details)
        self.assertNotIn("('bu-ist-demo-workload0',", details)
        self.assertIn("pull/246/head (625765a)", " ".join(details.split()))
        self.assertIn(
            "https://github.com/CCI-MOC/oac-apps/blob/pull/246/head/" + WORKLOAD_PATH,
            re.sub(r"\s+", "", details),
        )
        for source in self.report["metadata"]["sources"]:
            self.assertIn(source["sha"][:7], text)

    def test_recorded_live_oac_prod_fixture_remains_gap_free(self) -> None:
        report = json.loads((FIXTURES / "oac-prod-full-status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["severity_counts"], {"info": len(report["checks"])})
        self.assertNotIn("unknown", report["summary"]["state_counts"])
        self.assertIn("No deployment gaps in repository configuration.", render_text(report))
        self.assertIn("No deployment gaps in repository configuration.", render_markdown(report))


if __name__ == "__main__":
    unittest.main()
