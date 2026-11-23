"""Offline live-workflow acceptance tests; never use shared test fakes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.capture_live import (LOGIN_MESSAGE, CaptureError, REQUIRED,
                                  capture_live, native_resources)
from moc_env.verify_live import (LocalRepositories, Snapshot, _quantity, render_live_report,
                                 verify_live)

FIXTURES = Path(__file__).parent / "fixtures/live"
REPOS = FIXTURES / "repos"
WORKLOAD0 = FIXTURES / "workload0"


class VerifyLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = LocalRepositories(REPOS)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.snapshot = Path(temporary.name) / "snapshot"
        shutil.copytree(WORKLOAD0, self.snapshot)

    def report(self, workload="workload0", snapshot=None):
        # No subprocess (including oc/gh/git) or HTTP is needed with local repos.
        with (patch("subprocess.run", side_effect=AssertionError("subprocess forbidden")),
              patch("urllib.request.urlopen", side_effect=AssertionError("HTTP forbidden"))):
            return verify_live(self.client, "test-env", "test-env-" + workload, snapshot or self.snapshot)

    def row(self, section, name, report=None):
        return next(row for row in (report or self.report())["sections"][section] if row["name"] == name)

    def change_manifest(self, transform):
        path = self.snapshot / "manifest.json"
        data = json.loads(path.read_text())
        transform(data)
        path.write_text(json.dumps(data))

    def change_resource(self, key, transform):
        path = self.snapshot / f"{key}.json"
        data = json.loads(path.read_text())
        transform(data)
        path.write_text(json.dumps(data))

    def test_ten_declared_nine_live_with_case_insensitive_names(self):
        report = self.report()
        total = self.row("Nodes", "inventory total", report)
        self.assertEqual((total["declared"], total["live"], total["verdict"]), (10, 9, "drift"))
        missing = self.row("Nodes", "NODE-A10 (test-env-workload0-gpu-6)", report)
        self.assertEqual((missing["verdict"], missing["live"]), ("drift", "missing"))
        matched = self.row("Nodes", "NODE-A09 (test-env-workload0-gpu-5)", report)
        self.assertEqual((matched["verdict"], matched["live"]), ("match", "node-a09"))
        self.assertEqual(len(report["sections"]["Nodes"]), 11)

    def test_disabled_charts_cite_exact_default_line(self):
        for chart, line in (("jobset-operator", 8), ("kueue-operator", 7)):
            row = self.row("Charts", chart)
            self.assertEqual(row["verdict"], "expected-absent")
            self.assertEqual(row["detail"], f"charts/{chart}/values.yaml:{line} enabled: false")

    def test_workload1_enables_jobset_and_missing_is_drift(self):
        report = self.report("workload1", FIXTURES / "workload1")
        row = self.row("Charts", "jobset-operator", report)
        self.assertEqual((row["declared"], row["verdict"]), ("enabled", "drift"))
        source = REPOS / "oac-apps/values/test-env-infra/test-env-workload1/jobset-operator.yaml"
        self.assertIn("enabled: true", source.read_text())
        self.assertNotIn("WARNING:", render_live_report(report))

    def test_wrong_workload_exits_two_with_exact_one_line_error(self):
        self.change_manifest(lambda data: data.update(workload="test-env-workload1"))
        code, stdout, stderr = self.run_cli()
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(stderr, "moc-env: snapshot workload test-env-workload1 does not match requested workload test-env-workload0\n")

    def test_tenant_a_quota_matches_all_resolved_defaults(self):
        row = self.row("Quotas", "tenant-a")
        self.assertEqual(row["verdict"], "match")
        self.assertEqual(row["declared"]["requests.nvidia.com/gpu"], "20")
        self.assertEqual(row["declared"]["persistentvolumeclaims"], "20")

    def test_tenant_a_gpu_drift_names_both_numbers(self):
        shutil.copyfile(FIXTURES / "quota16/resourcequotas.json", self.snapshot / "resourcequotas.json")
        row = self.row("Quotas", "tenant-a")
        self.assertEqual(row["verdict"], "drift")
        self.assertIn("requests.nvidia.com/gpu: declared 20, live 16", row["detail"])

    def test_equivalent_kubernetes_quantities_match(self):
        self.change_resource("resourcequotas", lambda data: data["items"][0]["spec"]["hard"].update({
            "requests.cpu": "320000m", "requests.memory": "2048Gi"}))
        self.assertEqual(self.row("Quotas", "tenant-a")["verdict"], "match")
        for left, right in (("1Ti", "1024Gi"), ("1k", "1000"), ("1e3", "1000")):
            self.assertEqual(_quantity(left), _quantity(right))
        self.assertEqual(_quantity("invalid"), "invalid")

    def test_forbidden_dns_is_unverifiable(self):
        row = self.row("Charts", "dns-operator-config")
        self.assertEqual(row["verdict"], "unverifiable")
        self.assertIn("dnses.operator.openshift.io: Forbidden", row["detail"])

    def test_pod_4356_restarts_is_grouped_under_node(self):
        row = self.row("Health", "node-a07")
        self.assertEqual(row["verdict"], "match")
        self.assertIn("fixture/restarting-pod Ready=true restarts=4356", row["live"])

    def test_not_ready_pod_and_init_restarts_are_checked(self):
        def unhealthy(data):
            data["items"][0]["status"]["conditions"][0]["status"] = "False"
            data["items"][0]["status"]["initContainerStatuses"] = [{"restartCount": 51}]
        self.change_resource("pods", unhealthy)
        row = self.row("Health", "node-a09")
        self.assertEqual(row["verdict"], "drift")
        self.assertIn("Ready=false restarts=51", str(row["live"]))

    def test_rhoai_components_and_full_hardware_specs_match(self):
        rows = self.report()["sections"]["OpenShift AI"]
        self.assertEqual(len(rows), 13)
        self.assertEqual({row["verdict"] for row in rows}, {"match"})
        self.change_resource("datascienceclusters.datasciencecluster.opendatahub.io",
            lambda data: data["items"][0]["spec"]["components"]["dashboard"].update(managementState="Removed"))
        self.assertEqual(self.row("OpenShift AI", "component/dashboard")["verdict"], "drift")
        self.change_resource("hardwareprofiles.infrastructure.opendatahub.io",
            lambda data: data["items"][0]["spec"]["identifiers"][0].update(maxCount="100"))
        self.assertEqual(self.row("OpenShift AI", "hardwareprofile/gpu-profile-a")["verdict"], "drift")

    def test_removed_component_absent_cites_source_line(self):
        self.change_resource("datascienceclusters.datasciencecluster.opendatahub.io",
            lambda data: data["items"][0]["spec"]["components"].pop("modelregistry"))
        row = self.row("OpenShift AI", "component/modelregistry")
        self.assertEqual(row["verdict"], "expected-absent")
        self.assertRegex(row["detail"], r"charts/rhoai/values.yaml:\d+ .*Removed")

    def test_missing_forbidden_and_invalid_files_never_match(self):
        for key, section in (("nodes", "Nodes"), ("pods", "Health"), ("resourcequotas", "Quotas"),
            ("datascienceclusters.datasciencecluster.opendatahub.io", "OpenShift AI")):
            with self.subTest(key=key):
                self.change_manifest(lambda data: data["resources"][key].update(status="Forbidden"))
                rows = self.report()["sections"][section]
                relevant = [row for row in rows if key != "datascienceclusters.datasciencecluster.opendatahub.io" or row["name"].startswith("component/")]
                self.assertEqual({row["verdict"] for row in relevant}, {"unverifiable"})
                self.change_manifest(lambda data: data["resources"][key].update(status="captured"))
        (self.snapshot / "nodes.json").write_text("not json")
        self.assertEqual(self.row("Nodes", "inventory total")["verdict"], "unverifiable")
        self.change_manifest(lambda data: data["resources"].pop("pods"))
        self.assertEqual(self.row("Health", "pods")["verdict"], "unverifiable")

    def test_unread_template_kind_is_not_evidence_of_chart_absence(self):
        shutil.copytree(FIXTURES / "workload1", self.snapshot, dirs_exist_ok=True)
        self.change_manifest(lambda data: data["resources"].pop("operatorgroups.operators.coreos.com"))
        report = self.report("workload1")
        self.assertEqual(self.row("Charts", "jobset-operator", report)["verdict"], "unverifiable")

    def test_real_tracking_format_and_copied_annotations(self):
        snapshot = Snapshot(self.snapshot)
        expected = "BaselineAdminNetworkPolicy:/default"
        self.assertEqual(snapshot.tracked("test-env-workload0-restrict-tenant-networks"), [expected])
        self.assertEqual(snapshot.tracked("test-env-workload0-restrict"), [])
        self.assertTrue(snapshot.tracked("test-env-workload0-user-projects"))
        self.change_resource("baselineadminnetworkpolicies.policy.networking.k8s.io",
            lambda data: data["items"][0]["metadata"].update(name="copied-child"))
        self.assertEqual(Snapshot(self.snapshot).tracked("test-env-workload0-restrict-tenant-networks"), [])

    def test_snapshot_paths_cannot_escape_directory(self):
        self.change_manifest(lambda data: data["resources"]["nodes"].update(file="../outside.json"))
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.report()

    def run_cli(self, *options, workload="workload0", snapshot=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ["verify-live", "test-env", "--workload", workload, "--snapshot", str(snapshot or self.snapshot),
                     "--repository-root", str(REPOS), *options]
        with (contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
              patch.dict(os.environ, {"PATH": ""}),
              patch("subprocess.run", side_effect=AssertionError("no subprocess")),
              patch.object(cli, "_resolve_github_token", side_effect=AssertionError("no credentials"))):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_works_without_oc_credentials_or_network(self):
        code, stdout, stderr = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("  drift           inventory total | count: declared 10, live 9", stdout.splitlines())
        self.assertEqual(stderr, "")

    def test_workload1_cli_reports_missing_enabled_jobset(self):
        code, stdout, stderr = self.run_cli(workload="workload1", snapshot=FIXTURES / "workload1")
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertIn("  drift           jobset-operator | live: missing", stdout.splitlines())

    def test_cli_json_markdown_and_extension_inference(self):
        code, stdout, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 1)
        report = json.loads(stdout)
        self.assertEqual(set(report["summary"]), {"match", "drift", "expected-absent", "unverifiable"})
        for rows in report["sections"].values():
            self.assertTrue(all(row["verdict"] in report["summary"] for row in rows))
        output = self.snapshot.parent / "report.md"
        code, stdout, stderr = self.run_cli("--output", str(output))
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("| Name | Verdict |", output.read_text())
        self.assertEqual(stderr, f"moc-env: wrote markdown verification report to {output}\n")

    def test_succeeded_not_ready_pod_is_ignored(self):
        def completed(data):
            status = data["items"][0]["status"]
            status["phase"] = "Succeeded"
            status["conditions"][0]["status"] = "False"
            status["containerStatuses"][0]["restartCount"] = 4356
        self.change_resource("pods", completed)
        self.assertEqual(self.row("Health", "node-a09")["verdict"], "match")

    def test_three_or_more_chart_matches_include_operator_library_chart(self):
        rows = self.report()["sections"]["Charts"]
        matched = {row["name"] for row in rows if row["verdict"] == "match"}
        self.assertGreaterEqual(len(matched), 3)
        self.assertIn("nvidia-maintenance-operator", matched)
        source = REPOS / "oac-apps/charts/nvidia-maintenance-operator/Chart.yaml"
        self.assertIn("repository: file://../operator-library", source.read_text())

    def test_tracked_enabled_chart_matches_even_with_an_unread_kind(self):
        self.change_manifest(lambda data: data["resources"]["namespaces"].update(status="Forbidden"))
        self.assertEqual(self.row("Charts", "nvidia-maintenance-operator")["verdict"], "match")

    def test_disabled_but_tracked_chart_is_drift(self):
        def tracked(data):
            metadata = data["items"][0]["metadata"]
            metadata["annotations"]["argocd.argoproj.io/tracking-id"] = (
                "test-env-workload0-jobset-operator:operators.coreos.com/Subscription:fixture-operator/maintenance")
        self.change_resource("subscriptions.operators.coreos.com", tracked)
        self.assertEqual(self.row("Charts", "jobset-operator")["verdict"], "drift")

    def test_match_missing_and_quota_drift_text_is_exact_and_compact(self):
        text = render_live_report(self.report())
        self.assertIn("  match           tenant-a", text.splitlines())
        self.assertIn("  drift           NODE-A10 (test-env-workload0-gpu-6) | live: missing", text.splitlines())
        self.assertNotIn("{}", text)
        self.assertNotIn('"identifiers"', text)
        shutil.copyfile(FIXTURES / "quota16/resourcequotas.json", self.snapshot / "resourcequotas.json")
        text = render_live_report(self.report())
        self.assertIn("  drift           tenant-a | requests.nvidia.com/gpu: declared 20, live 16", text.splitlines())

    def test_synthetic_inventory_contains_only_host_identity(self):
        import yaml
        document = yaml.safe_load((REPOS / "oac-infra/infra/inventory/00hosts.yaml").read_text())
        self.assertEqual(set(document["all"]["children"]), {"test-env-workload0", "test-env-workload1"})
        for group in document["all"]["children"].values():
            for details in group["hosts"].values():
                self.assertEqual(set(details), {"node_name"})
                self.assertEqual(details["node_name"], details["node_name"].upper())


class CaptureLiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / "capture"
        self.config_path = self.directory / "never-read-kubeconfig"
        self.environment = patch.dict(os.environ, {"KUBECONFIG": str(self.config_path)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def oc(self, command, **kwargs):
        self.assertEqual(command[:2], ["oc", "get"])
        self.assertEqual(command[command.index("-o") + 1], "json")
        self.assertNotIn("env", kwargs)
        self.assertEqual(os.environ["KUBECONFIG"], str(self.config_path))
        self.assertFalse(self.config_path.exists())
        key = command[2]
        if key == "dnses.operator.openshift.io":
            return subprocess.CompletedProcess(command, 1, "", "Error from server (Forbidden)")
        if key == "users.user.openshift.io":
            data = {"metadata": {"name": "fixture-reader"}}
        elif key == "customresourcedefinitions.apiextensions.k8s.io":
            data = {"items": [
                {"apiVersion":"apiextensions.k8s.io/v1", "kind":"CustomResourceDefinition",
                 "metadata":{"name":"widgets.fixture.example"},
                 "spec": {"group": "fixture.example", "scope": "Namespaced",
                          "names": {"plural": "widgets", "kind": "Widget"}}},
                {"apiVersion":"apiextensions.k8s.io/v1", "kind":"CustomResourceDefinition",
                 "metadata":{"name":"unrelateds.fixture.example"},
                 "spec": {"group": "fixture.example", "scope": "Namespaced",
                          "names": {"plural": "unrelateds", "kind": "Unrelated"}}}]}
        elif key == "infrastructures.config.openshift.io":
            data = {"items": [{"apiVersion":"config.openshift.io/v1", "kind":"Infrastructure",
                "metadata":{"name":"cluster"}, "status":{"apiServerURL":"https://api-internal-test-env-workload0.internal.synthetic.invalid:6443"}}]}
        elif key == "pods":
            data = {"items": [{"apiVersion":"v1", "kind":"Pod", "metadata":{"name":"private-pod", "namespace":"fixture"},
                "spec":{"nodeName":"node-a09", "containers":[{"name":"main", "env":[{"name":"PRIVATE", "value":"POD_ENV_MUST_NOT_PERSIST"}]}]},
                "status":{"phase":"Running", "conditions":[{"type":"Ready", "status":"True", "message":"private-condition"}],
                          "containerStatuses":[{"name":"main", "ready":True, "restartCount":0, "imageID":"private-image"}]}}]}
        elif key == "applications.argoproj.io":
            data = {"items": [{"apiVersion":"argoproj.io/v1alpha1", "kind":"Application", "metadata":{"name":"private-app"},
                "spec":{"source":{"helm":{"values":"APPLICATION_HELM_MUST_NOT_PERSIST"}}}}]}
        elif key == "widgets.fixture.example":
            data = {"items": [{"apiVersion": "fixture.example/v1", "kind": "Widget", "metadata": {
                "name": "example", "namespace": "fixture", "annotations": {"argocd.argoproj.io/tracking-id": "app:fixture.example/Widget:fixture/example"}},
                "spec": {"sensitive": "not retained"}}]}
        else:
            data = {"items": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    def capture(self, **kwargs):
        with patch("shutil.which", return_value="/fixture/oc"), patch("subprocess.run", side_effect=self.oc) as run:
            manifest = capture_live("test-env", "test-env-workload0", self.output,
                                    client=LocalRepositories(REPOS), **kwargs)
        return manifest, run.call_args_list

    def test_only_read_only_get_json_commands_and_all_required_kinds(self):
        manifest, calls = self.capture()
        self.assertTrue(set(REQUIRED) <= set(manifest["resources"]))
        self.assertEqual(manifest["api_url"], "https://api-internal-test-env-workload0.internal.synthetic.invalid:6443")
        self.assertEqual(manifest["user"], "fixture-reader")
        self.assertTrue(manifest["timestamp"])
        self.assertEqual(len(manifest["commands"]), len(calls))
        self.assertTrue(all(command[:2] == ["oc", "get"] and "--as" not in command for command in manifest["commands"]))
        self.assertTrue(all((self.output / f"{key}.json").is_file() for key in manifest["resources"]))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.output / "manifest.json").stat().st_mode & 0o777, 0o600)

    def test_forbidden_recorded_and_custom_kind_discovered(self):
        manifest, _ = self.capture()
        self.assertEqual(manifest["forbidden"], ["dnses.operator.openshift.io"])
        self.assertEqual(json.loads((self.output / "dnses.operator.openshift.io.json").read_text())["reason"], "Forbidden")
        widget = json.loads((self.output / "widgets.fixture.example.json").read_text())["items"][0]
        self.assertIn("annotations", widget["metadata"])
        self.assertNotIn("spec", widget)
        command = next(cmd for cmd in manifest["commands"] if cmd[2] == "widgets.fixture.example")
        self.assertIn("--all-namespaces", command)

    def test_explicit_impersonation_only(self):
        manifest, _ = self.capture(as_user="requested-user")
        self.assertEqual(manifest["impersonated_user"], "requested-user")
        self.assertTrue(all(cmd[cmd.index("--as") + 1] == "requested-user" for cmd in manifest["commands"]))

    def test_missing_oc_cli_one_line_login_message(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {"PATH": ""}), contextlib.redirect_stderr(stderr):
            code = cli.main(["capture-live", "test-env", "--workload", "workload0", "--out", str(self.output)])
        self.assertEqual(code, 2)
        self.assertEqual(stderr.getvalue(), LOGIN_MESSAGE + "\n")
        self.assertFalse(self.output.exists())

    def test_expired_session_never_logs_in_or_refreshes(self):
        with (patch("shutil.which", return_value="/fixture/oc"),
              patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "Unauthorized")) as run):
            with self.assertRaisesRegex(CaptureError, "log in"):
                capture_live("test-env", "test-env-workload0", self.output)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:2], ["oc", "get"])

    def test_inherits_environment_without_reading_or_copying_credentials(self):
        manifest, calls = self.capture()
        self.assertFalse(self.config_path.exists())
        self.assertTrue(all("env" not in call.kwargs for call in calls))
        self.assertEqual(os.environ["KUBECONFIG"], str(self.config_path))
        self.assertEqual(manifest["user"], "fixture-reader")
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), ["capture"])

    def test_missing_session_requires_login_without_credential_inspection(self):
        with (patch("shutil.which", return_value="/fixture/oc"),
              patch("subprocess.run", return_value=subprocess.CompletedProcess(
                  [], 1, "", "Missing or incomplete configuration info")) as run):
            with self.assertRaises(CaptureError) as raised:
                capture_live("test-env", "test-env-workload0", self.output)
        self.assertEqual(str(raised.exception), LOGIN_MESSAGE)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:2], ["oc", "get"])
        self.assertNotIn("env", run.call_args.kwargs)
        self.assertFalse(self.output.exists())

    def test_expired_response_requires_exact_login_message(self):
        with (patch("shutil.which", return_value="/fixture/oc"),
              patch("subprocess.run", return_value=subprocess.CompletedProcess(
                  [], 1, "", "Authentication credentials expired")) as run):
            with self.assertRaises(CaptureError) as raised:
                capture_live("test-env", "test-env-workload0", self.output)
        self.assertEqual(str(raised.exception), LOGIN_MESSAGE)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:2], ["oc", "get"])
        self.assertFalse(self.output.exists())

    def test_discovery_forbidden_is_visible_not_silently_complete(self):
        original = self.oc
        def forbidden_crd(command, **kwargs):
            if command[2] == "customresourcedefinitions.apiextensions.k8s.io":
                return subprocess.CompletedProcess(command, 1, "", "Forbidden")
            return original(command, **kwargs)
        with patch("shutil.which", return_value="/fixture/oc"), patch("subprocess.run", side_effect=forbidden_crd):
            manifest = capture_live("test-env", "test-env-workload0", self.output, client=LocalRepositories(REPOS))
        self.assertFalse(manifest["discovery_complete"])
        self.assertIn("customresourcedefinitions.apiextensions.k8s.io: Forbidden", manifest["discovery_errors"])

    def test_existing_snapshot_is_not_overwritten(self):
        self.capture()
        with patch("shutil.which", return_value="/fixture/oc"):
            with self.assertRaisesRegex(CaptureError, "empty directory"):
                capture_live("test-env", "test-env-workload0", self.output)

    def test_native_kind_coverage_includes_prompt_examples(self):
        kinds = {item["kind"] for item in native_resources().values()}
        self.assertTrue({"Application", "Certificate", "DNS", "BaselineAdminNetworkPolicy",
                         "ClusterRoleBinding", "Subscription", "CustomResourceDefinition"} <= kinds)

    def test_pod_env_and_application_helm_values_never_reach_disk(self):
        self.capture()
        for path in self.output.iterdir():
            content = path.read_text()
            self.assertNotIn("POD_ENV_MUST_NOT_PERSIST", content)
            self.assertNotIn("APPLICATION_HELM_MUST_NOT_PERSIST", content)
            self.assertNotIn('"env"', content)
            self.assertNotIn('"helm"', content)
            self.assertNotIn("private-condition", content)
            self.assertNotIn("private-image", content)
        pod = json.loads((self.output / "pods.json").read_text())["items"][0]
        self.assertEqual(pod["spec"], {"nodeName":"node-a09"})
        self.assertEqual(pod["status"], {"phase":"Running", "conditions":[{"type":"Ready", "status":"True"}],
                                         "containerStatuses":[{"name":"main", "ready":True, "restartCount":0}]})
        app = json.loads((self.output / "applications.argoproj.io.json").read_text())["items"][0]
        self.assertEqual(set(app), {"apiVersion", "kind", "metadata"})

    def test_only_declared_or_required_kinds_are_requested_never_secrets(self):
        manifest, _ = self.capture()
        fetched = {command[2] for command in manifest["commands"]}
        self.assertEqual(fetched, set(REQUIRED) | {
            "users.user.openshift.io", "jobsetoperators.operator.openshift.io",
            "kueues.kueue.openshift.io", "operatorgroups.operators.coreos.com", "widgets.fixture.example"})
        self.assertTrue(fetched.isdisjoint({"secrets", "events", "endpoints", "replicasets.apps", "replicationcontrollers", "unrelateds.fixture.example"}))


if __name__ == "__main__":
    unittest.main()
