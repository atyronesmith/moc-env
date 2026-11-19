"""Offline coverage for the ``charts --view reference`` reader and view."""

from __future__ import annotations

import contextlib
import io
import json
import re
import unittest
from dataclasses import replace
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
        self.assertEqual(
            chart_reference.default_cell(values.rows[0]), "(section)"
        )

    def test_commented_out_key_block_becomes_a_row_and_example(self) -> None:
        values = chart_reference.read_values(
            """
namespace: metallb-system

# addressPools:
#   - name: default
#     addresses:
#       - 192.168.1.100-192.168.1.200
"""
        )

        row = next(row for row in values.rows if row.key == "addressPools")
        self.assertTrue(row.commented_out)
        self.assertEqual(chart_reference.default_cell(row), "(commented out)")
        self.assertIn("- name: default", row.example or "")
        self.assertEqual(values.other_comments, ())

    def test_unattached_non_key_comment_stays_in_other_comments(self) -> None:
        values = chart_reference.read_values(
            """
namespace: metallb-system

# This is a note, not a key.
"""
        )

        self.assertEqual(values.other_comments, ("This is a note, not a key.",))

    def test_conditional_required_key_carries_its_condition(self) -> None:
        unconditional, conditional, conditions = (
            chart_reference.required_value_details(
                '{{- if .Values.ingressController }}\n'
                '{{- if .Values.ingressController.enabled }}\n'
                '{{- required "domain" .Values.ingressController.domain }}\n'
                '{{- end }}\n'
                '{{- end }}\n'
            )
        )
        values = chart_reference.read_values(
            "ingressController:\n  enabled: false\n  domain: \"\"\n",
            conditional_required=conditional,
            conditions=conditions,
        )
        row = next(
            row for row in values.rows
            if row.key == "ingressController.domain"
        )

        self.assertEqual(unconditional, set())
        self.assertEqual(conditional, {"ingressController.domain"})
        self.assertEqual(row.condition, "ingressController.enabled")
        self.assertEqual(
            chart_reference.required_cell(row),
            "conditional (when ingressController.enabled)",
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

    def test_markdown_header_reproduces_the_cli_command(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["charts", "--view", "reference", "--chart", "alpha"]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "```sh\nmoc-env charts --view reference --chart alpha\n```",
            stdout,
        )
        self.assertIn(
            "Showing 1 of 4 deployed charts (filtered with --chart).",
            stdout,
        )
        self.assertIn(
            "1 of 4 deployed charts is shown; 3 deployed charts are omitted "
            "by --chart.",
            stdout,
        )

    def test_reference_view_prints_missing_description_warnings_to_stderr(
        self,
    ) -> None:
        warning = "moc-env: warning: required key has no description"
        with patch.object(
            cli,
            "missing_description_warnings",
            return_value=(warning,),
        ):
            exit_code, _, stderr = self.run_cli(
                ["charts", "--view", "reference", "--chart", "alpha"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn(warning, stderr)

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


def _synthetic_reference(
    chart_count: int = 46,
) -> chart_reference.ChartReference:
    charts = tuple(
        chart_reference.ChartEntry(
            name=f"chart-{index:02d}",
            description="",
            used_by=(),
            values=chart_reference.ValuesReference(present=False),
        )
        for index in range(chart_count)
    )
    return chart_reference.ChartReference(
        ref="main",
        sha="0" * 40,
        footer="Source: CCI-MOC/oac-apps @ main (0000000).",
        hub_always=("chart-00", "chart-01"),
        hub_gated=(),
        hub_drop_ins=("chart-02",),
        workload_creators=(
            chart_reference.ChartList(
                name="hosted-cluster",
                charts=("hosted-cluster",),
                detail="ApplicationSet hosted-clusters",
            ),
        ),
        workload_baseline=("chart-03",),
        workload_features=(
            chart_reference.ChartList(
                name="gpu",
                charts=("chart-00",),
                detail='massopen.cloud/feature-gpu: "true"',
            ),
            chart_reference.ChartList(
                name="metallb",
                charts=("chart-01", "chart-02"),
                detail='massopen.cloud/feature-metallb: "true"',
            ),
        ),
        charts=charts,
        undeployed_count=9,
        library_count=2,
    )


class ChartReferencePresentationTest(unittest.TestCase):
    def test_filtered_rules_count_blank_lines_and_heading_level(self) -> None:
        rendered = chart_reference.render_markdown(
            _synthetic_reference(), ("chart-00", "chart-01", "chart-02")
        )
        lines = rendered.splitlines()

        self.assertEqual(lines.count("---"), 6)
        for index, line in enumerate(lines):
            if line != "---":
                continue
            self.assertEqual(lines[index - 1], "")
            self.assertEqual(lines[index + 1], "")
        self.assertIn("#### Feature: gpu (1)", rendered)
        self.assertIn("#### Feature: metallb (2)", rendered)
        self.assertNotIn("\n### Feature:", rendered)
        self.assertLess(
            rendered.index("### Baseline"), rendered.index("### Optional features")
        )

    def test_unfiltered_rules_count(self) -> None:
        rendered = chart_reference.render_markdown(_synthetic_reference())

        self.assertEqual(rendered.splitlines().count("---"), 49)

    def test_generated_by_line_uses_normalized_quoted_command(self) -> None:
        rendered = chart_reference.render_markdown(
            _synthetic_reference(),
            ("chart-00",),
            (
                "charts",
                "--view",
                "reference",
                "--chart",
                "chart-00",
                "--output",
                "reports/chart reference.md",
            ),
        )

        self.assertIn("Generated by:\n\n```sh\n", rendered)
        self.assertIn(
            "moc-env charts --view reference --chart chart-00 --output "
            "'reports/chart reference.md'",
            rendered,
        )

    def test_filtered_and_unfiltered_intro_and_footer(self) -> None:
        filtered = chart_reference.render_markdown(
            _synthetic_reference(), ("chart-00", "chart-01", "chart-02")
        )
        unfiltered = chart_reference.render_markdown(_synthetic_reference())

        self.assertIn(
            "Showing 3 of 46 deployed charts (filtered with --chart).",
            filtered,
        )
        self.assertIn(
            "3 of 46 deployed charts are shown; 43 deployed charts are "
            "omitted by --chart.",
            filtered,
        )
        self.assertIn(
            "One entry per deployed chart, in name order.", unfiltered
        )
        self.assertNotIn("omitted by --chart", unfiltered)

    def test_hub_arrow_and_drop_in_notes_explain_the_mechanisms(self) -> None:
        rendered = chart_reference.render_markdown(_synthetic_reference())

        self.assertIn(
            'Each line reads "ApplicationSet -> chart names"',
            rendered,
        )
        self.assertIn(
            "A drop-in is an Application manifest checked in under "
            "`apps/<hub>/`.",
            rendered,
        )
        self.assertIn(
            'The defaults "(section)" and "(commented out)"', rendered
        )

    def test_missing_description_warnings_are_grouped_by_chart(self) -> None:
        entry = chart_reference.ChartEntry(
            name="demo",
            description="",
            used_by=(),
            values=chart_reference.ValuesReference(
                present=True,
                rows=(
                    chart_reference.ValueRow(
                        key="plain", default="", required="yes"
                    ),
                    chart_reference.ValueRow(
                        key="gated",
                        default="",
                        required="conditional",
                        condition="enabled",
                    ),
                    chart_reference.ValueRow(
                        key="documented",
                        default="",
                        required="yes",
                        description="Explained.",
                    ),
                ),
            ),
        )
        reference = replace(_synthetic_reference(1), charts=(entry,))

        warnings = chart_reference.missing_description_warnings(
            reference, ("demo",)
        )

        self.assertEqual(
            warnings,
            (
                "moc-env: warning: required or conditional keys without a "
                "description in values.yaml:",
                "  demo:",
                "    - plain (yes)",
                "    - gated (conditional (when enabled))",
            ),
        )

    def test_section_and_commented_out_defaults_render_in_tables(self) -> None:
        values = chart_reference.read_values(
            """
# Metrics settings.
metricsSet:
  enabled: true

# addressPools:
#   - name: default
#     addresses:
#       - 192.168.1.100-192.168.1.200
"""
        )
        entry = chart_reference.ChartEntry(
            name="demo",
            description="",
            used_by=(),
            values=values,
        )
        reference = replace(_synthetic_reference(1), charts=(entry,))
        rendered = chart_reference.render_markdown(reference)

        self.assertIn("| `metricsSet` | `(section)` |  | Metrics settings. |", rendered)
        self.assertIn(
            "| `addressPools` | `(commented out)` |  |  |", rendered
        )
        self.assertIn("Example for `addressPools`:", rendered)
        self.assertNotIn("Other comments in values.yaml:", rendered)

    def test_text_rules_are_eighty_characters(self) -> None:
        rendered = chart_reference.render_text(
            _synthetic_reference(), ("chart-00", "chart-01", "chart-02")
        )
        rules = [line for line in rendered.splitlines() if line == "─" * 80]

        self.assertEqual(len(rules), 6)

    def test_verbatim_guidance_appears_once(self) -> None:
        rendered = chart_reference.render_markdown(_synthetic_reference())
        texts = (
            "This document is generated from the oac-apps repository. It "
            "describes the two kinds of cluster the repository can deploy, "
            "the charts each kind receives, and the values each chart "
            "accepts. It describes what the repository declares, not what is "
            "running on any cluster.",
            "A hub is the management cluster. Every hub receives the same "
            "fixed set of charts. The only differences between hubs are the "
            "compliance charts and the drop-ins listed below.",
            "A feature is an optional group of charts. A workload cluster "
            "receives a\nfeature's charts only when its\n"
            "`hosted-clusters/<hub>/<cluster>/values.yaml` sets that feature's "
            "label\nunder `clusterLabels`. Every feature the repository "
            "defines is listed,\nincluding features no cluster uses today.",
            "Every workload cluster receives these charts. No label is needed.",
            "One entry per deployed chart, in name order. Each table lists "
            "the keys in the chart's own values.yaml.",
        )
        for text in texts:
            self.assertEqual(rendered.count(text), 1, text)

        feature_items = (
            "- Heading: the feature's name and, in parentheses, how many "
            "charts it installs.",
            "- Label: the exact line to add under `clusterLabels` to turn the "
            "feature on.",
            "- List: the charts installed on the cluster when the label is "
            'set. A chart\'s name can differ from the feature\'s name.',
        )
        for item in feature_items:
            self.assertEqual(rendered.count(item), 1, item)

        chart_items = (
            "- Key: the setting's path, written with dots.",
            "- Default: the value used when no values file overrides it.",
            '- Required: "yes" means the chart fails to render without it. '
            '"conditional" means it is required only when a related option is on.',
            "- Description: the comment written beside the key in values.yaml. "
            "Blank means the chart has no comment for that key.",
        )
        for item in chart_items:
            self.assertEqual(rendered.count(item), 1, item)

    def test_markdown_escapes_repository_text_and_code_spans_values(self) -> None:
        entry = chart_reference.ChartEntry(
            name="demo",
            description="Uses <hub> & <cluster>.",
            used_by=(),
            values=chart_reference.ValuesReference(
                present=True,
                rows=(
                    chart_reference.ValueRow(
                        key="angle",
                        default="<hub>",
                        description="Path values/<hub>/<chart>.yaml & more",
                    ),
                    chart_reference.ValueRow(key="backtick", default="a`b"),
                    chart_reference.ValueRow(key="pipe", default="a|b"),
                    chart_reference.ValueRow(
                        key="empty", default="", has_default=False
                    ),
                ),
            ),
        )
        reference = replace(_synthetic_reference(1), charts=(entry,))
        rendered = chart_reference.render_markdown(reference)

        self.assertIn("Uses &lt;hub&gt; &amp; &lt;cluster&gt;.", rendered)
        self.assertIn(
            '| `angle` | `"<hub>"` |  | '
            "Path values/&lt;hub&gt;/&lt;chart&gt;.yaml &amp; more |",
            rendered,
        )
        self.assertIn('| `backtick` | `` "a`b" `` |  |  |', rendered)
        self.assertIn('| `pipe` | `"a\\|b"` |  |  |', rendered)
        self.assertIn("| `empty` |  |  |  |", rendered)

        without_fences = re.sub(r"```.*?```", "", rendered, flags=re.DOTALL)
        without_code = re.sub(
            r"``.*?``|`[^`\n]*`", "", without_fences, flags=re.DOTALL
        )
        self.assertIsNone(re.search(r"<[A-Za-z]", without_code))

    def test_markdown_code_spans_marker_paths(self) -> None:
        marker = "hosted-clusters/<hub>/compliance.yaml"
        reference = replace(
            _synthetic_reference(1),
            hub_gated=(
                chart_reference.ChartList(
                    name="compliance", charts=("chart-00",), detail=marker
                ),
            ),
            workload_creators=(
                chart_reference.ChartList(
                    name="hosted-cluster-compliance",
                    charts=("hosted-cluster-compliance",),
                    detail=(
                        "ApplicationSet hosted-cluster-compliance; applies on "
                        f"compliant hubs (marker {marker})"
                    ),
                ),
            ),
        )
        rendered = chart_reference.render_markdown(reference)

        self.assertIn(
            "- compliance -> [chart-00](#chart-00) (marker `" + marker + "`)",
            rendered,
        )
        self.assertIn(
            "applies on compliant hubs (marker `" + marker + "`)", rendered
        )


if __name__ == "__main__":
    unittest.main()
