"""Managed chart selection respects per-hub files-generator gates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from moc_env import feature_charts
from moc_env.charts import collect_chart_inventory
from moc_env.repositories import OAC_APPS_REPOSITORY
from moc_env.verify_live import LocalRepositories, verify_live


GATED_APPLICATION_SET = """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
    name: guarded-components
spec:
    generators:
        - matrix:
            generators:
                - git:
                    repoURL: https://example.invalid/config.git
                    revision: main
                    files:
                        - path: "hosted-clusters/{{ $hub }}/compliance.yaml"
                - matrix:
                    generators:
                        - clusterDecisionResource:
                            labelSelector:
                                matchLabels:
                                    cluster.open-cluster-management.io/placement: all-managed-clusters
                        - list:
                            elements:
                                - component: compliance-operator
                                - component: nfs-tls
    template:
        spec:
            source:
                path: "charts/{{`{{component}}`}}"
"""

UNGATED_APPLICATION_SET = """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
    name: baseline-components
spec:
    generators:
        - matrix:
            generators:
                - clusterDecisionResource:
                    labelSelector:
                        matchLabels:
                            cluster.open-cluster-management.io/placement: all-managed-clusters
                - list:
                    elements:
                        - component: cert-manager
    template:
        spec:
            source:
                path: "charts/{{`{{component}}`}}"
