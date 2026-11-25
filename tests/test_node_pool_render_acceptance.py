"""CLI acceptance coverage for malformed node-pool names."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fakes import FakeGitHubClient
from moc_env import cli


class MalformedNameClient(FakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main") -> dict:
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            path = "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
            tree[path] = {"path": path}
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/oac-apps" and path.endswith(
            "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
        ):
            return text.replace("name: compute", "name: [compute]")
        return text


class MalformedDictNameClient(MalformedNameClient):
    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        return super().get_file(repository, path, ref).replace(
            "name: [compute]", "name: {nested: value}"
        )


class NodePoolRenderAcceptanceTest(unittest.TestCase):
    def test_malformed_name_is_blocking_and_renders_all_formats(self) -> None:
        for client_class in (MalformedNameClient, MalformedDictNameClient):
            with (
                self.subTest(client=client_class.__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                with (
                    patch.dict(
                        os.environ,
                        {"MOC_ENV_CACHE_DIR": str(Path(directory) / "cache")},
                    ),
                    patch.object(cli, "GitHubClient", client_class),
                    patch.object(cli, "_resolve_github_token", return_value=None),
                ):
                    for output_format in ("json", "markdown", "text"):
                        stdout, stderr = io.StringIO(), io.StringIO()
                        with (
                            contextlib.redirect_stdout(stdout),
                            contextlib.redirect_stderr(stderr),
                        ):
                            code = cli.main(
                                [
                                    "status",
                                    "bu-ist-demo",
                                    "--no-prs",
                                    "--details",
                                    "--format",
                                    output_format,
                                    "--fail-on",
                                    "blocking",
                                ]
                            )
                        self.assertEqual(code, 1, output_format)
                        if output_format == "json":
                            checks = json.loads(stdout.getvalue())["checks"]
                            pool_check = next(
                                item
                                for item in checks
                                if item["id"] == "workload.node_pool_hosts"
                            )
                            self.assertEqual(pool_check["state"], "value_mismatch")
                            self.assertEqual(pool_check["severity"], "blocking")
                            self.assertIn("name must be a string", pool_check["reason"])
                        else:
                            self.assertIn("Malformed nodePools", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
