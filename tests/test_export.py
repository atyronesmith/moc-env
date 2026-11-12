from __future__ import annotations

import unittest

import yaml

from moc_env.export import build_infra_export, render_infra_export
from moc_env.model import Environment
from moc_env.observed import read_infra_observation

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


if __name__ == "__main__":
    unittest.main()
