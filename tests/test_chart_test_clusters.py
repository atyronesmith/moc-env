"""Offline coverage for test workloads hosted on deployment hubs."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from test_chart_scope import ScopeFakeGitHubClient

from moc_env import cli
from moc_env.charts import _select_scope, collect_chart_inventory
from moc_env.registry import EnvironmentRegistry, RegistryError


class GuestClusterClient(ScopeFakeGitHubClient):
    """A synthetic deployment hub with a deployment workload and a guest."""

    HUBS = ("h-infra",)
    WORKLOADS = {"h-infra": "h-workload0"}

    def get_tree(self, repository, ref="main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree["hosted-clusters/h-infra/guest1/values.yaml"] = {}
        return tree


class ChartTestClustersTest(unittest.TestCase):
    def setUp(self):
        self.client = GuestClusterClient()
        self.tree = self.client.get_tree("CCI-MOC/oac-apps")
        self.defaults = {
            "required_local_cluster_components": [],
            "optional_local_cluster_components": [],
        }
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("offline test")))
        self.enterContext(patch("moc_env.github.urlopen", side_effect=AssertionError("offline test")))

    def registry(self, **scope):
        return EnvironmentRegistry.from_document({
            "defaults": self.defaults,
            "cluster_scope": {"deployment_hub_patterns": ["h-*"], **scope},
        })

    def select(self, tests=(), environment=None, workload=None, all_clusters=False):
        return _select_scope(
            self.tree, environment, workload,
            deployment_patterns=("h-*",), all_clusters=all_clusters, test_clusters=tests,
        )

    def run_cli(self, *arguments, tests=("guest1",)):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli.EnvironmentRegistry, "load", return_value=self.registry(test_clusters=list(tests))),
            patch.object(cli, "_new_github_client", return_value=self.client),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(["charts", *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_scope_hides_guest_and_classifies_it_as_test(self):
        hubs, workloads, scope, hidden, tests = self.select(("guest1",))
        self.assertEqual(hubs, ["h-infra"])
        self.assertEqual(workloads["h-infra"], ["h-workload0"])
        self.assertEqual((scope, hidden, tests), ("deployment", ("guest1",), ("guest1",)))

    def test_all_clusters_keeps_guest_and_classifies_it_as_test(self):
        hubs, workloads, scope, hidden, tests = self.select(("guest1",), all_clusters=True)
        self.assertEqual(hubs, ["h-infra"])
        self.assertEqual(workloads["h-infra"], ["guest1", "h-workload0"])
        self.assertEqual((scope, hidden, tests), ("all", (), ("guest1",)))

    def test_named_environment_keeps_guest(self):
        for environment in ("h", "h-infra"):
            with self.subTest(environment=environment):
                hubs, workloads, scope, hidden, tests = self.select(("guest1",), environment=environment)
                self.assertEqual(hubs, ["h-infra"])
                self.assertEqual(workloads["h-infra"], ["guest1", "h-workload0"])
                self.assertEqual((scope, hidden, tests), ("environment", (), ("guest1",)))

    def test_unknown_test_name_is_ignored_in_every_scope(self):
        for options in ({}, {"all_clusters": True}, {"environment": "h"}):
            with self.subTest(options=options):
                self.assertEqual(self.select(("absent-cluster",), **options), self.select(**options))

    def test_hub_test_name_is_rejected_in_every_scope(self):
        for options in ({}, {"all_clusters": True}, {"environment": "h"}):
            with self.subTest(options=options):
                with self.assertRaisesRegex(RegistryError, "h-infra"):
                    self.select(("h-infra",), **options)

    def test_registry_rejects_non_lists_and_invalid_entries(self):
        for value in ("guest1", None, 1, True, {}, ("guest1",), [1], [None], [""]):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RegistryError, r"cluster_scope\.test_clusters"):
                    self.registry(test_clusters=value)

    def test_registry_exposes_test_names_beside_patterns(self):
        registry = self.registry(test_clusters=["guest1"])
        self.assertEqual(registry.deployment_hub_patterns, ("h-*",))
        self.assertEqual(registry.test_clusters, ("guest1",))

    def test_missing_and_empty_test_lists_preserve_existing_scope(self):
        for registry in (self.registry(), self.registry(test_clusters=[])):
            self.assertEqual(registry.test_clusters, ())
            self.assertEqual(self.select(registry.test_clusters), self.select())
        registry = EnvironmentRegistry.from_document({"defaults": self.defaults})
        self.assertEqual(registry.test_clusters, ())

    def test_collect_inventory_excludes_guest_before_reading_its_values(self):
        original = self.client.get_file

        def read(repository, path, ref="main"):
            self.assertNotIn("/guest1/", path)
            return original(repository, path, ref)

        with patch.object(self.client, "get_file", side_effect=read):
            inventory = collect_chart_inventory(
                self.client, deployment_patterns=("h-*",), test_clusters=("guest1",),
            )
        self.assertEqual([cluster.name for cluster in inventory.clusters], ["h-infra", "h-workload0"])
        self.assertEqual(inventory.hidden_clusters, ("guest1",))
        self.assertEqual(inventory.test_clusters, ("guest1",))
        self.assertEqual(inventory.workload_counts, (("h-infra", 1),))

    def test_cli_default_scope_uses_registry_and_existing_note(self):
        code, output, _ = self.run_cli()
        self.assertEqual(code, 0)
        tables, note = output.split("Test clusters not shown:")
        self.assertIn("h-infra", tables)
        self.assertIn("h-workload0", tables)
        self.assertNotIn("guest1", tables)
        self.assertEqual(note.strip(), "guest1. Pass --all-clusters to include them.")

    def test_cli_all_and_named_scopes_show_guest(self):
        for arguments in (("--all-clusters",), ("h",), ("h", "--workload", "guest1")):
            with self.subTest(arguments=arguments):
                code, output, _ = self.run_cli(*arguments)
                self.assertEqual(code, 0)
                self.assertIn("guest1", output)
                self.assertNotIn("Test clusters not shown:", output)

    def test_cli_json_reports_hidden_guest(self):
        code, output, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 0)
        scope = json.loads(output)["scope"]
        self.assertEqual(scope["hidden_test_clusters"], ["guest1"])
        self.assertEqual(scope["test_clusters"], ["guest1"])

    def test_page_scope_excludes_guest_cluster_section(self):
        code, output, _ = self.run_cli("--view", "page")
        self.assertEqual(code, 0)
        self.assertIn("### h-infra (hub)", output)
        self.assertIn("### h-workload0 (workload)", output)
        self.assertNotIn("### guest1 (workload)", output)

    def test_cli_hub_test_name_is_a_clean_registry_error(self):
        code, output, error = self.run_cli(tests=("h-infra",))
        self.assertEqual((code, output), (2, ""))
        self.assertIn("cluster_scope.test_clusters names hub h-infra", error)

    def test_explicit_and_non_deployment_test_lists_are_combined(self):
        self.tree.update({
            "values/sandbox-infra/local-cluster/acm-placements.yaml": {},
            "hosted-clusters/sandbox-infra/sandbox-workload0/values.yaml": {},
        })
        _, _, _, hidden, tests = self.select(("guest1",))
        self.assertEqual(hidden, ("guest1", "sandbox-infra", "sandbox-workload0"))
        self.assertEqual(tests, hidden)


if __name__ == "__main__":
    unittest.main()
