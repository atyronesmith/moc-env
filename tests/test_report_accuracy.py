"""Acceptance regressions for ref-accurate, value-based status rendering."""

from __future__ import annotations

import re
from pathlib import Path
import unittest

from fakes import FullyConfiguredFakeGitHubClient, FakeGitHubClient, MultiWorkloadFakeGitHubClient

from moc_env.check_descriptions import DescriptionContext, apply_descriptions
from moc_env.checks import StatusChecker
from moc_env.model import CheckResult, Environment
from moc_env.report import render_markdown, render_text
from moc_env.report_fields import field_rows

ROOT = Path(__file__).resolve().parent.parent
HUB = "bu-ist-demo-infra"
WORKLOAD = "bu-ist-demo-workload0"
LABEL_PREFIXES = (
    "Cluster-specific",
    "Inventory group for",
    "Hub-image inventory entry",
    "covers ",
)


def status_report(client) -> dict:
    environment = Environment(
        name="bu-ist-demo", issue_number=666, workload_clusters=(WORKLOAD,)
    )
    return StatusChecker(client=client, include_prs=False).run(environment).to_dict()


def sample_context() -> DescriptionContext:
    return DescriptionContext(
        hub=HUB,
        workload=WORKLOAD,
        workloads=(WORKLOAD,),
        issue=666,
        domain="bu-ist-demo.int.massopen.cloud",
        machine_network="10.20.26.0/23",
        base_domain="int.massopen.cloud",
        hcp_external_domain="hcp.bu-ist-demo.int.massopen.cloud",
        keycloak_client=HUB,
    )


def detail_blocks(markdown: str) -> list[str]:
    return [
        block.split("</details>", 1)[0]
        for block in markdown.split("<details")[1:]
    ]


def table_cells(markdown: str) -> list[str]:
    cells = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells.extend(cell.strip() for cell in line.strip("|").split("|"))
    return cells


