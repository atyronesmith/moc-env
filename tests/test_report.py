from __future__ import annotations

import unittest
import re

from moc_env.model import CheckResult, Environment, StatusReport
from moc_env.report import _phase_cell, render_markdown, render_text


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
                severity="advisory",
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

    def test_phase_cell_aggregates_all_checks_and_unknowns(self) -> None:
        checks = [
            {"id": "one", "state": "declared_in_main"},
            {"id": "two", "state": "declared_in_main"},
            {"id": "three", "state": "unknown"},
            {"id": "four", "state": "missing", "severity": "blocking"},
        ]

        self.assertEqual(
            _phase_cell(checks),
            "FAIL 2/4 checks, 1 unknown",
        )
        self.assertEqual(
            _phase_cell(checks[:3]),
            "OK 2/3 checks, 1 unknown",
        )

    def test_mismatch_severity_controls_result_markers_and_detail_labels(self) -> None:
        """Blocking mismatches fail; advisory mismatches remain warnings."""

        for severity, marker, summary in (
            ("blocking", "FAIL", "1 blocking gaps"),
            ("advisory", "WARNING", "1 advisories"),
        ):
            with self.subTest(severity=severity):
                check = {
                    **self.report["checks"][0],
                    "id": "workload.fixture_mismatch",
                    "check": "Fixture mismatch",
                    "state": "value_mismatch",
                    "severity": severity,
                    "reason": "Observed value differs from the declaration.",
                    "next_action": "Correct the declaration.",
                }
                report = {**self.report, "checks": [check]}
                text = render_text(report, details=True)
                self.assertIn(summary, text)
                self.assertIn(marker + ": Fixture mismatch", text)
                self.assertIn("Observed value differs from the declaration.", text)

                markdown = render_markdown(report)
                self.assertIn(summary, markdown)
                self.assertIn("Fixture mismatch", markdown)

    def test_unchecked_phase_is_explicitly_manual(self) -> None:
        self.assertEqual(_phase_cell([]), "verify by hand")
        for rendered in (render_text(self.report), render_markdown(self.report)):
            self.assertRegex(rendered, r"3 Agent ISO boot[^\n]*verify by hand")

    def test_skipped_and_unavailable_pulls_do_not_claim_zero(self) -> None:
        for metadata, expected in (
            ({"pull_requests_skipped": True, "pull_requests_skip_reason": "skipped (--no-prs)"}, "Pull requests: skipped (--no-prs)"),
            ({"pull_requests_unavailable": "GitHub API request failed (503)"}, "Pull requests: unavailable (GitHub API request failed (503))"),
        ):
            for renderer in (render_text, render_markdown):
                rendered = renderer({**self.report, **metadata})
                self.assertEqual(rendered.count(expected), 1)
                self.assertNotIn("0 open PRs", rendered)

    def test_cache_header_identifies_repository_and_fetch_time(self) -> None:
        report = {**self.report, "metadata": {"generated_at": "2026-11-17T15:00:00Z", "sources": [
            {"repository": "CCI-MOC/oac-apps", "ref": "pull/246/head", "sha": "625765a" + "0" * 33, "from_cache": True, "fetched_at": "2026-11-16T12:00:00Z"},
        ]}}
        for renderer in (render_text, render_markdown):
            rendered = renderer(report)
            self.assertIn("oac-apps: from cache, fetched 2026-11-16T12:00:00Z", rendered)
            self.assertIn("NOT A REPORT ON MAIN" if renderer == render_text else "not a report on main", rendered)

    def test_blocked_summary_references_numbered_action(self) -> None:
        missing = {**self.report["checks"][0], "id": "workload.hosted_cluster_values", "state": "missing", "severity": "blocking", "blocked_by": []}
        blocked = {**missing, "id": "workload.api_address_network", "state": "blocked", "severity": "advisory", "blocked_by": [missing["id"]]}
        report = {**self.report, "checks": [missing, blocked]}
        for renderer in (render_text, render_markdown):
            rendered = renderer(report)
            self.assertIn("1 check blocked by action 1", rendered)
            self.assertNotIn("blocked until", rendered)

    def test_details_align_network_expected_and_observed_columns(self) -> None:
        check = {**self.report["checks"][0], "id": "workload.api_address_network", "expected": {"ipAddress": "10.20.3.13", "machine_network": "10.20.26.0/23"}, "actual": "10.20.3.13"}
        rendered = render_text({**self.report, "checks": [check]}, details=True)
        ledger = rendered.split("DETAILED CHECKS", 1)[1]
        self.assertRegex(ledger, r"services\.APIServer\.ipAddress\s+inside 10\.20\.26\.0/23\s+10\.20\.3\.13")
        self.assertNotRegex(ledger, r"\n\s+value\s+")
        self.assertIn("(advisory)", rendered)

    def test_rendered_actions_substitute_placeholders(self) -> None:
        check = {
            **self.report["checks"][0],
            "scope": "hub",
            "path": "values/fixture-env-infra",
            "next_action": "Edit values/<hub>/hcp-config.yaml.",
        }
        report = {**self.report, "checks": [check]}
        pattern = re.compile(r"<[A-Za-z][A-Za-z0-9_-]*>")
        text_actions = render_text(report).split("NEXT", 1)[1].split(
            "NOT CHECKED", 1
        )[0]
        markdown_actions = render_markdown(report).split(
            "## Next actions", 1
        )[1].split("## Not checked", 1)[0]
        for rendered in (text_actions, markdown_actions):
            with self.subTest(renderer=rendered):
                self.assertIn("values/fixture-env-infra/hcp-config.yaml", rendered)
                self.assertIsNone(pattern.search(rendered))

    def test_text_includes_reason_present_and_missing(self) -> None:
        rendered = render_text(self.report, details=True)
        self.assertIn("fixture-env · hub + workload", rendered)
        self.assertNotIn("Why checked:", rendered)
        self.assertIn("A URL exists, but it points to the generic discovery.iso.", rendered)
        self.assertIn("Expected", rendered)
        self.assertIn("Observed", rendered)
        self.assertIn("http://10.2.0.82/boot/discovery.iso", rendered)
        self.assertIn("URL:", rendered)
        self.assertNotIn('": ', rendered)

    def test_default_text_is_compact(self) -> None:
        rendered = render_text(self.report)
        self.assertIn("RESULT:", rendered)
        self.assertIn("NEXT", rendered)
        self.assertIn("NOT CHECKED — verify by hand", rendered)
        self.assertNotIn("DETAILED CHECKS", rendered)
        self.assertLessEqual(len(rendered.splitlines()), 60)
        self.assertIn("hub-specific discovery ISO", rendered)

    def test_markdown_is_verbose_and_actionable(self) -> None:
        rendered = render_markdown(self.report)
        self.assertIn("# fixture-env — environment configuration status", rendered)
        self.assertIn("**0 blocking gaps, 1 advisories, and 0 of 1 checks pass**", rendered)
        self.assertIn("## Phase summary", rendered)
        self.assertIn("## Next actions", rendered)
        self.assertIn("## Not checked — verify by hand", rendered)
        self.assertIn("## Details", rendered)
        self.assertIn("## Pull requests", rendered)
        self.assertIn("## Legend", rendered)
        self.assertIn("<details open>", rendered)
        self.assertIn("| Field | Expected | Observed |", rendered)
        first_by_hand_title = self.report["not_checked"][0]["title"]
        self.assertIn(f"- **{first_by_hand_title}**", rendered)
        self.assertNotIn("- [ ]", rendered)
        self.assertIn("Generate and publish a hub-specific discovery ISO", rendered)
        self.assertNotIn("```mermaid", rendered)
        self.assertNotIn("## Raw report data", rendered)
        self.assertNotIn("```json", rendered)

    def test_markdown_legend_uses_failure_mark_not_unprinted_state_word(self) -> None:
        check = {
            **self.report["checks"][0],
            "state": "missing",
            "severity": "blocking",
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        legend = rendered.split("## Legend", 1)[1]

        self.assertIn("- FAIL: A blocking check failed.", legend)
        self.assertNotIn("MISSING", legend)

    def test_requested_check_renders_its_state_word(self) -> None:
        check = {**self.report["checks"][0], "state": "requested"}
        report = {**self.report, "checks": [check]}

        for rendered in (render_text(report, details=True), render_markdown(report)):
            self.assertIn(f"REQUESTED: {check['check']}", rendered)

    def test_merged_check_renders_its_state_word(self) -> None:
        check = {**self.report["checks"][0], "state": "pr_merged"}
        report = {**self.report, "checks": [check]}

        for rendered in (render_text(report, details=True), render_markdown(report)):
            self.assertIn(f"MERGED: {check['check']}", rendered)

    def test_blocked_check_renders_its_state_word_and_legend(self) -> None:
        check = {**self.report["checks"][0], "state": "blocked"}
        report = {**self.report, "checks": [check]}
        markdown = render_markdown(report)

        for rendered in (render_text(report, details=True), markdown):
            self.assertIn(f"BLOCKED: {check['check']}", rendered)

        legend = markdown.split("## Legend", 1)[1]
        self.assertIn(
            "- BLOCKED: `blocked` — Cannot be checked until an earlier check passes.",
            legend,
        )
        self.assertNotIn("- UNKNOWN:", legend)

    def test_not_checked_is_rendered_after_next_actions(self) -> None:
        for rendered in (render_text(self.report), render_markdown(self.report)):
            with self.subTest(renderer=rendered):
                actions = rendered.index("NEXT" if "RESULT:" in rendered else "## Next actions")
                heading = rendered.index(
                    "NOT CHECKED — verify by hand"
                    if "RESULT:" in rendered
                    else "## Not checked — verify by hand"
                )
                self.assertLess(actions, heading)
                manual_section = rendered[heading:]
                self.assertIn("fixture-env-infra", manual_section)
                if "RESULT:" not in rendered:
                    self.assertIn("docs/infra-cluster-deployment.md", manual_section)

    def test_report_titles_identify_scope(self) -> None:
        for scope, title in (
            ("environment", "hub + workload"),
            ("hub", "hub"),
            ("workload", "workload"),
        ):
            with self.subTest(scope=scope):
                report = {**self.report, "scope": scope}
                self.assertIn(f"fixture-env · {title} ·", render_text(report))

    def test_text_and_markdown_headers_include_generation_and_sources(self) -> None:
        report = {
            **self.report,
            "metadata": {
                "generated_at": "2026-11-16T12:34:56Z",
                "sources": [
                    {
                        "repository": "CCI-MOC/oac-infra",
                        "ref": "main",
                        "sha": "2222222222222222222222222222222222222222",
                    }
                ],
            },
        }
        self.assertIn("as of 2026-11-16 12:34 UTC", render_text(report))
        self.assertIn("CCI-MOC/oac-infra", render_text(report))
        self.assertIn("2222222", render_text(report))
        self.assertIn("Generated 2026-11-16 12:34 UTC", render_markdown(report))
        self.assertIn("## Sources", render_markdown(report))

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
        self.assertIn("| `control-0` | `MOC-R4PAC10U31-S1A` |", rendered)
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
        known_parent = {
            **self.report["checks"][0],
            "state": "declared_in_main",
            "path": "values/fixture",
        }
        rendered = render_markdown({**self.report, "checks": [check, known_parent]})
        self.assertIn("| Field | Expected | Observed |", rendered)
        self.assertIn(
            "[`values/fixture/present.yaml`]"
            "(https://github.com/CCI-MOC/oac-infra/blob/main/values/fixture/present.yaml) "
            "| `present` | `present`",
            rendered,
        )
        self.assertIn(
            "[`values/fixture/missing.yaml`]"
            "(https://github.com/CCI-MOC/oac-infra/tree/main/values/fixture) "
            "| `present` | `missing`",
            rendered,
        )

    def test_markdown_renders_missing_issue_instruction(self) -> None:
        report = {
            **self.report,
            "environment": {**self.report["environment"], "issue_number": None},
        }
        rendered = render_markdown(report)
        self.assertIn("MOC issue: not set — pass `--issue N`", rendered)
        self.assertNotIn("MOC issue: None", rendered)

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
        self.assertIn("| Field | Expected | Observed |", rendered)
        self.assertIn("`cluster_domain_name` | `present` | `fixture-env`", rendered)
        self.assertIn("`api_ip` | `present` | `—`", rendered)
        self.assertNotIn("| Aspect | Value |", rendered)

    def test_markdown_links_environment_identity_to_sources(self) -> None:
        issue_url = "https://github.com/CCI-MOC/MOC-issues/issues/123"
        inventory_url = "https://github.com/CCI-MOC/oac-infra/blob/main/infra/inventory/00hosts.yaml"
        variables_url = "https://github.com/CCI-MOC/oac-infra/blob/main/hub-images/group_vars/fixture-env-infra/vars.yml"
        checks = [
            {
                **self.report["checks"][0],
                "check": "MOC issue",
                "id": "request.issue",
                "actual": "open",
                "url": issue_url,
            },
            {
                **self.report["checks"][0],
                "check": "fixture-env-infra host inventory",
                "path": "infra/inventory/00hosts.yaml",
                "url": inventory_url,
            },
            {
                **self.report["checks"][0],
                "check": "fixture-env-workload0 host inventory",
                "path": "infra/inventory/00hosts.yaml",
                "url": inventory_url,
            },
            {
                **self.report["checks"][0],
                "check": "Hub image variables",
                "path": "hub-images/group_vars/fixture-env-infra/vars.yml",
                "url": variables_url,
            },
        ]
        rendered = render_markdown({**self.report, "checks": checks})
        self.assertIn(f"MOC issue: [#123]({issue_url}) (open)", rendered)
        self.assertIn(
            f"[`infra/inventory/00hosts.yaml`]({inventory_url})", rendered
        )
        self.assertIn(
            f"[`hub-images/group_vars/fixture-env-infra/vars.yml`]({variables_url})",
            rendered,
        )

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
        self.assertIn("Status rule:", rendered)
        self.assertIn("must contain the full cluster name", rendered)
        self.assertIn("generic `discovery.iso`", rendered)

    def test_markdown_renders_pull_request_table(self) -> None:
        report = {
            **self.report,
            "pull_requests": [
                {
                    "number": 237,
                    "title": {"value": "Fixture buildout"},
                    "state": {"value": "open"},
                    "merged": {"value": False},
                    "classification": {"value": "open"},
                    "head_ref": {"value": "fixture-buildout"},
                    "html_url": {"value": "https://github.com/CCI-MOC/oac-apps/pull/237"},
                    "repository": {"value": "CCI-MOC/oac-apps"},
                    "changed_files": ["values/fixture-env/hcp-config.yaml"],
                }
            ],
        }
        rendered = render_markdown(report)
        self.assertIn("### Open", rendered)
        self.assertIn(
            "| Repository | PR | Title | Head branch | Changed files |",
            rendered,
        )
        self.assertIn("[#237](https://github.com/CCI-MOC/oac-apps/pull/237)", rendered)
        self.assertIn("Fixture buildout", rendered)


if __name__ == "__main__":
    unittest.main()
