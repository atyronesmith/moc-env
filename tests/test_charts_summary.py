"""Summary attribution uses actual per-cluster chart sets, with invented data."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from fakes import FakeGitHubClient
from moc_env.charts import (
    ChartCluster,
    ChartInventory,
    _summary_cell,
    _summary_tables,
    collect_chart_inventory,
    render_chart_inventory,
)


def managed_template(charts: tuple[str, ...], gate: str | None = None) -> str:
    marker = (
        '                - git:\n                    files:\n'
        f'                        - path: "{gate}"\n'
        if gate else ""
    )
    return (
        "spec:\n    generators:\n        - matrix:\n            generators:\n"
        + marker
        + "                - clusterDecisionResource:\n"
        "                    labelSelector:\n                        matchLabels:\n"
        "                            cluster.open-cluster-management.io/placement: all-managed-clusters\n"
        "                - list:\n                    elements:\n"
        + "".join(f"                        - component: {chart}\n" for chart in charts)
    )


class SummaryClient(FakeGitHubClient):
    """Two hubs share a baseline; just one hub enables an extra chart set."""

    FILES = {
        "applicationsets/templates/managed/base-set.yaml": managed_template(("a", "b")),
        "applicationsets/templates/managed/extra-set.yaml": managed_template(
            ("c", "d"), "flags/{{ $hub }}/enabled.yaml"
        ),
        "flags/beta-infra/enabled.yaml": "{}",
        **{
            f"values/{hub}-infra/local-cluster/acm-placements.yaml": "placements: []"
            for hub in ("alpha", "beta")
        },
        **{
            f"hosted-clusters/{hub}-infra/{hub}-worker/values.yaml": "clusterLabels: {}"
            for hub in ("alpha", "beta")
        },
    }

    def get_tree(self, repository: str, ref: str = "main"):
        return {path: {"path": path} for path in self.FILES}

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        return self.FILES[path]


def assert_attribution(test: unittest.TestCase, inventory: ChartInventory) -> None:
    """Reconstruct each workload's attributed union from the displayed tables."""

    tables = {table.name: table for table in _summary_tables(inventory)}
    workload_table = tables["Workload clusters"]
    features = {}
    for column, cell in tables["Workload features"].rows:
        common = set()
        extras = {}
        for section in _summary_cell(cell).split("; "):
            if section.startswith("also on "):
                cluster, charts = section[len("also on "):].split(": ", 1)
                extras[cluster] = set(charts.split(", "))
            elif section:
                common.update(section.split(", "))
        features[column] = common, extras
    by_name = {cluster.name: cluster for cluster in inventory.clusters if cluster.kind == "workload"}
    for row in workload_table.rows:
        attributed = set()
        for column, marked in zip(workload_table.columns[1:-1], row[1:-1]):
            if marked:
                common, extras = features[column]
                attributed.update(common | extras.get(row[0], set()))
        with test.subTest(cluster=row[0]):
            test.assertEqual(attributed, {item["chart"] for item in by_name[row[0]].rows})
            test.assertEqual(row[-1], len(attributed))


