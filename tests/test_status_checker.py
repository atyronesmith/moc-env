from __future__ import annotations

import unittest

from moc_env.checks import LOCAL_CLUSTER_COMPONENTS
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
        self.assertEqual(check["missing"]["declarations"], ["redirect_uri", "secret_name"])

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
        self.assertEqual(states["bu-ist-demo-workload0 host inventory"], "missing")
        self.assertEqual(states["Hub image inventory"], "missing")
        self.assertEqual(states["Hub image variables"], "missing")
        self.assertEqual(states["Infra OIDC client"], "missing")
        self.assertEqual(states["Infra hosted-cluster defaults"], "missing")
        self.assertEqual(states["Hub-wide component values"], "missing")
        self.assertEqual(states["Infra local-cluster values"], "missing")
        self.assertEqual(states["Infra ArgoCD applications"], "missing")
        self.assertEqual(states["Workload hosted-cluster values"], "missing")
        self.assertEqual(states["Workload component values"], "missing")
        self.assertEqual(states["Relevant pull requests"], "missing")

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
        self.assertEqual(check["state"], "pr_merged")

    def test_status_checker_reports_declared_apps_paths(self) -> None:
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
                        for name in LOCAL_CLUSTER_COMPONENTS
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


if __name__ == "__main__":
    unittest.main()
