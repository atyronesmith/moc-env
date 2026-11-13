from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.chart_values import render_chart_values_markdown
from moc_env.observed import read_chart_values_reference_observation

from fakes import FakeGitHubClient


class ValuesClient(FakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "values/bu-ist-demo-infra/hcp-config.yaml",
                "values/bu-ist-demo-infra/local-cluster/acm.yaml",
                "hosted-clusters/bu-ist-demo-infra/compliance.yaml",
                "hosted-clusters/bu-ist-demo-infra/values.yaml",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml",
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/cert-manager.yaml",
                "hosted-clusters/oac-prod-infra/"
                "oac-prod-workload0/values.yaml",
            }
            return {path: {"path": path} for path in paths}
        return super().get_tree(repository, ref)

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            files = {
                "values/bu-ist-demo-infra/hcp-config.yaml": """
sshKey:
  aws_secret_name: cluster/bu-ist-demo-infra/sshkey
""",
                "values/bu-ist-demo-infra/local-cluster/acm.yaml": """
multiClusterHub:
  availabilityConfig: High
""",
                "hosted-clusters/bu-ist-demo-infra/compliance.yaml": """
fips: true
""",
                "hosted-clusters/bu-ist-demo-infra/values.yaml": """
baseDomain: hcp.bu-ist-demo.int.massopen.cloud
hcpInternalDomain: hcp-int.bu-ist-demo.int.massopen.cloud
hcpExternalDomain: hcp.bu-ist-demo.int.massopen.cloud
dns:
  enabled: true
  autoGenerate: true
""",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml": """
clusterName: bu-ist-demo-workload0
release:
  channel: stable-4.22
nodePools:
  - name: compute
    replicas: 3
""",
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/cert-manager.yaml": """
aws:
  region: us-east-1
""",
                "hosted-clusters/oac-prod-infra/"
                "oac-prod-workload0/values.yaml": """
clusterName: oac-prod-workload0
release:
  channel: stable-4.19
""",
            }
            if path in files:
                return files[path]
        return super().get_file(repository, path, ref)


class ChartValuesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ValuesClient()
        self.observation = read_chart_values_reference_observation(self.client)

    def test_reference_classifies_all_deployment_scopes(self) -> None:
        scopes = {
            file_observation.scope.value
            for file_observation in self.observation.files
        }

        self.assertEqual(
            scopes,
            {
                "hub-wide",
                "hub-local-cluster",
                "hosted-cluster-defaults",
                "hosted-cluster",
                "workload-components",
            },
        )

    def test_reference_aggregates_keys_across_environments(self) -> None:
        key = next(
            key_observation
            for key_observation in self.observation.keys
            if key_observation.key.value == "release.channel"
        )

        self.assertEqual(key.file_count.value, 2)
        self.assertEqual(key.scopes.value, ("hosted-cluster",))
        self.assertEqual(key.charts.value, ("hosted-cluster",))
        self.assertEqual(key.types.value, ("str",))
        self.assertEqual(
            key.key.repository,
            "CCI-MOC/oac-apps",
        )

    def test_reference_documents_list_item_keys(self) -> None:
        key = next(
            key_observation
            for key_observation in self.observation.keys
            if key_observation.key.value == "nodePools[].replicas"
        )

        self.assertEqual(key.file_count.value, 1)
        self.assertEqual(key.types.value, ("int",))
        self.assertEqual(key.charts.value, ("hosted-cluster",))

    def test_unsupported_values_yaml_is_explicit(self) -> None:
        class UnsupportedValuesClient(ValuesClient):
            def get_file(self, repository: str, path: str, ref: str = "main") -> str:
                if (
                    repository == "CCI-MOC/oac-apps"
                    and path == "values/bu-ist-demo-infra/hcp-config.yaml"
                ):
                    return "- unsupported\n"
                return super().get_file(repository, path, ref)

        observation = read_chart_values_reference_observation(
            UnsupportedValuesClient()
        )
        file_observation = next(
            file_observation
            for file_observation in observation.files
            if file_observation.path.value
            == "values/bu-ist-demo-infra/hcp-config.yaml"
        )

        self.assertTrue(file_observation.present.value)
        self.assertEqual(file_observation.values.confidence, "unsupported")
        self.assertEqual(file_observation.entries, ())

    def test_render_chart_values_markdown_is_general_and_human_readable(self) -> None:
        rendered = render_chart_values_markdown(self.observation)

        self.assertIn("# 📘 Chart Configuration Reference", rendered)
        self.assertIn("Generated documentation", rendered)
        self.assertIn("do not edit the generated Markdown directly", rendered)
        self.assertIn("## Deployment model", rendered)
        self.assertIn("## Scope summary", rendered)
        self.assertIn("## Hosted Cluster DNS and Addressing", rendered)
        self.assertIn("### Hub-level domains", rendered)
        self.assertIn("#### `hcpExternalDomain`", rendered)
        self.assertIn(
            "| Source(s) | [DNS-1](#sources), [HCP-1](#sources) |",
            rendered,
        )
        self.assertIn("| Chart discovery | Charts:", rendered)
        self.assertIn("| Related keys |", rendered)
        self.assertIn("## Uncurated variables", rendered)
        self.assertIn("### hosted-cluster", rendered)
        self.assertIn("### workload-components", rendered)
        self.assertIn("| Key | Charts | Type | Files | What it controls |", rendered)
        self.assertIn("`release.channel`", rendered)
        self.assertIn("`nodePools[].replicas`", rendered)
        self.assertIn("OpenShift release channel used to select cluster updates", rendered)
        self.assertIn("⚠️ Secret-like name", rendered)
        self.assertIn("## Sources", rendered)
        self.assertIn("`DNS-1`", rendered)
        self.assertIn("[DNS-1](#sources)", rendered)
        self.assertNotIn("[Example](", rendered)
        self.assertNotIn("bu-ist-demo-workload0`\n", rendered)
        self.assertNotIn("stable-4.22", rendered)

    def test_cli_document_values_has_no_environment_argument(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "GitHubClient", ValuesClient),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(["document-values"])

        self.assertEqual(exit_code, 0)
        self.assertIn("# 📘 Chart Configuration Reference", stdout.getvalue())
        self.assertIn("Step 1: Chart values", stderr.getvalue())
        self.assertNotIn("Step 2:", stderr.getvalue())

    def test_cli_document_values_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "values.md"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(cli, "_resolve_github_token", return_value=None),
                patch.object(cli, "GitHubClient", ValuesClient),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main(["document-values", "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("wrote chart-values reference to", stderr.getvalue())
            self.assertIn("# 📘 Chart Configuration Reference", output.read_text())


if __name__ == "__main__":
    unittest.main()
