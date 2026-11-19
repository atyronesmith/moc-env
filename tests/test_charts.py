"""Offline coverage for the read-only ``moc-env charts`` command."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from moc_env import cli
from moc_env.charts import (
    _hub_chart_lists,
    _hub_rows,
    _undeployed_chart_data,
    collect_chart_inventory,
    footer,
    render_chart_inventory,
)
from moc_env.checks import StatusChecker
from moc_env.model import Environment

from fakes import CrossRepoFakeGitHubClient


GPU_LABEL = "massopen.cloud/feature-gpu"
WORKLOAD0 = "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
WORKLOAD1 = "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload1/values.yaml"


class ChartsFakeGitHubClient(CrossRepoFakeGitHubClient):
    """Cross-repository fixture with hub components, placements and drop-ins."""

    EXTRA_TREE = {
        "applicationsets/templates/hub/hub-components.yaml",
        "applicationsets/templates/managed/gpu-clusters.yaml",
        "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml",
        "values/bu-ist-demo-infra/hub-alpha.yaml",
        "values/bu-ist-demo-infra/local-cluster/hub-alpha.yaml",
        "values/bu-ist-demo-infra/hub-beta.yaml",
        "values/bu-ist-demo-infra/gamma.yaml",
        "values/bu-ist-demo-infra/bu-ist-demo-workload0/gamma.yaml",
        "values/bu-ist-demo-infra/bu-ist-demo-workload0/delta.yaml",
        "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
        "values/bu-ist-demo-infra/local-cluster/keycloak-oauth.yaml",
        "hosted-clusters/bu-ist-demo-infra/compliance.yaml",
        WORKLOAD1,
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update(
                {path: {"path": path} for path in self.EXTRA_TREE}
            )
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            files = {
                "applicationsets/templates/hub/hub-components.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hub-components
spec:
  generators:
    - list:
        elements:
          - component: hub-alpha
          - component: hub-beta
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
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: gpu-clusters
    - list:
        elements:
          - component: gamma
          - component: delta
""",
                "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml": """
placements:
  - name: gpu-clusters
    matchLabels:
      massopen.cloud/feature-gpu: "true"
""",
                WORKLOAD0: """
clusterName: bu-ist-demo-workload0
clusterLabels:
  massopen.cloud/feature-gpu: "true"
feature-gpu: "false"
services:
  APIServer:
    ipAddress: 10.20.26.10
ingress:
  poolAddress: 10.20.28.10
""",
                WORKLOAD1: """
clusterName: bu-ist-demo-workload1
clusterLabels: {}
services:
  APIServer:
    ipAddress: 10.20.26.11
ingress:
  poolAddress: 10.20.28.11
""",
            }
            if path in files:
                return files[path]
            if path in self.EXTRA_TREE:
                return "{}\n"
        return super().get_file(repository, path, ref)


class UnreadableApplicationSetsClient(ChartsFakeGitHubClient):
    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if (
            repository == "CCI-MOC/oac-apps"
            and path.startswith("applicationsets/templates/managed/")
        ):
            raise AssertionError("managed ApplicationSet templates are unreadable")
        return super().get_file(repository, path, ref)