"""


class WorkloadComplianceGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repositories = self.root / "repos"
        self.apps = self.repositories / "oac-apps"
        self.write_app(
            "applicationsets/templates/managed/guarded-components.yaml",
            GATED_APPLICATION_SET,
        )
        self.write_app(
            "applicationsets/templates/managed/baseline-components.yaml",
            UNGATED_APPLICATION_SET,
        )
        for base in ("alpha", "beta"):
            hub = f"{base}-infra"
            workload = f"{base}-workload0"
            self.write_app(
                f"hosted-clusters/{hub}/{workload}/values.yaml",
                json.dumps({"clusterName": workload, "clusterLabels": {}}),
            )
            self.write_app(
                f"values/{hub}/local-cluster/acm-placements.yaml",
                json.dumps({"placements": [{"name": "all-managed-clusters"}]}),
            )
        self.write_app("hosted-clusters/beta-infra/compliance.yaml", "{}\n")
        for chart in ("compliance-operator", "nfs-tls", "cert-manager"):
            self.write_app(
                f"charts/{chart}/Chart.yaml",
                json.dumps({"apiVersion": "v2", "name": chart, "version": "0.1.0"}),
            )
            self.write_app(f"charts/{chart}/values.yaml", "{}\n")
            self.write_app(
                f"charts/{chart}/templates/config.yaml",
                "apiVersion: v1\nkind: ConfigMap\nmetadata:\n    name: example-config\n",
            )
        inventory = self.repositories / "oac-infra/infra/inventory/00hosts.yaml"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(json.dumps({"all": {"children": {
            "alpha-workload0": {
                "vars": {"cluster": "alpha-workload0"},
                "hosts": {},
            },
        }}}))
        self.client = LocalRepositories(self.repositories)
        self.tree = self.client.get_tree(OAC_APPS_REPOSITORY)
        self.placements = [feature_charts.Placement("all-managed-clusters")]
        self.application_sets, errors = feature_charts.load_application_sets(
            self.tree, self.read_app,
        )
        self.assertEqual(errors, [])

    def write_app(self, path: str, text: str) -> None:
        target = self.apps / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def read_app(self, path: str) -> tuple[str, None]:
        return self.client.get_file(OAC_APPS_REPOSITORY, path), None

    def chart_names(self, hub: str, workload: str) -> list[str]:
        return [row["chart"] for row in feature_charts.workload_chart_rows(
            self.tree, hub, workload, {}, self.placements,
            self.application_sets, self.read_app,
        )]

    def test_parser_records_only_the_gated_application_set_gate(self) -> None:
        self.assertEqual(
            feature_charts.parse_application_set(GATED_APPLICATION_SET).gate_path,
            "hosted-clusters/{{ $hub }}/compliance.yaml",
        )
        self.assertIsNone(
            feature_charts.parse_application_set(UNGATED_APPLICATION_SET).gate_path,
        )

    def test_alpha_without_marker_receives_only_ungated_charts(self) -> None:
        self.assertEqual(self.chart_names("alpha-infra", "alpha-workload0"), ["cert-manager"])

    def test_beta_with_marker_receives_both_gated_and_ungated_charts(self) -> None:
        self.assertEqual(
            self.chart_names("beta-infra", "beta-workload0"),
            ["cert-manager", "compliance-operator", "nfs-tls"],
        )

    def test_alpha_chart_inventory_has_no_compliance_rows(self) -> None:
        inventory = collect_chart_inventory(self.client, "alpha", "alpha-workload0")
        self.assertFalse(inventory.has_errors)
        self.assertEqual(len(inventory.clusters), 1)
        self.assertEqual(inventory.clusters[0].name, "alpha-workload0")
        self.assertEqual(
            [row["chart"] for row in inventory.clusters[0].rows],
            ["cert-manager"],
        )

    def test_alpha_live_verification_has_no_compliance_chart_rows(self) -> None:
        snapshot = self.root / "snapshot"
        snapshot.mkdir()
        resources = {
            key: {"kind": kind, "status": "captured", "file": f"{key}.json"}
            for key, kind in (
                ("nodes", "Node"), ("pods", "Pod"),
                ("namespaces", "Namespace"), ("configmaps", "ConfigMap"),
            )
        }
        for key in resources:
            (snapshot / f"{key}.json").write_text(json.dumps({"items": []}))
        (snapshot / "manifest.json").write_text(json.dumps({
            "schema_version": 1,
            "environment": "alpha",
            "workload": "alpha-workload0",
            "timestamp": "2026-11-01T00:00:00Z",
            "resources": resources,
        }))
        result = verify_live(self.client, "alpha", "alpha-workload0", snapshot)
        self.assertEqual(
            [row["name"] for row in result["sections"]["Charts"]],
            ["cert-manager"],
        )

    def test_ungated_application_set_preserves_the_existing_row_shape(self) -> None:
        application_set = feature_charts.parse_application_set(
            UNGATED_APPLICATION_SET, "baseline-components",
        )
        for hub in ("alpha-infra", "beta-infra"):
            with self.subTest(hub=hub):
                rows = feature_charts.workload_chart_rows(
                    {}, hub, "example-workload0", {}, self.placements,
                    [application_set], self.read_app,
                )
                self.assertEqual(rows, [{
                    "chart": "cert-manager",
                    "application_set": "baseline-components",
                    "placement": "all-managed-clusters",
                    "feature_label": "baseline",
                    "hub_values_file": False,
                    "cluster_values_file": False,
                    "unmet_required_values": [],
                    "component": True,
                }])

    def test_gate_path_is_generic_not_specific_to_compliance_markers(self) -> None:
        application_set = feature_charts.parse_application_set(
            GATED_APPLICATION_SET.replace(
                "hosted-clusters/{{ $hub }}/compliance.yaml",
                "flags/{{ $hub }}/enabled.yaml",
            ),
        )
        arguments = ("alpha-infra", "alpha-workload0", {}, self.placements)
        self.assertEqual(feature_charts.workload_chart_rows(
            self.tree, *arguments, [application_set], self.read_app,
        ), [])
        rows = feature_charts.workload_chart_rows(
            {**self.tree, "flags/alpha-infra/enabled.yaml": {}},
            *arguments, [application_set], self.read_app,
        )
        self.assertEqual([row["chart"] for row in rows], ["compliance-operator", "nfs-tls"])


if __name__ == "__main__":
    unittest.main()
