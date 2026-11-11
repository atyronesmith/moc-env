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
        self.assertIn("Fields:", rendered)
        self.assertIn("boot_image_url", rendered)
        self.assertIn("http://10.2.0.82/boot/discovery.iso", rendered)
        self.assertIn("Missing fields:", rendered)
        self.assertIn("cluster_specific_image", rendered)
        self.assertIn("MISSING", rendered)
        self.assertIn("Stage summary:", rendered)

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

    def test_text_path_checks_use_aligned_checklist(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "GitOps configuration",
            "check": "Fixture path values",
            "expected": {"file_count": 2, "scope": "values/fixture"},
            "present": {"file_count": 1},
            "missing": {"file_count": 1, "paths": ["values/fixture/missing.yaml"]},
            "actual": {"matched_file_count": 1},
            "evidence": {
                "expected_paths": [
                    "values/fixture/present.yaml",
                    "values/fixture/missing.yaml",
                ],
                "paths": ["values/fixture/present.yaml"],
            },
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Expected paths:", rendered)
        self.assertIn("values/fixture/present.yaml", rendered)
        self.assertIn("✅", rendered)
        self.assertIn("❌", rendered)
        self.assertIn("1 of 2 expected paths present", rendered)

    def test_text_field_checks_use_aligned_value_table(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "Cluster build",
            "check": "Fixture variables",
            "expected": ["cluster_domain_name", "base_domain", "api_ip"],
            "present": {
                "fields": ["cluster_domain_name", "base_domain"],
                "values": {
                    "cluster_domain_name": "fixture-env",
                    "base_domain": "example.test",
                },
            },
            "missing": {"fields": ["api_ip"]},
            "actual": ["cluster_domain_name", "base_domain"],
            "evidence": {
                "values": {
                    "cluster_domain_name": "fixture-env",
                    "base_domain": "example.test",
                }
            },
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Expected fields:", rendered)
        self.assertIn("cluster_domain_name", rendered)
        self.assertIn("fixture-env", rendered)
        self.assertIn("base_domain", rendered)
        self.assertIn("example.test", rendered)
        self.assertIn("api_ip", rendered)
        self.assertIn("MISSING", rendered)
        self.assertIn("2 of 3 expected fields present", rendered)

    def test_text_path_scope_checks_are_compact(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "GitOps configuration",
            "check": "Fixture component values",
            "expected": "At least one matching path",
            "present": {"file_count": 0},
            "missing": {"file_count": 1, "paths": ["values/fixture/"]},
            "actual": {"matched_file_count": 0},
            "evidence": {
                "path_count": 0,
                "expected_path_count": 0,
                "expected_paths": [],
                "paths": [],
            },
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Result:       0 matching paths; expected at least one", rendered)
        self.assertNotIn("Present:", rendered)
        self.assertNotIn("Missing:", rendered)

    def test_text_pull_request_counts_are_compact(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "GitOps configuration",
            "check": "Relevant pull requests",
            "expected": "No open PRs; relevant changes merged into main",
            "present": {"matching_pr_count": 3, "merged_pr_count": 3},
            "missing": None,
            "actual": {"matching_pr_count": 3, "open_count": 0, "merged_count": 3},
            "evidence": {"pull_requests": []},
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Pull request counts:", rendered)
        self.assertIn("Matching PRs", rendered)
        self.assertIn("Merged PRs", rendered)
        self.assertIn("Open PRs", rendered)
        self.assertNotIn("Present:", rendered)
        self.assertNotIn("Missing:", rendered)

    def test_text_scalar_fields_are_compact(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "Hardware and inventory",
            "check": "Fixture host inventory",
            "expected": "Inventory group for fixture-env",
            "present": {"cluster_group": "fixture-env", "host_count": 3},
            "missing": None,
            "actual": {"found": True, "host_count": 3},
            "evidence": {"hosts": []},
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Fields:", rendered)
        self.assertIn("cluster_group", rendered)
        self.assertIn("fixture-env", rendered)
        self.assertIn("host_count", rendered)
        self.assertIn("3", rendered)
        self.assertNotIn("Present:", rendered)
        self.assertNotIn("Actual:", rendered)

    def test_text_expected_declarations_are_compact(self) -> None:
        check = self.report["checks"][0]
        check = {
            **check,
            "stage": "Identity",
            "check": "Fixture OIDC client",
            "expected": ["client", "redirect_uri", "secret_name"],
            "present": {"declarations": ["client", "secret_name"]},
            "missing": {"declarations": ["redirect_uri"]},
            "actual": ["client", "secret_name"],
            "evidence": {
                "client": True,
                "redirect_uri": False,
                "secret_name": True,
            },
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Expected fields:", rendered)
        self.assertIn("client", rendered)
        self.assertIn("present", rendered)
        self.assertIn("redirect_uri", rendered)
        self.assertIn("MISSING", rendered)
        self.assertIn("2 of 3 expected fields present", rendered)
        self.assertNotIn("Present:", rendered)
        self.assertNotIn("Actual:", rendered)


if __name__ == "__main__":
    unittest.main()
