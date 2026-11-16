from __future__ import annotations

import unittest

from moc_env.model import CheckResult, Environment, StatusReport
from moc_env.report import render_markdown, render_text


class ReportRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = Environment(name="fixture-env", issue_number=123)
        checks = [
            CheckResult(
                id="hub.boot_image",
                stage="Hardware and inventory",
                check="fixture cluster boot image",
                scope="hub",
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
                url="https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml",
                next_action=(
                    "Generate and publish a hub-specific discovery ISO, then "
                    "replace the generic boot_image_url for every host in the "
                    "hub cluster group."
                ),
            )
        ]
        self.report = StatusReport(
            environment=environment,
            checks=checks,
            overall_state="PARTIALLY CONFIGURED",
        ).to_dict()

    def test_text_includes_reason_present_and_missing(self) -> None:
        rendered = render_text(self.report)
        self.assertIn("Environment configuration status: fixture-env", rendered)
        self.assertIn("Why checked:", rendered)
        self.assertIn("A URL exists, but it points to the generic discovery.iso.", rendered)
        self.assertIn("Fields:", rendered)
        self.assertIn("boot_image_url", rendered)
        self.assertIn("http://10.2.0.82/boot/discovery.iso", rendered)
        self.assertIn("Missing fields:", rendered)
        self.assertIn("cluster_specific_image", rendered)
        self.assertIn("MISSING", rendered)
        self.assertIn("Stage summary:", rendered)
        self.assertIn("Suggested next actions:", rendered)
        self.assertIn("cluster_specific_image", rendered.split("Suggested next actions:", 1)[1])
        self.assertIn("Next:", rendered)
        self.assertIn("hub-specific discovery ISO", rendered)

    def test_markdown_is_verbose_and_actionable(self) -> None:
        rendered = render_markdown(self.report)
        self.assertIn("# Environment configuration status", rendered)
        self.assertIn("## Environment identity", rendered)
        self.assertIn("## Deployment context", rendered)
        self.assertIn("```mermaid", rendered)
        self.assertIn("## Stage summary", rendered)
        self.assertIn("## Detailed findings by stage", rendered)
        self.assertIn("Why this was checked", rendered)
        self.assertIn("**Result**", rendered)
        self.assertIn("| Aspect | Value |", rendered)
        self.assertIn("| Expected |", rendered)
        self.assertIn("| Present |", rendered)
        self.assertIn("| Missing |", rendered)
        self.assertIn("| Actual |", rendered)
        self.assertIn("## Suggested next actions", rendered)
        self.assertIn("Suggested action", rendered)
        self.assertIn("Generate and publish a hub-specific discovery ISO", rendered)
        self.assertIn("fixture-env-agent-discovery.iso", rendered)
        self.assertNotIn("## Raw report data", rendered)
        self.assertNotIn("```json", rendered)

    def test_report_titles_identify_scope(self) -> None:
        for scope, title in (
            ("environment", "Environment configuration status"),
            ("hub", "Hub environment configuration status"),
            ("workload", "Workload environment configuration status"),
        ):
            with self.subTest(scope=scope):
                report = {**self.report, "scope": scope}
                self.assertIn(f"{title}: fixture-env", render_text(report))
                self.assertIn(f"# {title}", render_markdown(report))

    def test_markdown_renders_host_table(self) -> None:
        check = {
            **self.report["checks"][0],
            "evidence": {
                "hosts": [
                    {
                        "name": "control-0",
                        "node_name": "MOC-R4PAC10U31-S1A",
                        "bmc_addr": "10.20.27.1",
                        "boot_image_url": "http://example.invalid/image.iso",
                    }
                ]
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Observed hosts**", rendered)
        self.assertIn("| Host | Node name | BMC address | Boot image URL |", rendered)
        source_url = "https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml"
        self.assertIn(f"[`control-0`]({source_url})", rendered)
        self.assertIn(f"[`MOC-R4PAC10U31-S1A`]({source_url})", rendered)
        self.assertIn(
            "`http://example.invalid/image.iso`",
            rendered,
        )
        self.assertNotIn("[http://example.invalid/image.iso](", rendered)

    def test_markdown_renders_expected_path_table(self) -> None:
        check = {
            **self.report["checks"][0],
            "expected": {"file_count": 2, "scope": "values/fixture"},
            "evidence": {
                "expected_paths": [
                    "values/fixture/present.yaml",
                    "values/fixture/missing.yaml",
                ],
                "paths": ["values/fixture/present.yaml"],
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Expected paths**", rendered)
        self.assertIn("| Path | Status |", rendered)
        source_url = "https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml"
        self.assertIn(f"[`values/fixture/present.yaml`]({source_url}) | **Present**", rendered)
        self.assertIn(f"[`values/fixture/missing.yaml`]({source_url}) | **Missing**", rendered)

    def test_markdown_renders_expected_field_table(self) -> None:
        check = {
            **self.report["checks"][0],
            "expected": ["cluster_domain_name", "base_domain", "api_ip"],
            "evidence": {
                "values": {
                    "cluster_domain_name": "fixture-env",
                    "base_domain": "example.test",
                }
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Expected fields**", rendered)
        self.assertIn("| Expected field | Status | Observed value |", rendered)
        self.assertIn("`cluster_domain_name` | **Present** | `fixture-env`", rendered)
        self.assertIn("`api_ip` | **Missing** | —", rendered)
        self.assertNotIn("| Aspect | Value |", rendered)

    def test_markdown_links_environment_identity_to_sources(self) -> None:
        issue_url = "https://github.com/CCI-MOC/MOC-issues/issues/123"
        inventory_url = "https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml"
        variables_url = "https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/fixture-env-infra/vars.yml"
        checks = [
            {
                **self.report["checks"][0],
                "check": "MOC issue",
                "url": issue_url,
            },
            {
                **self.report["checks"][0],
                "check": "fixture-env-infra host inventory",
                "url": inventory_url,
            },
            {
                **self.report["checks"][0],
                "check": "fixture-env-workload0 host inventory",
                "url": inventory_url,
            },
            {
                **self.report["checks"][0],
                "check": "Hub image variables",
                "url": variables_url,
            },
        ]
        rendered = render_markdown({**self.report, "checks": checks})
        self.assertIn(f"[`fixture-env`]({issue_url})", rendered)
        self.assertIn(f"[`123`]({issue_url})", rendered)
        self.assertIn(f"[`fixture-env-infra`]({inventory_url})", rendered)
        self.assertIn(f"[`fixture-env-workload0`]({inventory_url})", rendered)
        self.assertIn(f"[`fixture-env.int.massopen.cloud`]({variables_url})", rendered)

    def test_boot_image_rule_is_explicit(self) -> None:
        check = {
            **self.report["checks"][0],
            "evidence": {
                "check_rule": (
                    "The boot-image filename must contain the full cluster name "
                    "`fixture-env-infra`; generic `discovery.iso` does not satisfy "
                    "this rule."
                )
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Status rule:**", rendered)
        self.assertIn("must contain the full cluster name", rendered)
        self.assertIn("generic `discovery.iso`", rendered)

    def test_markdown_renders_pull_request_table(self) -> None:
        check = {
            **self.report["checks"][0],
            "evidence": {
                "pull_requests": [
                    {
                        "number": 237,
                        "title": {"value": "Fixture buildout"},
                        "state": {"value": "open"},
                        "merged": {"value": False},
                        "classification": {"value": "open"},
                        "head_ref": {"value": "fixture-buildout"},
                        "html_url": {"value": "https://github.com/CCI-MOC/oac-apps/pull/237"},
                        "changed_files": ["values/fixture/hcp-config.yaml"],
                    }
                ]
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Relevant pull requests**", rendered)
        self.assertIn(
            "| PR | Title | State | Merged | Classification | Head branch | Link | Changed files |",
            rendered,
        )
        self.assertIn("`237` | `Fixture buildout` | `open` | No", rendered)
        self.assertIn(
            "[https://github.com/CCI-MOC/oac-apps/pull/237](https://github.com/CCI-MOC/oac-apps/pull/237)",
            rendered,
        )

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
            "present": {
                "matching_pr_count": 3,
                "merged_pr_count": 3,
                "open_pr_count": 0,
                "closed_unmerged_pr_count": 0,
            },
            "missing": None,
            "actual": {
                "matching_pr_count": 3,
                "open_count": 0,
                "merged_count": 3,
                "closed_unmerged_count": 0,
            },
            "evidence": {"pull_requests": []},
        }
        report = {**self.report, "checks": [check]}
        rendered = render_text(report)
        self.assertIn("Pull request counts:", rendered)
        self.assertIn("Matching PRs", rendered)
        self.assertIn("Merged PRs", rendered)
        self.assertIn("Closed-unmerged PRs", rendered)
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
