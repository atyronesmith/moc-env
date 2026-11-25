"""Unit coverage for feature-label to chart resolution, without network IO."""

from __future__ import annotations

import unittest

from moc_env import feature_charts
from moc_env.cross_repo import (
    _feature_chart_values_check,
    _feature_placement_check,
)


PLACEMENT = "massopen.cloud/feature-gpu"


def gpu_application_set() -> str:
    return """
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
          - component: jobset-operator
          - component: kueue-operator
          - component: nfd-operator
          - component: nvidia-gpu-operator
          - component: nvidia-maintenance-operator
          - component: nvidia-network-operator
          - component: serverless-operator
          - component: servicemesh-operator
          # component: sriov-network-operator
          - component: rhoai
"""


class ApplicationSetParsingTest(unittest.TestCase):
    def test_commented_component_is_not_a_chart(self) -> None:
        application_set = feature_charts.parse_application_set(
            gpu_application_set(), "gpu-clusters"
        )

        self.assertNotIn("sriov-network-operator", application_set.components)

    def test_gpu_placement_has_nine_charts(self) -> None:
        application_set = feature_charts.parse_application_set(
            gpu_application_set(), "gpu-clusters"
        )

        self.assertEqual(application_set.placement, "gpu-clusters")
        self.assertEqual(len(application_set.components), 9)
        self.assertNotIn("sriov-network-operator", application_set.components)


class GeneratorSelectionTest(unittest.TestCase):
    """Invented templates exercise entry boundaries, not component proximity."""

    @staticmethod
    def template(*entries: str) -> str:
        return "spec:\n  generators:\n" + "\n".join(entries) + "\n  template: {}\n"

    @staticmethod
    def entry(
        placement: str,
        components: tuple[str, ...],
        *,
        gate: bool = True,
        cluster_gate: bool = False,
        components_first: bool = False,
    ) -> str:
        selector = (
            "          - clusterDecisionResource:\n"
            "              labelSelector:\n"
            "                matchLabels:\n"
            f"                  cluster.open-cluster-management.io/placement: {placement}\n"
        )
        charts = "          - list:\n              elements:\n" + "".join(
            f"                - component: {chart}\n" for chart in components
        )
        paths = []
        if gate:
            paths.append("hosted-clusters/{{ $hub }}/enabled.yaml")
        if cluster_gate:
            paths.append("values/{{ $hub }}/{{`{{name}}`}}/accelerator.yaml")
        files = "".join(
            '          - git:\n              files:\n'
            f'                - path: "{path}"\n'
            for path in paths
        )
        return "    - matrix:\n        generators:\n" + files + (
            charts + selector if components_first else selector + charts
        )

    def rows(
        self,
        template: str,
        *,
        hub_gate: bool = True,
        cluster_file: bool = False,
        feature: bool = False,
        cluster: str = "worker-one",
    ):
        tree = {}
        if hub_gate:
            tree["hosted-clusters/hub-one/enabled.yaml"] = {}
        if cluster_file:
            tree["values/hub-one/worker-one/accelerator.yaml"] = {}
        return feature_charts.workload_chart_rows(
            tree, "hub-one", cluster,
            {"example.test/feature-special": "true"} if feature else {},
            [
                feature_charts.Placement("p-all"),
                feature_charts.Placement("p-feat", {"example.test/feature-special": "true"}),
            ],
            [feature_charts.parse_application_set(template, "extra-set")],
            lambda path: (None, None),
        )

    def test_each_generator_owns_its_placement_and_components(self) -> None:
        template = self.template(
            self.entry("p-all", ("a", "b")), self.entry("p-feat", ("c",))
        )
        self.assertEqual([row["chart"] for row in self.rows(template)], ["a", "b"])
        rows = self.rows(template, feature=True)
        self.assertEqual([row["chart"] for row in rows], ["a", "b", "c"])
        self.assertEqual(rows[-1]["placement"], "p-feat")
        self.assertTrue(all(row["application_set"] == "extra-set" for row in rows))

    def test_components_can_precede_placement(self) -> None:
        template = self.template(self.entry("p-feat", ("a", "b"), components_first=True))
        self.assertEqual(self.rows(template), [])
        self.assertEqual([row["chart"] for row in self.rows(template, feature=True)], ["a", "b"])

    def test_cluster_gate_is_independent_of_satisfied_hub_gate(self) -> None:
        template = self.template(self.entry("p-all", ("a", "b"), cluster_gate=True))
        self.assertEqual([row["chart"] for row in self.rows(template, cluster_file=True)], ["a", "b"])
        self.assertEqual(self.rows(template, cluster_file=True, cluster="worker-two"), [])
        self.assertEqual(self.rows(template), [])

    def test_missing_hub_gate_suppresses_all_entries(self) -> None:
        template = self.template(
            self.entry("p-all", ("a", "b")),
            self.entry("p-feat", ("c",), cluster_gate=True),
        )
        for cluster in ("worker-one", "worker-two"):
            self.assertEqual(
                self.rows(template, hub_gate=False, cluster_file=True, feature=True, cluster=cluster),
                [],
            )

    def test_gates_are_entry_local(self) -> None:
        template = self.template(
            self.entry("p-all", ("a",), gate=False),
            self.entry("p-all", ("b",), cluster_gate=True),
        )
        self.assertEqual([row["chart"] for row in self.rows(template)], ["a"])
        self.assertEqual([row["chart"] for row in self.rows(template, cluster_file=True)], ["a", "b"])
        self.assertEqual([row["chart"] for row in self.rows(template, hub_gate=False)], ["a"])

    def test_ungated_single_generator_preserves_existing_row_keys(self) -> None:
        template = self.template(self.entry("p-all", ("a",), gate=False))
        self.assertEqual(self.rows(template), [{
            "chart": "a", "application_set": "extra-set", "placement": "p-all",
            "feature_label": "baseline", "hub_values_file": False,
            "cluster_values_file": False, "unmet_required_values": [],
            "component": True,
        }])
        parsed = feature_charts.parse_application_set(template, "extra-set")
        self.assertEqual(parsed.placement, "p-all")
        self.assertEqual(parsed.components, ("a",))
        self.assertIsNone(parsed.gate_path)

    def test_generator_boundaries_support_different_yaml_indentation(self) -> None:
        template = self.template(
            self.entry("p-all", ("a",)), self.entry("p-feat", ("b",), cluster_gate=True)
        )
        four_space = "\n".join(
            " " * (2 * (len(line) - len(line.lstrip()))) + line.lstrip()
            for line in template.splitlines()
        )
        for text in (template, four_space):
            with self.subTest(template=text):
                parsed = feature_charts.parse_application_set(text)
                self.assertEqual(len(parsed.generator_entries), 2)
                self.assertEqual(parsed.generator_entries[1].placement, "p-feat")
                self.assertEqual(
                    parsed.generator_entries[1].cluster_gate_path,
                    "values/{{ $hub }}/{{`{{name}}`}}/accelerator.yaml",
                )
                self.assertEqual([row["chart"] for row in self.rows(text, feature=True)], ["a"])