class ChartsSummaryTest(unittest.TestCase):
    def inventory(self) -> ChartInventory:
        return collect_chart_inventory(SummaryClient())

    def test_gated_sets_do_not_expand_the_shared_baseline(self) -> None:
        inventory = self.inventory()
        self.assertEqual(inventory.gated_application_sets, ("extra-set",))
        tables = {table.name: table for table in _summary_tables(inventory)}
        self.assertEqual(
            tables["Workload clusters"].columns,
            ("", "baseline", "extra-set", "Charts"),
        )
        self.assertEqual(tables["Workload clusters"].rows, (
            ("alpha-worker", "x", "", 2),
            ("beta-worker", "x", "x", 4),
        ))
        self.assertEqual(tables["Workload features"].rows, (
            ("baseline", ("a", "b")),
            ("extra-set", ("c", "d")),
        ))
        assert_attribution(self, inventory)

    def test_gate_metadata_uses_any_entry_and_sorted_unique_names(self) -> None:
        class MultipleEntriesClient(SummaryClient):
            FILES = {
                **SummaryClient.FILES,
                "applicationsets/templates/managed/extra-set.yaml": (
                    managed_template(("c",))
                    + managed_template(("d",), "flags/{{ $hub }}/enabled.yaml").split("    generators:\n", 1)[1]
                ),
                "applicationsets/templates/managed/another-set.yaml": managed_template(
                    ("e",), "flags/{{ $hub }}/absent.yaml"
                ),
            }

        inventory = collect_chart_inventory(MultipleEntriesClient())
        self.assertEqual(inventory.gated_application_sets, ("another-set", "extra-set"))
        tables = {table.name: table for table in _summary_tables(inventory)}
        self.assertEqual(tables["Workload features"].rows[-1], (
            "extra-set", "c; also on beta-worker: d",
        ))
        assert_attribution(self, inventory)

    def test_different_sets_show_common_charts_and_cluster_specific_extras(self) -> None:
        inventory = self.inventory()
        beta = next(cluster for cluster in inventory.clusters if cluster.name == "beta-worker")
        inventory = replace(inventory, clusters=(*inventory.clusters, ChartCluster(
            "gamma-worker", "workload", "gamma", rows=(
                *tuple(row for row in beta.rows if row["chart"] in {"a", "b", "c"}),
                {**beta.rows[-1], "chart": "e"},
            ),
        )))
        tables = {table.name: table for table in _summary_tables(inventory)}
        self.assertEqual(tables["Workload features"].rows[-1], (
            "extra-set", "c; also on beta-worker: d; also on gamma-worker: e",
        ))
        assert_attribution(self, inventory)
        for fmt in ("text", "markdown", "json"):
            self.assertIn(
                "c; also on beta-worker: d; also on gamma-worker: e",
                render_chart_inventory(inventory, format=fmt),
            )

    def test_disjoint_sets_do_not_invent_common_charts(self) -> None:
        inventory = self.inventory()
        workloads = tuple(cluster for cluster in inventory.clusters if cluster.kind == "workload")
        inventory = replace(inventory, clusters=tuple(
            replace(cluster, rows=tuple(row for row in cluster.rows if row["chart"] == chart))
            for cluster, chart in zip(workloads, ("a", "b"))
        ))
        self.assertEqual(_summary_tables(inventory)[1].rows, (
            ("baseline", "also on alpha-worker: a; also on beta-worker: b"),
        ))
        assert_attribution(self, inventory)

    def test_all_summary_formats_have_the_same_feature_columns(self) -> None:
        inventory = self.inventory()
        columns = ("", "baseline", "extra-set", "Charts")
        document = json.loads(render_chart_inventory(inventory, format="json"))
        self.assertEqual(document["tables"]["workload_clusters"]["columns"], list(columns))
        markdown = render_chart_inventory(inventory, format="markdown")
        self.assertIn("|  | baseline | extra-set | Charts |", markdown)
        text = render_chart_inventory(inventory, format="text")
        header = text.split("Workload clusters\n", 1)[1].splitlines()[0]
        self.assertEqual(header.split(), list(columns[1:]))
        self.assertNotIn("gated_application_sets", render_chart_inventory(inventory, format="json", view="cluster"))
        for fmt in ("text", "markdown", "json"):
            self.assertEqual(
                render_chart_inventory(inventory, format=fmt, view="cluster"),
                render_chart_inventory(replace(inventory, gated_application_sets=()), format=fmt, view="cluster"),
            )

    def test_existing_summary_fixtures_have_exact_per_cluster_attribution(self) -> None:
        from test_chart_overrides import OverridesFakeGitHubClient
        from test_chart_page import ChartPageFakeGitHubClient, ReaderPageFakeGitHubClient
        from test_chart_reference import ChartReferenceCommandFake
        from test_chart_scope import ScopeFakeGitHubClient, TestOnlyScopeFakeGitHubClient
        from test_charts import ChartsFakeGitHubClient, UnreadableApplicationSetsClient

        for client_type in (
            OverridesFakeGitHubClient, ChartPageFakeGitHubClient, ReaderPageFakeGitHubClient,
            ChartReferenceCommandFake, ScopeFakeGitHubClient, TestOnlyScopeFakeGitHubClient,
            ChartsFakeGitHubClient, UnreadableApplicationSetsClient,
        ):
            for all_clusters in (False, True):
                with self.subTest(client=client_type.__name__, all_clusters=all_clusters):
                    inventory = collect_chart_inventory(client_type(), all_clusters=all_clusters)
                    assert_attribution(self, inventory)


if __name__ == "__main__":
    unittest.main()
