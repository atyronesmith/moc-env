from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from moc_env import cli
from moc_env.environment_cache import environment_cache_path

from fakes import FakeGitHubClient


class CompletionTest(unittest.TestCase):
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

    def test_list_writes_cache_and_hidden_command_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"MOC_ENV_CACHE_DIR": temporary_directory},
            ):
                exit_code, _, stderr = self.run_cli(["list", "--format", "json"])
                cache_path = environment_cache_path()
                self.assertTrue(cache_path.is_file())
                document = json.loads(cache_path.read_text(encoding="utf-8"))
                self.assertEqual(document["version"], 1)
                self.assertEqual(len(document["clusters"]), 2)

                exit_code, stdout, _ = self.run_cli(
                    ["__complete-environment", "bu-ist-", "environment"]
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(stdout, "bu-ist-demo\n")

                exit_code, stdout, _ = self.run_cli(
                    ["__complete-environment", "bu-ist-", "workload"]
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(stdout, "bu-ist-demo-workload0\n")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_hidden_completion_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"MOC_ENV_CACHE_DIR": temporary_directory},
            ):
                exit_code, _, stderr = self.run_cli(
                    ["__complete-environment", "", "invalid"]
                )

        self.assertEqual(exit_code, 2)
        self.assertIn("unknown completion mode", stderr)

    def test_completion_scripts_are_printed(self) -> None:
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                exit_code, stdout, _ = self.run_cli(["completion", shell])
                self.assertEqual(exit_code, 0)
                self.assertIn("__complete-environment", stdout)
                self.assertIn("export-workload", stdout)
                self.assertIn("hub-status", stdout)
                self.assertIn("work-status", stdout)
                if shell == "bash":
                    self.assertIn("complete -o default", stdout)
                else:
                    self.assertIn("compdef _moc-env moc-env", stdout)
