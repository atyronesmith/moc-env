from __future__ import annotations

import unittest

import yaml

from moc_env.export import (
    build_infra_export,
    build_workload_export,
    render_infra_export,
    render_workload_export,
    workload_cluster_name,
)
from moc_env.model import Environment
from moc_env.observed import read_apps_observation, read_infra_observation

from fakes import FakeGitHubClient


class InfraExportTest(unittest.TestCase):
    def test_build_infra_export_preserves_values_and_provenance(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(FakeGitHubClient(), environment)
        document = build_infra_export(environment, observation)

        self.assertEqual(document["apiVersion"], "moc-env/v1alpha1")
        self.assertEqual(document["kind"], "InfraCluster")
        self.assertEqual(document["schemaVersion"], "1")
        self.assertEqual(
            document["metadata"]["name"],
            {
                "value": "bu-ist-demo-infra",
                "provenance": {
                    "repository": "CCI-MOC/oac-infra",
                    "path": "infra/inventory/00hosts.yaml",
                    "ref": "main",
                },
                "confidence": "inferred",
            },
        )
        self.assertEqual(document["spec"]["domain"]["value"], "bu-ist-demo.int.massopen.cloud")
        self.assertEqual(document["spec"]["domain"]["confidence"], "inferred")
        self.assertEqual(
            document["spec"]["variables"]["fields"]["api_ip"]["value"],
            "10.20.27.11",
        )
        self.assertEqual(
            document["spec"]["variables"]["fields"]["api_ip"]["confidence"],
            "exact",
        )
        self.assertEqual(
            document["spec"]["inventory"]["clusters"]["bu-ist-demo-infra"][
                "bootImage"
            ]["selected"]["value"],
            "http://10.2.0.82/boot/discovery.iso",
        )
        self.assertFalse(
            document["spec"]["inventory"]["clusters"]["bu-ist-demo-infra"][
                "bootImage"
            ]["ambiguous"],
        )

    def test_render_infra_export_is_deterministic_and_has_no_timestamps(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(FakeGitHubClient(), environment)
        first = render_infra_export(environment, observation)
        second = render_infra_export(environment, observation)

        self.assertEqual(first, second)
        self.assertNotIn("timestamp", first)
        self.assertNotIn("generated", first)
        document = yaml.safe_load(first)
        self.assertEqual(document["kind"], "InfraCluster")

    def test_infra_export_represents_ambiguous_boot_image(self) -> None:
        class AmbiguousBootImageClient(FakeGitHubClient):
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
        group0:
          vars:
            boot_image_url: http://example.invalid/one.iso
          hosts:
            node0:
              node_name: node-0
        group1:
          vars:
            boot_image_url: http://example.invalid/two.iso
          hosts:
            node1:
              node_name: node-1
"""
                return super().get_file(repository, path, ref)

        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(AmbiguousBootImageClient(), environment)
        document = build_infra_export(environment, observation)
        boot_image = document["spec"]["inventory"]["clusters"]["bu-ist-demo-infra"][
            "bootImage"
        ]

        self.assertTrue(boot_image["ambiguous"])
        self.assertIsNone(boot_image["selected"]["value"])
        self.assertEqual(boot_image["selected"]["confidence"], "unsupported")
        self.assertEqual(len(boot_image["urls"]), 2)

    def test_infra_export_represents_unsupported_variables(self) -> None:
        class UnsupportedVariablesClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "hub-images/group_vars/bu-ist-demo-infra/vars.yml"
                ):
                    return "- values\n"
                return super().get_file(repository, path, ref)

        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(UnsupportedVariablesClient(), environment)
        document = build_infra_export(environment, observation)

        self.assertIsNone(document["spec"]["domain"]["value"])
        self.assertEqual(document["spec"]["domain"]["confidence"], "unsupported")
        api_ip = document["spec"]["variables"]["fields"]["api_ip"]
        self.assertIsNone(api_ip["value"])
        self.assertEqual(api_ip["confidence"], "unsupported")


class WorkloadExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment(name="bu-ist-demo", issue_number=666)
        self.client = FakeGitHubClient()
        self.infra = read_infra_observation(self.client, self.environment)
        self.apps = read_apps_observation(
            self.client,
            self.environment,
            include_pull_requests=False,
        )

    def test_workload_cluster_name_accepts_full_and_short_names(self) -> None:
        self.assertEqual(
            workload_cluster_name(self.environment, "workload0"),
            "bu-ist-demo-workload0",
        )
        self.assertEqual(
            workload_cluster_name(self.environment, "bu-ist-demo-workload0"),
            "bu-ist-demo-workload0",
        )
        with self.assertRaises(ValueError):
            workload_cluster_name(self.environment, "workload1")

    def test_build_workload_export_preserves_inventory_and_parent(self) -> None:
        document = build_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            self.infra,
            self.apps,
        )

        self.assertEqual(document["apiVersion"], "moc-env/v1alpha1")
        self.assertEqual(document["kind"], "WorkloadCluster")
        self.assertEqual(document["schemaVersion"], "1")
        self.assertEqual(
            document["metadata"]["name"]["value"],
            "bu-ist-demo-workload0",
        )
        self.assertEqual(
            document["metadata"]["parentInfraCluster"]["value"],
            "bu-ist-demo-infra",
        )
        self.assertTrue(document["spec"]["inventory"]["groupPresent"]["value"])
        self.assertEqual(document["spec"]["inventory"]["hostCount"]["value"], 1)
        self.assertEqual(
            document["spec"]["inventory"]["hosts"]["value"][0]["name"],
            "compute-0",
        )

    def test_workload_export_keeps_missing_gitops_paths_explicit(self) -> None:
        document = build_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            self.infra,
            self.apps,
        )
        gitops = document["spec"]["gitOps"]

        self.assertFalse(gitops["hostedClusterValues"]["present"]["value"])
        self.assertEqual(
            gitops["hostedClusterValues"]["path"]["value"],
            "hosted-clusters/bu-ist-demo-infra/"
            "bu-ist-demo-workload0/values.yaml",
        )
        self.assertFalse(gitops["componentValues"]["present"]["value"])
        self.assertEqual(gitops["componentValues"]["paths"]["value"], [])
        self.assertFalse(gitops["applications"]["present"]["value"])
        self.assertEqual(gitops["applications"]["paths"]["value"], [])

    def test_workload_export_records_present_gitops_paths(self) -> None:
        class WorkloadAppsClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    paths = {
                        "hosted-clusters/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/values.yaml",
                        "values/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/cert-manager.yaml",
                        "values/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/metallb.yaml",
                        "apps/bu-ist-demo-infra/"
                        "bu-ist-demo-workload0/example.yaml",
                    }
                    return {path: {"path": path} for path in paths}
                return super().get_tree(repository, ref)

        apps = read_apps_observation(
            WorkloadAppsClient(),
            self.environment,
            include_pull_requests=False,
        )
        document = build_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            self.infra,
            apps,
        )
        gitops = document["spec"]["gitOps"]

        self.assertTrue(gitops["hostedClusterValues"]["present"]["value"])
        self.assertTrue(gitops["componentValues"]["present"]["value"])
        self.assertEqual(
            gitops["componentValues"]["paths"]["value"],
            [
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/cert-manager.yaml",
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/metallb.yaml",
            ],
        )
        self.assertTrue(gitops["applications"]["present"]["value"])
        self.assertEqual(
            gitops["applications"]["paths"]["value"],
            ["apps/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml"],
        )

    def test_workload_export_represents_ambiguous_boot_image(self) -> None:
        class AmbiguousWorkloadClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                if (
                    repository == "CCI-MOC/oac-infra"
                    and path == "infra/inventory/00hosts.yaml"
                ):
                    return """
all:
  children:
    bu_ist_demo_workload0:
      vars:
        cluster: bu-ist-demo-workload0
      children:
        group0:
          vars:
            boot_image_url: http://example.invalid/one.iso
          hosts:
            node0:
              node_name: node-0
        group1:
          vars:
            boot_image_url: http://example.invalid/two.iso
          hosts:
            node1:
              node_name: node-1
"""
                return super().get_file(repository, path, ref)

        infra = read_infra_observation(AmbiguousWorkloadClient(), self.environment)
        document = build_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            infra,
            self.apps,
        )
        boot_image = document["spec"]["inventory"]["bootImage"]

        self.assertTrue(boot_image["ambiguous"])
        self.assertIsNone(boot_image["selected"]["value"])
        self.assertEqual(boot_image["selected"]["confidence"], "unsupported")
        self.assertEqual(len(boot_image["urls"]), 2)

    def test_render_workload_export_is_deterministic_and_has_no_timestamps(self) -> None:
        first = render_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            self.infra,
            self.apps,
        )
        second = render_workload_export(
            self.environment,
            "bu-ist-demo-workload0",
            self.infra,
            self.apps,
        )

        self.assertEqual(first, second)
        self.assertNotIn("timestamp", first)
        self.assertNotIn("generated", first)
        document = yaml.safe_load(first)
        self.assertEqual(document["kind"], "WorkloadCluster")


if __name__ == "__main__":
    unittest.main()
