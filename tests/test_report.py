from __future__ import annotations

import unittest
import re
import copy

from moc_env.model import CheckResult, Environment, StatusReport
from moc_env.report import _phase_cell, render_json, render_markdown, render_text


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
            ("blocking", "FAIL", "1 blocking gap"),
            ("advisory", "WARNING", "1 advisory"),
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

    def test_headline_count_nouns_in_both_renderers(self) -> None:
        for blocking in range(3):
            for advisory in range(3):
                checks = [
                    {
                        **self.report["checks"][0], "id": f"{severity}.{index}",
                        "state": "missing", "severity": severity,
                    }
                    for severity, count in (("blocking", blocking), ("advisory", advisory))
                    for index in range(count)
                ]
                # Keep the count headline visible even when both counts are zero.
                checks.append({**self.report["checks"][0], "state": "unknown"})
                for renderer in (render_text, render_markdown):
                    with self.subTest(blocking=blocking, advisory=advisory, renderer=renderer):
                        rendered = renderer({**self.report, "scope": "hub", "checks": checks})
                        gap_phrase = ("0 blocking gaps", "1 blocking gap", "2 blocking gaps")[blocking]
                        advisory_phrase = ("0 advisories", "1 advisory", "2 advisories")[advisory]
                        separator = " ·" if renderer == render_text else ","
                        self.assertIn(gap_phrase + separator, rendered)
                        self.assertIn(advisory_phrase + separator, rendered)

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
        self.assertIn("**0 blocking gaps, 1 advisory, and 0 of 1 checks pass**", rendered)
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

    def test_agent_input_presence_is_separate_from_advisory_documentation(self) -> None:
        hosts = [
            {
                "host": "compute-0",
                "bm_management": "bmc",
                "mac_addr": "00:11:22:33:44:55",
                "resource_class": None,
                "documented_resource_class": "fc430",
            },
            {
                "host": "gpu-0",
                "bm_management": "bmc",
                "mac_addr": "00:11:22:33:44:66",
                "resource_class": "lenovo-sd665nv3-h100",
                "documented_resource_class": "h100",
            },
        ]
        check = {
            **self.report["checks"][0],
            "id": "workload.agent_labels_inputs",
            "check": "Workload update-agents inputs",
            "state": "partial",
            "severity": "blocking",
            "scope": "workload",
            "cluster": "fixture-env-workload0",
            "phase": 5,
            "path": "infra/update-agents.yaml",
            "reason": "Some non-openstack hosts are missing required inputs.",
            "next_action": "Set compute-0 resource_class to `fc430`.",
            "actual": hosts,
            "evidence": {
                "agent_label_hosts": hosts,
                "missing_variables": {"compute-0": ["resource_class"]},
                "resource_class_mismatches": [{
                    "host": "gpu-0",
                    "inventory_resource_class": "lenovo-sd665nv3-h100",
                    "documented_resource_class": "h100",
                }],
            },
        }
        report = {**self.report, "checks": [check]}
        before = copy.deepcopy(report)
        original_json = render_json(report)
        text = render_text(report, details=True)
        markdown = render_markdown(report)
        text_required = text.split("Required agent inputs", 1)[1].split(
            "Resource-class documentation comparison", 1
        )[0]
        markdown_required = markdown.split("**Required agent inputs", 1)[1].split(
            "**Resource-class documentation comparison", 1
        )[0]

        self.assertRegex(text_required, r"compute-0\.resource_class\s+present\s+not found")
        self.assertRegex(text_required, r"gpu-0\.resource_class\s+present\s+lenovo-sd665nv3-h100")
        for required in (text_required, markdown_required):
            self.assertNotIn("fc430", required)
        self.assertIn("| `compute-0.resource_class` | `present` | `—` |", markdown_required)
        self.assertIn(
            "| `gpu-0.resource_class` | `present` | `lenovo-sd665nv3-h100` |",
            markdown_required,
        )
        for rendered in (text, markdown):
            compact = " ".join(rendered.split())
            self.assertIn("Resource-class documentation comparison (advisory only)", compact)
            self.assertIn("not defaults or required values", compact)
            self.assertIn("Advisory difference only", rendered)
            self.assertIn("fc430", rendered)
            self.assertIn("h100", rendered)
            self.assertIn("Advisory documentation difference for gpu-0.resource_class", compact)
            self.assertNotIn("Set compute-0 resource_class to", rendered)
            self.assertNotIn("expected h100", compact)
        self.assertIn("RESULT: 1 blocking gap (workload 1) ·", text)
        self.assertEqual(report, before)
        self.assertEqual(render_json(report), original_json)

    def test_agent_input_documentation_comparison_skips_openstack_hosts(self) -> None:
        check = {
            **self.report["checks"][0],
            "id": "workload.agent_labels_inputs",
            "state": "declared_in_main",
            "severity": "info",
            "evidence": {"agent_label_hosts": [{
                "host": "openstack-0",
                "bm_management": "openstack",
                "resource_class": None,
                "documented_resource_class": "fc430",
            }]},
        }
        report = {**self.report, "checks": [check]}
        for rendered in (render_text(report, details=True), render_markdown(report)):
            self.assertIn("not required (OpenStack)", rendered)
            self.assertNotIn("Resource-class documentation comparison", rendered)

    def test_agent_descriptions_only_explain_the_observed_management_mode(self) -> None:
        for mode, label in (("bmc", "BMC-managed"), ("openstack", "OpenStack-managed")):
            with self.subTest(mode=mode):
                check = {
                    **self.report["checks"][0],
                    "id": "workload.agent_labels_inputs",
                    "check": "Workload update-agents inputs",
                    "state": "declared_in_main",
                    "severity": "info",
                    "reason": "Every non-openstack host has its required inputs.",
                    "verifies": "Generic description of both management modes.",
                    "not_verified": "Generic OpenStack exclusions.",
                    "evidence": {"agent_label_hosts": [{
                        "host": "worker-0",
                        "bm_management": mode,
                        "mac_addr": "00:11:22:33:44:55",
                        "resource_class": "fc430",
                    }]},
                }
                report = {**self.report, "checks": [check]}
                before = copy.deepcopy(report)
                for rendered in (render_text(report, details=True), render_markdown(report)):
                    detail = rendered.split("DETAILED CHECKS", 1)[1] if "DETAILED CHECKS" in rendered else rendered.split("## Details", 1)[1].split("## Sources", 1)[0]
                    self.assertIn(f"Host management: {label} ({mode})", detail)
                    self.assertIn(f"bm_management={mode}", detail)
                    self.assertNotIn("Generic description", detail)
                    if mode == "bmc":
                        self.assertNotIn("OpenStack", detail)
                        self.assertNotIn("openstack", detail)
                        self.assertIn("Required agent inputs (BMC-managed hosts)", detail)
                    else:
                        self.assertNotIn("BMC-managed", detail)
                        self.assertIn("not required", detail)
                        self.assertIn("Agent input overrides", detail)
                self.assertEqual(report, before)

    def test_mixed_agent_management_is_identified_per_host(self) -> None:
        check = {
            **self.report["checks"][0],
            "id": "workload.agent_labels_inputs",
            "evidence": {"agent_label_hosts": [
                {"host": "bmc-0", "bm_management": "bmc"},
                {"host": "openstack-0", "bm_management": "openstack"},
                {"host": "unrecorded-0", "bm_management": None},
            ]},
        }
        report = {**self.report, "checks": [check]}
        for rendered in (render_text(report, details=True), render_markdown(report)):
            compact = " ".join(rendered.split())
            self.assertIn("BMC-managed (bmc)", compact)
            self.assertIn("OpenStack-managed (openstack)", compact)
            self.assertIn("Not recorded", compact)
            self.assertIn("Agent input requirements by host", compact)
            self.assertIn("not required (OpenStack)", compact)
        markdown = render_markdown(report)
        self.assertIn("| `bmc-0.resource_class` | `present` |", markdown)
        self.assertIn("| `openstack-0.resource_class` | `not required (OpenStack)` |", markdown)
        self.assertIn("| `unrecorded-0.resource_class` | `present` |", markdown)

    def test_feature_chart_and_overlay_findings_are_explicit(self) -> None:
        overlay = "kustomize/pure-cosi/overlays/bu-ist-demo-workload0"
        check = {
            **self.report["checks"][0],
            "id": "workload.feature_chart_values",
            "check": "Workload feature chart values",
            "state": "partial",
            "severity": "blocking",
            "scope": "workload",
            "phase": 6,
            "cluster": "fixture-env-workload0",
            "reason": "Required chart values and an overlay are missing.",
            "next_action": "Set missing chart values and add the required overlay.",
            "evidence": {
                "chart_count": 34,
                "unmet_required_values": {
                    "nfs-tls": ["image.repository", "image.digest"],
                    "object-storage-proxy": ["backend.address", "network.cidr"],
                },
                "missing_overlays": [overlay],
                "orphan_values_files": [],
            },
        }
        report = {**self.report, "checks": [check]}
        before = copy.deepcopy(report)
        original_json = render_json(report)
        text = render_text(report, details=True)
        markdown = render_markdown(report)
        self.assertIn("| Chart / item | Requirement | Finding |", markdown)
        self.assertIn(
            "| `nfs-tls` | `All required values supplied` | `Missing: image.repository, image.digest` |",
            markdown,
        )
        self.assertIn(
            f"| `kustomize overlays` | `All required overlays present` | `Missing overlays: {overlay}` |",
            markdown,
        )
        self.assertRegex(text, r"Chart / item\s+Requirement\s+Finding")
        self.assertRegex(
            text,
            r"nfs-tls\s+All required values supplied\s+Missing: image.repository, image.digest",
        )
        for rendered in (text, markdown):
            compact = " ".join(rendered.split())
            self.assertIn("Missing overlays: " + overlay, compact)
            self.assertIn("No orphan values files", compact)
            self.assertIn("nfs-tls: missing required values image.repository, image.digest", compact)
            self.assertIn("Missing required kustomize overlays: " + overlay, compact)
            self.assertNotIn("expected none", compact)
        self.assertEqual(report, before)
        self.assertEqual(render_json(report), original_json)

    def test_feature_chart_findings_distinguish_clear_and_orphaned_values(self) -> None:
        for orphans in ([], ["unused-chart"]):
            with self.subTest(orphans=orphans):
                check = {
                    **self.report["checks"][0],
                    "id": "workload.feature_chart_values",
                    "evidence": {
                        "chart_count": 3,
                        "unmet_required_values": {},
                        "missing_overlays": [],
                        "orphan_values_files": orphans,
                    },
                }
                report = {**self.report, "checks": [check]}
                for rendered in (render_text(report, details=True), render_markdown(report)):
                    compact = " ".join(rendered.split())
                    self.assertIn("No missing required values", compact)
                    self.assertIn("No missing overlays", compact)
                    self.assertIn(
                        "Orphan values files: unused-chart" if orphans else "No orphan values files",
                        compact,
                    )

    def test_unevaluated_feature_charts_do_not_claim_no_missing_inputs(self) -> None:
        check = {
            **self.report["checks"][0],
            "id": "workload.feature_chart_values",
            "state": "unknown",
            "evidence": {},
        }
        report = {**self.report, "checks": [check]}
        for rendered in (render_text(report, details=True), render_markdown(report)):
            self.assertIn("Not evaluated", rendered)
            self.assertNotIn("No missing required values", rendered)
            self.assertNotIn("No missing overlays", rendered)

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
                        "bm_management": "bmc",
                        "bmc_addr": "10.20.27.1",
                        "boot_image_url": "http://example.invalid/image.iso",
                    }
                ]
            },
        }
        rendered = render_markdown({**self.report, "checks": [check]})
        self.assertIn("**Observed hosts**", rendered)
        self.assertIn("Management (bm_management)", rendered)
        self.assertIn("BMC-managed (bmc)", rendered)
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

    def test_shared_file_pulls_have_the_same_details_in_open_and_closed_tables(self) -> None:
        pulls = [
            {
                "repository": {"value": "CCI-MOC/moc-keycloak"},
                "number": number,
                "classification": {"value": classification},
                "title": {"value": f"Shared configuration {number}"},
                "head_ref": {"value": f"shared-config-{number}"},
                "html_url": {"value": f"https://github.com/CCI-MOC/moc-keycloak/pull/{number}"},
                "changed_files": ["main.tf", "modules/shared/variables.tf"],
            }
            for number, classification in enumerate(
                ("open", "merged", "closed_unmerged"), start=1
            )
        ]
        rendered = render_markdown({**self.report, "pull_requests": pulls})
        self.assertIn(
            "1 open pull request changes configuration relevant to this environment.",
            rendered,
        )
        self.assertNotIn("<summary>Merged and closed without merging</summary>", rendered)
        open_section = rendered.split("### Open", 1)[1]
        headers = "| Repository | PR | Title | Head branch | Changed files |"
        for number, section in ((1, open_section),):
            with self.subTest(number=number):
                url = f"https://github.com/CCI-MOC/moc-keycloak/pull/{number}"
                self.assertIn(headers, section)
                self.assertIn(
                    f"| moc-keycloak | [#{number}]({url}) | `Shared configuration {number}` "
                    f"| `shared-config-{number}` | [main.tf]({url}/files)<br>"
                    f"[modules/shared/variables.tf]({url}/files) |",
                    section,
                )
        self.assertNotIn("None.", open_section)
        self.assertNotIn("[#2]", open_section)
        self.assertNotIn("[#3]", open_section)

    def test_open_pull_with_no_file_list_is_not_hidden(self) -> None:
        pull = {
            "repository": "CCI-MOC/oac-infra",
            "number": 42,
            "classification": "open",
            "title": "Issue-linked infrastructure follow-up",
            "head_ref": "infrastructure-follow-up",
            "html_url": "https://github.com/CCI-MOC/oac-infra/pull/42",
            "changed_files": [],
        }
        rendered = render_markdown({**self.report, "pull_requests": [pull, pull]})
        open_section = rendered.split("### Open", 1)[1].split("<details>", 1)[0]
        self.assertIn(
            "1 open pull request changes configuration relevant to this environment.",
            rendered,
        )
        self.assertEqual(open_section.count("[#42]"), 1)
        self.assertIn("| `infrastructure-follow-up` | — |", open_section)
        self.assertNotIn("None.", open_section)


if __name__ == "__main__":
    unittest.main()
