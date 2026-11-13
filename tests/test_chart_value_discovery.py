from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli
from moc_env.chart_value_discovery import (
    build_discovery_report,
    discover_chart_values,
    render_discovery_markdown,
)
from moc_env.chart_values import (
    ManualDocumentation,
    ManualEvidence,
    ManualSource,
    ManualTopic,
    ManualVariable,
)


class ChartValueDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "MOC" / "oac-apps"
        self.cache = self.root / "cache"
        self.repository.mkdir(parents=True)
        self.cache.mkdir()

        values = self.repository / "hosted-clusters" / "example-infra"
        values.mkdir(parents=True)
        (values / "values.yaml").write_text(
            "hcpExternalDomain: example.com\nnewVariable: value\n",
            encoding="utf-8",
        )
        chart = self.repository / "charts" / "example-chart"
        chart.mkdir(parents=True)
        (chart / "values.yaml").write_text(
            "exampleDefault: true\n",
            encoding="utf-8",
        )

        self.manual = ManualDocumentation(
            sources={
                "dns-design": ManualSource(
                    source_id="dns-design",
                    short_id="DNS-1",
                    title="DNS Design",
                    repository="CCI-MOC/oac-apps",
                    path="docs/dns.md",
                    ref="abc123",
                    kind="design",
                    topics=("dns",),
                    summary="DNS design.",
                )
            },
            topics=(
                ManualTopic(
                    topic="dns",
                    title="DNS",
                    overview="DNS overview.",
                    variables=(
                        ManualVariable(
                            key="hcpExternalDomain",
                            title="External domain",
                            group="Domains",
                            required=False,
                            definition="External hosted-control-plane domain.",
                            related=("hcpInternalDomain",),
                            evidence=(ManualEvidence(source="dns-design"),),
                        ),
                        ManualVariable(
                            key="manualOnlyVariable",
                            title="Manual only",
                            group="Domains",
                            required=False,
                            definition="No current occurrence.",
                        ),
                    ),
                ),
            ),
        )

        documents = self.cache / "documents"
        documents.mkdir()
        (documents / "dns-design.md").write_text(
            "# DNS design\n",
            encoding="utf-8",
        )
        (self.cache / "manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "1",
                    "sources": {
                        "dns-design": {
                            "status": "current",
                            "documentPath": "documents/dns-design.md",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_discovery_reports_new_manual_and_missing_variables(self) -> None:
        manual_before = copy.deepcopy(self.manual)
        report = build_discovery_report(
            self.manual,
            self.repository,
            self.cache,
        )

        self.assertEqual(self.manual, manual_before)
        self.assertEqual(report.manual_variable_count, 2)
        self.assertEqual(report.discovered_variable_count, 2)
        self.assertEqual(report.matched_variable_count, 1)
        self.assertEqual(
            tuple(variable.key for variable in report.new_variables),
            ("newVariable",),
        )
        self.assertEqual(
            report.manual_without_occurrence,
            ("manualOnlyVariable",),
        )
        self.assertEqual(report.changed_evidence, ())
        self.assertEqual(report.missing_evidence, ())

    def test_discovery_reports_changed_and_missing_evidence(self) -> None:
        manifest = json.loads((self.cache / "manifest.json").read_text())
        manifest["sources"]["dns-design"]["status"] = "updated"
        (self.cache / "manifest.json").write_text(json.dumps(manifest))
        report = build_discovery_report(
            self.manual,
            self.repository,
            self.cache,
        )
        self.assertEqual(report.changed_evidence, ("dns-design",))

        (self.cache / "manifest.json").unlink()
        report = build_discovery_report(
            self.manual,
            self.repository,
            self.cache,
        )
        self.assertEqual(report.missing_evidence, ("dns-design",))

    def test_discovery_reports_default_conflict(self) -> None:
        manual = ManualDocumentation(
            sources={},
            topics=(
                ManualTopic(
                    topic="example",
                    title="Example",
                    overview="Example.",
                    variables=(
                        ManualVariable(
                            key="exampleDefault",
                            title="Example default",
                            group="Example",
                            required=False,
                            definition="Example default.",
                            default=False,
                        ),
                    ),
                ),
            ),
        )
        (self.repository / "values" / "example-infra").mkdir(parents=True)
        (self.repository / "values" / "example-infra" / "example-chart.yaml").write_text(
            "exampleDefault: false\n",
            encoding="utf-8",
        )

        report = build_discovery_report(
            manual,
            self.repository,
            self.cache,
        )

        self.assertEqual(len(report.default_conflicts), 1)
        conflict = report.default_conflicts[0]
        self.assertEqual(conflict.key, "exampleDefault")
        self.assertEqual(conflict.chart, "example-chart")
        self.assertEqual(conflict.manual_default, False)
        self.assertEqual(conflict.chart_default, True)

    def test_discovery_reports_unsupported_yaml(self) -> None:
        unsupported = self.repository / "values" / "example-infra" / "unsupported.yaml"
        unsupported.parent.mkdir(parents=True, exist_ok=True)
        unsupported.write_text("- not-a-mapping\n", encoding="utf-8")

        discovered, unsupported_files = discover_chart_values(self.repository)

        self.assertIn("values/example-infra/unsupported.yaml", unsupported_files)
        self.assertNotIn("unsupported", discovered)

    def test_discovery_markdown_is_human_readable(self) -> None:
        report = build_discovery_report(
            self.manual,
            self.repository,
            self.cache,
        )
        rendered = render_discovery_markdown(report)

        self.assertIn("# 🔍 Chart Values Discovery Report", rendered)
        self.assertIn("## New variables needing definitions", rendered)
        self.assertIn("`newVariable`", rendered)
        self.assertIn("## Manual variables without current occurrences", rendered)
        self.assertIn("`manualOnlyVariable`", rendered)
        self.assertIn("## Changed evidence", rendered)
        self.assertIn("## Missing evidence", rendered)
        self.assertIn("## Default conflicts", rendered)

    def test_cli_discover_values_dispatch(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "load_chart_values_manual", return_value=self.manual),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                [
                    "discover-values",
                    "--repository-root",
                    str(self.root / "MOC"),
                    "--cache-root",
                    str(self.cache),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["manual_variable_count"], 2)
        self.assertEqual(report["discovered_variable_count"], 2)
        self.assertEqual(
            [variable["key"] for variable in report["new_variables"]],
            ["newVariable"],
        )
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
