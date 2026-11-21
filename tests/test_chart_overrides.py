"""Offline coverage for the ``charts --view overrides`` report."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fakes import FakeGitHubClient
from moc_env import chart_overrides, cli

DEFAULTS = {
    "replicas": 1,
    "image": {"repo": "quay.io/x/demo", "tag": "1.0"},
    "nodes": [],
    "extra": {},
    "mode": "fast",
}
HUB_LAYER = {
    "replicas": 3,
    "image": {"tag": "1.0"},
    "mode": "slow",
}
WORKLOAD_LAYER = {
    "image": {"repo": "quay.io/y/demo"},
    "nodes": [{"name": "a"}],
    "extra": {"key": "v"},
    "newKey": 7,
    "mode": "fast",
}
HUB_PATH = "values/demo-infra/alpha.yaml"
LOCAL_PATH = "values/demo-infra/local-cluster/alpha.yaml"
WORKLOAD_PATH = "values/demo-infra/demo-workload0/alpha.yaml"


class OverridesFakeGitHubClient(FakeGitHubClient):
    """One hub and one workload with component and non-component charts."""

    TREE = {
        "applicationsets/templates/hub/hub-components.yaml",
        "applicationsets/templates/managed/workload-components.yaml",
        "applicationsets/templates/managed/hosted-ingress.yaml",
        "values/demo-infra/local-cluster/acm-placements.yaml",
        HUB_PATH,
        LOCAL_PATH,
        WORKLOAD_PATH,
        "values/demo-infra/demo-workload0/hosted-ingress.yaml",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml",
        "charts/alpha/values.yaml",
        "charts/beta/values.yaml",
        "charts/hosted-ingress/values.yaml",
    }

    FILES = {
        "applicationsets/templates/hub/hub-components.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hub-components
spec:
  generators:
    - list:
        elements:
          - component: alpha
          - component: beta
  template:
    spec:
      source:
        path: "charts/{{component}}"
""",
        "applicationsets/templates/managed/workload-components.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: workload-components
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: all-managed-clusters
    - list:
        elements:
          - component: alpha
          - component: beta
  template:
    metadata:
      annotations:
        cluster.open-cluster-management.io/placement: all-managed-clusters
    spec:
      source:
        path: "charts/{{component}}"
""",
        "applicationsets/templates/managed/hosted-ingress.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hosted-ingress
spec:
  template:
    metadata:
      annotations:
        cluster.open-cluster-management.io/placement: all-managed-clusters
    spec:
      source:
        path: "charts/hosted-ingress"
""",
        "values/demo-infra/local-cluster/acm-placements.yaml": "placements: []\n",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml": """
clusterName: demo-workload0
clusterLabels: {}
""",
        HUB_PATH: "replicas: 3\nimage:\n  tag: '1.0'\nmode: slow\n",
        LOCAL_PATH: "mode: fast\nnewKey: hub\n",
        WORKLOAD_PATH: """
image:
  repo: quay.io/y/demo
nodes:
  - name: a
extra:
  key: v
newKey: 7
mode: fast
""",
        "values/demo-infra/demo-workload0/hosted-ingress.yaml": "enabled: true\n",
        "charts/alpha/values.yaml": """
replicas: 1
image:
  repo: quay.io/x/demo
  tag: '1.0'