def expected_cells(block: str) -> list[str]:
    cells: list[str] = []
    in_table = False
    for line in block.splitlines():
        if line.startswith("| Field | Expected | Observed |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if line.startswith("|---"):
            continue
        cells.append(line.strip("|").split("|")[1].strip())
    return cells


def quoted_values(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


class RefAccuracyTest(unittest.TestCase):
    def test_non_main_ref_never_renders_in_main(self) -> None:
        client = FullyConfiguredFakeGitHubClient(
            refs={"CCI-MOC/oac-apps": "pull/246/head"}
        )
        report = status_report(client)
        markdown = render_markdown(report)
        text = render_text(report, details=True)

        self.assertNotIn("exists in main", markdown)
        self.assertNotIn("exists in main", text)
        matched = 0
        for block in detail_blocks(markdown):
            if "Source: CCI-MOC/oac-apps" not in block or "@ pull/246/head" not in block:
                continue
            matched += 1
            self.assertNotIn("in main", block)
        self.assertTrue(matched)
        for block in text.split("-" * 100)[1:]:
            if "Source: CCI-MOC/oac-apps" not in block or "@ pull/246/head" not in block:
                continue
            self.assertNotIn("in main", block)


class LabelCellTest(unittest.TestCase):
    def test_expected_cells_are_rules_not_labels(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient())
        markdown = render_markdown(report)
        for block in detail_blocks(markdown):
            for cell in expected_cells(block):
                for prefix in LABEL_PREFIXES:
                    self.assertFalse(
                        cell.startswith(prefix), f"{cell!r} in {block[:120]!r}"
                    )

    def test_boot_and_policy_cells_state_their_rules(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient())
        checks = {check["id"]: check for check in report["checks"]}

        boot = {row[0]: row for row in field_rows(checks["hub.boot_image"])}
        self.assertIn("filename contains", boot["boot_image_url"][1])
        self.assertIn("bu-ist-demo-infra", boot["boot_image_url"][1])

        inventory = {
            row[0]: row for row in field_rows(checks["hub.inventory"])
        }
        self.assertEqual(
            inventory["cluster_group"][1],
            "a group with vars.cluster == bu-ist-demo-infra",
        )

        image_inventory = {
            row[0]: row for row in field_rows(checks["hub.image_inventory"])
        }
        self.assertEqual(
            image_inventory["inventory_key"][1],
            f"key all.children.{HUB}",
        )

        policy = field_rows(checks["hub.moc_aws_cert_manager_policy"])
        self.assertEqual(
            policy[0][1],
            "policy_name or cluster_subdomain names bu-ist-demo-infra",
        )


class RenderingConsistencyTest(unittest.TestCase):
    def test_no_boolean_table_cell_uses_yes_or_no(self) -> None:
        for client in (
            FullyConfiguredFakeGitHubClient(),
            FakeGitHubClient(),
            MultiWorkloadFakeGitHubClient(),
        ):
            report = status_report(client)
            markdown = render_markdown(report)
            text = render_text(report, details=True)
            self.assertFalse(
                [cell for cell in table_cells(markdown) if cell in {"Yes", "No"}]
            )
            self.assertNotIn("Yes | Yes", text)

    def test_all_six_path_checks_use_present_words(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient())
        checks = {check["id"]: check for check in report["checks"]}
        for check_id in (
            "hub.hosted_cluster_defaults",
            "hub.component_values",
            "hub.local_cluster_values",
            "hub.argocd_apps",
            "workload.hosted_cluster_values",
            "workload.component_values",
        ):
            rows = field_rows(checks[check_id])
            self.assertTrue(rows, check_id)
            for field, expected, observed in rows:
                if str(field).endswith(".yaml"):
                    self.assertEqual(expected, "present", (check_id, field, expected))
                    self.assertIn(observed, {"present", "missing"}, (check_id, field, observed))

    def test_hub_oidc_rows_use_attribute_names_from_description(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient())
        check = next(
            item for item in report["checks"] if item["id"] == "hub.oidc_client"
        )
        labels = {row[0] for row in field_rows(check)}

        self.assertIn("openshift_redirect_uri", labels)
        self.assertIn("client_secret_name", labels)
        self.assertNotIn("redirect_uri", labels)
        self.assertNotIn("secret_name", labels)
        self.assertIn("openshift_redirect_uri", check["verifies"])
        self.assertIn("client_secret_name", check["verifies"])


def _check(check_id: str, expected, evidence=None) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage="fixture",
        check=check_id,
        scope="workload",
        cluster=WORKLOAD,
        repository="CCI-MOC/moc-keycloak",
        path="main.tf",
        ref="pull/246/head",
        state="declared_in_main",
        severity="info",
        expected=expected,
        actual=expected,
        reason="fixture",
        evidence=evidence or {},
    )


class DescriptionValueTest(unittest.TestCase):
    def _verify_quotes_match_rows(self, check: CheckResult) -> None:
        rows = field_rows(check.to_dict())
        row_expected = {str(row[1]) for row in rows}
        quoted = [
            value
            for value in quoted_values(check.verifies)
            if value.startswith("https://") or value.startswith("cluster/")
        ]
        self.assertTrue(quoted, check.verifies)
        for value in quoted:
            self.assertIn(value, row_expected, check.verifies)

    def test_hub_oidc_description_tracks_expected_values(self) -> None:
        expected = {
            "client": HUB,
            "openshift_redirect_uri": "https://oauth-openshift.apps.example.test/oauth2callback/mocsso",
            "client_secret_name": "cluster/example-hub/keycloak-oidc",
        }
        check = _check("hub.oidc_client", dict(expected))
        apply_descriptions([check], sample_context())
        self._verify_quotes_match_rows(check)

        changed = {
            **expected,
            "openshift_redirect_uri": "https://oauth-openshift.apps.changed.test/oauth2callback/mocsso",
            "client_secret_name": "cluster/changed-hub/keycloak-oidc",
        }
        check.expected = changed
        apply_descriptions([check], sample_context())
        self.assertIn(changed["openshift_redirect_uri"], check.verifies)
        self.assertIn(changed["client_secret_name"], check.verifies)
        self._verify_quotes_match_rows(check)

    def test_workload_keycloak_description_tracks_expected_values(self) -> None:
        expected = {
            "cluster_name": WORKLOAD,
            "openshift_redirect_uri": "https://oauth-example.test:443/oauth2callback/mocsso",
            "client_secret_name": "cluster/example-hub/hostedcluster/example-workload/keycloak-oidc",
        }
        check = _check("workload.keycloak_oidc_client", dict(expected))
        apply_descriptions([check], sample_context())
        self._verify_quotes_match_rows(check)

        changed = {
            **expected,
            "openshift_redirect_uri": "https://oauth-changed.test:443/oauth2callback/mocsso",
            "client_secret_name": "cluster/changed/hostedcluster/changed/keycloak-oidc",
        }
        check.expected = changed
        apply_descriptions([check], sample_context())
        self.assertIn(changed["openshift_redirect_uri"], check.verifies)
        self.assertIn(changed["client_secret_name"], check.verifies)
        self._verify_quotes_match_rows(check)

    def test_identity_provider_description_tracks_expected_values(self) -> None:
        expected = {
            "cluster_name": WORKLOAD,
            "openshift_redirect_uri": "https://oauth-identity.test:443/oauth2callback/mocsso",
            "client_secret_name": "cluster/identity/hostedcluster/identity/keycloak-oidc",
        }
        check = _check(
            "workload.identity_provider",
            {"oauth.mocsso.enabled": True},
            {"client_fields": {name: {"expected": value} for name, value in expected.items()}},
        )
        apply_descriptions([check], sample_context())
        self._verify_quotes_match_rows(check)

        changed = {
            **expected,
            "openshift_redirect_uri": "https://oauth-identity-changed.test:443/oauth2callback/mocsso",
            "client_secret_name": "cluster/changed/hostedcluster/changed/keycloak-oidc",
        }
        check.evidence = {
            "client_fields": {name: {"expected": value} for name, value in changed.items()}
        }
        apply_descriptions([check], sample_context())
        self.assertIn(changed["openshift_redirect_uri"], check.verifies)
        self.assertIn(changed["client_secret_name"], check.verifies)
        self._verify_quotes_match_rows(check)

    def test_dns_description_uses_expected_domains(self) -> None:
        check = _check(
            "workload.dns_base_domain",
            {"baseDomain": "expected.test", "hcpExternalDomain": "hcp.expected.test"},
        )
        apply_descriptions([check], sample_context())
        self.assertIn("expected.test", check.verifies)
        self.assertIn("hcp.expected.test", check.verifies)

    def test_hub_dns_description_uses_expected_record_domain(self) -> None:
        check = _check(
            "hub.moc_dns_records",
            {
                "api.changed.example": "10.0.0.1",
                "api-int.changed.example": "10.0.0.1",
                "*.apps.changed.example": "10.0.0.2",
            },
        )
        apply_descriptions([check], sample_context())
        self.assertIn("changed.example", check.verifies)
        self.assertNotIn("bu-ist-demo.int.massopen.cloud", check.verifies)


class SourceHygieneTest(unittest.TestCase):
    def test_no_replace_in_main_remains_in_source(self) -> None:
        matches = []
        for path in (ROOT / "src" / "moc_env").glob("*.py"):
            if '.replace("in main"' in path.read_text(encoding="utf-8"):
                matches.append(path.name)
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
