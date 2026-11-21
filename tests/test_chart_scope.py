"""Offline coverage for deployment-cluster scoping in ``moc-env charts``."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from fakes import FakeGitHubClient

from moc_env import cli
from moc_env.registry import EnvironmentRegistry, RegistryError


DEPLOYMENT_HUB = "oac-demo-infra"
DEPLOYMENT_WORKLOAD = "oac-demo-workload0"
TEST_HUB = "bu-ist-demo-infra"
TEST_WORKLOAD = "bu-ist-demo-workload0"

HUB_APPLICATION_SET = """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hub-components
spec:
  generators:
    - list:
        elements:
          - component: hub-alpha
  template:
    spec:
      source:
        path: "charts/{{`{{component}}`}}"
"""

MANAGED_APPLICATION_SET = """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: all-managed-clusters
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: all-managed-clusters
    - list:
        elements:
          - component: gamma
  template:
    spec:
      source:
        path: "charts/{{`{{component}}`}}"
"""


class ScopeFakeGitHubClient(FakeGitHubClient):
    """One deployment hub and one test hub, each with one workload cluster."""

    HUBS = (DEPLOYMENT_HUB, TEST_HUB)
    WORKLOADS = {
        DEPLOYMENT_HUB: DEPLOYMENT_WORKLOAD,
        TEST_HUB: TEST_WORKLOAD,
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "applicationsets/templates/hub/hub-components.yaml",
                "applicationsets/templates/managed/all-managed-clusters.yaml",
            }
            for hub in self.HUBS:
                workload = self.WORKLOADS[hub]
                paths.update(
                    {
                        f"values/{hub}/hub-alpha.yaml",
                        f"values/{hub}/local-cluster/acm-placements.yaml",
                        f"hosted-clusters/{hub}/{workload}/values.yaml",
                    }
                )
            paths.add(f"apps/{TEST_HUB}/test-only.yaml")
            tree.update({path: {"path": path} for path in paths})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            if path == "applicationsets/templates/hub/hub-components.yaml":
                return HUB_APPLICATION_SET
            if (
                path
                == "applicationsets/templates/managed/all-managed-clusters.yaml"
            ):
                return MANAGED_APPLICATION_SET
            if path.endswith("/local-cluster/acm-placements.yaml"):
                return "placements: []\n"
            if path.startswith("hosted-clusters/") and path.endswith(
                "/values.yaml"
            ):
                return "clusterLabels: {}\n"
            if path.startswith("values/") and path.endswith(".yaml"):
                return "{}\n"
            if path.endswith("/test-only.yaml"):
                return "kind: Application\n"
        return super().get_file(repository, path, ref)


class TestOnlyScopeFakeGitHubClient(ScopeFakeGitHubClient):
    HUBS = (TEST_HUB,)
    WORKLOADS = {TEST_HUB: TEST_WORKLOAD}


class ChartScopeTest(unittest.TestCase):
    def run_cli(self, client, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "GitHubClient", lambda **kwargs: client),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_default_scope_shows_deployment_clusters_only(self) -> None:
        exit_code, stdout, _ = self.run_cli(ScopeFakeGitHubClient(), ["charts"])

        self.assertEqual(exit_code, 0)
        tables = stdout.split("Test clusters not shown")[0]
        self.assertIn(DEPLOYMENT_HUB, tables)
        self.assertIn(DEPLOYMENT_WORKLOAD, tables)
        self.assertNotIn(TEST_HUB, tables)
        self.assertNotIn(TEST_WORKLOAD, tables)

    def test_default_scope_names_hidden_test_clusters(self) -> None:
        exit_code, stdout, _ = self.run_cli(ScopeFakeGitHubClient(), ["charts"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            stdout.endswith(
                "Test clusters not shown: bu-ist-demo-infra, "
                "bu-ist-demo-workload0. Pass --all-clusters to include them.\n"
            )
        )

    def test_all_clusters_includes_and_names_test_clusters(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ScopeFakeGitHubClient(), ["charts", "--all-clusters"]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(TEST_HUB, stdout)
        self.assertIn(TEST_WORKLOAD, stdout)
        self.assertTrue(
            stdout.endswith(
                "Test clusters shown: bu-ist-demo-infra, "
                "bu-ist-demo-workload0.\n"
            )
        )

    def test_named_test_environment_is_shown_whatever_its_class(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ScopeFakeGitHubClient(), ["charts", "bu-ist-demo"]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(TEST_HUB, stdout)
        self.assertIn(TEST_WORKLOAD, stdout)
        self.assertNotIn(DEPLOYMENT_HUB, stdout)
        self.assertNotIn("Test clusters not shown", stdout)

    def test_named_test_environment_with_workload_is_shown(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ScopeFakeGitHubClient(),
            ["charts", "bu-ist-demo", "--workload", TEST_WORKLOAD],
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(TEST_WORKLOAD, stdout)
        self.assertNotIn(DEPLOYMENT_WORKLOAD, stdout)

    def test_empty_default_scope_reports_hidden_count_without_tables(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            TestOnlyScopeFakeGitHubClient(), ["charts"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout,
            "No deployment clusters found. 2 test clusters not shown; "
            "pass --all-clusters to include them.\n",
        )
        self.assertNotIn("Workload clusters", stdout)
        self.assertNotIn("|", stdout)

    def test_reference_view_omits_test_hub_drop_ins_by_default(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ScopeFakeGitHubClient(), ["charts", "--view", "reference", "--format", "json"]
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(document["hub"]["drop_ins"], [])

        exit_code, stdout, _ = self.run_cli(
            ScopeFakeGitHubClient(),
            ["charts", "--view", "reference", "--format", "json", "--all-clusters"],
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(document["hub"]["drop_ins"], ["test-only"])

    def test_malformed_cluster_scope_raises_registry_error(self) -> None:
        base = {
            "defaults": {
                "required_local_cluster_components": [],
                "optional_local_cluster_components": [],
            },
            "environments": {},
        }
        for scope in (
            [],
            {},
            {"deployment_hub_patterns": []},
            {"deployment_hub_patterns": [""]},
            {"deployment_hub_patterns": "oac-*"},
            {"deployment_hub_patterns": [1]},
            {"deployment_hub_patterns": ["oac-*"], "extra": True},
        ):
            with self.subTest(scope=scope):
                with self.assertRaises(RegistryError):
                    EnvironmentRegistry.from_document(
                        {**base, "cluster_scope": scope}
                    )


if __name__ == "__main__":
    unittest.main()
