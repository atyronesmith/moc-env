"""End-to-end NEXT text for workload.feature_chart_values."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from unittest.mock import patch

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.report import render_text

from test_charts import ChartsFakeGitHubClient

WORKLOAD = "bu-ist-demo-workload0"
CHECK_ID = "workload.feature_chart_values"
TEMPLATE = "charts/gamma/templates/deployment.yaml"
ORPHAN = "values/bu-ist-demo-infra/bu-ist-demo-workload0/epsilon.yaml"
KUSTOMIZE = "applicationsets/templates/managed/pure-cosi.yaml"

TEMPLATE_TEXT = """
spec:
  template:
    spec:
      containers:
        - env:
            - name: BACKEND
              value: {{ required "backend address" .Values.backend.address }}
"""
KUSTOMIZE_TEXT = """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: pure-cosi
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: gpu-clusters
  template:
    spec:
      source:
        path: "kustomize/pure-cosi/overlays/{{`{{name}}`}}"
"""


class FeatureChartsClient(ChartsFakeGitHubClient):
    """Add the chart template, orphan values file or overlay under test."""

    FILES: dict[str, str] = {}

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update({path: {"path": path} for path in self.FILES})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps" and path in self.FILES:
            return self.FILES[path]
        return super().get_file(repository, path, ref)


class TemplateOnlyClient(FeatureChartsClient):
    FILES = {TEMPLATE: TEMPLATE_TEXT}


class OrphanOnlyClient(FeatureChartsClient):
    FILES = {ORPHAN: "{}\n"}


class TemplateAndOrphanClient(FeatureChartsClient):
    FILES = {TEMPLATE: TEMPLATE_TEXT, ORPHAN: "{}\n"}


class TemplateAndKustomizeClient(FeatureChartsClient):
    FILES = {TEMPLATE: TEMPLATE_TEXT, KUSTOMIZE: KUSTOMIZE_TEXT}


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class FeatureChartValuesNextTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(
            os.environ, {"MOC_ENV_CACHE_DIR": temporary.name}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def run_status(self, client: ChartsFakeGitHubClient) -> tuple[dict, str]:
        report = StatusChecker(client, include_prs=False).run(
            Environment(name="bu-ist-demo", issue_number=666)
        )
        data = report.to_dict()
        return data, render_text(data)

    def check(self, report: dict) -> dict:
        return next(
            check
            for check in report["checks"]
            if check["id"] == CHECK_ID and check["cluster"] == WORKLOAD
        )

    def next_section(self, text: str) -> str:
        section = text.split("\nNEXT\n", 1)[1]
        return collapse(section.split("\nNOT CHECKED", 1)[0])

    def assert_result(self, text: str, result: str) -> None:
        self.assertEqual(
            next(line for line in text.splitlines() if line.startswith("RESULT:")),
            "RESULT: " + result,
        )

    def test_unmodified_fixture_passes_without_next_item(self) -> None:
        report, text = self.run_status(FeatureChartsClient())
        check = self.check(report)

        self.assertEqual(check["state"], "declared_in_main")
        self.assertEqual(check["severity"], "info")
        self.assert_result(
            text, "3 blocking gaps (workload 0) · 3 advisories · 27 of 33 checks pass"
        )
        section = self.next_section(text)
        self.assertNotIn("Set the missing required chart values", section)
        self.assertNotIn("add the kustomize overlay", section)
        self.assertNotIn(
            "Remove the values files for charts the cluster does not receive",
            section,
        )

    def test_template_only_names_the_missing_values_file(self) -> None:
        report, text = self.run_status(TemplateOnlyClient())
        check = self.check(report)

        self.assertEqual(check["state"], "missing")
        self.assertEqual(check["severity"], "blocking")
        self.assert_result(
            text, "4 blocking gaps (workload 1) · 3 advisories · 26 of 33 checks pass"
        )
        section = self.next_section(text)
        self.assertIn(
            "bu-ist-demo-workload0: Set the missing required chart values in "
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/gamma.yaml. "
            "unmet required values is gamma backend.address; expected none.",
            section,
        )
        self.assertNotIn("charts received", section)
        self.assertNotIn("kustomize overlay", section)
        self.assertNotIn("orphan", section)

    def test_orphan_only_is_an_advisory(self) -> None:
        report, text = self.run_status(OrphanOnlyClient())
        check = self.check(report)

        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "advisory")
        self.assert_result(
            text, "3 blocking gaps (workload 0) · 4 advisories · 26 of 33 checks pass"
        )
        section = self.next_section(text)
        self.assertIn(
            "bu-ist-demo-workload0: Remove the values files for charts the cluster "
            "does not receive. (advisory) orphan values files is epsilon; "
            "expected none.",
            section,
        )
        self.assertNotIn("Set the missing", section)
        self.assertNotIn("kustomize overlay", section)

    def test_template_and_orphan_join_both_clauses(self) -> None:
        report, text = self.run_status(TemplateAndOrphanClient())
        check = self.check(report)

        self.assertEqual(check["state"], "missing")
        self.assertEqual(check["severity"], "blocking")
        self.assert_result(
            text, "4 blocking gaps (workload 1) · 3 advisories · 26 of 33 checks pass"
        )
        self.assertIn(
            "bu-ist-demo-workload0: Set the missing required chart values in "
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/gamma.yaml and "
            "remove the values files for charts the cluster does not receive. "
            "unmet required values is gamma backend.address; expected none. "
            "orphan values files is epsilon; expected none.",
            self.next_section(text),
        )

    def test_template_and_kustomize_join_both_clauses(self) -> None:
        report, text = self.run_status(TemplateAndKustomizeClient())
        check = self.check(report)

        self.assertEqual(check["state"], "missing")
        self.assertEqual(check["severity"], "blocking")
        self.assert_result(
            text, "4 blocking gaps (workload 1) · 3 advisories · 26 of 33 checks pass"
        )
        self.assertIn(
            "bu-ist-demo-workload0: Set the missing required chart values in "
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/gamma.yaml and add "
            "the kustomize overlay. unmet required values is gamma "
            "backend.address; expected none. missing kustomize overlays is "
            "kustomize/pure-cosi/overlays/bu-ist-demo-workload0; expected none.",
            self.next_section(text),
        )


if __name__ == "__main__":
    unittest.main()
