from __future__ import annotations

import json
import unittest
from pathlib import Path

from moc_env.checks import StatusChecker
from moc_env.registry import EnvironmentRegistry
from moc_env.checks import StatusChecker
from moc_env.checks import list_environments
from moc_env.model import Environment
from moc_env.github import GitHubError, RateLimitError
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

    def test_pull_request_failures_preserve_configuration_report(self) -> None:
        for failure in (GitHubError("502 bad gateway"), RateLimitError("quota exhausted")):
            with self.subTest(failure=str(failure)):
                class UnavailablePullsClient(FakeGitHubClient):
                    def pulls(self, repository, state="all"):
                        raise failure

                report = StatusChecker(UnavailablePullsClient()).run(
                    Environment(name="bu-ist-demo", issue_number=666)
                )
                self.assertFalse(report.rate_limited)
                self.assertTrue(report.checks)
                self.assertIn(str(failure), report.pull_requests_unavailable)
                self.assertIn("CCI-MOC/oac-apps", report.to_dict()["pull_requests_unavailable"])

    def test_pull_request_file_failure_is_nonfatal(self) -> None:
        class UnavailableFilesClient(FakeGitHubClient):
            def pr_files(self, repository, number):
                raise GitHubError("PR files unavailable")

        report = StatusChecker(UnavailableFilesClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        )
        self.assertTrue(report.checks)
        self.assertFalse(report.rate_limited)
        self.assertIn("PR files unavailable", report.pull_requests_unavailable)

    def test_malformed_pull_records_are_nonfatal(self) -> None:
        cases = (
            None,
            {},
            {"number": [], "state": "open"},
            {"number": 246, "state": "open", "head": []},
        )
        for record in cases:
            with self.subTest(record=record):
                class MalformedPullsClient(FakeGitHubClient):
                    def pulls(self, repository, state="all"):
                        yield record

                report = StatusChecker(MalformedPullsClient()).run(
                    Environment(name="bu-ist-demo", issue_number=666)
                )
                self.assertTrue(report.checks)
                self.assertFalse(report.rate_limited)
                self.assertIn("Malformed pull-request record", report.pull_requests_unavailable)

    def test_malformed_pull_file_records_are_nonfatal(self) -> None:
        for record in (None, {}, {"filename": []}):
            with self.subTest(record=record):
                class MalformedFilesClient(FakeGitHubClient):
                    def pr_files(self, repository, number):
                        yield record

                report = StatusChecker(MalformedFilesClient()).run(
                    Environment(name="bu-ist-demo", issue_number=666)
                )
                self.assertTrue(report.checks)
                self.assertFalse(report.rate_limited)
                self.assertIn("Malformed pull-request file record", report.pull_requests_unavailable)

    def test_disabled_pull_lookup_is_recorded_without_request(self) -> None:
        class NoPullsClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                self.fail("pull-request lookup must be skipped")

        report = StatusChecker(NoPullsClient(), include_prs=False).run(
            Environment(name="bu-ist-demo", issue_number=666)
        )
        self.assertTrue(report.pull_requests_skipped)
        self.assertEqual(report.pull_requests_skip_reason, "skipped (--no-prs)")

    def test_check_refs_and_urls_use_repository_override(self) -> None:
        report = StatusChecker(
            FakeGitHubClient(refs={"CCI-MOC/oac-apps": "pull/246/head"}),
            include_prs=False,
        ).run(Environment(name="bu-ist-demo", issue_number=666))
        app_checks = [check for check in report.checks if check.repository == "CCI-MOC/oac-apps"]
        self.assertTrue(app_checks)
        for check in app_checks:
            self.assertEqual(check.ref, "pull/246/head")
            self.assertIn("/blob/pull/246/head/", check.url)

    def test_bu_ist_demo_milestone_one_states(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        report = StatusChecker(FakeGitHubClient()).run(environment).to_dict()

        states = {(check["check"], check["state"]) for check in report["checks"]}
        self.assertIn(("MOC issue", "requested"), states)
        self.assertIn(("bu-ist-demo-infra host inventory", "declared_in_main"), states)
        self.assertIn(("bu-ist-demo-workload0 host inventory", "declared_in_main"), states)
        self.assertIn(("bu-ist-demo-infra boot image", "partial"), states)
        self.assertIn(("Hub image variables", "declared_in_main"), states)
        self.assertIn(("Hub OIDC client", "declared_in_main"), states)
        self.assertTrue(report["pull_requests"])
        self.assertNotIn("pull_requests", {check["id"] for check in report["checks"]})
        self.assertEqual(report["overall_state"], "CONFIGURATION IN PROGRESS")
        for check in report["checks"]:
            self.assertNotIn("expected_paths", check.get("present") or {})

    def test_oac_prod_fixture_has_zero_gaps_and_no_unknowns(self) -> None:
        with Path("tests/fixtures/oac-prod-status.json").open(
            encoding="utf-8"
        ) as fixture:
            report = json.load(fixture)

        self.assertEqual(report["overall_state"], "DECLARED IN MAIN")
        self.assertEqual(
            report["summary"]["severity_counts"], {"info": 14}
        )
        self.assertNotIn("unknown", report["summary"]["state_counts"])
        self.assertEqual(report["summary"]["check_count"], 14)

    def test_full_oac_prod_fixture_has_zero_gaps_and_no_unknowns(self) -> None:
        with Path("tests/fixtures/oac-prod-full-status.json").open(
            encoding="utf-8"
        ) as fixture:
            report = json.load(fixture)

        self.assertIn(
            "oac-prod-workload0", report["environment"]["workload_clusters"]
        )
        self.assertEqual(report["overall_state"], "DECLARED IN MAIN")
        self.assertNotIn("unknown", report["summary"]["state_counts"])
        self.assertEqual(
            report["summary"]["severity_counts"],
            {"info": report["summary"]["check_count"]},
        )

    def test_workload_checks_are_mapped_to_workload_phase_rows(self) -> None:
        report = StatusChecker(FakeGitHubClient(), include_prs=False).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        workload_phases = {
            phase["phase"] for phase in report["phases"]["workload"]
        }
        workload_checks = [
            check for check in report["checks"] if check["scope"] == "workload"
        ]
        self.assertTrue(workload_checks)
        self.assertTrue(
            all(check["phase"] in workload_phases for check in workload_checks)
        )
        rendered = render_text(report)
        workload_table = rendered.split("WORKLOAD PHASES", 1)[1].split(
            "NEXT", 1
        )[0]
        for phase in workload_phases:
            phase_checks = [
                check
                for check in workload_checks
                if check["phase"] == phase
            ]
            row = next(
                line for line in workload_table.splitlines()
                if line.startswith(f"{phase} ")
            )
            if phase_checks:
                self.assertNotIn("–", row)
                self.assertNotIn("[--]", row)

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
        self.assertIn("Hub OIDC client", checks)
        self.assertIn("Hub local-cluster values", checks)
        self.assertNotIn("pull_requests", {check["id"] for check in report["checks"]})
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
        self.assertNotIn("pull_requests", {check["id"] for check in report["checks"]})
        self.assertNotIn("bu-ist-demo-infra host inventory", checks)
        self.assertNotIn("Hub image variables", checks)
        self.assertNotIn("Hub OIDC client", checks)

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
                if check["state"] in {"partial", "missing", "pr_open", "unknown"}:
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

    def test_checks_have_ordered_deployment_phase_metadata(self) -> None:
        report = StatusChecker(FakeGitHubClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        checks = report["checks"]
        by_id = {check["id"]: check for check in checks}

        self.assertTrue(checks)
        for check in checks:
            with self.subTest(check=check["id"]):
                self.assertIsInstance(check["phase"], int)
                self.assertIsInstance(check["phase_title"], str)
                self.assertIsInstance(check["blocked_by"], list)

        self.assertEqual(by_id["hub.inventory"]["phase"], 1)
        self.assertEqual(by_id["hub.image_inventory"]["phase"], 2)
        self.assertEqual(by_id["hub.boot_image"]["phase"], 3)
        self.assertEqual(by_id["hub.oidc_client"]["phase"], 4)
        self.assertEqual(by_id["hub.argocd_apps"]["phase"], 5)
        self.assertEqual(
            by_id["hub.image_inventory"]["blocked_by"], ["hub.inventory"]
        )
        self.assertEqual(
            by_id["workload.hosted_cluster_values"]["blocked_by"],
            ["hub.hosted_cluster_defaults"],
        )

        scope_order = {"hub": 0, "workload": 1, "shared": 2}
        order = [
            (scope_order[check["scope"]], check["phase"]) for check in checks
        ]
        self.assertEqual(order, sorted(order))

    def test_empty_hub_current_phase_and_json_metadata(self) -> None:
        class EmptyRepositoryClient(FakeGitHubClient):
            def get_tree(self, repository: str, ref: str = "main"):
                return {}

        report = StatusChecker(
            EmptyRepositoryClient(),
            include_prs=False,
        ).run_hub(Environment(name="bu-ist-demo")).to_dict()

        self.assertEqual(report["current_phase"], 1)
        checks = {check["id"]: check for check in report["checks"]}
        self.assertEqual(checks["hub.inventory"]["state"], "missing")
        self.assertEqual(checks["hub.inventory"]["blocked_by"], [])
        self.assertEqual(
            checks["hub.image_inventory"]["blocked_by"], ["hub.inventory"]
        )

        rendered = json.dumps(report)
        for field in ("phase", "phase_title", "blocked_by", "current_phase"):
            self.assertIn(field, rendered)

    def test_not_checked_entries_are_scoped_and_cluster_specific(self) -> None:
        checker = StatusChecker(FakeGitHubClient(), include_prs=False)
        environment = Environment(name="bu-ist-demo", issue_number=666)

        hub = checker.run_hub(environment).to_dict()
        workload = checker.run_workload(environment).to_dict()

        self.assertTrue(hub["not_checked"])
        workload_titles = [entry["title"] for entry in workload["not_checked"]]
        self.assertIn("Agents visible in hardware-inventory", workload_titles)
        self.assertIn("Agents labelled and approved", workload_titles)
        for entry in workload["not_checked"]:
            with self.subTest(workload_entry=entry["title"]):
                self.assertEqual(
                    entry["where"]["document"],
                    "docs/workload-cluster-deployment.md",
                )
        for entry in hub["not_checked"]:
            with self.subTest(entry=entry["title"]):
                self.assertIn("bu-ist-demo-infra", entry["title"])
                self.assertNotIn("<cluster>", entry["title"])
                self.assertNotIn("<cluster>", entry["why"])
                self.assertEqual(
                    entry["where"]["document"],
                    "docs/infra-cluster-deployment.md",
                )
                self.assertIn(entry["where"]["heading"], {
                    "Infrastructure Configuration",
                    "Cluster Deployment",
                    "Cluster Configuration",
                })

    def test_workload_sequence_uses_oac_apps_deployment_guide(self) -> None:
        report = StatusChecker(FakeGitHubClient(), include_prs=False).run_workload(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()

        phases = report["phases"]
        self.assertEqual(
            [phase["title"] for phase in phases],
            [
                "Host inventory entry",
                "Hub agent discovery ISO",
                "Agent ISO boot",
                "Agent visibility",
                "Agent labels and approval",
                "oac-apps values",
                "Shared-service prerequisites",
            ],
        )
        for phase in phases:
            with self.subTest(phase=phase["title"]):
                self.assertEqual(
                    phase["guide"]["document"],
                    "docs/workload-cluster-deployment.md",
                )

        checks = {check["id"]: check for check in report["checks"]}
        self.assertEqual(checks["workload.inventory"]["phase"], 1)
        self.assertEqual(checks["workload.boot_image"]["phase"], 2)
        self.assertEqual(checks["workload.agent_labels_inputs"]["phase"], 5)
        self.assertEqual(checks["workload.hosted_cluster_values"]["phase"], 6)
        self.assertEqual(checks["workload.pure_storage_realm"]["phase"], 7)

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
            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak":
                    raise GitHubError("GitHub raw download failed (404) for main.tf")
                return super().get_file(repository, path, ref)

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
            item for item in report["checks"] if item["check"] == "Hub OIDC client"
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
            item for item in report["checks"] if item["check"] == "Hub OIDC client"
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
            item for item in report["checks"] if item["check"] == "Hub OIDC client"
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

        text = render_text(report, details=True)
        markdown = render_markdown(report)
        self.assertIn("Expected", text)
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

            def get_file(self, repository, path, ref="main"):
                if repository == "CCI-MOC/moc-keycloak":
                    raise GitHubError("GitHub raw download failed (404) for main.tf")
                return super().get_file(repository, path, ref)

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
        self.assertEqual(states["Hub OIDC client"], "missing")
        self.assertEqual(states["Hub hosted-cluster defaults"], "missing")
        self.assertEqual(states["Hub-wide component values"], "missing")
        self.assertEqual(states["Hub local-cluster values"], "missing")
        self.assertEqual(states["Hub ArgoCD applications"], "missing")
        self.assertEqual(report["pull_requests"], [])
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
        self.assertEqual(states["Hub local-cluster values"], "partial")
        self.assertTrue(report["pull_requests"])

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
        self.assertEqual(len(report["pull_requests"]), 1)
        self.assertEqual(
            report["pull_requests"][0]["classification"]["value"], "merged"
        )

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
        self.assertEqual(report["pull_requests"], [])
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
        pulls = report["pull_requests"]
        self.assertEqual(len(pulls), 3)
        self.assertEqual(
            [item["classification"]["value"] for item in pulls],
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

        self.assertEqual(hub_report["pull_requests"], [])
        self.assertEqual(len(workload_report["pull_requests"]), 1)
        self.assertEqual(
            workload_report["pull_requests"][0]["classification"]["value"], "open"
        )

    def test_closed_pull_request_file_fetches_are_limited_to_recent_twenty(self) -> None:
        class LimitedPullRequestClient(FakeGitHubClient):
            def __init__(self):
                super().__init__()
                self.requested_files = []

            def pulls(self, repository, state="all"):
                if repository not in {
                    "CCI-MOC/oac-apps",
                    "CCI-MOC/oac-infra",
                    "CCI-MOC/moc-keycloak",
                }:
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
                self.requested_files.append((repository, number))
                if repository == "CCI-MOC/oac-apps":
                    yield {
                        "filename": "values/bu-ist-demo-infra/example.yaml"
                    }
                elif repository == "CCI-MOC/oac-infra":
                    yield {
                        "filename": "infra/inventory/00hosts.yaml",
                        "patch": "+cluster: bu-ist-demo-infra\n",
                    }
                else:
                    yield {
                        "filename": "main.tf",
                        "patch": '+cluster_name = "bu-ist-demo-infra"\n',
                    }

        client = LimitedPullRequestClient()
        report = StatusChecker(client).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()

        self.assertEqual(len(client.requested_files), 60)
        requested_by_repository = {
            repository: [] for repository in (
                "CCI-MOC/oac-apps",
                "CCI-MOC/oac-infra",
                "CCI-MOC/moc-keycloak",
            )
        }
        for repository, number in client.requested_files:
            requested_by_repository[repository].append(number)
        self.assertEqual(requested_by_repository, {
            "CCI-MOC/oac-apps": list(range(5, 25)),
            "CCI-MOC/oac-infra": list(range(5, 25)),
            "CCI-MOC/moc-keycloak": list(range(5, 25)),
        })
        self.assertEqual(len(report["pull_requests"]), 60)

    def test_infra_pull_request_for_other_environment_is_not_relevant(self) -> None:
        class OtherEnvironmentInfraPullClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository == "CCI-MOC/oac-infra":
                    yield {
                        "number": 27,
                        "title": "Update another environment",
                        "body": None,
                        "state": "open",
                        "merged_at": None,
                        "updated_at": "2026-11-16T00:00:00Z",
                        "head": {"ref": "another-environment", "sha": "abc123"},
                        "html_url": (
                            "https://github.com/CCI-MOC/oac-infra/pull/27"
                        ),
                    }
                    return
                yield from super().pulls(repository, state)

            def pr_files(self, repository, number):
                if repository == "CCI-MOC/oac-infra" and number == 27:
                    yield {
                        "filename": "infra/inventory/00hosts.yaml",
                        "patch": (
                            "@@ -1,3 +1,3 @@\n"
                            "-cluster: another-env-infra\n"
                            "+cluster: another-env-workload0\n"
                        ),
                    }
                    return
                yield from super().pr_files(repository, number)

        report = StatusChecker(OtherEnvironmentInfraPullClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        numbers = [
            item["number"]
            for item in report["pull_requests"]
        ]
        self.assertNotIn(27, numbers)
        self.assertEqual(len(report["pull_requests"]), 1)

    def test_issue_link_and_multi_repository_pull_request_counts(self) -> None:
        issue_url = "https://github.com/CCI-MOC/MOC-issues/issues/666"

        class MultiRepositoryPullClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                if repository == "CCI-MOC/oac-infra":
                    yield {
                        "number": 28,
                        "title": "Infrastructure follow-up",
                        "body": f"Part of {issue_url}",
                        "state": "open",
                        "merged_at": None,
                        "updated_at": "2026-11-16T00:00:00Z",
                        "head": {"ref": "infra-follow-up", "sha": "abc123"},
                        "html_url": (
                            "https://github.com/CCI-MOC/oac-infra/pull/28"
                        ),
                    }
                    return
                if repository == "CCI-MOC/moc-keycloak":
                    yield {
                        "number": 7,
                        "title": "Update OIDC client",
                        "body": None,
                        "state": "open",
                        "merged_at": None,
                        "updated_at": "2026-11-16T00:00:00Z",
                        "head": {"ref": "bu-ist-demo-oidc", "sha": "def456"},
                        "html_url": (
                            "https://github.com/CCI-MOC/moc-keycloak/pull/7"
                        ),
                    }
                    return
                yield from super().pulls(repository, state)

            def pr_files(self, repository, number):
                if repository == "CCI-MOC/oac-infra" and number == 28:
                    yield {"filename": "docs/inventory-follow-up.md"}
                    return
                if repository == "CCI-MOC/moc-keycloak" and number == 7:
                    yield {
                        "filename": "main.tf",
                        "patch": (
                            '@@ -1,3 +1,3 @@\n'
                            '-cluster_name = "old-infra"\n'
                            '+cluster_name = "bu-ist-demo-infra"\n'
                        ),
                    }
                    return
                yield from super().pr_files(repository, number)

        report = StatusChecker(MultiRepositoryPullClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        pulls = report["pull_requests"]
        expected_repository_counts = {
            "CCI-MOC/moc-keycloak": 1,
            "CCI-MOC/oac-apps": 1,
            "CCI-MOC/oac-infra": 1,
        }
        self.assertEqual(len(pulls), 3)
        evidence_repositories = {
            item["repository"]["value"]
            for item in pulls
        }
        self.assertEqual(evidence_repositories, set(expected_repository_counts))
        text_report = render_text(report, details=True)
        markdown_report = render_markdown(report)
        self.assertIn("PULL REQUESTS", text_report)
        self.assertIn("open PRs touch this environment", text_report)
        self.assertIn("## Pull requests", markdown_report)
        self.assertIn("CCI-MOC/oac-infra", markdown_report)

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
        self.assertEqual(states["Hub hosted-cluster defaults"], "declared_in_main")
        self.assertEqual(states["Hub-wide component values"], "declared_in_main")
        self.assertEqual(states["Hub local-cluster values"], "declared_in_main")
        self.assertEqual(states["Hub ArgoCD applications"], "declared_in_main")
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
            if item["check"] == "Hub local-cluster values"
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
        check = next(item for item in report["checks"] if item["check"] == "Hub OIDC client")
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
            item for item in report["checks"] if item["check"] == "Hub OIDC client"
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
        self.assertIn("bu-ist-demo-worker", check["next_action"])
        self.assertIn("NodePool", check["next_action"])
        text_report = render_text(report, details=True)
        markdown_report = render_markdown(report)
        self.assertIn("Expected", text_report)
        self.assertIn("Agent label inputs", markdown_report)
        self.assertIn("| `compute-0` | `bmc` |", markdown_report)

    def test_documented_resource_class_mismatch_is_advisory(self) -> None:
        class ResourceClassMismatchClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return content.replace(
                        "resource_class: bu-ist-demo-worker",
                        "resource_class: custom-worker",
                    )
                return content

        report = StatusChecker(ResourceClassMismatchClient()).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item for item in report["checks"]
            if item["id"] == "workload.agent_labels_inputs"
        )
        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "advisory")
        self.assertIn("inventory has `custom-worker`", check["reason"])
        self.assertIn("documentation has `bu-ist-demo-worker`", check["reason"])
        self.assertEqual(
            check["evidence"]["resource_class_mismatches"],
            [
                {
                    "host": "compute-0",
                    "node_name": "MOC-R4PAC10U31-S1B",
                    "inventory_resource_class": "custom-worker",
                    "documented_resource_class": "bu-ist-demo-worker",
                }
            ],
        )

    def test_unavailable_resource_class_documentation_is_skipped_silently(
        self,
    ) -> None:
        for document in (
            "",
            "# No table here\n",
            "# Unparsable\n\n| Nope |\n",
            "| Node Name | Resource Class |\n|---|---|\n"
            "| other-node | other-class |\n",
        ):
            with self.subTest(document=document):
                class UnavailableDocumentationClient(FakeGitHubClient):
                    def get_file(self, repository, path, ref="main"):
                        if (
                            repository == "CCI-MOC/oac-infra"
                            and path
                            == "docs/hardware-and-network-configuration.md"
                        ):
                            return document
                        return super().get_file(repository, path, ref)

                report = StatusChecker(UnavailableDocumentationClient()).run(
                    Environment(name="bu-ist-demo", issue_number=666)
                ).to_dict()
                check = next(
                    item for item in report["checks"]
                    if item["id"] == "workload.agent_labels_inputs"
                )
                self.assertEqual(check["state"], "declared_in_main")
                self.assertEqual(check["severity"], "info")
                self.assertEqual(check["evidence"]["resource_class_mismatches"], [])
                self.assertNotIn("documentation has", check["reason"])

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
