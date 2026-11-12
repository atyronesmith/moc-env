from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli
from moc_env.compare import compare_infra
from moc_env.export import build_infra_export
from moc_env.model import Environment
from moc_env.observed import read_apps_observation, read_infra_observation

from fakes import FakeGitHubClient


class CompareInfraTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment(name="bu-ist-demo", issue_number=666)
        self.client = FakeGitHubClient()
        self.observation = read_infra_observation(self.client, self.environment)
        self.apps = read_apps_observation(self.client, self.environment)
        self.document = build_infra_export(self.environment, self.observation)

    def test_exported_current_state_matches_main(self) -> None:
        report = compare_infra(
            self.document,
            self.environment,
            self.observation,
            self.apps,
        )
        states = [check.state for check in report.checks]

        self.assertNotIn("value_mismatch", states)
        self.assertNotIn("missing_from_main", states)
        self.assertNotIn("unexpected_in_main", states)
        self.assertNotIn("unsupported_check", states)
        self.assertNotIn("ambiguous", states)
        self.assertIn("pr_open", states)
        self.assertEqual(
            [state for state in states if state != "pr_open"],
            ["matches_main"] * (len(states) - 1),
        )

    def test_one_changed_desired_value_produces_exactly_one_mismatch(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["value"] = "10.20.27.99"

        report = compare_infra(
            document,
            self.environment,
            self.observation,
            self.apps,
        )
        mismatches = [
            check for check in report.checks if check.state == "value_mismatch"
        ]

        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].field, "spec.variables.fields.api_ip.value")
        self.assertEqual(mismatches[0].desired, "10.20.27.99")
        self.assertEqual(mismatches[0].current, "10.20.27.11")

    def test_desired_cluster_missing_from_main(self) -> None:
        document = copy.deepcopy(self.document)
        document["metadata"]["name"]["value"] = "missing-env-infra"
        document["metadata"]["environment"]["value"] = "missing-env"
        document["spec"]["inventory"]["clusters"] = {
            "missing-env-infra": document["spec"]["inventory"]["clusters"][
                "bu-ist-demo-infra"
            ]
        }

        report = compare_infra(
            document,
            Environment(name="missing-env"),
            self.observation,
            None,
        )
        missing = [
            check for check in report.checks if check.state == "missing_from_main"
        ]

        self.assertEqual(len(missing), 1)
        self.assertEqual(
            missing[0].field,
            "spec.inventory.clusters.missing-env-infra",
        )

    def test_current_cluster_unexpected_in_main(self) -> None:
        document = copy.deepcopy(self.document)
        del document["spec"]["inventory"]["clusters"]["bu-ist-demo-workload0"]

        report = compare_infra(
            document,
            self.environment,
            self.observation,
            None,
        )
        unexpected = [
            check for check in report.checks if check.state == "unexpected_in_main"
        ]

        self.assertEqual(len(unexpected), 1)
        self.assertEqual(
            unexpected[0].field,
            "spec.inventory.clusters.bu-ist-demo-workload0",
        )

    def test_unsupported_desired_value(self) -> None:
        document = copy.deepcopy(self.document)
        del document["spec"]["variables"]["fields"]["dns_ip"]["value"]

        report = compare_infra(
            document,
            self.environment,
            self.observation,
            None,
        )
        unsupported = [
            check for check in report.checks if check.state == "unsupported_check"
        ]

        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0].field, "spec.variables.fields.dns_ip.value")

    def test_ambiguous_current_boot_image(self) -> None:
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

        ambiguous_observation = read_infra_observation(
            AmbiguousBootImageClient(),
            self.environment,
        )
        report = compare_infra(
            self.document,
            self.environment,
            ambiguous_observation,
            None,
        )
        ambiguous = [check for check in report.checks if check.state == "ambiguous"]

        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(
            ambiguous[0].field,
            "spec.inventory.clusters.bu-ist-demo-infra.bootImage.selected.value",
        )

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

    def test_cli_check_infra_json_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "infra.yaml"
            path.write_text(yaml.safe_dump(self.document), encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli(
                ["check-infra", str(path), "--format", "json"]
            )

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["environment"]["name"], "bu-ist-demo")
        self.assertIn("matches_main", report["summary"]["state_counts"])
        self.assertIn("pr_open", report["summary"]["state_counts"])
        self.assertIn("Step 1: Hardware and inventory", stderr)
        self.assertIn("Step 5: GitOps configuration", stderr)

    def test_cli_check_infra_markdown_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "infra.yaml"
            output_path = Path(temporary_directory) / "comparison.md"
            input_path.write_text(yaml.safe_dump(self.document), encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli(
                [
                    "check-infra",
                    str(input_path),
                    "--format",
                    "markdown",
                    "--output",
                    str(output_path),
                ]
            )
            rendered = output_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertIn(
            f"wrote markdown comparison report to {output_path}",
            stderr,
        )
        self.assertIn("# 🔍 Infra Desired-State Comparison", rendered)
        self.assertIn("## Detailed comparison", rendered)
        self.assertIn("`matches_main`", rendered)

    def test_cli_check_infra_returns_nonzero_for_mismatch(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["value"] = "10.20.27.99"
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "infra.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            exit_code, stdout, _ = self.run_cli(
                ["check-infra", str(path), "--format", "json", "--no-prs"]
            )

        self.assertEqual(exit_code, 1)
        report = json.loads(stdout)
        self.assertEqual(report["summary"]["state_counts"]["value_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
