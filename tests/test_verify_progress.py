"""Offline verification progress and capture handoff regressions."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.charts import collect_chart_inventory
from moc_env.live_cli import _declared_workload
from moc_env.verify_live import LocalRepositories, Snapshot, _values, verify_live


FIXTURES = (Path(__file__).parent / "fixtures/live").resolve()
REPOS = FIXTURES / "repos"
WORKLOAD = "test-env-workload0"


class VerifyProgressTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.client = LocalRepositories(REPOS)
        self.events = []

    def verify(self, progress=None):
        ticks = itertools.count()
        with (
            patch("subprocess.run", side_effect=AssertionError("verification is offline")),
            patch("urllib.request.urlopen", side_effect=AssertionError("no HTTP")),
            patch("moc_env.verify_live.monotonic", side_effect=lambda: next(ticks) / 10),
        ):
            return verify_live(self.client, "test-env", WORKLOAD, FIXTURES / "workload0", progress=progress)

    def verify_cli(self, format="text", force=False, tty=False, output=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ["verify-live", "test-env", "--workload", "workload0",
                    "--snapshot", str(FIXTURES / "workload0"),
                    "--repository-root", str(REPOS), "--format", format]
        if force:
            arguments.append("--progress")
        if output is not None:
            arguments.extend(["--output", str(output)])
        ticks = itertools.count()
        with (
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
            patch.object(stderr, "isatty", return_value=tty),
            patch.object(stderr, "flush", wraps=stderr.flush) as flush,
            patch("subprocess.run", side_effect=AssertionError("verification is offline")),
            patch("urllib.request.urlopen", side_effect=AssertionError("no HTTP")),
            patch("moc_env.verify_live.monotonic", side_effect=lambda: next(ticks) / 10),
            patch.object(cli, "_resolve_github_token", side_effect=AssertionError("local repos need no credentials")),
        ):
            code = cli.main(arguments)
            flushes = flush.call_count
        return code, stdout.getvalue(), stderr.getvalue(), flushes

    def test_callback_order_positions_totals_verdicts_and_sections(self):
        def manifest(directory):
            self.assertEqual(self.events[-1]["event"], "manifest")
            return Snapshot(directory)

        def inventory(*args, **kwargs):
            self.assertEqual(self.events[-1]["event"], "inventory")
            self.assertTrue(callable(kwargs["progress"]))
            return collect_chart_inventory(*args, **kwargs)

        def values(*args, **kwargs):
            self.assertEqual(self.events[-1]["event"], "chart_start")
            return _values(*args, **kwargs)

        with (
            patch("moc_env.verify_live.Snapshot", side_effect=manifest),
            patch("moc_env.verify_live.collect_chart_inventory", side_effect=inventory),
            patch("moc_env.verify_live._values", side_effect=values),
        ):
            report = self.verify(self.events.append)
        self.assertEqual([event["event"] for event in self.events[:2]], ["manifest", "inventory"])
        reads = [event for event in self.events if event["event"] == "chart"]
        self.assertTrue(reads)
        self.assertTrue(all(event["repository"] == "CCI-MOC/oac-apps" for event in reads))
        starts = [event for event in self.events if event["event"] == "chart_start"]
        ends = [event for event in self.events if event["event"] == "chart_end"]
        rows = report["sections"]["Charts"]
        self.assertEqual(len(starts), len(rows))
        self.assertEqual(len(ends), len(rows))
        for position, (start, end, row) in enumerate(zip(starts, ends, rows), 1):
            with self.subTest(chart=row["name"]):
                expected = {"chart": row["name"], "position": position, "total": len(rows)}
                self.assertEqual(start, {"event": "chart_start", **expected})
                for key, value in expected.items():
                    self.assertEqual(end[key], value)
                self.assertEqual(end["verdict"], row["verdict"])
                self.assertAlmostEqual(end["elapsed"], 0.1)
                self.assertEqual(self.events.index(end), self.events.index(start) + 1)
        self.assertEqual(self.events[-4:], [
            {"event": "section", "section": name}
            for name in ("Nodes", "Quotas", "OpenShift AI", "Health")
        ])

    def test_progress_does_not_print_or_change_structured_report(self):
        with patch("builtins.print", side_effect=AssertionError("verify_live must not print")):
            plain = self.verify()
            reporting = self.verify(self.events.append)
        self.assertTrue(self.events)
        self.assertEqual(reporting, plain)

    def test_non_terminal_success_writes_nothing_to_stderr(self):
        code, stdout, stderr, _ = self.verify_cli()
        self.assertEqual((code, stderr), (1, ""))
        self.assertTrue(stdout)

    def test_progress_preserves_stdout_exactly_in_all_formats(self):
        rows = self.verify()["sections"]["Charts"]
        for format in ("text", "json", "markdown"):
            with self.subTest(format=format):
                code, plain, stderr, _ = self.verify_cli(format)
                reporting_code, reporting, progress, flushes = self.verify_cli(format, force=True)
                self.assertEqual((code, reporting_code, stderr), (1, 1, ""))
                self.assertEqual(reporting.encode(), plain.encode())
                lines = progress.splitlines()
                self.assertEqual(lines[:3], [
                    "▶ Resolving workload clusters for test-env",
                    "▶ Reading snapshot manifest",
                    "▶ Reading chart declarations",
                ])
                charts = [line for line in lines if " chart " in line and " ... " in line]
                self.assertEqual(charts, [
                    f"▶ {position}/{len(rows)} chart {row['name']} ... {row['verdict']} in 0.1s"
                    for position, row in enumerate(rows, 1)
                ])
                self.assertGreaterEqual(flushes, 2 * len(rows))
                self.assertEqual(lines[-4:], ["▶ Nodes", "▶ Quotas", "▶ OpenShift AI", "▶ Health"])

    def test_progress_preserves_output_file_bytes_in_all_formats(self):
        for format in ("text", "json", "markdown"):
            with self.subTest(format=format):
                plain = self.directory / f"plain.{format}"
                reporting = self.directory / f"reporting.{format}"
                code, stdout, stderr, _ = self.verify_cli(format, output=plain)
                reporting_code, reporting_stdout, progress, _ = self.verify_cli(format, force=True, output=reporting)
                self.assertEqual((code, reporting_code, stdout, reporting_stdout), (1, 1, "", ""))
                self.assertEqual(plain.read_bytes(), reporting.read_bytes())
                self.assertEqual(stderr, f"moc-env: wrote {format} verification report to {plain}\n")
                self.assertEqual(progress.splitlines()[-1],
                                f"moc-env: wrote {format} verification report to {reporting}")

    def test_chart_start_is_flushed_before_values_are_read(self):
        def read(client, tree, paths):
            chart = paths[0].split("/")[1]
            self.assertTrue(sys.stderr.getvalue().endswith(f"chart {chart} ... "))
            return _values(client, tree, paths)

        with patch("moc_env.verify_live._values", side_effect=read):
            self.assertEqual(self.verify_cli(force=True)[0], 1)

    def test_terminal_automatically_enables_progress(self):
        code, _, stderr, _ = self.verify_cli(tty=True)
        self.assertEqual(code, 1)
        self.assertEqual(stderr.splitlines()[0], "▶ Resolving workload clusters for test-env")

    def test_workload_resolution_status_precedes_inventory_reads(self):
        def resolve(*args):
            self.assertEqual(sys.stderr.getvalue(), "▶ Resolving workload clusters for test-env\n")
            return _declared_workload(*args)

        with patch("moc_env.live_cli._declared_workload", side_effect=resolve):
            self.assertEqual(self.verify_cli(force=True)[0], 1)

    def test_capture_handoff_uses_absolute_path_resolved_workload_and_shell_quoting(self):
        def resolve(*args):
            self.assertEqual(sys.stderr.getvalue(), "▶ Resolving workload clusters for test-env\n")
            return _declared_workload(*args)

        def oc(command, **kwargs):
            if command[2] == "infrastructures.config.openshift.io":
                data = {"items": [{"metadata": {"name": "cluster"}, "status": {
                    "apiServerURL": f"https://api-internal-{WORKLOAD}.internal.synthetic.invalid:6443",
                }}]}
            elif command[2] == "users.user.openshift.io":
                data = {"metadata": {"name": "synthetic-reader"}}
            else:
                data = {"items": []}
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.chdir(self.directory),
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=oc),
            patch("moc_env.live_cli.monotonic", return_value=0),
            patch("moc_env.live_cli._declared_workload", side_effect=resolve),
        ):
            code = cli.main([
                "capture-live", "test-env", "--workload", "workload0", "--out", "synthetic capture",
                "--repository-root", str(REPOS), "--progress",
            ])
        output = self.directory.resolve() / "synthetic capture"
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(),
                        f"Snapshot: {output} · 19 kinds · 0 forbidden · 0s\n"
                        f"Next: moc-env verify-live test-env --workload {WORKLOAD} --snapshot {shlex.quote(str(output))}\n")
        self.assertTrue((output / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
