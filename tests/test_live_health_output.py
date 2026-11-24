"""Synthetic coverage for node health output and undeclared AI components."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from moc_env.capture_live import reduce_object
from moc_env.verify_live import LocalRepositories, render_live_report, verify_live


FIXTURES = Path(__file__).parent / "fixtures/live"


class LiveHealthOutputTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.snapshot = Path(temporary.name) / "snapshot"
        shutil.copytree(FIXTURES / "workload0", self.snapshot)
        self.client = LocalRepositories(FIXTURES / "repos")

    def report(self):
        return verify_live(self.client, "test-env", "test-env-workload0", self.snapshot)

    def pod(self, name, node, ready, restarts, **status):
        return {
            "metadata": {"namespace": "fixture", "name": name},
            "spec": {"nodeName": node},
            "status": {
                "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                "containerStatuses": [{"restartCount": restarts}],
                **status,
            },
        }

    def set_pods(self, *pods):
        (self.snapshot / "pods.json").write_text(json.dumps({"items": pods}))

    def health(self, report, node):
        return next(row for row in report["sections"]["Health"] if row["name"] == node)

    def test_ready_restarting_pod_is_a_match_with_note_in_every_format(self):
        self.set_pods(self.pod("proxy-a02", "node-a02", True, 60))
        report = self.report()
        row = self.health(report, "node-a02")
        self.assertEqual(row["verdict"], "match")
        self.assertEqual(row["detail"], "note: 1 Ready pod over 50 restarts")
        text = render_live_report(report).splitlines()
        self.assertIn("  match           node-a02 | note: 1 Ready pod over 50 restarts", text)
        self.assertIn("                    fixture/proxy-a02  Ready · containers 0/1 · 60 restarts", text)
        document = json.loads(render_live_report(report, "json"))
        self.assertEqual(self.health(document, "node-a02")["pods"], [{
            "namespace": "fixture", "name": "proxy-a02", "ready": True, "restarts": 60,
            "phase": None, "containers": "0/1", "reason": None, "age_seconds": None,
        }])
        markdown = render_live_report(report, "markdown")
        self.assertIn(
            "| `node-a02` | `match` | `note: 1 Ready pod over 50 restarts`"
            "<br>`fixture/proxy-a02  Ready · containers 0/1 · 60 restarts` |", markdown,
        )

    def test_mixed_node_lists_each_pod_once_with_not_ready_first(self):
        self.set_pods(
            self.pod("proxy-a07", "node-a07", True, 60),
            self.pod("importer-1", "node-a07", False, 0),
        )
        report = self.report()
        row = self.health(report, "node-a07")
        self.assertEqual((row["verdict"], row["detail"]), ("drift", "1 pod not Ready"))
        self.assertEqual([pod["name"] for pod in row["pods"]], ["importer-1", "proxy-a07"])
        for format in ("text", "markdown"):
            output = render_live_report(report, format)
            self.assertEqual(output.count("fixture/importer-1"), 1)
            self.assertEqual(output.count("fixture/proxy-a07"), 1)
            self.assertLess(output.index("fixture/importer-1"), output.index("fixture/proxy-a07"))
            self.assertIn("not Ready · containers 0/1 · 0 restarts", output)
            self.assertIn("Ready · containers 0/1 · 60 restarts", output)
        markdown_row = next(line for line in render_live_report(report, "markdown").splitlines()
            if line.startswith("| `node-a07`"))
        self.assertEqual(markdown_row.count("<br>"), 2)

    def test_not_ready_then_restarts_descending_and_exact_text_layout(self):
        self.set_pods(
            self.pod("proxy-a07", "node-a07", True, 60),
            self.pod("importer-1", "node-a07", False, 0),
            self.pod("storage-agent", "node-a07", False, 19019),
        )
        report = self.report()
        text = render_live_report(report)
        self.assertIn(
            "  drift           node-a07 | 2 pods not Ready\n"
            "                    fixture/storage-agent  not Ready · containers 0/1 · 19019 restarts\n"
            "                    fixture/importer-1     not Ready · containers 0/1 · 0 restarts\n"
            "                    fixture/proxy-a07      Ready · containers 0/1 · 60 restarts\n", text,
        )
        self.assertIn("  match           node-a03\n", text)
        self.assertEqual(self.health(report, "node-a03")["pods"], [])

    def test_pending_init_pod_reports_snapshot_age_in_every_format(self):
        pod = self.pod("pod-a", "node-a07", False, 0, phase="Pending",
            initContainerStatuses=[{"ready": False}],
            containerStatuses=[{"ready": False}, {"ready": False}])
        pod["metadata"]["creationTimestamp"] = "2026-11-19T08:00:00Z"
        path = self.snapshot / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["timestamp"] = "2026-11-24T12:00:00+00:00"
        path.write_text(json.dumps(manifest))
        self.set_pods(pod)
        report = self.report()
        expected = "not Ready · Pending · init 0/1 · containers 0/2 · 5d4h · 0 restarts"
        line = next(line for line in render_live_report(report).splitlines() if "fixture/pod-a" in line)
        self.assertEqual(line, f"                    fixture/pod-a  {expected}")
        self.assertIn(f"`fixture/pod-a  {expected}`", render_live_report(report, "markdown"))
        document = json.loads(render_live_report(report, "json"))
        self.assertEqual(self.health(document, "node-a07")["pods"], [{
            "namespace": "fixture", "name": "pod-a", "ready": False, "restarts": 0,
            "phase": "Pending", "init": "0/1", "containers": "0/2", "reason": None,
            "age_seconds": (5 * 24 + 4) * 3600,
        }])

    def test_crash_loop_reason_is_rendered_and_init_reason_has_priority(self):
        for init, expected in (([], "CrashLoopBackOff"),
                ([{"ready": False, "state": {"terminated": {"reason": "InitFailure"}}}], "InitFailure")):
            with self.subTest(init=init):
                self.set_pods(self.pod("crashing", "node-a07", False, 60,
                    containerStatuses=[{"ready": False, "restartCount": 60,
                        "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                    initContainerStatuses=init))
                report = self.report()
                health_pod = self.health(report, "node-a07")["pods"][0]
                self.assertEqual(health_pod["reason"], expected)
                for format in ("text", "markdown"):
                    line = next(line for line in render_live_report(report, format).splitlines()
                        if "fixture/crashing" in line)
                    self.assertIn(f" · {expected} · 60 restarts", line)

    def test_old_shape_pod_has_no_age_or_reason(self):
        self.set_pods(self.pod("old-pod", "node-a07", False, 0))
        report = self.report()
        pod = self.health(report, "node-a07")["pods"][0]
        self.assertIsNone(pod["age_seconds"])
        self.assertIsNone(pod["reason"])
        self.assertNotIn("init", pod)
        line = next(line for line in render_live_report(report).splitlines() if "fixture/old-pod" in line)
        self.assertEqual(line, "                    fixture/old-pod  not Ready · containers 0/1 · 0 restarts")

    def test_age_formats_and_unavailable_details(self):
        path = self.snapshot / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["timestamp"] = "2026-11-24T12:00:00Z"
        path.write_text(json.dumps(manifest))
        for created, age, displayed in (
            ("2026-11-23T12:00:00Z", 86400, "1d0h"),
            ("2026-11-24T10:56:00Z", 3840, "1h4m"),
            ("2026-11-24T11:00:00Z", 3600, "1h0m"),
            ("2026-11-24T11:56:00Z", 240, "4m"),
            ("2026-11-24T11:59:59Z", 1, "0m"),
            ("invalid", None, None),
            ("2026-11-24T12:00:00", None, None),
        ):
            with self.subTest(created=created):
                pod = self.pod("aged", "node-a07", False, 0)
                pod["metadata"]["creationTimestamp"] = created
                del pod["status"]["containerStatuses"]
                self.set_pods(pod)
                report = self.report()
                self.assertEqual(self.health(report, "node-a07")["pods"][0]["age_seconds"], age)
                line = next(line for line in render_live_report(report).splitlines() if "fixture/aged" in line)
                expected = f"not Ready · {displayed} · 0 restarts" if displayed else "not Ready · 0 restarts"
                self.assertEqual(line, f"                    fixture/aged  {expected}")

    def test_capture_keeps_only_pod_creation_time_and_state_reasons(self):
        pod = self.pod("reduced", "node-a07", False, 0)
        pod["kind"] = "Pod"
        pod["metadata"]["creationTimestamp"] = "2026-11-19T08:00:00Z"
        pod["spec"]["containers"] = [{"image": "private-image", "env": [{"name": "PRIVATE", "value": "secret"}]}]
        for field in ("containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses"):
            pod["status"][field] = [{
                "name": "worker", "ready": False, "restartCount": 60, "image": "private-image",
                "env": [{"name": "PRIVATE", "value": "secret"}],
                "state": {
                    "waiting": {"reason": "CrashLoopBackOff", "message": "private-message"},
                    "terminated": {"reason": "Error", "message": "private-message", "exitCode": 1},
                    "running": {"startedAt": "2026-11-19T08:00:00Z"},
                },
            }]
        reduced = reduce_object(pod)
        self.assertEqual(reduced["metadata"]["creationTimestamp"], pod["metadata"]["creationTimestamp"])
        self.assertEqual(reduced["spec"], {"nodeName": "node-a07"})
        for field in ("containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses"):
            self.assertEqual(reduced["status"][field], [{
                "name": "worker", "ready": False, "restartCount": 60,
                "state": {"waiting": {"reason": "CrashLoopBackOff"}, "terminated": {"reason": "Error"}},
            }])
        for forbidden in ("env", "image", "message"):
            self.assertNotIn(forbidden, json.dumps(reduced))

    def test_summary_counts_one_unhealthy_node_and_three_note_only_nodes(self):
        baseline = self.report()
        self.set_pods(
            self.pod("storage-agent", "node-a07", False, 19019),
            *(self.pod(f"proxy-a0{number}", f"node-a0{number}", True, 60)
                for number in (2, 3, 4)),
        )
        report = self.report()
        health = report["sections"]["Health"]
        self.assertEqual(len(health), 9)
        self.assertEqual(sum(row["verdict"] == "drift" for row in health), 1)
        self.assertEqual(sum(row["detail"].startswith("note:") for row in health), 3)
        self.assertEqual(report["summary"]["drift"], baseline["summary"]["drift"] + 1)
        self.assertEqual(report["summary"]["match"], baseline["summary"]["match"] - 1)

    def test_restart_threshold_plural_notes_and_all_container_types(self):
        self.set_pods(
            self.pod("proxy-a02", "node-a02", True, 50),
            self.pod("proxy-a03", "node-a03", True, 20,
                initContainerStatuses=[{"restartCount": 20}],
                ephemeralContainerStatuses=[{"restartCount": 11}]),
            self.pod("proxy-extra", "node-a03", True, 100),
        )
        report = self.report()
        self.assertEqual(self.health(report, "node-a02")["pods"], [])
        row = self.health(report, "node-a03")
        self.assertEqual(row["verdict"], "match")
        self.assertEqual(row["detail"], "note: 2 Ready pods over 50 restarts")
        self.assertEqual([pod["restarts"] for pod in row["pods"]], [100, 51])

    def test_succeeded_pods_ignored_and_unscheduled_pod_reported(self):
        self.set_pods(
            self.pod("completed", "node-a07", False, 19019, phase="Succeeded"),
            self.pod("pending", "", False, 0, phase="Pending"),
        )
        report = self.report()
        self.assertEqual(self.health(report, "node-a07")["pods"], [])
        self.assertEqual(self.health(report, "unscheduled")["verdict"], "drift")
        self.assertNotIn("fixture/completed", render_live_report(report))

    def test_unreadable_and_empty_snapshots_still_have_pods_lists(self):
        path = self.snapshot / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["resources"]["pods"]["status"] = "Forbidden"
        path.write_text(json.dumps(manifest))
        row = self.health(self.report(), "pods")
        self.assertEqual((row["verdict"], row["pods"]), ("unverifiable", []))
        self.assertIn("pods: Forbidden", render_live_report(self.report()))
        manifest["resources"]["pods"]["status"] = "captured"
        path.write_text(json.dumps(manifest))
        self.set_pods()
        (self.snapshot / "nodes.json").write_text(json.dumps({"items": []}))
        row = self.health(self.report(), "pods")
        self.assertEqual((row["verdict"], row["pods"]), ("match", []))

    def test_undeclared_components_need_a_live_management_state(self):
        path = self.snapshot / "datascienceclusters.datasciencecluster.opendatahub.io.json"
        data = json.loads(path.read_text())
        data["items"][0]["spec"]["components"].update({
            "synthetic-empty": {},
            "synthetic-config-only": {"configuration": {}},
            "synthetic-null": {"managementState": None},
            "synthetic-managed": {"managementState": "Managed"},
        })
        path.write_text(json.dumps(data))
        rows = {row["name"]: row for row in self.report()["sections"]["OpenShift AI"]}
        for name in ("synthetic-empty", "synthetic-config-only", "synthetic-null"):
            self.assertNotIn(f"component/{name}", rows)
        row = rows["component/synthetic-managed"]
        self.assertEqual((row["verdict"], row["declared"], row["live"]), ("drift", None, "Managed"))


if __name__ == "__main__":
    unittest.main()
