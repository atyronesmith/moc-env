from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.chart_values import render_chart_values_markdown
from moc_env.model import Environment
from moc_env.observed import read_chart_values_observation

from fakes import FakeGitHubClient


class ValuesClient(FakeGitHubClient):
    def get_tree(self, repository, ref="main"):
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "values/bu-ist-demo-infra/hcp-config.yaml",
                "values/bu-ist-demo-infra/local-cluster/acm.yaml",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml",
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/cert-manager.yaml",
            }
            return {path: {"path": path} for path in paths}
        return super().get_tree(repository, ref)

    def get_file(self, repository, path, ref="main"):
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
            }
            if path in files:
                return files[path]
        return super().get_file(repository, path, ref)


class ChartValuesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment(name="bu-ist-demo", issue_number=666)
        self.client = ValuesClient()
        self.observation = read_chart_values_observation(
            self.client,
            self.environment,
            "bu-ist-demo-workload0",
        )

    def test_read_chart_values_observation_classifies_scopes(self) -> None:
        scopes = {scope.scope.value: scope for scope in self.observation.scopes}

        self.assertEqual(
            set(scopes),
            {
                "hub-wide",
                "hub-local-cluster",
                "hosted-cluster",
                "workload-components",
            },
        )
        self.assertTrue(scopes["hub-wide"].present.value)
        self.assertEqual(
            scopes["hub-wide"].files[0].path.value,
            "values/bu-ist-demo-infra/hcp-config.yaml",
        )
        self.assertEqual(
            scopes["hub-local-cluster"].files[0].chart.value,
            "acm",
        )
        self.assertEqual(
            scopes["hosted-cluster"].files[0].chart.value,
            "hosted-cluster",
        )
        self.assertEqual(
            scopes["workload-components"].files[0].chart.value,
            "cert-manager",
        )

    def test_chart_values_entries_preserve_provenance(self) -> None:
        hosted = next(
            scope
            for scope in self.observation.scopes
            if scope.scope.value == "hosted-cluster"
        )
        entry = next(
            entry
            for entry in hosted.files[0].entries
            if entry.key.value == "release.channel"
        )

        self.assertEqual(entry.value.value, "stable-4.22")
        self.assertEqual(entry.key.repository, "CCI-MOC/oac-apps")
        self.assertEqual(
            entry.key.path,
            "hosted-clusters/bu-ist-demo-infra/"
            "bu-ist-demo-workload0/values.yaml",
        )
        self.assertEqual(entry.key.confidence, "exact")

    def test_missing_hosted_values_file_is_explicit(self) -> None:
        class EmptyAppsClient(FakeGitHubClient):
            def get_tree(self, repository, ref="main"):
                if repository == "CCI-MOC/oac-apps":
                    return {}
                return super().get_tree(repository, ref)

        observation = read_chart_values_observation(
            EmptyAppsClient(),
            self.environment,
            "bu-ist-demo-workload0",
        )
        hosted = next(
            scope
            for scope in observation.scopes
            if scope.scope.value == "hosted-cluster"
        )

        self.assertFalse(hosted.present.value)
        self.assertEqual(len(hosted.files), 1)
        self.assertFalse(hosted.files[0].present.value)
        self.assertIsNone(hosted.files[0].values.value)

    def test_unsupported_values_yaml_is_explicit(self) -> None:
        class UnsupportedValuesClient(ValuesClient):
            def get_file(self, repository, path, ref="main"):
                if (
                    repository == "CCI-MOC/oac-apps"
                    and path == "values/bu-ist-demo-infra/hcp-config.yaml"
                ):
                    return "- unsupported\n"
                return super().get_file(repository, path, ref)

        observation = read_chart_values_observation(
            UnsupportedValuesClient(),
            self.environment,
            "bu-ist-demo-workload0",
        )
        hub = next(
            scope
            for scope in observation.scopes
            if scope.scope.value == "hub-wide"
        )

        self.assertTrue(hub.files[0].present.value)
        self.assertEqual(hub.files[0].values.confidence, "unsupported")
        self.assertEqual(hub.files[0].entries, ())

    def test_render_chart_values_markdown_is_human_readable(self) -> None:
        rendered = render_chart_values_markdown(
            self.environment,
            self.observation,
        )

        self.assertIn("# 📘 Hub and Hosted Cluster Chart Values", rendered)
        self.assertIn("## Scope summary", rendered)
        self.assertIn("## How the scopes relate", rendered)
        self.assertIn("## hub-local-cluster", rendered)
        self.assertIn("### `acm`", rendered)
        self.assertIn("| Key | Current value | Type | Notes |", rendered)
        self.assertIn("`multiClusterHub.availabilityConfig`", rendered)
        self.assertIn("⚠️ Secret-like name", rendered)
        self.assertIn("[Open values file](", rendered)

    def test_cli_document_values_dispatch(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "GitHubClient", ValuesClient),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(["document-values", "bu-ist-demo"])

        self.assertEqual(exit_code, 0)
        self.assertIn("# 📘 Hub and Hosted Cluster Chart Values", stdout.getvalue())
        self.assertIn("Step 4: Chart values", stderr.getvalue())
        self.assertNotIn("Step 5:", stderr.getvalue())

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
                exit_code = cli.main(
                    [
                        "document-values",
                        "bu-ist-demo",
                        "--workload",
                        "workload0",
                        "--output",
                        str(output),
                    ]
                )

            rendered = output.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(f"wrote chart-values guide to {output}", stderr.getvalue())
        self.assertIn("## hosted-cluster", rendered)


if __name__ == "__main__":
    unittest.main()
