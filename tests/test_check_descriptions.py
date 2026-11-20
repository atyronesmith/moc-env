"""Acceptance regressions for per-check descriptions and honest field rows."""

from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

from fakes import (
    FullyConfiguredFakeGitHubClient,
)

from moc_env import checks as checks_module
from moc_env import cross_repo as cross_module
from moc_env.check_descriptions import (
    CHECK_DESCRIPTIONS,
    DescriptionContext,
    describe,
)
from moc_env.checks import StatusChecker, _NEXT_ACTIONS
from moc_env.model import Environment
from moc_env.registry import DEFAULT_REGISTRY_PATH, EnvironmentRegistry
from moc_env.report import render_json, render_markdown, render_text
from moc_env.report_fields import field_rows

HUB = "bu-ist-demo-infra"
WORKLOAD = "bu-ist-demo-workload0"
SCOPE_FILES = (
    "hub.hosted_cluster_defaults",
    "hub.component_values",
    "hub.local_cluster_values",
    "hub.argocd_apps",
    "workload.hosted_cluster_values",
    "workload.component_values",
)
REGISTRY = EnvironmentRegistry.load(DEFAULT_REGISTRY_PATH)


def emitted_check_ids() -> set[str]:
    """Collect every check id the status code can emit, from the code itself."""

    ids = set(_NEXT_ACTIONS) | set(cross_module._CHECK_LABELS)
    pattern = re.compile(
        r"""["']((?:request|hub|workload)\.[a-z0-9_]+)["']"""
    )
    for module in (checks_module, cross_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        ids.update(pattern.findall(source))
    return ids


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
        required_components=REGISTRY.required_components("bu-ist-demo"),
        optional_components=REGISTRY.optional_components("bu-ist-demo"),
        keycloak_client="bu-ist-demo-infra",
        vlan_name="BU-IST-DEMO-WORKLOAD0",
        vlan_subnet="10.20.28.0/24",
    )


def status_report(client_class, name: str = "bu-ist-demo") -> dict:
    checker = StatusChecker(client=client_class(), include_prs=False)
    environment = Environment(
        name=name, issue_number=666, workload_clusters=(WORKLOAD,)
    )
    return checker.run(environment).to_dict()


class EmptyInventoryFakeClient(FullyConfiguredFakeGitHubClient):
    """Hub group exists but declares no hosts."""

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            return super().get_file(repository, path, ref).replace(
                """              hosts:
                control-0:
                  node_name: MOC-R4PAC10U31-S1A
""",
                """              hosts: {}
""",
            )
        return super().get_file(repository, path, ref)


REMOVED_PATHS = {
    "hosted-clusters/bu-ist-demo-infra/values.yaml",
    "values/bu-ist-demo-infra/hcp-config.yaml",
    "values/bu-ist-demo-infra/local-cluster/acm.yaml",
    "values/bu-ist-demo-infra/local-cluster/metallb.yaml",
    "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
    "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
    "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml",
}


class PartialPathFakeClient(FullyConfiguredFakeGitHubClient):
    """Same fixture with one or more required path-check files removed."""

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            for path in REMOVED_PATHS:
                tree.pop(path, None)
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if path in REMOVED_PATHS:
            raise AssertionError(f"removed path read: {path}")
        return super().get_file(repository, path, ref)


