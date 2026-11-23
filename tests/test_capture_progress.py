"""Synthetic capture progress checks; existing tests and fakes stay untouched."""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.capture_live import CaptureError, capture_live
from moc_env.verify_live import LocalRepositories


REPOS = Path(__file__).parent / "fixtures/live/repos"
WORKLOAD = "test-env-workload0"
INFRASTRUCTURE = "infrastructures.config.openshift.io"
CRDS = "customresourcedefinitions.apiextensions.k8s.io"
WIDGETS = "widgets.fixture.example"


class CaptureProgressTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "snapshot"
        self.client = LocalRepositories(REPOS)
        self.events = []
        self.calls = []
        self.seconds = 0.0
        self.failures = {"dnses.operator.openshift.io": "Forbidden", WIDGETS: "timeout"}
        self.on_get = None
        self.api_url = f"https://api-internal-{WORKLOAD}.internal.synthetic.invalid:6443"

    def oc(self, command, **kwargs):
        self.calls.append(command)
        if self.on_get is not None:
            self.on_get(command)
        key = command[2]
        failure = self.failures.get(key)
        if failure == "timeout":
            self.seconds += 45.0
            raise subprocess.TimeoutExpired(command, 45)
        if failure:
            self.seconds += 0.3
            if failure == "invalid JSON":
                return subprocess.CompletedProcess(command, 0, "{", "")
            return subprocess.CompletedProcess(command, 1, "", failure)
        self.seconds += 0.2
        if key == "users.user.openshift.io":
            data = {"metadata": {"name": "synthetic-reader"}}
        elif key == INFRASTRUCTURE:
            data = {"items": [{
                "apiVersion": "config.openshift.io/v1", "kind": "Infrastructure",
                "metadata": {"name": "cluster"}, "status": {"apiServerURL": self.api_url},
            }]}
        elif key == CRDS:
            data = {"items": [{
                "apiVersion": "apiextensions.k8s.io/v1", "kind": "CustomResourceDefinition",
                "metadata": {"name": WIDGETS},
                "spec": {"group": "fixture.example", "scope": "Namespaced",
                        "names": {"plural": "widgets", "kind": "Widget"}},
            }]}
        elif key == "pods":
            data = {"items": [
                {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "synthetic"}}
                for name in ("synthetic-pod-a", "synthetic-pod-b")
            ]}
        else:
            data = {"items": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    @contextlib.contextmanager
    def boundary(self):
        with (
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=self.oc),
            patch("moc_env.capture_live.monotonic", side_effect=lambda: self.seconds),
            patch("moc_env.live_cli.monotonic", side_effect=lambda: self.seconds),
        ):
            yield

    def capture(self, progress=None):
        with self.boundary():
            return capture_live("test-env", WORKLOAD, self.output, client=self.client, progress=progress)

    def capture_cli(self, force=False, tty=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ["capture-live", "test-env", "--workload", "workload0",
                    "--out", str(self.output), "--repository-root", str(REPOS)]
        if force:
            arguments.append("--progress")
        with (
            self.boundary(), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
            patch.object(stderr, "isatty", return_value=tty),
            patch.object(stderr, "flush", wraps=stderr.flush) as flush,
        ):
            code = cli.main(arguments)
            flushes = flush.call_count
        return code, stdout.getvalue(), stderr.getvalue(), flushes

    def test_callback_order_positions_totals_and_chart_reads(self):
        def on_get(command):
            self.assertEqual(self.events[-1]["event"], "oc_start")
            self.assertEqual(self.events[-1]["resource"], command[2])

        self.on_get = on_get
        manifest = self.capture(self.events.append)
        self.assertEqual(self.events[0], {"event": "declarations", "message": "Reading chart declarations"})
        self.assertEqual(self.events[-1], {"event": "identity", "verified": True, "reason": None})
        starts = [event for event in self.events if event["event"] == "oc_start"]
        ends = [event for event in self.events if event["event"] == "oc_end"]
        self.assertEqual(len(starts), len(self.calls))
        self.assertEqual(len(ends), len(starts))
        self.assertEqual([event["resource"] for event in starts[:3]],
                        ["users.user.openshift.io", INFRASTRUCTURE, CRDS])
        self.assertEqual(len(starts), len(manifest["resources"]) + 1)
        for index, (start, end, command) in enumerate(zip(starts, ends, self.calls), 1):
            with self.subTest(resource=command[2]):
                self.assertEqual(start["position"], index)
                self.assertEqual(start["resource"], command[2])
                self.assertEqual(start["total"], None if index <= 3 else len(starts))
                for key, value in start.items():
                    if key != "event":
                        self.assertEqual(end[key], value)
                self.assertLess(self.events.index(start), self.events.index(end))
        charts = [event for event in self.events if event["event"] == "chart"]
        self.assertTrue(charts)
        self.assertTrue(all(event["repository"] == "CCI-MOC/oac-apps" for event in charts))
        self.assertTrue(any("applicationsets/" in event["path"] for event in charts))

    def test_forbidden_timeout_and_object_counts(self):
        self.capture(self.events.append)
        ends = {event["resource"]: event for event in self.events if event["event"] == "oc_end"}
        self.assertEqual(ends["dnses.operator.openshift.io"]["outcome"], "Forbidden")
        self.assertEqual(ends[WIDGETS]["outcome"], "timed out")
        self.assertAlmostEqual(ends[WIDGETS]["elapsed"], 45.0)
        self.assertEqual((ends["pods"]["outcome"], ends["pods"]["count"]), ("captured", 2))
        self.assertEqual(ends["users.user.openshift.io"]["count"], 1)

    def test_not_served_and_failed_outcomes(self):
        self.failures.update({"nodes": "NotFound", "resourcequotas": "synthetic server error",
                            "namespaces": "invalid JSON"})
        self.capture(self.events.append)
        ends = {event["resource"]: event for event in self.events if event["event"] == "oc_end"}
        self.assertEqual(ends["nodes"]["outcome"], "not-served")
        self.assertEqual(ends["resourcequotas"]["outcome"], "failed")
        self.assertEqual(ends["namespaces"]["outcome"], "failed")

    def test_non_terminal_success_is_silent_without_progress_flag(self):
        code, stdout, stderr, _ = self.capture_cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(
            stdout,
            f"Snapshot: {self.output.resolve()} · 20 kinds · 1 forbidden · 49s\n"
            f"Next: moc-env verify-live test-env --workload test-env-workload0 --snapshot {self.output.resolve()}\n",
        )

    def test_forced_progress_completes_one_line_per_oc_step_and_only_summary_on_stdout(self):
        def on_get(command):
            # This executes while subprocess.run is in progress, before it returns.
            import sys
            self.assertTrue(sys.stderr.getvalue().endswith(" ... "))
            self.assertIn(command[2], sys.stderr.getvalue().splitlines()[-1])

        self.on_get = on_get
        code, stdout, stderr, flushes = self.capture_cli(force=True)
        self.assertEqual(code, 0)
        lines = stderr.splitlines()
        steps = [line for line in lines if re.match(r"▶ \d+/", line)]
        self.assertEqual(len(steps), len(self.calls))
        self.assertGreaterEqual(flushes, 2 * len(self.calls))
        self.assertTrue(any("pods (all namespaces) ... captured 2 objects in 0.2s" in line for line in steps))
        self.assertTrue(any("dnses.operator.openshift.io ... Forbidden in 0.3s" in line for line in steps))
        self.assertTrue(any(f"{WIDGETS} (all namespaces) ... timed out after 45.0s" in line for line in steps))
        self.assertEqual(lines[-1], "▶ Cluster identity: verified")
        self.assertEqual(
            stdout,
            f"Snapshot: {self.output.resolve()} · 20 kinds · 1 forbidden · 49s\n"
            f"Next: moc-env verify-live test-env --workload test-env-workload0 --snapshot {self.output.resolve()}\n",
        )

    def test_terminal_automatically_enables_progress(self):
        code, _, stderr, _ = self.capture_cli(tty=True)
        self.assertEqual(code, 0)
        self.assertIn("▶ 1/? users.user.openshift.io ... captured 1 object in 0.2s", stderr)

    def test_identity_unverified_reason_is_reported_last(self):
        self.failures[INFRASTRUCTURE] = "Forbidden"
        manifest = self.capture(self.events.append)
        self.assertFalse(manifest["identity_verified"])
        self.assertEqual(self.events[-1], {"event": "identity", "verified": False, "reason": "Forbidden"})

    def test_wrong_cluster_reports_identity_failure_and_writes_nothing(self):
        self.api_url = "https://api.other.invalid:6443"
        with self.assertRaises(CaptureError):
            self.capture(self.events.append)
        self.assertEqual(self.events[-1]["event"], "identity")
        self.assertFalse(self.events[-1]["verified"])
        self.assertIn("api.other.invalid", self.events[-1]["reason"])
        self.assertFalse(self.output.exists())

    def test_progress_does_not_print_from_capture_or_change_snapshot_bytes(self):
        first = self.output
        with patch("builtins.print", side_effect=AssertionError("capture must not print")):
            self.capture()
            self.output = first.parent / "with-progress"
            self.capture(self.events.append)
        self.assertTrue(self.events)
        self.assertEqual({path.name for path in first.iterdir()},
                        {path.name for path in self.output.iterdir()})
        for path in first.iterdir():
            expected = path.read_bytes()
            actual = (self.output / path.name).read_bytes()
            if path.name == "manifest.json":
                expected = expected.replace(json.loads(expected)["timestamp"].encode(), b"<timestamp>")
                actual = actual.replace(json.loads(actual)["timestamp"].encode(), b"<timestamp>")
            self.assertEqual(actual, expected, path.name)


if __name__ == "__main__":
    unittest.main()
