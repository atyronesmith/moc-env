from __future__ import annotations

import unittest

from moc_env.checks import StatusChecker
from moc_env.checks import list_environments
from moc_env.model import Environment
from moc_env.observed import (
    read_environment_observation,
    read_infra_observation,
)

from fakes import FakeGitHubClient


class StatusCheckerTest(unittest.TestCase):
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

    def test_list_environments_returns_base_names_and_workloads(self) -> None:
        environments = list_environments(FakeGitHubClient())
        self.assertEqual(len(environments), 1)
        self.assertEqual(environments[0]["name"], "bu-ist-demo")
        self.assertEqual(environments[0]["infra_cluster"], "bu-ist-demo-infra")
        self.assertEqual(
            environments[0]["workload_clusters"],
            ["bu-ist-demo-workload0"],
        )
        self.assertEqual(environments[0]["status_command"], "moc-env bu-ist-demo")

    def test_read_infra_observation_normalizes_repository_inputs(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(FakeGitHubClient(), environment)

        self.assertEqual(observation.repository, "CCI-MOC/oac-infra")
        self.assertTrue(observation.inventory_present)
        self.assertTrue(observation.clusters["bu-ist-demo-infra"].group_found)
        self.assertTrue(observation.clusters["bu-ist-demo-workload0"].group_found)
        self.assertEqual(len(observation.clusters["bu-ist-demo-infra"].hosts), 1)
        self.assertTrue(observation.hub_inventory.cluster_key_present)
        self.assertEqual(observation.hub_variables.values["api_ip"], "10.20.27.11")

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
        self.assertEqual(observation.apps.pull_requests[0].number, 237)
        self.assertEqual(
            observation.apps.pull_requests[0].changed_files,
            ("values/bu-ist-demo-infra/hcp-config.yaml",),
        )
        self.assertEqual(observation.infra_cluster.cluster, "bu-ist-demo-infra")
        self.assertEqual(
            observation.workload_cluster.inventory.cluster,
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
        self.assertFalse(observation.keycloak.path_present)
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
        self.assertEqual(check["missing"]["declarations"], ["redirect_uri", "secret_name"])


if __name__ == "__main__":
    unittest.main()
