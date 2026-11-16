from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli

from fakes import FakeGitHubClient


class CliDispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        cache_directory = tempfile.TemporaryDirectory()
        self.addCleanup(cache_directory.cleanup)
        environment = patch.dict(
            os.environ,
            {"MOC_ENV_CACHE_DIR": cache_directory.name},
        )
        environment.start()
        self.addCleanup(environment.stop)

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "GitHubClient", FakeGitHubClient),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_list_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["list"])
        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo", stdout)
        self.assertIn("moc-env status-hub bu-ist-demo", stdout)
        self.assertIn("moc-env status-workload bu-ist-demo", stdout)
        self.assertEqual(stderr, "")

    def test_top_level_help_lists_every_command(self) -> None:
        rendered = cli.build_parser().format_help()

        self.assertIn("Commands:", rendered)
        for command in (
            "status",
            "status-hub",
            "status-workload",
            "list",
            "export-infra",
            "export-workload",
            "export-environment",
            "validate",
            "check-infra",
            "check-workload",
            "check-environment",
            "plan-infra",
            "document-values",
            "refresh-doc-catalog",
            "discover-values",
            "completion",
        ):
            with self.subTest(command=command):
                self.assertIn(command, rendered)

    def test_no_arguments_prints_command_help(self) -> None:
        for arguments in ([], ["--help"], ["-h"]):
            with self.subTest(arguments=arguments):
                exit_code, stdout, stderr = self.run_cli(arguments)

                self.assertEqual(exit_code, 0)
                self.assertIn("Commands:", stdout)
                self.assertIn("status", stdout)
                self.assertIn("status-hub", stdout)
                self.assertIn("status-workload", stdout)
                self.assertEqual(stderr, "")

    def test_environment_without_command_is_rejected(self) -> None:
        exit_code, _, stderr = self.run_cli(
            ["bu-ist-demo", "--format", "json", "--no-prs"]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("unknown command: bu-ist-demo", stderr)
        self.assertIn("Commands:", stderr)

    def test_old_status_command_names_are_rejected(self) -> None:
        for command in ("hub-status", "work-status"):
            with self.subTest(command=command):
                exit_code, _, stderr = self.run_cli(
                    [command, "bu-ist-demo", "--format", "json", "--no-prs"]
                )

                self.assertEqual(exit_code, 2)
                self.assertIn(f"unknown command: {command}", stderr)

    def test_list_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(["list", "--format", "json"])
        self.assertEqual(exit_code, 0)
        clusters = json.loads(stdout)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["environment"], "bu-ist-demo")
        self.assertEqual(clusters[0]["cluster"], "bu-ist-demo-infra")
        self.assertEqual(clusters[0]["type"], "hub")
        self.assertEqual(clusters[1]["cluster"], "bu-ist-demo-workload0")
        self.assertEqual(clusters[1]["type"], "workload")

    def test_status_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--format", "json", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["environment"]["name"], "bu-ist-demo")
        self.assertGreater(len(report["checks"]), 0)

    def test_status_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("Environment configuration status: bu-ist-demo", stdout)
        self.assertIn("Step 1:", stderr)
        self.assertIn("Step 6:", stderr)
        self.assertNotIn("Step 7:", stderr)

    def test_hub_status_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status-hub", "bu-ist-demo", "--format", "json", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["scope"], "hub")
        checks = {check["check"] for check in report["checks"]}
        self.assertIn("Hub image variables", checks)
        self.assertNotIn("Workload hosted-cluster values", checks)

    def test_work_status_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["status-workload", "bu-ist-demo", "--format", "text", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Workload environment configuration status: bu-ist-demo", stdout
        )
        self.assertIn("bu-ist-demo-workload0 host inventory", stdout)
        self.assertNotIn("Hub image variables", stdout)
        self.assertIn("Step 1:", stderr)

    def test_status_markdown_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "report.md"
            exit_code, stdout, stderr = self.run_cli(
                [
                    "status",
                    "bu-ist-demo",
                    "--format",
                    "markdown",
                    "--no-prs",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote markdown report to {output}", stderr)
            report = output.read_text(encoding="utf-8")
        self.assertIn("# Environment configuration status", report)

    def test_export_infra_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["export-infra", "bu-ist-demo"])
        self.assertEqual(exit_code, 0)
        document = yaml.safe_load(stdout)
        self.assertEqual(document["kind"], "InfraCluster")
        self.assertEqual(document["metadata"]["name"]["value"], "bu-ist-demo-infra")
        self.assertIn("Step 1:", stderr)
        self.assertIn("Step 3:", stderr)
        self.assertNotIn("Step 4:", stderr)

    def test_export_infra_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "desired-state" / "infra-cluster.yaml"
            exit_code, stdout, stderr = self.run_cli(
                ["export-infra", "bu-ist-demo", "--output", str(output)]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote InfraCluster YAML to {output}", stderr)
            document = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(document["apiVersion"], "moc-env/v1alpha1")

    def test_export_workload_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["export-workload", "bu-ist-demo", "workload0"]
        )
        self.assertEqual(exit_code, 0)
        document = yaml.safe_load(stdout)
        self.assertEqual(document["kind"], "WorkloadCluster")
        self.assertEqual(
            document["metadata"]["name"]["value"],
            "bu-ist-demo-workload0",
        )
        self.assertIn("Step 1:", stderr)
        self.assertIn("Step 4:", stderr)
        self.assertNotIn("Step 5:", stderr)

    def test_export_workload_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = (
                Path(temporary_directory)
                / "desired-state"
                / "bu-ist-demo-workload0.yaml"
            )
            exit_code, stdout, stderr = self.run_cli(
                [
                    "export-workload",
                    "bu-ist-demo",
                    "workload0",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote WorkloadCluster YAML to {output}", stderr)
            document = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(document["kind"], "WorkloadCluster")