class CheckDescriptionCoverageTest(unittest.TestCase):
    def test_every_emitted_check_id_has_a_description(self) -> None:
        ids = emitted_check_ids()

        self.assertEqual(len(ids), 34, sorted(ids))
        self.assertEqual(set(CHECK_DESCRIPTIONS), ids)

    def test_descriptions_are_multi_sentence_and_render_cleanly(self) -> None:
        context = sample_context()
        for check_id in sorted(CHECK_DESCRIPTIONS):
            with self.subTest(check_id=check_id):
                verifies, not_verified = describe(check_id, context)
                self.assertGreaterEqual(len(_sentences(verifies)), 2, verifies)
                self.assertGreaterEqual(
                    len(_sentences(not_verified)), 1, not_verified
                )
                self.assertNotIn("{", verifies + not_verified)
                self.assertNotIn("}", verifies + not_verified)

    def test_markdown_rows_and_descriptions_match_check_count(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        markdown = render_markdown(report)
        checks = len(report["checks"])

        self.assertNotIn("| Field | Observed |", markdown)
        self.assertEqual(markdown.count("<details"), checks)
        self.assertEqual(markdown.count("Verifies:"), checks)
        self.assertEqual(markdown.count("Not verified:"), checks)
        self.assertEqual(
            markdown.count("| Field | Expected | Observed |"), checks
        )
        for block in _passing_detail_blocks(markdown):
            for expected in _expected_cells(block):
                self.assertNotIn(
                    expected.strip(), {"", "—", "-", "not found"}
                )

    def test_path_check_descriptions_name_repository_and_path(self) -> None:
        context = sample_context()
        expectations = {
            "hub.hosted_cluster_defaults": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/values.yaml",
            ),
            "hub.component_values": (
                "CCI-MOC/oac-apps",
                "values/bu-ist-demo-infra/hcp-config.yaml",
            ),
            "hub.local_cluster_values": (
                "CCI-MOC/oac-apps",
                "values/bu-ist-demo-infra/local-cluster/",
            ),
            "hub.argocd_apps": (
                "CCI-MOC/oac-apps",
                "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
            ),
            "workload.hosted_cluster_values": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
            ),
            "workload.component_values": (
                "CCI-MOC/oac-apps",
                "values/bu-ist-demo-infra/bu-ist-demo-workload0/",
            ),
        }
        for check_id, (repository, path) in expectations.items():
            with self.subTest(check_id=check_id):
                verifies, not_verified = describe(check_id, context)
                self.assertIn(repository, verifies)
                self.assertIn(path, verifies)
                self.assertIn("file contents are not read", not_verified.lower())

    def test_local_cluster_description_lists_registry_components(self) -> None:
        verifies, _ = describe("hub.local_cluster_values", sample_context())

        required = REGISTRY.required_components("bu-ist-demo")
        self.assertTrue(required)
        for name in required:
            self.assertIn(name, verifies)

    def test_text_and_json_carry_descriptions_for_every_check(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        text = render_text(report, details=True)
        payload = json.loads(render_json(report))
        checks = payload["checks"]

        self.assertEqual(text.count("Verifies:"), len(checks))
        self.assertEqual(text.count("Not verified:"), len(checks))
        for check in checks:
            self.assertTrue(check.get("verifies"), check["id"])
            self.assertTrue(check.get("not_verified"), check["id"])

    def test_next_actions_name_the_repository_that_is_read(self) -> None:
        for check_id in ("hub.component_values", "hub.hosted_cluster_defaults"):
            with self.subTest(check_id=check_id):
                action = _NEXT_ACTIONS[check_id]
                self.assertIn("CCI-MOC/oac-apps", action)
                self.assertNotIn("oac-infra", action)


class FieldRowTest(unittest.TestCase):
    def test_inventory_with_zero_hosts_keeps_state_and_honest_rule(self) -> None:
        report = status_report(EmptyInventoryFakeClient)
        check = next(
            item for item in report["checks"] if item["id"] == "hub.inventory"
        )

        self.assertEqual(check["actual"]["host_count"], 0)
        self.assertEqual(check["state"], "declared_in_main")
        rows = {row[0]: row for row in field_rows(check)}
        self.assertNotIn("at least 1", rows["host_count"][1])
        self.assertIn("reported", rows["host_count"][1])

    def test_component_values_rows_name_each_matched_file(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.component_values"
        )
        rows = field_rows(check)
        labels = [row[0] for row in rows]

        self.assertIn(
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml", labels
        )
        rule = next(row for row in rows if "at least 1" in str(row[1]))
        self.assertIn(
            "values/bu-ist-demo-infra/bu-ist-demo-workload0", rule[0]
        )

    def test_address_uniqueness_rows_describe_this_workload(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.address_uniqueness"
        )
        rows = field_rows(check)

        self.assertTrue(rows)
        for field, expected, observed in rows:
            self.assertIn("no other cluster", expected.lower())
            self.assertNotIn("bu-ist-demo-workload0: ", str(observed))
        self.assertTrue(
            any("services.APIServer" in str(row[0]) for row in rows)
        )

    def test_identity_provider_shows_compared_values(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.identity_provider"
        )
        rows = field_rows(check)

        self.assertNotIn("matches", [row[2] for row in rows])
        self.assertTrue(any("openshift_redirect_uri" in str(row[0]) for row in rows))

    def test_oidc_cluster_row_states_prefixes_are_unconstrained(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.moc_aws_oidc_cluster"
        )
        rows = {row[0]: row for row in field_rows(check)}

        self.assertIn("not constrained", rows["eso_writable_secret_prefixes"][1])


class PathCheckReasonTest(unittest.TestCase):
    def test_passing_reasons_state_count_scope_and_are_honest(self) -> None:
        report = status_report(FullyConfiguredFakeGitHubClient)
        checks = {item["id"]: item for item in report["checks"]}

        for check_id in SCOPE_FILES:
            with self.subTest(check_id=check_id):
                check = checks[check_id]
                self.assertEqual(check["state"], "declared_in_main")
                reason = check["reason"]
                self.assertNotIn("All expected files for", reason)
                self.assertIn("contents are not read", reason.lower())
                scope = (
                    check["expected"]["scope"]
                    if isinstance(check["expected"], dict)
                    else check["path"]
                )
                self.assertIn(scope, reason)
                self.assertRegex(reason, r"\b\d+ (?:of \d+ required|files?)\b")

    def test_partial_reasons_name_every_missing_path(self) -> None:
        report = status_report(PartialPathFakeClient)
        checks = {item["id"]: item for item in report["checks"]}

        for check_id in SCOPE_FILES:
            with self.subTest(check_id=check_id):
                check = checks[check_id]
                self.assertIn(
                    check["state"], {"partial", "missing"}, check["reason"]
                )
                if check_id == "workload.component_values":
                    self.assertIn("at least 1 is required", check["reason"])
                    continue
                for path in check["missing"]["paths"]:
                    self.assertIn(path, check["reason"])


def _sentences(text: str) -> list[str]:
    return [item for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item]


def _passing_detail_blocks(markdown: str) -> list[str]:
    blocks = []
    for block in markdown.split("<details")[1:]:
        body = block.split("</details>", 1)[0]
        if body.startswith(" open>"):
            continue
        blocks.append(body)
    return blocks


def _expected_cells(block: str) -> list[str]:
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
        cells.append(line.strip("|").split("|")[1])
    return cells


if __name__ == "__main__":
    unittest.main()
