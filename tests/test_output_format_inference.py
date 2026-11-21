"""Offline coverage for inferring output format from --output extensions."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fakes import FakeGitHubClient
from test_charts import ChartsFakeGitHubClient

from moc_env import cli


VALID_INFRA = Path(__file__).parent / "fixtures" / "oac-prod-infra.yaml"


class OutputFormatInferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

    def run_cli(
        self,
        arguments: list[str],
        client_class=FakeGitHubClient,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "GitHubClient", client_class),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                exit_code = cli.main(arguments)
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 2
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def charts_arguments(self, *extra: str) -> list[str]:
        return ["charts", "bu-ist-demo", *extra]

    def status_arguments(self, *extra: str) -> list[str]:
        return ["status", "bu-ist-demo", "--no-prs", *extra]

    def validate_arguments(self, *extra: str) -> list[str]:
        return ["validate", str(VALID_INFRA), *extra]

    def test_charts_md_extension_writes_markdown(self) -> None:
        output = self.root / "charts.md"

        exit_code, stdout, stderr = self.run_cli(
            self.charts_arguments("--output", str(output)),
            ChartsFakeGitHubClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertTrue(
            output.read_text(encoding="utf-8").startswith("## Workload clusters")
        )
        self.assertIn("wrote markdown chart inventory", stderr)

    def test_charts_json_extension_writes_json(self) -> None:
        output = self.root / "charts.json"

        exit_code, _, _ = self.run_cli(
            self.charts_arguments("--output", str(output)),
            ChartsFakeGitHubClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("tables", json.loads(output.read_text(encoding="utf-8")))

    def test_charts_txt_and_extensionless_outputs_use_text(self) -> None:
        for path in (self.root / "charts.txt", self.root / "charts"):
            with self.subTest(path=path.name):
                exit_code, _, _ = self.run_cli(
                    self.charts_arguments("--output", str(path)),
                    ChartsFakeGitHubClient,
                )
                rendered = path.read_text(encoding="utf-8")
                self.assertEqual(exit_code, 0)
                self.assertTrue(rendered.startswith("Workload clusters"))
                self.assertFalse(rendered.startswith("## "))

    def test_charts_explicit_format_wins_over_extension(self) -> None:
        output = self.root / "charts.md"

        exit_code, _, _ = self.run_cli(
            self.charts_arguments(
                "--format", "text", "--output", str(output)
            ),
            ChartsFakeGitHubClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            output.read_text(encoding="utf-8").startswith("Workload clusters")
        )

    def test_charts_no_output_keeps_text_default(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            self.charts_arguments(), ChartsFakeGitHubClient
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(stdout.startswith("Workload clusters"))

    def test_status_md_extension_writes_markdown(self) -> None:
        output = self.root / "status.MD"

        exit_code, stdout, stderr = self.run_cli(
            self.status_arguments("--output", str(output))
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertTrue(
            output.read_text(encoding="utf-8").startswith("# bu-ist-demo")
        )
        self.assertIn("wrote markdown report", stderr)

    def test_status_json_extension_writes_json(self) -> None:
        output = self.root / "status.json"

        exit_code, _, _ = self.run_cli(
            self.status_arguments("--output", str(output))
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("checks", json.loads(output.read_text(encoding="utf-8")))

    def test_status_txt_and_extensionless_outputs_use_text(self) -> None:
        for path in (self.root / "status.txt", self.root / "status"):
            with self.subTest(path=path.name):
                exit_code, _, _ = self.run_cli(
                    self.status_arguments("--output", str(path))
                )
                rendered = path.read_text(encoding="utf-8")
                self.assertEqual(exit_code, 0)
                self.assertIn("RESULT:", rendered)
                self.assertFalse(rendered.startswith("# "))

    def test_status_explicit_format_wins_over_extension(self) -> None:
        output = self.root / "status.md"

        exit_code, _, _ = self.run_cli(
            self.status_arguments("--format", "text", "--output", str(output))
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("RESULT:", output.read_text(encoding="utf-8"))

    def test_status_no_output_keeps_text_default(self) -> None:
        exit_code, stdout, _ = self.run_cli(self.status_arguments())

        self.assertEqual(exit_code, 0)
        self.assertIn("RESULT:", stdout)
        self.assertFalse(stdout.startswith("# "))

    def test_status_inferred_markdown_still_requires_an_environment(self) -> None:
        output = self.root / "fleet.md"

        exit_code, _, stderr = self.run_cli(
            ["status", "--no-prs", "--output", str(output)]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn(
            "--format markdown requires an environment name", stderr
        )

    def test_validate_md_extension_writes_markdown(self) -> None:
        output = self.root / "validation.markdown"

        exit_code, stdout, stderr = self.run_cli(
            self.validate_arguments("--output", str(output))
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertTrue(
            output.read_text(encoding="utf-8").startswith(
                "# 🧪 Desired-State Validation"
            )
        )
        self.assertIn("wrote markdown validation report", stderr)

    def test_validate_json_extension_writes_json(self) -> None:
        output = self.root / "validation.json"

        exit_code, _, _ = self.run_cli(
            self.validate_arguments("--output", str(output))
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            json.loads(output.read_text(encoding="utf-8"))["valid"]
        )

    def test_validate_txt_and_extensionless_outputs_use_text(self) -> None:
        for path in (self.root / "validation.txt", self.root / "validation"):
            with self.subTest(path=path.name):
                exit_code, _, _ = self.run_cli(
                    self.validate_arguments("--output", str(path))
                )
                rendered = path.read_text(encoding="utf-8")
                self.assertEqual(exit_code, 0)
                self.assertIn("Desired-state validation: VALID", rendered)
                self.assertFalse(rendered.startswith("# "))

    def test_validate_explicit_format_wins_over_extension(self) -> None:
        output = self.root / "validation.md"

        exit_code, _, _ = self.run_cli(
            self.validate_arguments(
                "--format", "text", "--output", str(output)
            )
        )

        self.assertEqual(exit_code, 0)
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("Desired-state validation: VALID", rendered)
        self.assertFalse(rendered.startswith("# "))

    def test_validate_no_output_keeps_text_default(self) -> None:
        exit_code, stdout, _ = self.run_cli(self.validate_arguments())

        self.assertEqual(exit_code, 0)
        self.assertIn("Desired-state validation: VALID", stdout)
        self.assertFalse(stdout.startswith("# "))

    def test_unsupported_inferred_format_warns_and_uses_default(self) -> None:
        output = self.root / "catalog.md"

        with patch.object(cli, "load_catalog_sources", return_value={}):
            exit_code, stdout, stderr = self.run_cli(
                [
                    "refresh-doc-catalog",
                    "--repository-root",
                    str(self.root / "MOC"),
                    "--cache-root",
                    str(self.root / "cache"),
                    "--output",
                    str(output),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("Documentation catalog refresh", rendered)
        self.assertFalse(rendered.startswith("# "))
        warnings = [
            line for line in stderr.splitlines() if "warning:" in line
        ]
        self.assertEqual(len(warnings), 1, stderr)
        self.assertIn(str(output), warnings[0])
        self.assertIn("markdown", warnings[0])
        self.assertIn("text", warnings[0])


if __name__ == "__main__":
    unittest.main()
