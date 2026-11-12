from __future__ import annotations

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli
from moc_env.compare import compare_environment, desired_environment
from moc_env.export import build_environment_export, render_environment_export
from moc_env.model import Environment
from moc_env.observed import (
    read_apps_observation,
    read_infra_observation,
    read_issue_observation,
)
from moc_env.validate import load_environment_document, validate_environment

from fakes import FakeGitHubClient


class EnvironmentAppsClient(FakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml",
                "values/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/cert-manager.yaml",
                "apps/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/example.yaml",
            }
            return {path: {"path": path} for path in paths}
        return super().get_tree(repository, ref)


class EnvironmentBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment(name="bu-ist-demo", issue_number=666)
        self.client = EnvironmentAppsClient()
        self.issue = read_issue_observation(self.client, self.environment)
        self.infra = read_infra_observation(self.client, self.environment)
        self.apps = read_apps_observation(
            self.client,
            self.environment,
            include_pull_requests=False,
        )
        self.document = build_environment_export(
            self.environment,
            self.issue,
            self.infra,
            self.apps,
        )

    def test_build_environment_export_records_bundle_references(self) -> None:
        self.assertEqual(self.document["apiVersion"], "moc-env/v1alpha1")
        self.assertEqual(self.document["kind"], "Environment")
        self.assertEqual(self.document["schemaVersion"], "1")
        self.assertEqual(
            self.document["metadata"]["name"]["value"],
            "bu-ist-demo",
        )
        self.assertEqual(
            self.document["spec"]["issue"]["value"],
            "https://github.com/CCI-MOC/MOC-issues/issues/666",
        )
        self.assertEqual(
            self.document["spec"]["hubCluster"]["value"],
            "bu-ist-demo-infra",
        )
        self.assertEqual(
            self.document["spec"]["workloadClusters"][0]["name"]["value"],
            "bu-ist-demo-workload0",
        )
        self.assertEqual(
            self.document["spec"]["workloadClusters"][0]["parentHubCluster"]["value"],
            "bu-ist-demo-infra",
        )
        self.assertEqual(
            self.document["spec"]["domain"]["value"],
            "bu-ist-demo.int.massopen.cloud",
        )
        self.assertEqual(
            self.document["spec"]["network"]["machineNetwork"]["value"],
            "10.20.26.0/23",
        )

    def test_environment_export_renders_deterministic_yaml(self) -> None:
        rendered = render_environment_export(
            self.environment,
            self.issue,
            self.infra,
            self.apps,
        )
        parsed = yaml.safe_load(rendered)

        self.assertEqual(parsed, self.document)

    def test_environment_bundle_validates(self) -> None:
        result = validate_environment(self.document)

        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])
        self.assertTrue(result.checks)

    def test_environment_bundle_rejects_reference_and_network_errors(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["hubCluster"]["value"] = "wrong-infra"
        document["spec"]["workloadClusters"][0]["parentHubCluster"]["value"] = (
            "another-infra"
        )
        document["spec"]["domain"]["value"] = "not a domain"
        document["spec"]["network"]["machineNetwork"]["value"] = "not-a-cidr"
        document["spec"]["workloadClusters"].append(
            copy.deepcopy(document["spec"]["workloadClusters"][0])
        )

        result = validate_environment(document)

        self.assertFalse(result.valid)
        self.assertIn(
            "spec.hubCluster.value: expected 'bu-ist-demo-infra', got 'wrong-infra'",
            result.errors,
        )
        self.assertIn(
            "spec.workloadClusters[0].parentHubCluster.value: expected "
            "'wrong-infra', got 'another-infra'",
            result.errors,
        )
        self.assertIn("spec.domain.value: invalid domain", result.errors)
        self.assertIn("spec.network.machineNetwork.value: invalid CIDR", result.errors)
        self.assertIn(
            "spec.workloadClusters: duplicate workload names: "
            "bu-ist-demo-workload0",
            result.errors,
        )

    def test_check_environment_compares_references_and_gitops(self) -> None:
        comparison = compare_environment(
            self.document,
            desired_environment(self.document),
            self.issue,
            self.infra,
            self.apps,
        )

        self.assertEqual(comparison.kind, "Environment")
        self.assertEqual(comparison.overall_state, "MATCHES MAIN")
        fields = {check.field for check in comparison.checks}
        self.assertIn("metadata.name.value", fields)
        self.assertIn("spec.issue.value", fields)
        self.assertIn("spec.hubCluster.value", fields)
        self.assertIn("spec.domain.value", fields)
        self.assertIn("spec.network.machineNetwork.value", fields)
        self.assertIn("spec.workloadClusters[0].gitOps.hostedClusterValues", fields)
        self.assertIn("spec.workloadClusters[0].gitOps.componentValues", fields)
        self.assertIn("spec.workloadClusters[0].gitOps.applications", fields)

    def test_check_environment_reports_missing_gitops(self) -> None:
        empty_apps = read_apps_observation(
            FakeGitHubClient(),
            self.environment,
            include_pull_requests=False,
        )
        comparison = compare_environment(
            self.document,
            self.environment,
            self.issue,
            self.infra,
            empty_apps,
        )

        self.assertEqual(comparison.overall_state, "DIFFERENCES FOUND")
        self.assertTrue(
            any(
                check.state == "missing_from_main"
                for check in comparison.checks
                if check.category == "GitOps"
            )
        )

    def test_cli_exports_validates_and_checks_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "environment.yaml"
            export_stdout = io.StringIO()
            export_stderr = io.StringIO()
            with (
                patch.object(cli, "_resolve_github_token", return_value=None),
                patch.object(cli, "GitHubClient", EnvironmentAppsClient),
                contextlib.redirect_stdout(export_stdout),
                contextlib.redirect_stderr(export_stderr),
            ):
                export_code = cli.main(
                    ["export-environment", "bu-ist-demo", "--output", str(path)]
                )

            self.assertEqual(export_code, 0)
            self.assertIn("wrote Environment YAML to", export_stderr.getvalue())

            document, validation = load_environment_document(path)
            self.assertTrue(validation.valid)

            check_stdout = io.StringIO()
            check_stderr = io.StringIO()
            with (
                patch.object(cli, "_resolve_github_token", return_value=None),
                patch.object(cli, "GitHubClient", EnvironmentAppsClient),
                contextlib.redirect_stdout(check_stdout),
                contextlib.redirect_stderr(check_stderr),
            ):
                check_code = cli.main(
                    [
                        "check-environment",
                        str(path),
                        "--no-prs",
                        "--format",
                        "markdown",
                    ]
                )

            self.assertEqual(check_code, 0)
            self.assertIn(
                "# 🔍 Environment Desired-State Comparison",
                check_stdout.getvalue(),
            )
            self.assertIn("Environment", check_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
