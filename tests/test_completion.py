from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from moc_env import cli
from moc_env.completion import argument_completion, positional_actions
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
        self.assertEqual(stderr, "GitHub API: 0 requests, 0 counted against quota, 0 from cache\n")

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

    def test_hidden_completion_refreshes_an_empty_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": temporary_directory}),
                patch.object(cli, "GitHubClient", FakeGitHubClient),
            ):
                cache_path = environment_cache_path()
                exit_code, stdout, stderr = self.run_cli(
                    ["__complete-environment", "bu-ist-", "environment"]
                )
                self.assertTrue(cache_path.is_file())

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "bu-ist-demo\n")
        self.assertEqual(stderr, "GitHub API: 0 requests, 0 counted against quota, 0 from cache\n")

    def test_hidden_completion_lists_command_options(self) -> None:
        exit_code, stdout, _ = self.run_cli(["__complete-options", "status", "--"])

        self.assertEqual(exit_code, 0)
        options = stdout.splitlines()
        for option in (
            "--format",
            "--no-prs",
            "--ref",
            "--details",
            "--fail-on",
            "--offline",
            "--refresh",
            "--output",
        ):
            self.assertIn(option, options)
        self.assertNotIn("--workload", options)

    def test_hidden_completion_lists_option_choices(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["__complete-option", "status", "--format", "m"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "markdown\n")

        exit_code, stdout, _ = self.run_cli(
            ["__complete-option", "status", "--no-prs", ""]
        )

        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout, "")

        exit_code, stdout, _ = self.run_cli(
            ["__complete-option", "status", "--output", "reports/"]
        )

        self.assertEqual(exit_code, 4)
        self.assertEqual(stdout, "")

    def test_hidden_completion_identifies_file_positionals(self) -> None:
        exit_code, _, _ = self.run_cli(
            ["__complete-positional", "validate", "2", "moc-env", "validate", ""]
        )
        self.assertEqual(exit_code, 4)

        exit_code, _, _ = self.run_cli(
            ["__complete-positional", "list", "2", "moc-env", "list", ""]
        )
        self.assertEqual(exit_code, 3)

    def test_hidden_completion_follows_positional_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": temporary_directory}):
                exit_code, _, _ = self.run_cli(["list", "--format", "json"])
                self.assertEqual(exit_code, 0)

                for arguments, expected in (
                    (
                        ["__complete-positional", "diff", "2", "moc-env", "diff", "bu-ist-"],
                        "bu-ist-demo\n",
                    ),
                    (
                        [
                            "__complete-positional",
                            "diff",
                            "3",
                            "moc-env",
                            "diff",
                            "bu-ist-demo",
                            "bu-ist-",
                        ],
                        "bu-ist-demo\n",
                    ),
                    (
                        [
                            "__complete-positional",
                            "status",
                            "3",
                            "moc-env",
                            "status",
                            "--details",
                            "bu-ist-",
                        ],
                        "bu-ist-demo\n",
                    ),
                    (
                        [
                            "__complete-positional",
                            "export-workload",
                            "3",
                            "moc-env",
                            "export-workload",
                            "bu-ist-demo",
                            "bu-ist-",
                        ],
                        "bu-ist-demo-workload0\n",
                    ),
                    (
                        ["__complete-positional", "completion", "2", "moc-env", "completion", "b"],
                        "bash\n",
                    ),
                    (
                        [
                            "__complete-option",
                            "status-workload",
                            "--workload",
                            "bu-ist-",
                        ],
                        "bu-ist-demo-workload0\n",
                    ),
                ):
                    with self.subTest(arguments=arguments):
                        exit_code, stdout, _ = self.run_cli(arguments)
                        self.assertEqual(exit_code, 0)
                        self.assertEqual(stdout, expected)

    def test_hidden_completion_rejects_an_unknown_command(self) -> None:
        exit_code, _, stderr = self.run_cli(["__complete-options", "nope", "--"])

        self.assertEqual(exit_code, 2)
        self.assertIn("unknown completion command", stderr)

    def test_every_command_positional_declares_completion(self) -> None:
        parser = cli.build_parser()
        for action in parser._actions:
            if not hasattr(action, "choices") or not isinstance(action.choices, dict):
                continue
            for command, command_parser in action.choices.items():
                for positional in positional_actions(command_parser):
                    with self.subTest(command=command, positional=positional.dest):
                        if positional.choices:
                            self.assertIsNone(argument_completion(positional))
                        else:
                            self.assertIn(
                                argument_completion(positional),
                                {"environment", "workload", "file"},
                            )

    def test_completion_scripts_are_printed(self) -> None:
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                exit_code, stdout, _ = self.run_cli(["completion", shell])
                self.assertEqual(exit_code, 0)
                self.assertIn("__complete-positional", stdout)
                self.assertIn("export-workload", stdout)
                self.assertIn("status", stdout)
                self.assertIn("status-hub", stdout)
                self.assertIn("status-workload", stdout)
                self.assertIn("uv run moc-env", stdout)
                self.assertIn("MOC_ENV_COMPLETION_COMMAND", stdout)
                self.assertIn("__complete-options", stdout)
                self.assertIn("__complete-option", stdout)
                if shell == "bash":
                    self.assertIn("complete -o filenames", stdout)
                else:
                    self.assertIn("compdef _moc-env moc-env", stdout)

    def test_bash_completion_offers_commands_and_environments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {
                    "MOC_ENV_CACHE_DIR": temporary_directory,
                    "MOC_ENV_COMPLETION_COMMAND": f"{sys.executable} -m moc_env.cli",
                },
            ):
                exit_code, _, _ = self.run_cli(["list", "--format", "json"])
                self.assertEqual(exit_code, 0)

                script = self.run_cli(["completion", "bash"])[1]
                for words, cword, expected in (
                    ("moc-env status-", 1, "status-hub\nstatus-workload\n"),
                    ("moc-env status-hub bu-ist-", 2, "bu-ist-demo\n"),
                    ("moc-env status --for", 2, "--format\n"),
                    ("moc-env status --format ", 3, "text\njson\nmarkdown\n"),
                    ("moc-env diff bu-ist-", 2, "bu-ist-demo\n"),
                    ("moc-env diff bu-ist-demo bu-ist-", 3, "bu-ist-demo\n"),
                    ("moc-env status --details bu-ist-", 3, "bu-ist-demo\n"),
                    ("moc-env completion b", 2, "bash\n"),
                ):
                    with self.subTest(words=words):
                        completion = subprocess.run(
                            [
                                "bash",
                                "-c",
                                script
                                + f'\nCOMP_WORDS=({words}); COMP_CWORD={cword}; '
                                + '_moc_env_complete; printf \'%s\\n\' "${COMPREPLY[@]}"',
                            ],
                            cwd=os.getcwd(),
                            text=True,
                            capture_output=True,
                            check=True,
                        )
                        self.assertEqual(completion.stdout, expected)

    def test_bash_completion_offers_files_for_file_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            for name in ("report.md", "doc.yaml"):
                with open(os.path.join(temporary_directory, name), "w", encoding="utf-8"):
                    pass
            with patch.dict(
                os.environ,
                {
                    "MOC_ENV_CACHE_DIR": temporary_directory,
                    "MOC_ENV_COMPLETION_COMMAND": f"{sys.executable} -m moc_env.cli",
                },
            ):
                script = self.run_cli(["completion", "bash"])[1]
                for words, cword, expected in (
                    ("moc-env status --output rep", 3, "report.md\n"),
                    ("moc-env validate doc", 2, "doc.yaml\n"),
                ):
                    with self.subTest(words=words):
                        completion = subprocess.run(
                            [
                                "bash",
                                "-c",
                                script
                                + f'\nCOMP_WORDS=({words}); COMP_CWORD={cword}; '
                                + '_moc_env_complete; printf \'%s\\n\' "${COMPREPLY[@]}"',
                            ],
                            cwd=temporary_directory,
                            text=True,
                            capture_output=True,
                            check=True,
                        )
                        self.assertEqual(completion.stdout, expected)