class ChartsCommandTest(unittest.TestCase):
    def run_cli(self, client, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "GitHubClient", lambda **kwargs: client),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_cluster_view_prints_each_cluster_section(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(), ["charts", "bu-ist-demo", "--view", "cluster"]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo-infra · hub", stdout)
        self.assertIn("bu-ist-demo-workload0 · workload", stdout)
        self.assertIn("bu-ist-demo-workload1 · workload", stdout)
        self.assertIn("hub-alpha", stdout)
        self.assertIn("gamma", stdout)
        self.assertIn("delta", stdout)
        self.assertIn("keycloak-oauth", stdout)
        self.assertIn("drop-in", stdout)

    def test_workload_filter_prints_only_that_cluster(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(),
            [
                "charts",
                "bu-ist-demo",
                "--workload",
                "bu-ist-demo-workload0",
            ],
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo-workload0", stdout)
        self.assertIn("Workload clusters", stdout)
        self.assertIn("Workload features", stdout)
        self.assertNotIn("Hubs", stdout)
        self.assertNotIn("bu-ist-demo-workload1", stdout)

    def test_summary_markdown_has_one_table_per_heading(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(),
            ["charts", "bu-ist-demo", "--format", "markdown"],
        )

        self.assertEqual(exit_code, 0)
        headings = [
            line[3:] for line in stdout.splitlines() if line.startswith("## ")
        ]
        self.assertEqual(
            headings,
            [
                "Workload clusters",
                "Workload features",
                "Hubs",
                "Hub groups",
                "Hub add-ons",
                "Charts not deployed by GitOps",
            ],
        )
        self.assertIn("|  | baseline | gpu | Charts |", stdout)
        self.assertIn("|---|---|:---:|---|", stdout)
        self.assertIn("| bu-ist-demo-workload0 |  | x | 2 |", stdout)
        self.assertIn("| gpu | delta, gamma |", stdout)
        self.assertIn("|---|:---:|:---:|---|", stdout)
        self.assertEqual(stdout.count("\n|---"), 6)

    def test_json_includes_source_and_chart_rows(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(),
            ["charts", "bu-ist-demo", "--view", "cluster", "--format", "json"],
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(document["ref"], "main")
        self.assertTrue(document["sha"])
        charts = [
            row["chart"]
            for row in document["clusters"]["bu-ist-demo-workload0"]["charts"]
        ]
        self.assertEqual(charts, ["gamma", "delta"])

    def test_summary_json_carries_all_five_tables(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(),
            ["charts", "bu-ist-demo", "--format", "json"],
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(document["ref"], "main")
        self.assertTrue(document["sha"])
        self.assertEqual(
            list(document["tables"]),
            [
                "workload_clusters",
                "workload_features",
                "hubs",
                "hub_groups",
                "hub_addons",
                "charts_not_deployed",
            ],
        )
        self.assertEqual(
            document["tables"]["workload_clusters"]["columns"],
            ["", "baseline", "gpu", "Charts"],
        )
        self.assertEqual(
            document["tables"]["workload_features"]["rows"][1],
            ["gpu", ["delta", "gamma"]],
        )
        self.assertEqual(
            document["tables"]["hub_addons"]["rows"],
            [["bu-ist-demo-infra", "x", 2]],
        )

    def test_unreadable_application_sets_exit_non_zero_with_reason(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            UnreadableApplicationSetsClient(), ["charts", "bu-ist-demo"]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Errors", stdout)
        self.assertIn(
            "bu-ist-demo-workload0: Application-set templates could not be read",
            stdout,
        )

    def test_hub_drop_ins_are_listed(self) -> None:
        inventory = collect_chart_inventory(
            ChartsFakeGitHubClient(), environment="bu-ist-demo"
        )
        hub = inventory.clusters[0]

        self.assertEqual(hub.name, "bu-ist-demo-infra")
        by_chart = {row["chart"]: row for row in hub.rows}
        self.assertEqual(by_chart["hub-alpha"]["application_set"], "hub-components")
        self.assertEqual(by_chart["hub-alpha"]["feature_label"], "hub")
        self.assertEqual(
            by_chart["keycloak-oauth"]["application_set"], "cluster-apps"
        )
        self.assertEqual(by_chart["keycloak-oauth"]["feature_label"], "drop-in")

    def test_workload_rows_equal_status_evidence_rows(self) -> None:
        client = ChartsFakeGitHubClient()
        report = StatusChecker(client, include_prs=False).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "workload.feature_chart_values"
        )
        inventory = collect_chart_inventory(
            client,
            environment="bu-ist-demo",
            workload="bu-ist-demo-workload0",
        )

        self.assertEqual(
            [dict(row) for row in inventory.clusters[0].rows],
            check["evidence"]["charts"],
        )

    def test_footer_is_verbatim(self) -> None:
        rendered = render_chart_inventory(
            collect_chart_inventory(
                ChartsFakeGitHubClient(), environment="bu-ist-demo", workload="bu-ist-demo-workload0"
            )
        )

        self.assertTrue(
            rendered.endswith(footer("main", "3" * 40) + "\n")
        )
        self.assertIn(
            "Not shown in the cluster tables: the hosted-cluster chart that creates\n"
            "each workload cluster on the hub, and kustomize overlays.\n",
            rendered,
        )

    def test_unrecognized_hub_application_set_exits_one_and_is_named(self) -> None:
        class SurpriseClient(ChartsFakeGitHubClient):
            def get_tree(self, repository: str, ref: str = "main"):
                tree = super().get_tree(repository, ref)
                if repository == "CCI-MOC/oac-apps":
                    tree["applicationsets/templates/hub/surprise.yaml"] = {
                        "path": "applicationsets/templates/hub/surprise.yaml"
                    }
                return tree

            def get_file(self, repository: str, path: str, ref: str = "main") -> str:
                if (
                    repository == "CCI-MOC/oac-apps"
                    and path == "applicationsets/templates/hub/surprise.yaml"
                ):
                    return "apiVersion: v1\nkind: ConfigMap\n"
                return super().get_file(repository, path, ref)

        exit_code, stdout, _ = self.run_cli(SurpriseClient(), ["charts", "bu-ist-demo"])

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "Unrecognized ApplicationSets (charts may be missing): "
            "applicationsets/templates/hub/surprise.yaml",
            stdout,
        )
        self.assertLess(
            stdout.index("Unrecognized ApplicationSets"),
            stdout.index("Source: CCI-MOC/oac-apps"),
        )

    def test_gated_hub_chart_list_requires_its_marker_file(self) -> None:
        list_path = "applicationsets/templates/hub/compliance-components.yaml"
        text = """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: compliance-components
spec:
  generators:
    - matrix:
        generators:
          - git:
              files:
                - path: "hosted-clusters/{{ $hub }}/compliance.yaml"
          - list:
              elements:
                - component: file-integrity
  template:
    spec:
      source:
        path: "charts/{{`{{component}}`}}"
"""
        tree = {
            list_path: {"path": list_path},
            "hosted-clusters/compliant-hub/compliance.yaml": {
                "path": "hosted-clusters/compliant-hub/compliance.yaml"
            },
        }
        lists, unrecognized = _hub_chart_lists(
            tree, lambda path: (text if path == list_path else None, None)
        )

        self.assertEqual(unrecognized, [])
        self.assertIn(
            "file-integrity",
            [row["chart"] for row in _hub_rows(tree, "compliant-hub", lists)],
        )
        self.assertNotIn(
            "file-integrity",
            [row["chart"] for row in _hub_rows(tree, "plain-hub", lists)],
        )

    def test_undeployed_charts_classify_components_comments_apps_and_libraries(
        self,
    ) -> None:
        paths = [
            "charts/component-chart/Chart.yaml",
            "charts/commented-chart/Chart.yaml",
            "charts/apps-chart/Chart.yaml",
            "charts/library-chart/Chart.yaml",
            "charts/user-chart/Chart.yaml",
            "charts/orphan-chart/Chart.yaml",
            "applicationsets/templates/managed/example.yaml",
            "apps/hub/drop-in.yaml",
            "values/hub/local-cluster/orphan-chart.yaml",
        ]
        tree = {path: {"path": path} for path in paths}
        texts = {
            "charts/component-chart/Chart.yaml": "name: component-chart\n",
            "charts/commented-chart/Chart.yaml": "name: commented-chart\n",
            "charts/apps-chart/Chart.yaml": "name: apps-chart\n",
            "charts/library-chart/Chart.yaml": "name: library-chart\n",
            "charts/user-chart/Chart.yaml": (
                "name: user-chart\n"
                "dependencies:\n"
                "  - name: library-chart\n"
                "    repository: file://../library-chart\n"
            ),
            "charts/orphan-chart/Chart.yaml": "name: orphan-chart\n",
            "applicationsets/templates/managed/example.yaml": (
                "generators:\n"
                "  - list:\n"
                "      elements:\n"
                "        - component: component-chart\n"
                "        - component: user-chart\n"
                "        # component: commented-chart\n"
            ),
            "apps/hub/drop-in.yaml": "spec:\n  source:\n    path: charts/apps-chart\n",
        }

        rows, libraries = _undeployed_chart_data(
            tree, lambda path: (texts.get(path), None)
        )

        by_chart = {row["chart"]: row for row in rows}
        self.assertEqual(sorted(by_chart), ["commented-chart", "orphan-chart"])
        self.assertEqual(
            by_chart["commented-chart"]["commented_out_in"],
            ["applicationsets/templates/managed/example.yaml"],
        )
        self.assertEqual(
            by_chart["orphan-chart"]["values_files"],
            ["values/hub/local-cluster/orphan-chart.yaml"],
        )
        self.assertEqual(libraries, ("library-chart",))
        deployed = 3
        self.assertEqual(deployed + len(libraries) + len(rows), 6)

    def test_summary_json_carries_undeployed_and_library_charts(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ChartsFakeGitHubClient(),
            ["charts", "bu-ist-demo", "--format", "json"],
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(document["undeployed_charts"], [])
        self.assertEqual(document["library_charts"], [])

    def test_unrecognized_managed_application_set_makes_chart_values_unknown(
        self,
    ) -> None:
        class SurpriseManagedClient(ChartsFakeGitHubClient):
            path = "applicationsets/templates/managed/surprise.yaml"

            def get_tree(self, repository: str, ref: str = "main"):
                tree = super().get_tree(repository, ref)
                if repository == "CCI-MOC/oac-apps":
                    tree[self.path] = {"path": self.path}
                return tree

            def get_file(self, repository: str, path: str, ref: str = "main") -> str:
                if repository == "CCI-MOC/oac-apps" and path == self.path:
                    return "apiVersion: v1\nkind: ConfigMap\n"
                return super().get_file(repository, path, ref)

        report = StatusChecker(
            SurpriseManagedClient(), include_prs=False
        ).run(Environment(name="bu-ist-demo", issue_number=666)).to_dict()
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "workload.feature_chart_values"
        )

        self.assertEqual(check["state"], "unknown")
        self.assertIn("surprise.yaml", check["reason"])


if __name__ == "__main__":
    unittest.main()
