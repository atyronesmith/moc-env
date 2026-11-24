"""Offline checks for the Make interface and documentation command references."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    "help", "setup", "completion-init", "test", "lint", "typecheck", "coverage",
    "check", "build", "lock", "clean", "clean-all", "sample-reports", "cli",
    "sample-live", "update-samples",
}
SAMPLES = (
    "charts-summary.md", "charts-page.md", "status-oac-prod.md", "status-compliant-dev.md",
)
OFFLINE_UV = "synthetic-uv-must-not-execute"


def make_references(markdown):
    """Find literal make commands in inline code, fences, and command lines."""
    fence = None
    for number, line in enumerate(markdown.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence:
            fragments = [line]
        else:
            fragments = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", line)
            if re.match(r"^\s*(?:\$\s+)?make\s+", line):
                fragments.append(line)
        for fragment in fragments:
            for match in re.finditer(r"\bmake[ \t]+([A-Za-z][A-Za-z0-9_-]*)", fragment):
                yield number, match[1]


class MakefileTest(unittest.TestCase):
    def setUp(self):
        self.makefile = (ROOT / "Makefile").read_text()
        self.targets = set(re.findall(r"^([A-Za-z0-9_-]+):", self.makefile, re.MULTILINE))

    def make(self, *arguments):
        environment = os.environ.copy()
        for name in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
            environment.pop(name, None)
        return subprocess.run(
            ["make", *arguments, f"UV={OFFLINE_UV}"], cwd=ROOT, env=environment,
            text=True, capture_output=True, timeout=20,
        )

    def test_defined_and_phony_targets_are_exactly_the_public_interface(self):
        logical_lines = re.sub(r"\\\n[ \t]*", " ", self.makefile)
        phony = re.findall(r"^\.PHONY:\s*(.*)$", logical_lines, re.MULTILINE)
        self.assertEqual(len(phony), 1)
        self.assertEqual(set(phony[0].split()), TARGETS)
        self.assertEqual(self.targets, TARGETS)

    def test_every_target_has_help_and_is_listed_by_make_help(self):
        help_targets = set(re.findall(
            r"^([A-Za-z0-9_-]+):[^\n]*## .+", self.makefile, re.MULTILINE,
        ))
        self.assertEqual(help_targets, TARGETS)
        result = self.make("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        target_section = result.stdout.split("Targets:\n", 1)[1].split("\nCommon variables:", 1)[0]
        listed = set(re.findall(r"^  ([A-Za-z0-9_-]+)\s", target_section, re.MULTILINE))
        self.assertEqual(listed, TARGETS)

    def test_only_six_configurable_variables_and_help_is_the_default(self):
        variables = set(re.findall(r"^([A-Z_]+)\s*\?=", self.makefile, re.MULTILINE))
        self.assertEqual(variables, {
            "UV", "COMPLETION_SHELL", "COMPLETION_RC", "ARGS", "SAMPLE_DIR", "EXAMPLE_DIR",
        })
        assignments = set(re.findall(r"^([A-Z_]+)\s*[:?+]?=", self.makefile, re.MULTILINE))
        self.assertEqual(assignments, variables | {"SHELL"})
        self.assertRegex(self.makefile, r"(?m)^SHELL := /bin/sh$")
        self.assertRegex(self.makefile, r"(?m)^\.DEFAULT_GOAL := help$")
        self.assertEqual(self.make().stdout, self.make("help").stdout)

    def test_all_tracked_markdown_make_references_name_defined_targets(self):
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"], cwd=ROOT,
            text=True, capture_output=True, check=True,
        ).stdout.split("\0")
        unknown = []
        for name in filter(None, tracked):
            for line, target in make_references((ROOT / name).read_text()):
                if target not in self.targets:
                    unknown.append(f"{name}:{line}: make {target}")
        self.assertEqual(unknown, [], "Undefined documented targets:\n" + "\n".join(unknown))

    def test_documentation_guard_detects_removed_commands_but_not_prose(self):
        markdown = (
            "This does not make an environment configured.\n"
            "Use `make removed-inline`.\n"
            "```sh\nmake removed-fenced\n```\n"
            "$ make removed-command\n"
        )
        self.assertEqual(list(make_references(markdown)), [
            (2, "removed-inline"), (4, "removed-fenced"), (6, "removed-command"),
        ])

    def test_sample_live_dry_run_writes_exactly_four_named_outputs(self):
        for directory in ("reports/samples", "synthetic samples"):
            with self.subTest(directory=directory):
                arguments = [] if directory == "reports/samples" else [f"SAMPLE_DIR={directory}"]
                result = self.make("-n", "sample-live", *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                commands = [shlex.split(line) for line in result.stdout.splitlines()]
                invocations = [command for command in commands if "moc-env" in command]
                expected_arguments = [
                    ["charts"], ["charts", "--view", "page"],
                    ["status", "oac-prod"], ["status", "compliant-dev"],
                ]
                self.assertEqual(invocations, [
                    [OFFLINE_UV, "run", "--locked", "moc-env", *arguments,
                        "--output", f"{directory}/{name}"]
                    for arguments, name in zip(expected_arguments, SAMPLES)
                ])
                self.assertEqual(commands[0], ["mkdir", "-p", directory])

    def test_update_samples_rejects_missing_empty_or_incomplete_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for state in ("missing", "empty", "incomplete"):
                with self.subTest(state=state):
                    source = root / state
                    destination = root / f"{state}-examples"
                    if state != "missing":
                        source.mkdir()
                    if state == "incomplete":
                        (source / SAMPLES[0]).write_text("synthetic output\n")
                    result = self.make("update-samples", f"SAMPLE_DIR={source}", f"EXAMPLE_DIR={destination}")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("SAMPLE_DIR", result.stderr)
                    self.assertIn(str(source), result.stderr)
                    self.assertFalse(destination.exists())

    def test_update_samples_copies_only_four_files_and_requests_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "synthetic samples", root / "synthetic examples"
            source.mkdir()
            for name in (*SAMPLES, "unrelated.txt"):
                (source / name).write_text(f"synthetic output: {name}\n")
            result = self.make("update-samples", f"SAMPLE_DIR={source}", f"EXAMPLE_DIR={destination}")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path.name for path in destination.iterdir()}, set(SAMPLES))
            for name in SAMPLES:
                self.assertEqual((destination / name).read_bytes(), (source / name).read_bytes())
            self.assertIn(str(destination), result.stdout)
            self.assertIn("Review the diff", result.stdout)

    def test_check_dry_run_preserves_every_ci_step_in_order(self):
        result = self.make("-n", "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            f"{OFFLINE_UV} run --locked ruff check src tests tools",
            f"{OFFLINE_UV} run --locked mypy",
            f"{OFFLINE_UV} run --locked coverage run -m unittest discover -s tests",
            f"{OFFLINE_UV} run --locked coverage report",
            f"{OFFLINE_UV} run --locked python -m compileall -q src tests",
            "git diff --check",
            f"{OFFLINE_UV} run --locked python tools/check_pii.py",
            f"{OFFLINE_UV} build",
        ])

    def test_cli_dry_run_forwards_arguments_without_environment_defaults(self):
        result = self.make("-n", "cli", "ARGS=charts --view page")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{OFFLINE_UV} run --locked moc-env charts --view page")


if __name__ == "__main__":
    unittest.main()
