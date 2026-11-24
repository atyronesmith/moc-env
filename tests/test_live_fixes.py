"""Synthetic regressions for live credentials, workload discovery, and identity."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.capture_live import capture_live
from moc_env.checks import list_environments
from moc_env.verify_live import LocalRepositories, render_live_report, verify_live


FIXTURES = Path(__file__).parent / "fixtures/live"
REPOS = FIXTURES / "repos"
INFRASTRUCTURE = "infrastructures.config.openshift.io"
WRONG_CLUSTER = (
    "moc-env: cluster API host api.other.invalid does not match declared API hosts "
    "api-internal-test-env-workload0.internal.synthetic.invalid, "
    "api-external-test-env-workload0.external.synthetic.invalid for test-env-workload0\n"
)


class LiveFixesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / "snapshot"
        self.client = LocalRepositories(REPOS)
        self.api_url = "https://api-internal-test-env-workload0.internal.synthetic.invalid:6443"
        self.infrastructure_error = None

    def oc(self, command, **kwargs):
        key = command[2]
        if key == INFRASTRUCTURE and self.infrastructure_error:
            return subprocess.CompletedProcess(command, 1, "", self.infrastructure_error)
        if key == INFRASTRUCTURE:
            data = {"items": [{
                "apiVersion": "config.openshift.io/v1", "kind": "Infrastructure",
                "metadata": {"name": "cluster"}, "status": {"apiServerURL": self.api_url},
            }]}
        elif key == "users.user.openshift.io":
            data = {"metadata": {"name": "synthetic-reader"}}
        else:
            data = {"items": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def capture_cli(self, *options, workload="workload0", local=False):
        arguments = ["capture-live", "test-env", "--workload", workload,
                    "--out", str(self.output), *options]
        if local:
            arguments.extend(["--repository-root", str(REPOS)])
        with (
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=self.oc),
            patch.object(cli, "_resolve_github_token", return_value="synthetic-token"),
            patch.object(cli, "_new_github_client", return_value=self.client),
        ):
            return self.invoke(arguments)

    def manifest(self):
        return json.loads((self.output / "manifest.json").read_text())

    def test_local_inventory_declares_both_workloads(self):
        rows = list_environments(self.client)
        self.assertEqual(
            [row["cluster"] for row in rows if row["environment"] == "test-env"
            and row["type"] == "workload"],
            ["test-env-workload0", "test-env-workload1"],
        )

    def test_verify_resolves_both_workloads_by_short_and_full_name_offline(self):
        with (
            patch("subprocess.run", side_effect=AssertionError("no subprocess")),
            patch("urllib.request.urlopen", side_effect=AssertionError("no HTTP")),
            patch.object(cli, "_resolve_github_token", side_effect=AssertionError("no credentials")),
        ):
            for suffix in ("workload0", "workload1"):
                for workload in (suffix, "test-env-" + suffix):
                    with self.subTest(workload=workload):
                        code, stdout, stderr = self.invoke([
                            "verify-live", "test-env", "--workload", workload,
                            "--snapshot", str(FIXTURES / suffix), "--repository-root", str(REPOS),
                        ])
                        self.assertEqual((code, stderr), (1, ""))
                        self.assertIn("test-env-" + suffix + " · live verification", stdout)

    def test_capture_resolves_both_workloads_by_short_and_full_name(self):
        for suffix in ("workload0", "workload1"):
            for workload in (suffix, "test-env-" + suffix):
                with self.subTest(workload=workload):
                    self.output = self.directory / workload
                    self.api_url = f"https://api-internal-test-env-{suffix}.internal.synthetic.invalid:6443"
                    code, _, stderr = self.capture_cli(workload=workload, local=True)
                    self.assertEqual((code, stderr), (0, ""))
                    self.assertEqual(self.manifest()["workload"], "test-env-" + suffix)

    def test_unknown_workload_uses_exact_shared_resolver_error(self):
        expected = (
            "moc-env: unknown workload cluster: workload9\nKnown workload clusters:\n"
            "  test-env-workload0\n  test-env-workload1\n"
        )
        with patch("subprocess.run", side_effect=AssertionError("no oc query")):
            code, stdout, stderr = self.invoke([
                "verify-live", "test-env", "--workload", "workload9", "--snapshot", str(self.output),
                "--repository-root", str(REPOS),
            ])
        self.assertEqual((code, stdout, stderr), (2, "", expected))
        code, stdout, stderr = self.capture_cli(workload="workload9", local=True)
        self.assertEqual((code, stdout, stderr), (2, "", expected))
        self.assertFalse(self.output.exists())

    def test_capture_without_repository_root_uses_credential_factory_client(self):
        with (
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=self.oc),
            patch.object(cli, "_resolve_github_token", return_value="synthetic-token") as token,
            patch.object(cli, "_new_github_client", return_value=self.client) as factory,
            patch("moc_env.live_cli.capture_live", wraps=capture_live) as capture,
        ):
            code, _, stderr = self.invoke([
                "capture-live", "test-env", "--workload", "workload0", "--out", str(self.output),
                "--no-auth", "--offline", "--timeout", "7",
            ])
        self.assertEqual((code, stderr), (0, ""))
        token.assert_called_once()
        factory.assert_called_once_with(token.call_args.args[0], "synthetic-token")
        self.assertTrue(factory.call_args.args[0].no_auth)
        self.assertTrue(factory.call_args.args[0].offline)
        self.assertEqual(factory.call_args.args[0].timeout, 7)
        self.assertIs(capture.call_args.kwargs["client"], self.client)
        self.assertNotIn("synthetic-token", (self.output / "manifest.json").read_text())

    def test_local_capture_does_not_resolve_github_credentials(self):
        with (
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=self.oc),
            patch.object(cli, "_resolve_github_token", side_effect=AssertionError("no credentials")),
            patch.object(cli, "_new_github_client", side_effect=AssertionError("no GitHub factory")),
        ):
            code, _, stderr = self.invoke([
                "capture-live", "test-env", "--workload", "workload0", "--out", str(self.output),
                "--repository-root", str(REPOS),
            ])
        self.assertEqual((code, stderr), (0, ""))

    def test_matching_host_captures_and_infrastructure_is_read_once(self):
        with (
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=self.oc) as run,
        ):
            manifest = capture_live("test-env", "test-env-workload0", self.output, client=self.client)
        self.assertTrue(manifest["identity_verified"])
        self.assertNotIn("identity_reason", manifest)
        self.assertEqual(sum(call.args[0][2] == INFRASTRUCTURE for call in run.call_args_list), 1)
        self.assertEqual(self.manifest(), manifest)

    def test_host_comparison_ignores_case_trailing_dot_and_port(self):
        self.api_url = "https://API-INTERNAL-TEST-ENV-WORKLOAD0.INTERNAL.SYNTHETIC.INVALID.:443"
        self.assertEqual(self.capture_cli()[0], 0)
        self.assertTrue(self.manifest()["identity_verified"])

    def test_wrong_cluster_exits_two_with_exact_error_and_empty_output(self):
        self.output.mkdir(mode=0o755)
        self.api_url = "https://api.other.invalid:6443"
        self.assertEqual(self.capture_cli(), (2, "", WRONG_CLUSTER))
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o755)

    def test_wrong_cluster_does_not_create_output(self):
        self.api_url = "https://api.other.invalid:6443"
        self.assertEqual(self.capture_cli(), (2, "", WRONG_CLUSTER))
        self.assertFalse(self.output.exists())

    def test_unreadable_infrastructure_records_reason_and_verify_prints_line(self):
        self.infrastructure_error = "Forbidden"
        self.assertEqual(self.capture_cli()[0], 0)
        manifest = self.manifest()
        self.assertIs(manifest["identity_verified"], False)
        self.assertEqual(manifest["identity_reason"], "Forbidden")
        self.assertIn(INFRASTRUCTURE, manifest["forbidden"])
        for format in ("text", "markdown", "json"):
            with self.subTest(format=format), patch(
                "subprocess.run", side_effect=AssertionError("verify must be offline")
            ):
                code, stdout, stderr = self.invoke([
                    "verify-live", "test-env", "--workload", "workload0",
                    "--snapshot", str(self.output), "--repository-root", str(REPOS),
                    "--format", format,
                ])
                self.assertEqual((code, stderr), (1, ""))
                if format == "json":
                    self.assertIs(json.loads(stdout)["snapshot"]["identity_verified"], False)
                else:
                    lines = stdout.splitlines()
                    result = next(i for i, line in enumerate(lines) if line.startswith("RESULT:"))
                    self.assertEqual(
                        lines[result + 1], "Snapshot's cluster identity was not verified: Forbidden."
                    )

    def test_missing_declared_address_continues_unverified(self):
        self.api_url = "https://192.0.2.10:6443"
        original = self.client.get_file

        def read(repository, path, ref="main"):
            text = original(repository, path, ref)
            return text.split("services:")[0] if path.endswith("test-env-workload0/values.yaml") else text

        with patch.object(self.client, "get_file", side_effect=read):
            self.assertEqual(self.capture_cli()[0], 0)
        self.assertIs(self.manifest()["identity_verified"], False)
        self.assertIn("services.APIServer.ipAddress and externalIpAddress missing", self.manifest()["identity_reason"])

    def test_unreadable_declared_values_continues_unverified(self):
        original = self.client.get_file

        def read(repository, path, ref="main"):
            if path.startswith("hosted-clusters/"):
                raise OSError("synthetic unavailable file")
            return original(repository, path, ref)

        with patch.object(self.client, "get_file", side_effect=read):
            self.assertEqual(self.capture_cli()[0], 0)
        self.assertIs(self.manifest()["identity_verified"], False)
        self.assertIn("declared API address unavailable", self.manifest()["identity_reason"])
        self.assertFalse(self.manifest()["discovery_complete"])
        self.assertIn("declared chart resources unavailable", self.manifest()["discovery_errors"][0])

    def test_invalid_declared_yaml_continues_unverified(self):
        original = self.client.get_file

        def read(repository, path, ref="main"):
            if path.startswith("hosted-clusters/"):
                return "services: ["
            return original(repository, path, ref)

        with patch.object(self.client, "get_file", side_effect=read):
            self.assertEqual(self.capture_cli()[0], 0)
        self.assertIs(self.manifest()["identity_verified"], False)
        self.assertIn("declared API address unavailable", self.manifest()["identity_reason"])
        self.assertFalse(self.manifest()["discovery_complete"])

    def test_skip_identity_check_explicitly_records_unverified_reason(self):
        self.api_url = "https://api.other.invalid:6443"
        code, _, stderr = self.capture_cli("--skip-identity-check")
        self.assertEqual((code, stderr), (0, ""))
        self.assertIs(self.manifest()["identity_verified"], False)
        self.assertEqual(self.manifest()["identity_reason"], "skipped with --skip-identity-check")


class UndeclaredHardwareProfilesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.snapshot = self.directory / "snapshot"
        self.repositories = self.directory / "repos"
        shutil.copytree(FIXTURES / "workload0", self.snapshot)
        shutil.copytree(REPOS, self.repositories)
        self.client = LocalRepositories(self.repositories)
        self.values = self.repositories / "oac-apps/values/test-env-infra/test-env-workload0/rhoai.yaml"
        self.values.write_text(json.dumps({
            "hardwareProfiles": [{"name": "gpu-a"}, {"name": "gpu-b"}],
            "enabledHardwareProfiles": [],
        }))
        nodes = json.loads((self.snapshot / "nodes.json").read_text())
        nodes["items"].append({"kind": "Node", "metadata": {"name": "node-a10"}})
        (self.snapshot / "nodes.json").write_text(json.dumps(nodes))
        manifest_path = self.snapshot / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["forbidden"] = []
        manifest["resources"]["dnses.operator.openshift.io"]["status"] = "captured"
        manifest_path.write_text(json.dumps(manifest))
        (self.snapshot / "dnses.operator.openshift.io.json").write_text(json.dumps({"items": [{
            "apiVersion": "operator.openshift.io/v1", "kind": "DNS",
            "metadata": {"name": "default", "annotations": {
                "argocd.argoproj.io/tracking-id": "test-env-workload0-dns-operator-config:operator.openshift.io/DNS:/default",
            }},
        }]}))

    def set_profiles(self, *names):
        path = self.snapshot / "hardwareprofiles.infrastructure.opendatahub.io.json"
        path.write_text(json.dumps({"items": [{
            "kind": "HardwareProfile", "metadata": {
                "name": name, "namespace": "ai-applications",
                "annotations": {"opendatahub.io/disabled": "false"},
            }, "spec": {},
        } for name in names]}))

    def report(self):
        return verify_live(self.client, "test-env", "test-env-workload0", self.snapshot)

    def invoke(self, format):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main([
                "verify-live", "test-env", "--workload", "workload0", "--snapshot", str(self.snapshot),
                "--repository-root", str(self.repositories), "--format", format,
            ])
        self.assertEqual(stderr.getvalue(), "")
        return code, stdout.getvalue()

    def test_undeclared_live_profile_is_a_note_not_a_verdict(self):
        expected_note = {"section": "OpenShift AI", "name": "hardwareprofile/site-default",
            "detail": "live, not defined by the rhoai chart"}
        text_note = "  note            hardwareprofile/site-default | live, not defined by the rhoai chart"
        markdown_note = "note: `hardwareprofile/site-default` | live, not defined by the rhoai chart"
        for live_gpu, expected_exit in ((True, 1), (False, 0)):
            with self.subTest(live_gpu=live_gpu):
                self.set_profiles("site-default", *(("gpu-a",) if live_gpu else ()))
                report = self.report()
                rows = {row["name"]: row["verdict"] for row in report["sections"]["OpenShift AI"]
                    if row["name"].startswith("hardwareprofile/")}
                self.assertEqual(rows, {
                    "hardwareprofile/gpu-a": "drift" if live_gpu else "expected-absent",
                    "hardwareprofile/gpu-b": "expected-absent",
                })
                self.assertEqual(report["undeclared"], [expected_note])
                self.assertEqual(report["summary"]["drift"], expected_exit)
                for format, note in (("text", text_note), ("markdown", markdown_note), ("json", None)):
                    with self.subTest(format=format):
                        code, output = self.invoke(format)
                        self.assertEqual(code, expected_exit)
                        if format == "json":
                            self.assertEqual(json.loads(output)["undeclared"], [expected_note])
                        else:
                            self.assertIn(note, output.splitlines())
                            self.assertLess(output.index("hardwareprofile/gpu-b"), output.index(note))
                            self.assertLess(output.index(note), output.index("Health\n"))
                            self.assertEqual(output.count("hardwareprofile/site-default"), 1)

    def test_enabled_undefined_profile_is_still_drift(self):
        self.values.write_text(json.dumps({"hardwareProfiles": [], "enabledHardwareProfiles": ["unknown-gpu"]}))
        for present in (False, True):
            with self.subTest(present=present):
                self.set_profiles(*(("unknown-gpu",) if present else ()))
                report = self.report()
                row = next(row for row in report["sections"]["OpenShift AI"]
                    if row["name"] == "hardwareprofile/unknown-gpu")
                self.assertEqual(row["verdict"], "drift")
                self.assertEqual(report["undeclared"], [])
                self.assertEqual(self.invoke("text")[0], 1)

    def test_undeclared_list_is_present_and_empty_without_extra_profiles(self):
        self.set_profiles()
        report = self.report()
        self.assertEqual(report["undeclared"], [])
        self.assertEqual(json.loads(render_live_report(report, "json"))["undeclared"], [])
        self.assertNotIn("  note            hardwareprofile/", render_live_report(report))


if __name__ == "__main__":
    unittest.main()
