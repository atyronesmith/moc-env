"""Offline verification progress and capture handoff regressions."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.charts import ChartInventoryError, collect_chart_inventory
from moc_env.live_cli import LiveProgressReporter, _declared_workload
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

    def verify_cli(self, format="text", force=False, tty=False, output=None, verbose=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ["verify-live", "test-env", "--workload", "workload0",
                    "--snapshot", str(FIXTURES / "workload0"),
                    "--repository-root", str(REPOS), "--format", format]
        if force:
            arguments.append("--progress")
        if verbose:
            arguments.append("--verbose")
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
                reporting_code, reporting, progress, _ = self.verify_cli(format, force=True)
                self.assertEqual((code, reporting_code, stderr), (1, 1, ""))
                self.assertEqual(reporting.encode(), plain.encode())
                lines = progress.splitlines()
                self.assertEqual(lines[:3], [
                    "▶ Resolving workload clusters for test-env",
                    "▶ Reading snapshot manifest",
                    "▶ Reading chart declarations",
                ])
                charts = [line for line in lines if " chart " in line and " ... " in line]
                self.assertEqual(charts, [])
                self.assertEqual(lines[-4:], ["▶ Nodes", "▶ Quotas", "▶ OpenShift AI", "▶ Health"])
                verbose_code, verbose_output, verbose_progress, flushes = self.verify_cli(format, verbose=True)
                self.assertEqual(verbose_code, code)
                self.assertEqual(verbose_output.encode(), plain.encode())
                charts = [line for line in verbose_progress.splitlines() if " chart " in line and " ... " in line]
                self.assertEqual(charts, [
                    f"▶ {position}/{len(rows)} chart {row['name']} ... {row['verdict']}"
                    for position, row in enumerate(rows, 1)
                ])
                self.assertGreaterEqual(flushes, 2 * len(rows))

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
            self.assertEqual(self.verify_cli(verbose=True)[0], 1)

    def test_terminal_automatically_enables_progress(self):
        code, _, stderr, _ = self.verify_cli(tty=True)
        self.assertEqual(code, 1)
        self.assertEqual(stderr.splitlines()[0], "▶ Resolving workload clusters for test-env")

    def test_stage_summary_events_count_files_and_time_the_complete_chart_loop(self):
        report = self.verify(self.events.append)
        reads = [event for event in self.events if event["event"] == "chart"]
        inventory_ends = [event for event in self.events if event["event"] == "inventory_end"]
        charts_ends = [event for event in self.events if event["event"] == "charts_end"]
        total = len(report["sections"]["Charts"])
        self.assertEqual(inventory_ends, [{"event": "inventory_end", "files": len(reads), "elapsed": 0.1}])
        self.assertEqual(len(charts_ends), 1)
        self.assertEqual(charts_ends[0]["total"], total)
        self.assertAlmostEqual(charts_ends[0]["elapsed"], (2 * total + 1) / 10)
        self.assertEqual(self.events.index(inventory_ends[0]), self.events.index(reads[-1]) + 1)
        self.assertEqual(self.events[self.events.index(charts_ends[0]) - 1]["event"], "chart_end")
        self.assertEqual(self.events[self.events.index(charts_ends[0]) + 1], {"event": "section", "section": "Nodes"})

    def test_forced_progress_has_only_stage_summaries_not_file_or_chart_lines(self):
        _, _, stderr, _ = self.verify_cli(force=True)
        lines = stderr.splitlines()
        self.assertFalse(any("— read" in line for line in lines))
        self.assertFalse(any(re.match(r"^\S \d+/\d+ chart ", line) for line in lines))
        self.assertEqual(sum("Chart declarations read:" in line for line in lines), 1)
        self.assertEqual(sum("charts checked in" in line for line in lines), 1)
        self.assertNotIn("\r", stderr)

    def test_verbose_prints_each_file_and_chart_without_per_chart_timings(self):
        report = self.verify(self.events.append)
        reads = [event for event in self.events if event["event"] == "chart"]
        code, _, stderr, _ = self.verify_cli(verbose=True)
        self.assertEqual(code, 1)
        lines = stderr.splitlines()
        self.assertEqual([line for line in lines if "— read" in line], [
            f"▶ {event['stage']} — {event['action']} ({event['repository']}/{event['path']})" for event in reads
        ])
        self.assertEqual(sum(bool(re.match(r"^\S \d+/\d+ chart ", line)) for line in lines),
            len(report["sections"]["Charts"]))
        self.assertFalse(any(line.endswith("in 0.0s") for line in lines))
        self.assertIn(f"▶ Chart declarations read: {len(reads)} files in 0.1s", lines)

    def test_terminal_file_liveness_rewrites_one_line_and_is_flushed_before_reads(self):
        original = LocalRepositories.get_file
        updates = []

        def read(client, repository, path, ref="main"):
            output = sys.stderr.getvalue()
            if "\r▶ Reading chart declarations ... " in output and "Chart declarations read:" not in output:
                current = output.rsplit("\r", 1)[-1]
                self.assertRegex(current, r"^▶ Reading chart declarations \.\.\. \d+ files$")
                updates.append(current)
            return original(client, repository, path, ref)

        with patch.object(LocalRepositories, "get_file", new=read):
            _, terminal_stdout, stderr, _ = self.verify_cli(tty=True)
        self.assertTrue(updates)
        self.assertEqual(updates, [f"▶ Reading chart declarations ... {index} files"
            for index in range(1, len(updates) + 1)])
        summary = next(line for line in stderr.splitlines() if "Chart declarations read:" in line)
        self.assertIn(f"{len(updates)} files", summary)
        inventory_output = stderr.split("▶ Reading chart declarations\n", 1)[1].split(summary, 1)[0]
        self.assertNotIn("\n", inventory_output)
        self.assertNotIn("— read", stderr)
        self.assertEqual(terminal_stdout.encode(), self.verify_cli()[1].encode())

    def test_stage_summaries_format_elapsed_seconds(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            reporter = LiveProgressReporter(force=True)
            reporter({"event": "inventory_end", "files": 251, "elapsed": 3.2})
            reporter({"event": "charts_end", "total": 27, "elapsed": 0.1})
        self.assertEqual(stderr.getvalue(),
            "▶ Chart declarations read: 251 files in 3.2s\n▶ 27 charts checked in 0.1s\n")

    def test_terminal_file_counter_is_cleared_before_verification_errors(self):
        def fail(*args, progress, **kwargs):
            progress("oac-apps charts", "read unavailable.yaml", "CCI-MOC/oac-apps", "unavailable.yaml")
            raise ChartInventoryError("synthetic declaration failure")

        with patch("moc_env.verify_live.collect_chart_inventory", side_effect=fail):
            code, stdout, stderr, _ = self.verify_cli(tty=True)
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("\r▶ Reading chart declarations ... 1 files", stderr)
        self.assertEqual(stderr.rsplit("\r", 1)[-1], "moc-env: synthetic declaration failure\n")

    def test_terminal_file_counter_is_cleared_before_capture_errors(self):
        def fail(*args, progress, **kwargs):
            progress({"event": "chart", "stage": "oac-apps charts", "action": "read unavailable.yaml",
                "repository": "CCI-MOC/oac-apps", "path": "unavailable.yaml"})
            raise ChartInventoryError("synthetic declaration failure")

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
            patch.object(stderr, "isatty", return_value=True),
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("moc_env.live_cli.capture_live", side_effect=fail),
        ):
            code = cli.main([
                "capture-live", "test-env", "--workload", "workload0", "--out", str(self.directory / "snapshot"),
                "--repository-root", str(REPOS),
            ])
        self.assertEqual((code, stdout.getvalue()), (2, ""))
        self.assertIn("\r▶ Reading chart declarations ... 1 files", stderr.getvalue())
        self.assertEqual(stderr.getvalue().rsplit("\r", 1)[-1], "moc-env: synthetic declaration failure\n")

    def test_verbose_preserves_output_file_bytes_in_all_formats(self):
        for format in ("text", "json", "markdown"):
            with self.subTest(format=format):
                plain = self.directory / f"plain.{format}"
                verbose = self.directory / f"verbose.{format}"
                code, stdout, _, _ = self.verify_cli(format, output=plain)
                verbose_code, verbose_stdout, _, _ = self.verify_cli(format, output=verbose, verbose=True)
                self.assertEqual((code, verbose_code, stdout, verbose_stdout), (1, 1, "", ""))
                self.assertEqual(plain.read_bytes(), verbose.read_bytes())

    def test_capture_verbose_implies_progress_and_preserves_oc_lines(self):
        def capture(*args, progress, **kwargs):
            progress({"event": "declarations", "message": "Reading chart declarations"})
            progress({"event": "chart", "stage": "oac-apps charts", "action": "read charts/rhoai/values.yaml",
                "repository": "CCI-MOC/oac-apps", "path": "charts/rhoai/values.yaml"})
            progress({"event": "oc_start", "position": 1, "total": 1,
                "resource": "pods", "all_namespaces": True})
            progress({"event": "oc_end", "outcome": "captured", "count": 2, "elapsed": 0.2})
            return {"resources": {"pods": {}}, "forbidden": []}

        results = []
        for flag in ("--progress", "--verbose"):
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
                patch.object(stderr, "isatty", return_value=False),
                patch("shutil.which", return_value="/synthetic/oc"),
                patch("moc_env.live_cli.capture_live", side_effect=capture),
                patch("moc_env.live_cli.monotonic", return_value=0),
            ):
                code = cli.main([
                    "capture-live", "test-env", "--workload", "workload0", "--out", str(self.directory / "snapshot"),
                    "--repository-root", str(REPOS), flag,
                ])
            self.assertEqual(code, 0)
            results.append((stdout.getvalue(), stderr.getvalue()))
        self.assertEqual(results[0][0], results[1][0])
        for _, stderr in results:
            self.assertIn("▶ 1/1 pods (all namespaces) ... captured 2 objects in 0.2s", stderr.splitlines())
        self.assertNotIn("— read", results[0][1])
        self.assertIn("— read charts/rhoai/values.yaml", results[1][1])

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
