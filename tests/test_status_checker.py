from __future__ import annotations

import unittest

from moc_env.checks import StatusChecker
from moc_env.registry import EnvironmentRegistry
from moc_env.checks import StatusChecker
from moc_env.checks import list_environments
from moc_env.model import Environment
from moc_env.observed import (
    read_environment_observation,
    read_infra_observation,
)
from moc_env.report import render_markdown, render_text

from fakes import FakeGitHubClient


class StatusCheckerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = EnvironmentRegistry.load()
        self.required_components = self.registry.required_components(
            "bu-ist-demo"
        )

    def test_bu_ist_demo_milestone_one_states(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        report = StatusChecker(FakeGitHubClient()).run(environment).to_dict()

        states = {(check["check"], check["state"]) for check in report["checks"]}
        self.assertIn(("MOC issue", "requested"), states)
        self.assertIn(("bu-ist-demo-infra host inventory", "declared_in_main"), states)
        self.assertIn(("bu-ist-demo-workload0 host inventory", "declared_in_main"), states)
        self.assertIn(("bu-ist-demo-infra boot image", "partial"), states)
        self.assertIn(("Hub image variables", "declared_in_main"), states)
        self.assertIn(("Infra OIDC client", "declared_in_main"), states)
        self.assertIn(("Relevant pull requests", "pr_open"), states)
        self.assertEqual(report["overall_state"], "CONFIGURATION IN PROGRESS")
        for check in report["checks"]:
            self.assertNotIn("expected_paths", check.get("present") or {})

    def test_boot_image_checks_state_the_matching_rule(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        rules = [
            check["evidence"]["check_rule"]
            for check in report["checks"]
            if check["check"].endswith("boot image")
        ]
        self.assertEqual(len(rules), 2)
        self.assertIn("must contain the full cluster name", rules[0])
        self.assertIn("generic `discovery.iso`", rules[0])
        self.assertIn("parent hub name", rules[1])
        self.assertIn("generic `discovery.iso`", rules[1])

    def test_hub_status_includes_hub_checks_and_excludes_workload_checks(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run_hub(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        checks = {check["check"] for check in report["checks"]}

        self.assertEqual(report["scope"], "hub")
        self.assertIn("MOC issue", checks)
        self.assertIn("bu-ist-demo-infra host inventory", checks)
        self.assertIn("bu-ist-demo-infra boot image", checks)
        self.assertIn("Hub image variables", checks)
        self.assertIn("Infra OIDC client", checks)
        self.assertIn("Infra local-cluster values", checks)
        self.assertIn("Relevant pull requests", checks)
        self.assertNotIn("bu-ist-demo-workload0 host inventory", checks)
        self.assertNotIn("Workload hosted-cluster values", checks)

    def test_work_status_includes_workload_checks_and_excludes_hub_checks(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run_workload(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        checks = {check["check"] for check in report["checks"]}

        self.assertEqual(report["scope"], "workload")
        self.assertIn("MOC issue", checks)
        self.assertIn("bu-ist-demo-workload0 host inventory", checks)
        self.assertIn("bu-ist-demo-workload0 boot image", checks)
        self.assertIn("Workload hosted-cluster values", checks)
        self.assertIn("Workload component values", checks)
        self.assertIn("Relevant pull requests", checks)
        self.assertNotIn("bu-ist-demo-infra host inventory", checks)
        self.assertNotIn("Hub image variables", checks)
        self.assertNotIn("Infra OIDC client", checks)

    def test_check_metadata_and_next_actions_are_machine_readable(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        checks = report["checks"]

        self.assertTrue(checks)
        for check in checks:
            with self.subTest(check=check["id"]):
                self.assertIn("id", check)
                self.assertIn(check["scope"], {"hub", "workload", "shared"})
                self.assertIn("next_action", check)
                if check["state"] in {"partial", "missing", "pr_open"}:
                    self.assertIsInstance(check["next_action"], str)
                    self.assertTrue(check["next_action"])
                else:
                    self.assertIsNone(check["next_action"])

        component_values = next(
            check for check in checks if check["id"] == "hub.component_values"
        )
        self.assertEqual(component_values["scope"], "hub")
        self.assertIn(
            "values/<hub>/hcp-config.yaml",
            component_values["next_action"],
        )
        self.assertNotIn(
            "Create the workload component-values directory",
            component_values["next_action"],
        )

    def test_environment_name_that_already_ends_in_infra_is_not_suffixed_again(self) -> None:
        environment = Environment(name="oac-prod-infra")
        self.assertEqual(environment.infra_cluster, "oac-prod-infra")
        self.assertEqual(environment.workload_cluster, "oac-prod-workload0")

    def test_environment_domain_override_is_reported(self) -> None:
        environment = Environment(
            name="oac-prod-infra",
            domain_override="infra.oac.ocp.massopen.cloud",
        )
        self.assertEqual(environment.domain, "infra.oac.ocp.massopen.cloud")
        self.assertEqual(environment.to_dict()["domain_source"], "repository")

    def test_boot_image_accepts_oac_shortened_workload_name(self) -> None:
        from moc_env.checks import _boot_image_state

        url = "http://10.2.0.82/boot/prod-workload0-agent-discovery.iso"
        self.assertEqual(
            _boot_image_state(url, "oac-prod-workload0"),
            "declared_in_main",
        )

    def test_list_environments_returns_hub_and_workload_clusters(self) -> None:
        environments = list_environments(FakeGitHubClient())
        self.assertEqual(len(environments), 2)
        self.assertEqual(
            environments[0],
            {
                "environment": "bu-ist-demo",
                "cluster": "bu-ist-demo-infra",
                "type": "hub",
                "status_command": "moc-env status-hub bu-ist-demo",
                "source_repository": "CCI-MOC/oac-infra",
                "source_path": "hub-images/inventory.yml",
            },
        )
        self.assertEqual(
            environments[1],
            {
                "environment": "bu-ist-demo",
                "cluster": "bu-ist-demo-workload0",
                "type": "workload",
                "status_command": (
                    "moc-env status-workload bu-ist-demo --workload workload0"
                ),
                "source_repository": "CCI-MOC/oac-infra",
                "source_path": "infra/inventory/00hosts.yaml",
            },
        )

    def test_read_infra_observation_normalizes_repository_inputs(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(FakeGitHubClient(), environment)

        self.assertEqual(observation.repository, "CCI-MOC/oac-infra")
        self.assertTrue(observation.inventory_present)
        self.assertTrue(observation.clusters["bu-ist-demo-infra"].group_found.value)
        self.assertTrue(observation.clusters["bu-ist-demo-workload0"].group_found.value)
        self.assertEqual(
            len(observation.clusters["bu-ist-demo-infra"].hosts.value),
            1,
        )
        self.assertTrue(observation.hub_inventory.cluster_key_present.value)
        self.assertEqual(
            observation.hub_variables.values.value["api_ip"],
            "10.20.27.11",
        )

    def test_read_environment_observation_normalizes_all_phase_one_sources(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_environment_observation(FakeGitHubClient(), environment)

        self.assertEqual(observation.issue.state.value, "open")
        self.assertEqual(observation.issue.state.confidence, "exact")
        self.assertEqual(
            observation.keycloak.client.cluster_name.value,
            "bu-ist-demo-infra",
        )
        self.assertEqual(
            observation.keycloak.client.secret_name.value,
            "cluster/bu-ist-demo-infra/keycloak-oidc",
        )
        self.assertEqual(observation.apps.pull_requests[0].number.value, 237)
        self.assertEqual(
            observation.apps.pull_requests[0].changed_files.value,
            ("values/bu-ist-demo-infra/hcp-config.yaml",),
        )
        self.assertEqual(observation.infra_cluster.cluster.value, "bu-ist-demo-infra")
        self.assertEqual(
            observation.workload_cluster.inventory.cluster.value,
            "bu-ist-demo-workload0",
        )

    def test_read_environment_observation_handles_missing_keycloak(self) -> None:
        class MissingKeycloakClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/moc-keycloak":
                    return {}
                return super().get_tree(repository, ref)

        observation = read_environment_observation(
            MissingKeycloakClient(),
            Environment(name="bu-ist-demo", issue_number=666),
        )
        self.assertFalse(observation.keycloak.path_present.value)
        self.assertIsNone(observation.keycloak.client)

    def test_keycloak_observation_reports_partial_declaration(self) -> None:
        class PartialKeycloakClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak":
                    return """
bu_ist_demo_infra = {
  cluster_name = "bu-ist-demo-infra"
  openshift_redirect_uri = "https://example.invalid/callback"
  client_secret_name = "cluster/wrong/keycloak-oidc"
}
"""
                return super().get_file(repository, path, ref)

        report = StatusChecker(PartialKeycloakClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Infra OIDC client"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(
            check["missing"]["fields"],
            ["redirect_uri", "secret_name"],
        )
        self.assertEqual(
            check["evidence"]["fields"]["redirect_uri"],
            {
                "expected": (
                    "https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud"
                    "/oauth2callback/mocsso"
                ),
                "observed": "https://example.invalid/callback",
                "status": "mismatch",
            },
        )
        self.assertIn(
            "openshift_redirect_uri = "
            "`https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud"
            "/oauth2callback/mocsso`",
            check["next_action"],
        )

    def test_keycloak_observation_reports_full_match(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Infra OIDC client"
        )

        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["reason"], "All expected Keycloak OIDC client fields match.")
        self.assertEqual(
            [result["status"] for result in check["evidence"]["fields"].values()],
            ["match", "match", "match"],
        )

    def test_keycloak_observation_reports_near_match_block_name(self) -> None:
        class DizzyKeycloakClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak":
                    return """
dizzy = {
  cluster_name = "dizzy"
  openshift_redirect_uri = "https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso"
  client_secret_name = "cluster/dizzy/keycloak-oidc"
}
"""
                return super().get_file(repository, path, ref)

        report = StatusChecker(DizzyKeycloakClient()).run(
            Environment(name="dizzy", workload_clusters=())
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Infra OIDC client"
        )

        self.assertEqual(check["state"], "partial")
        self.assertIn("near-match block `dizzy`", check["reason"])
        self.assertEqual(
            check["evidence"]["fields"]["client"],
            {
                "expected": "dizzy-infra",
                "observed": "dizzy",
                "status": "mismatch",
            },
        )
        self.assertIn(
            "client_secret_name = `cluster/dizzy-infra/keycloak-oidc`",
            check["next_action"],
        )

        text = render_text(report)
        markdown = render_markdown(report)
        self.assertIn("Keycloak OIDC fields:", text)
        self.assertIn("| Field | Expected | Observed |", markdown)
        self.assertIn("cluster/dizzy/keycloak-oidc", text)
        self.assertIn("cluster/dizzy/keycloak-oidc", markdown)

    def test_status_checker_reports_missing_repository_files(self) -> None:
        class MissingRepositoryFilesClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository in {
                    "CCI-MOC/oac-infra",
                    "CCI-MOC/moc-keycloak",
                    "CCI-MOC/oac-apps",
                }:
                    return {}
                return super().get_tree(repository, ref)

            def pulls(self, repository, state="all"):
                return
                yield

        report = StatusChecker(MissingRepositoryFilesClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        states = {check["check"]: check["state"] for check in report["checks"]}

        self.assertEqual(states["bu-ist-demo-infra host inventory"], "missing")
        self.assertEqual(states["Hub image inventory"], "missing")
        self.assertEqual(states["Hub image variables"], "missing")
        self.assertEqual(states["Infra OIDC client"], "missing")
        self.assertEqual(states["Infra hosted-cluster defaults"], "missing")
        self.assertEqual(states["Hub-wide component values"], "missing")
        self.assertEqual(states["Infra local-cluster values"], "missing")
        self.assertEqual(states["Infra ArgoCD applications"], "missing")
        self.assertEqual(states["Relevant pull requests"], "missing")
        self.assertEqual(
            report["environment"]["workload_notice"],
            "No workload cluster is declared for this hub.",
        )

    def test_status_checker_reports_partial_repository_files(self) -> None:
        class PartialRepositoryFilesClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return """
all:
  children:
    bu_ist_demo_infra:
      vars:
        cluster: bu-ist-demo-infra
      children:
        controller:
          hosts:
            control-0:
              node_name: MOC-R4PAC10U31-S1A
"""
                if repository == "CCI-MOC/oac-infra" and path == "hub-images/inventory.yml":
                    return "all:\n  children:\n"
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "hub-images/group_vars/bu-ist-demo-infra/vars.yml"
                ):
                    return "cluster_domain_name: bu-ist-demo\nbase_domain: int.massopen.cloud\n"
                return super().get_file(repository, path, ref)

            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    return {
                        "values/bu-ist-demo-infra/local-cluster/acm.yaml": {
                            "path": "values/bu-ist-demo-infra/local-cluster/acm.yaml",
                        },
                    }
                return super().get_tree(repository, ref)

        report = StatusChecker(PartialRepositoryFilesClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        states = {check["check"]: check["state"] for check in report["checks"]}

        self.assertEqual(states["bu-ist-demo-workload0 host inventory"], "partial")
        self.assertEqual(states["Hub image inventory"], "partial")
        self.assertEqual(states["Hub image variables"], "partial")
        self.assertEqual(states["Infra local-cluster values"], "partial")
        self.assertEqual(states["Relevant pull requests"], "pr_open")

    def test_infra_observation_accepts_inventory_without_all_root(self) -> None:
        class DirectInventoryClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return """
bu_ist_demo_infra:
  vars:
    cluster: bu-ist-demo-infra
  children:
    controller:
      vars:
        boot_image_url: http://example.invalid/infra-agent-discovery.iso
      hosts:
        control-0:
          node_name: control-0
"""
                return super().get_file(repository, path, ref)

        observation = read_infra_observation(
            DirectInventoryClient(),
            Environment(name="bu-ist-demo", issue_number=666),
        )
        cluster = observation.clusters["bu-ist-demo-infra"]
        self.assertTrue(cluster.group_found.value)
        self.assertEqual(cluster.boot_image_urls, ["http://example.invalid/infra-agent-discovery.iso"])

    def test_infra_observation_marks_unsupported_yaml_shapes(self) -> None:
        class UnsupportedYamlClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/oac-infra":
                    if path == "infra/inventory/00hosts.yaml":
                        return "- inventory\n"
                    if path == "hub-images/inventory.yml":
                        return "- hub\n"
                    if path == "hub-images/group_vars/bu-ist-demo-infra/vars.yml":
                        return "- values\n"
                return super().get_file(repository, path, ref)

        observation = read_infra_observation(
            UnsupportedYamlClient(),
            Environment(name="bu-ist-demo", issue_number=666),
        )
        self.assertTrue(observation.inventory_present.value)
        self.assertEqual(observation.inventory_present.confidence, "unsupported")
        self.assertTrue(observation.hub_inventory.inventory_present.value)
        self.assertEqual(
            observation.hub_inventory.inventory_present.confidence,
            "unsupported",
        )
        self.assertEqual(observation.hub_variables.values.value, {})
        self.assertEqual(observation.hub_variables.values.confidence, "unsupported")

    def test_status_checker_reports_closed_issue(self) -> None:
        class ClosedIssueClient(FakeGitHubClient):
            def get_json(self, path_or_url):
                if path_or_url == "/repos/CCI-MOC/MOC-issues/issues/666":
                    return {
                        "state": "closed",
                        "title": "RH HW Request - IS&T Tester cluster",
                        "html_url": "https://github.com/CCI-MOC/MOC-issues/issues/666",
                    }
                return super().get_json(path_or_url)

        report = StatusChecker(ClosedIssueClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(item for item in report["checks"] if item["check"] == "MOC issue")
        self.assertEqual(check["state"], "missing")

    def test_status_checker_reports_merged_pull_request(self) -> None:
        class MergedPullRequestClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository != "CCI-MOC/oac-apps":
                    return
                yield {
                    "number": 237,
                    "title": "Added initial values for bu-ist-demo infra cluster",
                    "body": None,
                    "state": "closed",
                    "merged_at": "2026-11-11T00:00:00Z",
                    "head": {
                        "ref": "bu-ist-demo-buildout",
                        "sha": "7b528394600996dae5c1e5d497236050d8810edc",
                    },
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/237",
                }

        report = StatusChecker(MergedPullRequestClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Relevant pull requests"
        )
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["actual"]["merged_count"], 1)

    def test_pull_request_body_match_alone_is_not_relevant(self) -> None:
        class UnrelatedPullRequestClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository != "CCI-MOC/oac-apps":
                    return
                yield {
                    "number": 999,
                    "title": "Unrelated chart update",
                    "body": "This mentions oac-prod but does not change it.",
                    "state": "open",
                    "merged_at": None,
                    "updated_at": "2026-11-16T00:00:00Z",
                    "head": {"ref": "unrelated", "sha": "abc123"},
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/999",
                }

            def pr_files(self, repository, number):
                yield {"filename": "values/oac-dev-infra/example.yaml"}

        report = StatusChecker(UnrelatedPullRequestClient()).run(
            Environment(name="oac-prod", workload_clusters=())
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Relevant pull requests"
        )

        self.assertEqual(check["state"], "missing")
        self.assertEqual(check["actual"]["matching_pr_count"], 0)
        self.assertNotIn("pr_open", report["summary"]["state_counts"])

    def test_pull_requests_classify_closed_unmerged_and_counts_add_up(self) -> None:
        class ClassifiedPullRequestClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository != "CCI-MOC/oac-apps":
                    return
                yield {
                    "number": 1,
                    "title": "Open",
                    "body": None,
                    "state": "open",
                    "merged_at": None,
                    "updated_at": "2026-11-16T03:00:00Z",
                    "head": {"ref": "open", "sha": "abc123"},
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/1",
                }
                yield {
                    "number": 2,
                    "title": "Merged",
                    "body": None,
                    "state": "closed",
                    "merged_at": "2026-11-15T00:00:00Z",
                    "updated_at": "2026-11-15T00:00:00Z",
                    "head": {"ref": "merged", "sha": "def456"},
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/2",
                }
                yield {
                    "number": 3,
                    "title": "Closed without merge",
                    "body": None,
                    "state": "closed",
                    "merged_at": None,
                    "updated_at": "2026-11-14T00:00:00Z",
                    "head": {"ref": "closed", "sha": "789012"},
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/3",
                }

            def pr_files(self, repository, number):
                yield {
                    "filename": f"values/bu-ist-demo-infra/pr-{number}.yaml"
                }

        report = StatusChecker(ClassifiedPullRequestClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Relevant pull requests"
        )

        actual = check["actual"]
        self.assertEqual(actual["matching_pr_count"], 3)
        self.assertEqual(actual["open_count"], 1)
        self.assertEqual(actual["merged_count"], 1)
        self.assertEqual(actual["closed_unmerged_count"], 1)
        self.assertEqual(
            actual["open_count"]
            + actual["merged_count"]
            + actual["closed_unmerged_count"],
            actual["matching_pr_count"],
        )
        self.assertEqual(
            [item["classification"]["value"] for item in check["evidence"]["pull_requests"]],
            ["open", "merged", "closed_unmerged"],
        )

    def test_workload_only_pull_request_is_not_hub_work(self) -> None:
        class WorkloadOnlyPullRequestClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository != "CCI-MOC/oac-apps":
                    return
                yield {
                    "number": 900,
                    "title": "Workload-only change",
                    "body": None,
                    "state": "open",
                    "merged_at": None,
                    "updated_at": "2026-11-16T00:00:00Z",
                    "head": {"ref": "workload", "sha": "abc123"},
                    "html_url": "https://github.com/CCI-MOC/oac-apps/pull/900",
                }

            def pr_files(self, repository, number):
                yield {
                    "filename": (
                        "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml"
                    )
                }

        environment = Environment(
            name="bu-ist-demo",
            issue_number=666,
            workload_clusters=("bu-ist-demo-workload0",),
        )
        checker = StatusChecker(WorkloadOnlyPullRequestClient())
        hub_report = checker.run_hub(environment).to_dict()
        workload_report = checker.run_workload(environment).to_dict()

        hub_check = next(
            item
            for item in hub_report["checks"]
            if item["check"] == "Relevant pull requests"
        )
        workload_check = next(
            item
            for item in workload_report["checks"]
            if item["check"] == "Relevant pull requests"
        )
        self.assertEqual(hub_check["state"], "missing")
        self.assertEqual(workload_check["state"], "pr_open")

    def test_closed_pull_request_file_fetches_are_limited_to_recent_twenty(self) -> None:
        class LimitedPullRequestClient(FakeGitHubClient):
            def __init__(self):
                super().__init__()
                self.requested_files = []

            def pulls(self, repository, state="all"):
                if repository != "CCI-MOC/oac-apps":
                    return
                for number in range(25):
                    yield {
                        "number": number,
                        "title": f"Closed PR {number}",
                        "body": None,
                        "state": "closed",
                        "merged_at": None,
                        "updated_at": (
                            f"2026-11-{number + 1:02d}T00:00:00Z"
                        ),
                        "head": {"ref": f"closed-{number}", "sha": "abc123"},
                        "html_url": (
                            "https://github.com/CCI-MOC/oac-apps/pull/"
                            f"{number}"
                        ),
                    }

            def pr_files(self, repository, number):
                self.requested_files.append(number)
                yield {"filename": "values/bu-ist-demo-infra/example.yaml"}

        client = LimitedPullRequestClient()
        report = StatusChecker(client).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()

        self.assertEqual(len(client.requested_files), 20)
        self.assertEqual(sorted(client.requested_files), list(range(5, 25)))
        check = next(
            item for item in report["checks"] if item["check"] == "Relevant pull requests"
        )
        self.assertEqual(check["actual"]["matching_pr_count"], 20)

    def test_status_checker_reports_declared_apps_paths(self) -> None:
        required_components = self.required_components

        class DeclaredAppsClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    paths = {
                        "hosted-clusters/bu-ist-demo-infra/values.yaml",
                        "values/bu-ist-demo-infra/hcp-config.yaml",
                        "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
                        "hosted-clusters/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/values.yaml",
                        "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml",
                    }
                    paths.update(
                        f"values/bu-ist-demo-infra/local-cluster/{name}"
                        for name in required_components
                    )
                    return {path: {"path": path} for path in paths}
                return super().get_tree(repository, ref)

        report = StatusChecker(DeclaredAppsClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        states = {check["check"]: check["state"] for check in report["checks"]}
        self.assertEqual(states["Infra hosted-cluster defaults"], "declared_in_main")
        self.assertEqual(states["Hub-wide component values"], "declared_in_main")
        self.assertEqual(states["Infra local-cluster values"], "declared_in_main")
        self.assertEqual(states["Infra ArgoCD applications"], "declared_in_main")
        self.assertEqual(states["Workload hosted-cluster values"], "declared_in_main")
        self.assertEqual(states["Workload component values"], "declared_in_main")

    def test_optional_component_absence_is_advisory(self) -> None:
        optional_component = "user-workload-monitoring.yaml"
        required_components = tuple(
            name
            for name in self.required_components
            if name != optional_component
        )
        registry = EnvironmentRegistry.from_document(
            {
                "defaults": {
                    "required_local_cluster_components": required_components,
                    "optional_local_cluster_components": [optional_component],
                },
                "environments": {
                    "bu-ist-demo": {
                        "issue": 666,
                        "required_local_cluster_components": list(
                            required_components
                        ),
                        "optional_local_cluster_components": [optional_component],
                    }
                },
            }
        )

        class OptionalComponentClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    content = content.replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/boot/"
                        "bu-ist-demo-infra-agent-discovery.iso",
                        1,
                    )
                    content = content.replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/boot/"
                        "bu-ist-demo-workload0-agent-discovery.iso",
                        1,
                    )
                return content

            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    paths = {
                        "hosted-clusters/bu-ist-demo-infra/values.yaml",
                        "values/bu-ist-demo-infra/hcp-config.yaml",
                        "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
                        "hosted-clusters/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/values.yaml",
                        "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml",
                    }
                    paths.update(
                        f"values/bu-ist-demo-infra/local-cluster/{name}"
                        for name in required_components
                    )
                    return {path: {"path": path} for path in paths}
                return super().get_tree(repository, ref)

        report = StatusChecker(
            OptionalComponentClient(),
            include_prs=False,
            registry=registry,
        ).run(Environment(name="bu-ist-demo", issue_number=666)).to_dict()
        check = next(
            item for item in report["checks"]
            if item["check"] == "Infra local-cluster values"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "advisory")
        self.assertEqual(report["summary"]["advisory_count"], 1)
        self.assertEqual(report["overall_state"], "DECLARED IN MAIN")

    def test_generic_hub_boot_image_with_later_evidence_is_advisory(self) -> None:
        required_components = self.required_components

        class DeclaredAppsClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    paths = {
                        "hosted-clusters/bu-ist-demo-infra/values.yaml",
                        "values/bu-ist-demo-infra/hcp-config.yaml",
                        "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
                        "hosted-clusters/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/values.yaml",
                        "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml",
                    }
                    paths.update(
                        f"values/bu-ist-demo-infra/local-cluster/{name}"
                        for name in required_components
                    )
                    return {path: {"path": path} for path in paths}
                return super().get_tree(repository, ref)

        report = StatusChecker(
            DeclaredAppsClient(),
            include_prs=False,
        ).run(Environment(name="bu-ist-demo", issue_number=666)).to_dict()
        check = next(
            item for item in report["checks"]
            if item["check"] == "bu-ist-demo-infra boot image"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "advisory")
        self.assertEqual(report["overall_state"], "DECLARED IN MAIN")

    def test_status_checker_reports_keycloak_block_for_other_cluster(self) -> None:
        class OtherKeycloakClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
                    return """
other_infra = {
  cluster_name = "other-infra"
  openshift_redirect_uri = "https://example.invalid/callback"
  client_secret_name = "cluster/other-infra/keycloak-oidc"
}
"""
                return super().get_file(repository, path, ref)

        report = StatusChecker(OtherKeycloakClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(item for item in report["checks"] if item["check"] == "Infra OIDC client")
        self.assertEqual(check["state"], "missing")
        self.assertEqual(check["reason"], "No Keycloak OIDC client block exists for this hub.")
        self.assertEqual(
            [result["status"] for result in check["evidence"]["fields"].values()],
            ["absent", "absent", "absent"],
        )

    def test_registry_can_override_keycloak_client_name(self) -> None:
        registry = EnvironmentRegistry.from_document(
            {
                "defaults": {
                    "required_local_cluster_components": list(
                        self.required_components
                    ),
                    "optional_local_cluster_components": [],
                },
                "environments": {
                    "bu-ist-demo": {
                        "issue": 666,
                        "keycloak_client_name": "custom-oidc-client",
                    }
                },
            }
        )

        class CustomKeycloakClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
                    return """
custom_client = {
  cluster_name = "custom-oidc-client"
  openshift_redirect_uri = "https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso"
  client_secret_name = "cluster/bu-ist-demo-infra/keycloak-oidc"
}
"""
                return super().get_file(repository, path, ref)

        report = StatusChecker(
            CustomKeycloakClient(),
            include_prs=False,
            registry=registry,
        ).run(Environment(name="bu-ist-demo", issue_number=666)).to_dict()
        check = next(
            item for item in report["checks"] if item["check"] == "Infra OIDC client"
        )
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["expected"]["client"], "custom-oidc-client")

    def test_status_checker_reports_boot_image_check_states(self) -> None:
        def boot_states(urls):
            class BootImageClient(FakeGitHubClient):
                def get_file(self, repository, path, ref="main"):
                    if (
                        repository == "CCI-MOC/oac-infra"
                        and path == "infra/inventory/00hosts.yaml"
                    ):
                        groups = "".join(
                            f"""
          group{index}:
            vars:
              boot_image_url: {url}
            hosts:
              node{index}:
                node_name: node-{index}
"""
                            for index, url in enumerate(urls)
                        )
                        return f"""
all:
  children:
    bu_ist_demo_infra:
      vars:
        cluster: bu-ist-demo-infra
      children:{groups}
"""
                    return super().get_file(repository, path, ref)

            report = StatusChecker(BootImageClient()).run(
                Environment(name="bu-ist-demo", issue_number=666)
            ).to_dict()
            return next(
                item
                for item in report["checks"]
                if item["check"] == "bu-ist-demo-infra boot image"
            )

        self.assertEqual(
            boot_states(["http://example.invalid/other.iso"])["state"],
            "partial",
        )
        self.assertEqual(
            boot_states(
                [
                    "http://example.invalid/one.iso",
                    "http://example.invalid/two.iso",
                ]
            )["state"],
            "partial",
        )
        self.assertEqual(
            boot_states(["http://example.invalid/bu-ist-demo-infra-agent.iso"])["state"],
            "declared_in_main",
        )

    def test_workload_boot_image_accepts_parent_hub_image(self) -> None:
        class WorkloadBootImageClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return content.replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/boot/"
                        "bu-ist-demo-infra-agent-discovery.iso",
                        1,
                    ).replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/boot/"
                        "bu-ist-demo-infra-agent-discovery.iso",
                        1,
                    )
                return content

        report = StatusChecker(WorkloadBootImageClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["check"] == "bu-ist-demo-workload0 boot image"
        )
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "info")

    def test_workload_generic_boot_image_is_a_named_gap(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["check"] == "bu-ist-demo-workload0 boot image"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "blocking")
        self.assertIn("still on the generic discovery.iso", check["reason"])
        self.assertIn("bu-ist-demo-infra-agent-discovery.iso", check["reason"])

    def test_workload_unrecognized_boot_image_name_is_advisory(self) -> None:
        class UnrecognizedBootImageClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return content.replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/boot/"
                        "bu-ist-demo-infra-agent-discovery.iso",
                        1,
                    ).replace(
                        "http://10.2.0.82/boot/discovery.iso",
                        "http://10.2.0.82/dev-workload-agent.iso",
                        1,
                    )
                return content

        report = StatusChecker(UnrecognizedBootImageClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["check"] == "bu-ist-demo-workload0 boot image"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "advisory")
        self.assertIn("dev-workload-agent.iso", check["reason"])

    def test_workload_agent_labels_missing_resource_class_is_partial(self) -> None:
        class MissingResourceClassClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return content.replace(
                        "bm_management: ipmi\n"
                        "                  mac_addr: 00:11:22:33:44:55\n"
                        "                  resource_class: bu-ist-demo-worker",
                        "bm_management: bmc\n"
                        "                  mac_addr: 00:11:22:33:44:55",
                    )
                return content

        report = StatusChecker(MissingResourceClassClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.agent_labels_inputs"
        )
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "blocking")
        self.assertEqual(
            check["missing"]["hosts"], {"compute-0": ["resource_class"]}
        )
        self.assertIn("infra/update-agents.yaml", check["next_action"])
        self.assertIn("compute-0", check["next_action"])
        self.assertIn("resource_class", check["next_action"])
        self.assertIn("NodePool", check["next_action"])
        text_report = render_text(report)
        markdown_report = render_markdown(report)
        self.assertIn("Agent label inputs:", text_report)
        self.assertIn("bm_management", text_report)
        self.assertIn("MISSING", text_report)
        self.assertIn("Agent label inputs", markdown_report)
        self.assertIn("| `compute-0` | `bmc` |", markdown_report)

    def test_workload_agent_labels_skips_openstack_hosts(self) -> None:
        class OpenStackHostClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return content.replace(
                        "bm_management: ipmi\n"
                        "                  mac_addr: 00:11:22:33:44:55\n"
                        "                  resource_class: bu-ist-demo-worker",
                        "bm_management: openstack",
                    )
                return content

        report = StatusChecker(OpenStackHostClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.agent_labels_inputs"
        )
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "info")
        self.assertIn("openstack", check["reason"])
        self.assertEqual(check["evidence"]["openstack_hosts_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
