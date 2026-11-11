from __future__ import annotations

import unittest

from moc_env_status.model import CheckResult, Environment, StatusReport
from moc_env_status.report import render_markdown, render_text


class ReportRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = Environment(name="fixture-env", issue_number=123)
        checks = [
            CheckResult(
                stage="Hardware and inventory",
                check="fixture cluster boot image",
                repository="CCI-MOC/oac-infra",
                path="infra/inventory/00hosts.yaml",
                ref="main",
                state="partial",
                expected="Cluster-specific discovery image",
                actual=["http://10.2.0.82/boot/discovery.iso"],
                reason="A URL exists, but it points to the generic discovery.iso.",
                present={"boot_image_url": "http://10.2.0.82/boot/discovery.iso"},
                missing={"cluster_specific_image": "fixture-env-agent-discovery.iso"},
                evidence={"generic_discovery_iso": True},
                url="https://example.com/source",
            )
        ]
        self.report = StatusReport(
            environment=environment,
            checks=checks,
            overall_state="PARTIALLY CONFIGURED",
        ).to_dict()

    def test_text_includes_reason_present_and_missing(self) -> None:
        rendered = render_text(self.report)
        self.assertIn("Why checked:", rendered)
        self.assertIn("A URL exists, but it points to the generic discovery.iso.", rendered)
        self.assertIn("fixture-env-agent-discovery.iso", rendered)
        self.assertIn("Stage summary:", rendered)
        self.assertIn(
            "  Present:      {\n"
            + " " * 18
            + "\"boot_image_url\": \"http://10.2.0.82/boot/discovery.iso\"\n"
            + " " * 16
            + "}",
            rendered,
        )

    def test_markdown_is_verbose_and_actionable(self) -> None:
        rendered = render_markdown(self.report)
        self.assertIn("# 🛰️ MOC Environment Configuration Status", rendered)
        self.assertIn("## Environment identity", rendered)
        self.assertIn("## Stage summary", rendered)
        self.assertIn("## Detailed findings by stage", rendered)
        self.assertIn("Why this was checked", rendered)
        self.assertIn("What is present", rendered)
        self.assertIn("What is missing", rendered)
        self.assertIn("## Suggested next actions", rendered)
        self.assertIn("fixture-env-agent-discovery.iso", rendered)
        self.assertIn("## Raw report data", rendered)


if __name__ == "__main__":
    unittest.main()