nodes: []
extra: {}
mode: fast
""",
        "charts/beta/values.yaml": "replicas: 1\n",
        "charts/hosted-ingress/values.yaml": "enabled: false\n",
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update({path: {"path": path} for path in self.TREE})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            return self.FILES.get(path, "{}\n")
        return super().get_file(repository, path, ref)


class OverrideRowsTest(unittest.TestCase):
    def test_acceptance_inputs(self) -> None:
        rows = chart_overrides.override_rows(
            DEFAULTS,
            [
                ("values/h-infra/demo.yaml", HUB_LAYER),
                ("values/h-infra/h-workload0/demo.yaml", WORKLOAD_LAYER),
            ],
        )

        changed = [row for row in rows if row["status"] != "restated"]
        self.assertEqual(
            [(row["key"], row["status"]) for row in changed],
            [
                ("extra.key", "added"),
                ("image.repo", "changed"),
                ("newKey", "added"),
                ("nodes", "changed"),
                ("replicas", "changed"),
            ],
        )
        by_key = {row["key"]: row for row in rows}
        self.assertNotIn("default", by_key["extra.key"])
        self.assertEqual(by_key["extra.key"]["value"], "v")
        self.assertEqual(
            by_key["extra.key"]["source"], "values/h-infra/h-workload0/demo.yaml"
        )
        self.assertEqual(by_key["image.repo"]["default"], "quay.io/x/demo")
        self.assertEqual(by_key["image.repo"]["value"], "quay.io/y/demo")
        self.assertEqual(
            by_key["image.repo"]["source"], "values/h-infra/h-workload0/demo.yaml"
        )
        self.assertEqual(by_key["nodes"]["default"], [])
        self.assertEqual(by_key["nodes"]["value"], [{"name": "a"}])
        self.assertEqual(by_key["replicas"]["default"], 1)
        self.assertEqual(by_key["replicas"]["value"], 3)
        self.assertEqual(by_key["replicas"]["source"], "values/h-infra/demo.yaml")
        self.assertEqual(
            sum(1 for row in rows if row["status"] == "restated"), 2
        )
        self.assertEqual(by_key["mode"]["source"], "values/h-infra/h-workload0/demo.yaml")
        self.assertEqual(by_key["image.tag"]["source"], "values/h-infra/demo.yaml")

    def test_no_layers_produce_no_rows(self) -> None:
        self.assertEqual(chart_overrides.override_rows(DEFAULTS, []), [])

    def test_non_mapping_overrides_a_default_mapping(self) -> None:
        rows = chart_overrides.override_rows(
            {"image": {"repo": "quay.io/x/demo"}},
            [("values/hub/a.yaml", {"image": "disabled"})],
        )

        self.assertEqual(
            rows,
            [
                {
                    "key": "image",
                    "status": "changed",
                    "default": {"repo": "quay.io/x/demo"},
                    "value": "disabled",
                    "source": "values/hub/a.yaml",
                }
            ],
        )


class OverridesCommandTest(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "GitHubClient", lambda **kwargs: OverridesFakeGitHubClient()),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_text_lists_hub_and_workload_overrides(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("demo-infra · hub", stdout)
        self.assertIn("demo-workload0 · workload", stdout)
        self.assertIn("Chart: alpha", stdout)
        self.assertIn("image.repo", stdout)
        self.assertIn("quay.io/x/demo", stdout)
        self.assertIn("quay.io/y/demo", stdout)
        self.assertIn("values/demo-infra/demo-workload0/alpha.yaml", stdout)
        self.assertIn("Charts with no overrides: beta", stdout)
        self.assertIn("Restated values not shown: 2", stdout)
        self.assertIn("Not compared: hosted-ingress", stdout)
        self.assertIn("Source: CCI-MOC/oac-apps @ main", stdout)
        self.assertIn("does not cover", stdout)

    def test_markdown_has_a_table_only_for_changed_or_added_rows(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--workload",
                "demo-workload0",
                "--view",
                "overrides",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("## demo-workload0 (workload)", stdout)
        self.assertIn("### alpha", stdout)
        self.assertIn("| Key | Status | Default | Value | Set in |", stdout)
        self.assertIn("| nodes | changed | [] | [{\"name\":\"a\"}] |", stdout)
        self.assertIn("Not compared: hosted-ingress", stdout)
        self.assertNotIn("### beta", stdout)
        self.assertNotIn("### hosted-ingress", stdout)

    def test_json_keeps_full_values_and_per_chart_files(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
                "--format",
                "json",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        document = json.loads(stdout)
        self.assertEqual(document["view"], "overrides")
        self.assertEqual(document["repository"], "CCI-MOC/oac-apps")
        self.assertEqual(document["ref"], "main")
        self.assertTrue(document["sha"])
        self.assertIn("scope", document)
        self.assertIn("footer", document)
        workload = document["clusters"]["demo-workload0"]
        self.assertEqual(workload["not_compared"], ["hosted-ingress"])
        alpha = workload["charts"]["alpha"]
        self.assertEqual(
            alpha["files"],
            [HUB_PATH, WORKLOAD_PATH],
        )
        self.assertEqual(alpha["restated"], 2)
        by_key = {row["key"]: row for row in alpha["overrides"]}
        self.assertNotIn("default", by_key["extra.key"])
        self.assertEqual(by_key["nodes"]["value"], [{"name": "a"}])
        self.assertEqual(by_key["nodes"]["default"], [])
        hub_alpha = document["clusters"]["demo-infra"]["charts"]["alpha"]
        self.assertEqual(hub_alpha["files"], [HUB_PATH, LOCAL_PATH])
        self.assertEqual(hub_alpha["restated"], 2)

    def test_chart_filter_limits_the_overrides_view(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
                "--chart",
                "alpha",
                "--format",
                "json",
            ]
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(list(document["clusters"]["demo-infra"]["charts"]), ["alpha"])
        self.assertEqual(
            list(document["clusters"]["demo-workload0"]["charts"]), ["alpha"]
        )
        self.assertEqual(document["clusters"]["demo-workload0"]["not_compared"], [])

    def test_output_extension_infers_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for suffix, expected in (
                (".md", "## demo-workload0 (workload)"),
                (".json", '"view": "overrides"'),
            ):
                path = Path(directory) / f"overrides{suffix}"
                exit_code, stdout, stderr = self.run_cli(
                    [
                        "charts",
                        "demo",
                        "--workload",
                        "demo-workload0",
                        "--view",
                        "overrides",
                        "--output",
                        str(path),
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)
                self.assertEqual(stdout, "")
                self.assertIn(expected, path.read_text())


if __name__ == "__main__":
    unittest.main()
