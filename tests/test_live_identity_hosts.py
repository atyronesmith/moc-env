"""Hosted-cluster API identity regressions using synthetic DNS and TEST-NET IPs."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from ipaddress import ip_address, ip_network
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli
from moc_env.verify_live import APPS, LocalRepositories


REPOS = Path(__file__).parent / "fixtures/live/repos"
HUB_VALUES = "hosted-clusters/test-env-infra/values.yaml"
INTERNAL = "api-internal-test-env-workload0.internal.synthetic.invalid"
EXTERNAL = "api-external-test-env-workload0.external.synthetic.invalid"


class LiveIdentityHostsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "snapshot"
        self.client = LocalRepositories(REPOS)
        self.hub_values = self.client.get_file(APPS, HUB_VALUES)
        self.live_host = INTERNAL

    def capture(self):
        original = self.client.get_file

        def read(repository, path, ref="main"):
            if path == HUB_VALUES:
                if self.hub_values is None:
                    raise FileNotFoundError("synthetic hub values missing")
                return self.hub_values
            return original(repository, path, ref)

        def oc(command, **kwargs):
            if command[2] == "infrastructures.config.openshift.io":
                data = {"items": [{
                    "apiVersion": "config.openshift.io/v1", "kind": "Infrastructure",
                    "metadata": {"name": "cluster"},
                    "status": {"apiServerURL": f"https://{self.live_host}:6443"},
                }]}
            elif command[2] == "users.user.openshift.io":
                data = {"metadata": {"name": "synthetic-reader"}}
            else:
                data = {"items": []}
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(self.client, "get_file", side_effect=read),
            patch("shutil.which", return_value="/synthetic/oc"),
            patch("subprocess.run", side_effect=oc),
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "_new_github_client", return_value=self.client),
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
        ):
            code = cli.main([
                "capture-live", "test-env", "--workload", "workload0", "--out", str(self.output),
            ])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_verified(self):
        code, _, stderr = self.capture()
        self.assertEqual((code, stderr), (0, ""))
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertIs(manifest["identity_verified"], True)
        self.assertNotIn("identity_reason", manifest)

    def test_internal_api_dns_name_verifies(self):
        self.assert_verified()

    def test_external_api_dns_name_verifies(self):
        self.live_host = EXTERNAL
        self.assert_verified()

    def test_internal_ip_address_verifies(self):
        self.live_host = "192.0.2.10"
        self.assert_verified()

    def test_external_ip_address_verifies(self):
        self.live_host = "192.0.2.11"
        self.assert_verified()

    def test_wrong_name_exits_two_and_lists_both_names_without_writing(self):
        self.live_host = "api.other.invalid"
        code, stdout, stderr = self.capture()
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(
            stderr,
            f"moc-env: cluster API host api.other.invalid does not match declared API hosts "
            f"{INTERNAL}, {EXTERNAL} for test-env-workload0\n",
        )
        self.assertFalse(self.output.exists())

    def test_wrong_ip_exits_two_and_lists_both_addresses_without_writing(self):
        self.live_host = "192.0.2.99"
        code, stdout, stderr = self.capture()
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(
            stderr,
            "moc-env: cluster API host 192.0.2.99 does not match declared API hosts "
            "192.0.2.10, 192.0.2.11 for test-env-workload0\n",
        )
        self.assertFalse(self.output.exists())

    def test_external_domain_defaults_to_internal_domain(self):
        self.hub_values = "hcpInternalDomain: internal.synthetic.invalid\n"
        self.live_host = "api-external-test-env-workload0.internal.synthetic.invalid"
        self.assert_verified()

    def test_missing_hub_values_captures_unverified_with_reason(self):
        self.hub_values = None
        code, _, stderr = self.capture()
        self.assertEqual((code, stderr), (0, ""))
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertIs(manifest["identity_verified"], False)
        self.assertEqual(manifest["identity_reason"], f"declared API domains unavailable: {HUB_VALUES}")

    def test_missing_internal_domain_captures_unverified_with_reason(self):
        self.hub_values = "hcpExternalDomain: external.synthetic.invalid\n"
        code, _, stderr = self.capture()
        self.assertEqual((code, stderr), (0, ""))
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertIs(manifest["identity_verified"], False)
        self.assertIn("declared API names cannot be derived", manifest["identity_reason"])

    def test_ip_address_verification_does_not_require_hub_domains(self):
        self.hub_values = None
        self.live_host = "192.0.2.10"
        self.assert_verified()

    def test_synthetic_api_address_fields_are_documentation_ips_not_hostnames(self):
        for workload in ("test-env-workload0", "test-env-workload1"):
            path = f"hosted-clusters/test-env-infra/{workload}/values.yaml"
            values = yaml.safe_load(self.client.get_file(APPS, path))
            for field in ("ipAddress", "externalIpAddress"):
                with self.subTest(workload=workload, field=field):
                    self.assertIn(ip_address(values["services"]["APIServer"][field]), ip_network("192.0.2.0/24"))


if __name__ == "__main__":
    unittest.main()
