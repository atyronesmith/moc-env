"""Offline coverage for the ``charts --view reference`` reader and view."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from moc_env import chart_reference, cli

from fakes import CrossRepoFakeGitHubClient


class ChartReferenceReaderTest(unittest.TestCase):
    def test_description_example_and_unattached_comments(self) -> None:
        values = chart_reference.read_values(
            """
# Description for alpha.
alpha: 1
beta: []
# Example line one.
# Example line two.

# Unattached block.
"""
        )

        rows = {row.key: row for row in values.rows}
        self.assertEqual(rows["alpha"].description, "Description for alpha.")
        self.assertEqual(rows["beta"].example, "Example line one.\nExample line two.")
        self.assertEqual(values.other_comments, ("Unattached block.",))

    def test_blank_line_breaks_comment_adjacency(self) -> None:
        values = chart_reference.read_values(
            """
# This block is not adjacent.

alpha: 1
"""
        )

        self.assertEqual(values.rows[0].description, "")
        self.assertEqual(values.other_comments, ("This block is not adjacent.",))

    def test_trailing_comment_appends_to_description(self) -> None:
        values = chart_reference.read_values(
            """
# Prefix.
alpha: "" # defaults to beta
"""
        )

        self.assertEqual(values.rows[0].description, "Prefix. defaults to beta")

    def test_hash_inside_a_quoted_string_is_not_a_comment(self) -> None:
        values = chart_reference.read_values(
            'alpha: "#ffffff"\n'
        )

        self.assertEqual(values.rows[0].default, "#ffffff")
        self.assertEqual(values.rows[0].description, "")

    def test_a_list_is_a_leaf(self) -> None:
        values = chart_reference.read_values(
            """
items:
  - name: first
    value: 1
"""
        )

        self.assertEqual([row.key for row in values.rows], ["items"])
        self.assertEqual(
            chart_reference.compact_json(values.rows[0].default),
            '[{"name":"first","value":1}]',
        )

    def test_commented_parent_mapping_gets_its_own_row(self) -> None:
        values = chart_reference.read_values(
            """
# Parent settings.
parent:
  child: true
"""
        )

        self.assertEqual(
            [(row.key, row.default, row.description) for row in values.rows],
            [
                ("parent", "", "Parent settings."),
                ("parent.child", True, ""),
            ],
        )

    def test_required_paths_are_yes_or_conditional(self) -> None:
        unconditional, conditional = chart_reference.required_value_sets(
            '{{- required "plain" .Values.plain }}\n'
            '{{- if .Values.enabled }}\n'
            '{{- required "gated" .Values.gated }}\n'
            '{{- end }}\n'
        )

        self.assertEqual(unconditional, {"plain"})
        self.assertEqual(conditional, {"gated"})

    def test_required_path_missing_from_values_gets_a_row(self) -> None:
        values = chart_reference.read_values(
            "alpha: 1\n", unconditional_required={"missing.path"}
        )
        row = next(row for row in values.rows if row.key == "missing.path")

        self.assertEqual(row.default, chart_reference.MISSING_DEFAULT)
        self.assertEqual(row.required, "yes")


class ChartReferenceCommandFake(CrossRepoFakeGitHubClient):
    """Small oac-apps tree with hub, workload and feature chart placements."""

    TREE = {
        "applicationsets/templates/hub/hub-components.yaml",
        "applicationsets/templates/hub/hosted-clusters.yaml",
        "applicationsets/templates/managed/all-managed-clusters.yaml",
        "applicationsets/templates/managed/gpu-clusters.yaml",
        "values/demo-infra/local-cluster/acm-placements.yaml",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml",
        "charts/alpha/Chart.yaml",
        "charts/alpha/values.yaml",
        "charts/alpha/templates/config.yaml",
        "charts/beta/Chart.yaml",
        "charts/beta/values.yaml",
        "charts/beta/templates/config.yaml",
        "charts/hosted-cluster/Chart.yaml",
        "charts/hosted-cluster/values.yaml",
        "charts/gpu-chart/Chart.yaml",
        "charts/gpu-chart/values.yaml",
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
        path: "charts/{{`{{component}}`}}"
""",
        "applicationsets/templates/hub/hosted-clusters.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hosted-clusters
spec:
  generators:
    - git:
        directories:
          - path: "hosted-clusters/{{ $hub }}/*"
  template:
    spec:
      source:
        path: charts/hosted-cluster
""",
        "applicationsets/templates/managed/all-managed-clusters.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: all-managed-clusters
spec:
  generators:
    - clusterDecisionResource:
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: all-managed-clusters
    - list:
        elements:
          - component: alpha
  template:
    spec:
      source:
        path: "charts/{{`{{component}}`}}"
""",
        "applicationsets/templates/managed/gpu-clusters.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: gpu-clusters
spec:
  generators:
    - clusterDecisionResource:
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: gpu-clusters
    - list:
        elements:
          - component: gpu-chart
  template:
    spec:
      source:
        path: "charts/{{`{{component}}`}}"
""",
        "values/demo-infra/local-cluster/acm-placements.yaml": """
placements:
  - name: gpu-clusters
    matchLabels:
      massopen.cloud/feature-gpu: "true"
""",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml": """
clusterName: demo-workload0
clusterLabels: {}
""",
        "charts/alpha/Chart.yaml": "name: alpha\ndescription: Alpha chart.\n",
        "charts/alpha/values.yaml": "# Alpha setting.\nalpha: 1\n",
        "charts/alpha/templates/config.yaml": (
            '{{- required "alpha required" .Values.alpha }}\n'
        ),
        "charts/beta/Chart.yaml": "name: beta\ndescription: Beta chart.\n",
        "charts/beta/values.yaml": "beta: false\n",
        "charts/beta/templates/config.yaml": "kind: ConfigMap\n",
        "charts/hosted-cluster/Chart.yaml": (
            "name: hosted-cluster\ndescription: Create a workload cluster.\n"
        ),
        "charts/hosted-cluster/values.yaml": "clusterName: \"\"\n",
        "charts/gpu-chart/Chart.yaml": "name: gpu-chart\ndescription: GPU settings.\n",
        "charts/gpu-chart/values.yaml": "enabled: true\n",
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update({path: {"path": path} for path in self.TREE})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps" and path in self.FILES:
            return self.FILES[path]
        return super().get_file(repository, path, ref)


class ChartReferenceCommandTest(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli, "GitHubClient", lambda **kwargs: ChartReferenceCommandFake()
            ),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_chart_option_limits_only_the_reference_section(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["charts", "--view", "reference", "--chart", "alpha"]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("### Charts every hub receives (2)", stdout)
        self.assertIn("- [alpha](#alpha)", stdout)
        self.assertIn("- beta", stdout)
        self.assertNotIn("[beta](#beta)", stdout)
        self.assertIn("\n### alpha\n", stdout)
        self.assertNotIn("\n### beta\n", stdout)

    def test_feature_without_a_matching_cluster_still_gets_a_section(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["charts", "--view", "reference", "--format", "json"]
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        features = {
            feature["name"]: feature
            for feature in document["workload"]["features"]
        }
        self.assertEqual(features["gpu"]["charts"], ["gpu-chart"])
        self.assertEqual(
            features["gpu"]["label"], 'massopen.cloud/feature-gpu: "true"'
        )
        self.assertEqual(document["charts"]["alpha"]["rows"][0]["required"], "yes")


if __name__ == "__main__":
    unittest.main()
