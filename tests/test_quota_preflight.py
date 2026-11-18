"""Acceptance tests for the status preflight quota estimate."""

from __future__ import annotations

import contextlib
import io
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from moc_env import cli

from fakes import FakeGitHubClient


COMMIT_PATH = re.compile(r"^/repos/([^/]+/[^/]+)/commits/(.+)$")


class QuotaCountingClient(FakeGitHubClient):
    """Fixture client that counts API requests like the real client.

    ``FakeGitHubClient`` short-circuits the transport, so this subclass mirrors
    the quota-counted API calls a cold run would make: commit resolution, trees,
    and the MOC issue endpoint. Raw file downloads are free and stay uncounted.
    """

    instances: list["QuotaCountingClient"] = []
    rate_limit: int | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if type(self).rate_limit is not None:
            self.rate_limit_remaining = type(self).rate_limit
        self.estimated_calls: int | None = None
        self.candidate_urls: list[str] = []
        self._resolved: set[tuple[str, str]] = set()
        self._tree_urls: set[tuple[str, str]] = set()
        type(self).instances.append(self)

    def reserve_quota(self, estimated_calls, candidate_urls=None) -> None:
        self.estimated_calls = estimated_calls
        self.candidate_urls = list(candidate_urls or [])
        super().reserve_quota(estimated_calls, candidate_urls)

    def _count_commit(self, repository: str) -> None:
        ref = self.ref_for(repository)
        key = (repository, ref)
        if key in self._resolved:
            return
        self._resolved.add(key)
        self.counted_endpoints.append(f"/repos/{repository}/commits/{ref}")

    def get_json(self, path_or_url: str):
        match = COMMIT_PATH.fullmatch(path_or_url)
        if match:
            self._resolved.add((match.group(1), match.group(2)))
        self.counted_endpoints.append(path_or_url)
        return super().get_json(path_or_url)

    def get_tree(self, repository: str, ref: str = "main"):
        self._count_commit(repository)
        key = (repository, self.ref_for(repository))
        if key not in self._tree_urls:
            self._tree_urls.add(key)
            self.counted_endpoints.append(
                f"/repos/{repository}/git/trees/{key[1]}?recursive=1"
            )
        tree = dict(super().get_tree(repository, ref))
        if repository == "CCI-MOC/oac-infra":
            tree["hub-images/group_vars/oac-prod-infra/vars.yml"] = {
                "path": "hub-images/group_vars/oac-prod-infra/vars.yml"
            }
        if repository == "CCI-MOC/oac-apps":
            for path in (
                "hosted-clusters/oac-prod-infra/values.yaml",
                "hosted-clusters/oac-prod-infra/"
                "oac-prod-workload0/values.yaml",
            ):
                tree[path] = {"path": path}
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        self._count_commit(repository)
        if repository == "CCI-MOC/oac-infra" and path == "hub-images/inventory.yml":
            return """
all:
  children:
    bu-ist-demo-infra:
      hosts:
        bu-ist-demo-infra:
          ansible_connection: local
    oac-prod-infra:
      hosts:
        oac-prod-infra:
          ansible_connection: local
"""
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            return super().get_file(repository, path, ref) + """
    oac_prod_clusters:
          children:
            oac_prod_infra:
              vars:
                cluster: oac-prod-infra
              children:
                controller:
                  hosts:
                    control-0:
                      node_name: MOC-R4PAC10U31-S1C
            oac_prod_workload0:
              vars:
                cluster: oac-prod-workload0
              children:
                compute:
                  hosts:
                    compute-0:
                      node_name: MOC-R4PAC10U31-S1D
"""
        if (
            repository == "CCI-MOC/oac-infra"
            and path == "hub-images/group_vars/oac-prod-infra/vars.yml"
        ):
            return """
cluster_domain_name: oac-prod
base_domain: oac.ocp.massopen.cloud
machine_network: 10.20.8.0/23
api_ip: 10.20.9.11
ingress_ip: 10.20.9.12
dns_ip: 8.8.8.8
"""
        if repository == "CCI-MOC/oac-apps" and path.startswith(
            "hosted-clusters/oac-prod-infra/"
        ):
            return "{}\n"
        return super().get_file(repository, path, ref)


class QuotaPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        cache_directory = tempfile.TemporaryDirectory()
        self.addCleanup(cache_directory.cleanup)
        environment = patch.dict(
            os.environ,
            {"MOC_ENV_CACHE_DIR": cache_directory.name},
        )
        environment.start()
        self.addCleanup(environment.stop)
        QuotaCountingClient.instances = []
        QuotaCountingClient.rate_limit = None

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str, QuotaCountingClient]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "GitHubClient", QuotaCountingClient),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue(), QuotaCountingClient.instances[-1]

    def test_preflight_matches_cold_counted_endpoints(self) -> None:
        cases = (
            ("oac-prod", 10),
            ("bu-ist-demo", 12),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                exit_code, _, stderr, client = self.run_cli(
                    ["status", environment, "--no-prs", "--format", "json"]
                )
                self.assertEqual(exit_code, 0, stderr)
                self.assertEqual(client.estimated_calls, len(client.candidate_urls))
                self.assertEqual(client.estimated_calls, len(client.counted_endpoints))
                self.assertEqual(expected, len(client.counted_endpoints))

    def test_quota_equal_to_counted_calls_succeeds(self) -> None:
        _, _, _, measured = self.run_cli(
            ["status", "bu-ist-demo", "--no-prs", "--format", "json"]
        )
        counted = len(measured.counted_endpoints)
        with tempfile.TemporaryDirectory() as cache:
            with patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": cache}):
                QuotaCountingClient.rate_limit = counted
                exit_code, _, stderr, client = self.run_cli(
                    ["status", "bu-ist-demo", "--no-prs", "--format", "json"]
                )
        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(len(client.counted_endpoints), counted)

    def test_quota_one_below_counted_calls_raises_before_requests(self) -> None:
        _, _, _, measured = self.run_cli(
            ["status", "bu-ist-demo", "--no-prs", "--format", "json"]
        )
        counted = len(measured.counted_endpoints)
        with tempfile.TemporaryDirectory() as cache:
            with patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": cache}):
                QuotaCountingClient.rate_limit = counted - 1
                exit_code, _, stderr, client = self.run_cli(
                    ["status", "bu-ist-demo", "--no-prs", "--format", "json"]
                )
        self.assertEqual(exit_code, 2)
        self.assertIn("GitHub API quota is too small for this run", stderr)
        self.assertIn(f"{counted} calls needed, {counted - 1} available", stderr)
        self.assertEqual(client.counted_endpoints, [])


if __name__ == "__main__":
    unittest.main()