class PlacementCheckTest(unittest.TestCase):
    def test_label_no_hub_matches_is_unused_evidence_and_passes(self) -> None:
        check = _feature_placement_check(
            "bu-ist-demo-infra",
            "bu-ist-demo-workload0",
            {PLACEMENT: "true"},
            [],
            {"bu-ist-demo-infra": []},
            "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml",
        )

        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.severity, "info")
        self.assertEqual(check.evidence["unused_labels"], [PLACEMENT])

    def test_label_matched_only_on_another_hub_is_blocking(self) -> None:
        other = feature_charts.Placement(
            name="gpu-clusters", match_labels={PLACEMENT: "true"}
        )
        check = _feature_placement_check(
            "bu-ist-demo-infra",
            "bu-ist-demo-workload0",
            {PLACEMENT: "true"},
            [],
            {"bu-ist-demo-infra": [], "oac-prod-infra": [other]},
            "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml",
        )

        self.assertEqual(check.state, "value_mismatch")
        self.assertEqual(check.severity, "blocking")
        self.assertEqual(check.evidence["unused_labels"], [])


class RequiredValueTest(unittest.TestCase):
    def test_required_inside_if_is_ignored_and_outside_is_reported(self) -> None:
        template = (
            '{{ if .Values.enabled }}{{ required "x" .Values.inside }}{{ end }}\n'
            '{{ required "y" .Values.outside }}\n'
        )

        self.assertEqual(
            feature_charts.required_value_paths(template), ["outside"]
        )

    def test_empty_default_is_satisfied_by_hub_or_cluster_values(self) -> None:
        defaults = {"backend": {"address": ""}, "network": {"cidr": ""}}
        hub_values = {"backend": {"address": "10.9.8.10"}}
        cluster_values = {"network": {"cidr": "10.9.8.0/22"}}

        merged = feature_charts.merge_value_layers(
            defaults, hub_values, cluster_values
        )

        self.assertEqual(
            feature_charts.unmet_required(
                ["backend.address", "network.cidr"], merged
            ),
            [],
        )
        self.assertEqual(
            feature_charts.unmet_required(
                ["backend.address"], feature_charts.merge_value_layers(defaults)
            ),
            ["backend.address"],
        )


class ChartValuesCheckTest(unittest.TestCase):
    def test_values_file_for_unreceived_chart_is_advisory(self) -> None:
        tree = {
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/orphan.yaml": {
                "path": "values/bu-ist-demo-infra/bu-ist-demo-workload0/orphan.yaml"
            }
        }
        application_set = feature_charts.ApplicationSet(
            name="example-clusters",
            placement="all-managed-clusters",
            components=("example",),
        )
        check = _feature_chart_values_check(
            None,
            tree,
            "bu-ist-demo-infra",
            "bu-ist-demo-workload0",
            {},
            [],
            [application_set],
            "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml",
            {},
            None,
        )

        self.assertEqual(check.state, "value_mismatch")
        self.assertEqual(check.severity, "advisory")
        self.assertEqual(check.evidence["orphan_values_files"], ["orphan"])

    def test_portworx_cluster_without_overlay_is_blocking(self) -> None:
        placements = [
            feature_charts.Placement(
                name="portworx-clusters",
                match_labels={"massopen.cloud/feature-portworx": "true"},
            )
        ]
        application_set = feature_charts.ApplicationSet(
            name="pure-cosi",
            placement="portworx-clusters",
            kustomize_path="kustomize/pure-cosi/overlays/{{`{{name}}`}}",
        )
        check = _feature_chart_values_check(
            None,
            {},
            "bu-ist-demo-infra",
            "bu-ist-demo-workload0",
            {"massopen.cloud/feature-portworx": "true"},
            placements,
            [application_set],
            "values/bu-ist-demo-infra/local-cluster/acm-placements.yaml",
            {},
            None,
        )

        self.assertEqual(check.state, "missing")
        self.assertEqual(check.severity, "blocking")
        self.assertEqual(
            check.evidence["missing_overlays"],
            ["kustomize/pure-cosi/overlays/bu-ist-demo-workload0"],
        )


if __name__ == "__main__":
    unittest.main()
