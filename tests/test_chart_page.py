"""Offline acceptance tests for ``moc-env charts --view page``."""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fakes import FakeGitHubClient
from moc_env import chart_page, chart_reference, cli
from moc_env.chart_page import heading_id, render_chart_page
from moc_env.chart_reference import ChartEntry, ChartList, ValueRow, ValuesReference
from moc_env.charts import collect_chart_inventory

FIXTURE_EMAIL = "ops" + "@" + "example.com"


class ChartPageFakeGitHubClient(FakeGitHubClient):
    """One hub, one workload, a feature placement, and a hub drop-in."""

    TREE = {
        "applicationsets/templates/hub/hub-components.yaml",
        "applicationsets/templates/managed/workload-components.yaml",
        "applicationsets/templates/managed/gpu-clusters.yaml",
        "values/demo-infra/local-cluster/acm-placements.yaml",
        "apps/demo-infra/keycloak-oauth.yaml",
        "values/demo-infra/alpha.yaml",
        "values/demo-infra/keycloak-oauth.yaml",
        "values/demo-infra/local-cluster/keycloak-oauth.yaml",
        "values/demo-infra/demo-workload0/alpha.yaml",
        "values/demo-infra/demo-workload0/beta.yaml",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml",
        "charts/alpha/Chart.yaml",
        "charts/alpha/values.yaml",
        "charts/beta/Chart.yaml",
        "charts/beta/values.yaml",
        "charts/keycloak-oauth/Chart.yaml",
        "charts/keycloak-oauth/values.yaml",
    }

    ALPHA_DEFAULTS = """
contact: none
docs: none
flag: none
piped: none
quoted: "false"
replicas: 1
tick: none
templated: default
"""
    ALPHA_LAYER = """
contact: __CONTACT__
docs: https://example.com/docs
flag: --flag
piped: left|right
quoted: "true"
replicas: 3
tick: "tick`mark"
""".replace("__CONTACT__", FIXTURE_EMAIL)

    def __init__(self, *, templated: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.templated = templated

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update({path: {"path": path} for path in self.TREE})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository != "CCI-MOC/oac-apps":
            return super().get_file(repository, path, ref)
        if path == "values/demo-infra/alpha.yaml":
            layer = self.ALPHA_LAYER
            if self.templated:
                layer += 'templated: "{{ .Values.x }}"\n'
            return layer
        return self.FILES.get(path, "{}\n")

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
  template:
    spec:
      source:
        path: "charts/{{component}}"
        helm:
          valueFiles:
            - "/values/{{ $hub }}/{{`{{component}}`}}.yaml"
            - "/values/{{ $hub }}/local-cluster/{{`{{component}}`}}.yaml"
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
  template:
    metadata:
      annotations:
        cluster.open-cluster-management.io/placement: all-managed-clusters
    spec:
      source:
        path: "charts/{{component}}"
        helm:
          valueFiles:
            - "/values/{{ $hub }}/{{`{{component}}`}}.yaml"
            - "/values/{{ $hub }}/{{`{{name}}`}}/{{`{{component}}`}}.yaml"
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
          - component: beta
  template:
    metadata:
      annotations:
        cluster.open-cluster-management.io/placement: gpu-clusters
    spec:
      source:
        path: "charts/{{component}}"
        helm:
          valueFiles:
            - "/values/{{ $hub }}/{{`{{component}}`}}.yaml"
            - "/values/{{ $hub }}/{{`{{name}}`}}/{{`{{component}}`}}.yaml"
""",
        "values/demo-infra/local-cluster/acm-placements.yaml": """
placements:
  - name: all-managed-clusters
    matchLabels: {}
  - name: gpu-clusters
    matchLabels:
      massopen.cloud/feature-gpu: "true"
""",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml": """
clusterName: demo-workload0
clusterLabels:
  massopen.cloud/feature-gpu: "true"
""",
        "apps/demo-infra/keycloak-oauth.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: hub-keycloak-oauth
spec:
  source:
    path: charts/keycloak-oauth
    helm:
      valueFiles:
        - /values/demo-infra/keycloak-oauth.yaml
        - /values/demo-infra/local-cluster/keycloak-oauth.yaml
""",
        "values/demo-infra/keycloak-oauth.yaml": "mode: custom\n",
        "values/demo-infra/local-cluster/keycloak-oauth.yaml": "mode: custom\n",
        "values/demo-infra/demo-workload0/alpha.yaml": "replicas: 4\n",
        "values/demo-infra/demo-workload0/beta.yaml": "replicas: 5\n",
        "charts/alpha/Chart.yaml": (
            f"description: Alpha chart for {FIXTURE_EMAIL} and "
            "https://example.com/alpha\n"
        ),
        "charts/alpha/values.yaml": ALPHA_DEFAULTS,
        "charts/beta/Chart.yaml": "description: Beta chart\n",
        "charts/beta/values.yaml": "replicas: 1\n",
        "charts/keycloak-oauth/Chart.yaml": "description: Keycloak OAuth\n",
        "charts/keycloak-oauth/values.yaml": "mode: default\n",
    }


class ReaderPageFakeGitHubClient(ChartPageFakeGitHubClient):
    """A deployment environment, hidden test environment, and excluded charts."""

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {
                path.replace("demo-", "oac-demo-") for path in self.TREE
            } | {
                "charts/unused/Chart.yaml",
                "charts/namespace-guardrails/Chart.yaml",
                "charts/operator-library/Chart.yaml",
            }
            tree.update({path: {"path": path} for path in paths})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            if path == "charts/alpha/Chart.yaml":
                return super().get_file(repository, path, ref) + (
                    "dependencies:\n"
                    "  - name: namespace-guardrails\n"
                    "    repository: file://../namespace-guardrails\n"
                    "  - name: operator-library\n"
                    "    repository: file://../operator-library\n"
                )
            if path in {
                "charts/namespace-guardrails/Chart.yaml",
                "charts/operator-library/Chart.yaml",
            }:
                return "type: library\n"
            if path == "charts/unused/Chart.yaml":
                return "description: Not deployed\n"
            if "oac-demo-" in path:
                return super().get_file(
                    repository, path.replace("oac-demo-", "demo-"), ref
                ).replace("demo-", "oac-demo-")
        return super().get_file(repository, path, ref)


def _usage_inventory():
    """Exercise every usage kind, including groups absent from the tables."""

    inventory = collect_chart_inventory(
        ChartPageFakeGitHubClient(), "demo", include_reference=True
    )
    reference = inventory.reference
    assert reference is not None
    extra_names = ("compliance", "hidden-drop-in", "creator", "unused-feature")
    reference = replace(
        reference,
        hub_gated=(ChartList("hub-components-compliance", ("compliance",)),),
        hub_drop_ins=(*reference.hub_drop_ins, "hidden-drop-in"),
        workload_creators=(ChartList("creator", ("creator",)),),
        workload_features=(
            *reference.workload_features,
            ChartList("connectivity-link", ("unused-feature",)),
            ChartList("github-oauth", ("keycloak-oauth",)),
        ),
        charts=(
            *reference.charts,
            *(ChartEntry(name, "", (), ValuesReference(False)) for name in extra_names),
        ),
    )
    return replace(inventory, reference=reference)


def _run_cli(client, arguments):
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


def _page(client=None):
    exit_code, stdout, stderr = _run_cli(
        client or ChartPageFakeGitHubClient(),
        ["charts", "demo", "--view", "page"],
    )
    assert exit_code == 0, stderr
    return stdout


def _headings(page):
    headings = []
    in_fence = False
    for line in page.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6}) +(.+)$", line)
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


def _section(page, heading):
    lines = page.splitlines()
    start = lines.index(heading)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^#{1,3} ", lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def _split_row(line):
    body = line.strip()
    assert body.startswith("|") and body.endswith("|")
    body = body[1:-1]
    cells = []
    current = []
    index = 0
    while index < len(body):
        if body[index] == "\\" and index + 1 < len(body) and body[index + 1] == "|":
            current.append("\\|")
            index += 2
        elif body[index] == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
        else:
            current.append(body[index])
            index += 1
    cells.append("".join(current).strip())
    return cells


def _table_rows(section):
    rows = []
    in_table = False
    for line in section.splitlines():
        if line.startswith("| Chart | Key |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            rows.append(_split_row(line))
        elif in_table and not line.startswith("|"):
            break
    return rows


def _code_content(cell):
    if cell.startswith("`` ") and cell.endswith(" ``"):
        return cell[3:-3]
    if cell.startswith("`") and cell.endswith("`"):
        return cell[1:-1]
    return None


def _outside_code_and_links(page):
    text = re.sub(r"```.*?```", "", page, flags=re.DOTALL)
    text = re.sub(r"(`+)(.*?)\1", "", text, flags=re.DOTALL)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)
    return text


def _generated_prose(inventory):
    """Collect builder prose at its source, without rendering upstream text."""

    reference = inventory.reference
    assert reference is not None
    rendered = {entry.name for entry in reference.charts}
    with (
        patch.object(chart_page, "_markdown_table", return_value=[]),
        patch.object(chart_reference, "chart_entries_markdown", return_value=[]),
    ):
        lines = [
            chart_page._source_line(inventory.sha),
            *chart_page._summary_section(inventory, rendered),
            *chart_page._values_section(inventory, rendered),
            *chart_page._reference_section(inventory),
            *chart_page._coverage_section(inventory),
        ]
    lines.extend(
        "Used by: " + "; ".join(entry.used_by)
        for entry in chart_page._page_chart_entries(inventory, reference)
        if entry.used_by
    )
    return lines


class ChartPageTest(unittest.TestCase):
    def test_used_by_uses_page_table_names_and_preserves_multiple_uses(self) -> None:
        page = render_chart_page(_usage_inventory())
        suffix = " (no cluster on this page uses it)"
        expected = {
            "alpha": "Hub group: hub charts; Workload feature: baseline",
            "beta": "Workload feature: gpu",
            "keycloak-oauth": "Hub group: keycloak-oauth; "
            "Workload feature: github-oauth" + suffix,
            "compliance": "Hub group: hub-components-compliance" + suffix,
            "hidden-drop-in": "Hub group: hidden-drop-in" + suffix,
            "creator": "Hub, once for each workload cluster",
            "unused-feature": "Workload feature: connectivity-link" + suffix,
        }
        self.assertEqual(page.count("\nUsed by: "), len(expected))
        for chart, usage in expected.items():
            self.assertIn("\nUsed by: " + usage + "\n", _section(page, f"### {chart}"))
        self.assertNotRegex(page, r"(?m)^Used by: (Hub|Workload) cluster")

    def test_each_usage_is_in_its_page_table_or_marked_unused(self) -> None:
        page = render_chart_page(_usage_inventory())
        names = {
            kind: {
                _split_row(line)[0]
                for line in _section(page, "### " + table).splitlines()[4:]
                if line.startswith("|")
            }
            for kind, table in (
                ("Hub group", "Hub groups"),
                ("Workload feature", "Workload features"),
            )
        }
        for line in page.splitlines():
            if not line.startswith("Used by: "):
                continue
            for usage in line.removeprefix("Used by: ").split("; "):
                if usage == "Hub, once for each workload cluster":
                    continue
                kind, name = usage.split(": ", 1)
                self.assertIn(kind, names)
                if not name.endswith(" (no cluster on this page uses it)"):
                    self.assertIn(name, names[kind])

    def test_absent_hub_and_baseline_groups_are_marked_unused(self) -> None:
        inventory = _usage_inventory()
        page = render_chart_page(replace(inventory, clusters=()))
        self.assertIn(
            "Used by: Hub group: hub charts (no cluster on this page uses it); "
            "Workload feature: baseline (no cluster on this page uses it)",
            page,
        )

    def test_used_compliance_group_has_no_unused_suffix(self) -> None:
        inventory = _usage_inventory()
        hub = inventory.clusters[0]
        hub = replace(hub, rows=(*hub.rows, {
            "chart": "compliance",
            "application_set": "hub-components-compliance",
            "feature_label": "hub",
        }))
        page = render_chart_page(
            replace(inventory, clusters=(hub, *inventory.clusters[1:]))
        )
        self.assertIn(
            "\nUsed by: Hub group: hub-components-compliance\n",
            _section(page, "### compliance"),
        )

    def test_rendering_page_does_not_mutate_shared_reference(self) -> None:
        inventory = _usage_inventory()
        before = repr(inventory)
        render_chart_page(inventory)
        self.assertEqual(repr(inventory), before)

    def test_undeployed_and_library_notes_follow_the_undeployed_table(self) -> None:
        page = _page(ReaderPageFakeGitHubClient())
        section = _section(page, "### Charts not deployed by GitOps")
        self.assertEqual(
            section.rstrip().split("\n\n")[2:],
            [
                "No ApplicationSet or drop-in installs these charts yet.",
                "Library charts (dependencies only): namespace-guardrails, operator-library",
            ],
        )
        self.assertIn("| unused |", section)
        self.assertEqual(page.count("No ApplicationSet or drop-in"), 1)
        reference = page.split("## Chart values reference\n", 1)[1]
        for name in ("unused", "namespace-guardrails", "operator-library"):
            self.assertNotIn(f"### {name}\n", reference)

    def test_closing_paragraphs_default_and_all_clusters(self) -> None:
        first = (
            "This page does not cover: Helm parameters set inside an ApplicationSet, "
            "defaults that come from a chart dependency, kustomize applications, "
            "and the values of the hosted-cluster chart."
        )
        last = (
            "Charts that no cluster receives (1 not deployed, 2 library) "
            "have no entry under Chart values reference."
        )
        for options, middle in (
            ([], ["Test clusters are not shown: demo-infra, demo-workload0."]),
            (["--all-clusters"], []),
        ):
            with self.subTest(options=options):
                code, page, stderr = _run_cli(
                    ReaderPageFakeGitHubClient(),
                    ["charts", "--view", "page", *options],
                )
                self.assertEqual(code, 0, stderr)
                self.assertEqual(
                    _section(page, "## What this page does not cover").split("\n\n"),
                    ["## What this page does not cover", first, *middle, last],
                )

    def test_closing_omits_chart_note_only_when_both_counts_are_zero(self) -> None:
        inventory = _usage_inventory()
        for undeployed, libraries in (
            ((), ()),
            (({"chart": "unused", "values_files": (), "commented_out_in": ()},), ()),
            ((), ("operator-library",)),
        ):
            with self.subTest(undeployed=undeployed, libraries=libraries):
                page = render_chart_page(replace(
                    inventory, undeployed_charts=undeployed, library_charts=libraries
                ))
                paragraphs = _section(
                    page, "## What this page does not cover"
                ).split("\n\n")[1:]
                self.assertEqual(len(paragraphs), 2 if undeployed or libraries else 1)
                self.assertNotIn("Test clusters are not shown:", page)
                if undeployed or libraries:
                    self.assertEqual(
                        paragraphs[-1],
                        f"Charts that no cluster receives ({len(undeployed)} not deployed, "
                        f"{len(libraries)} library) have no entry under Chart values reference.",
                    )

    def assert_reader_prose(self, inventory) -> None:
        for line in _generated_prose(inventory):
            self.assertNotRegex(line, r"(?i)\bview\b")
            outside_code = re.sub(r"(`+)(.*?)\1", "", line)
            self.assertNotRegex(outside_code, r"--[A-Za-z]")

    def test_generated_prose_has_no_tool_wording_outside_intro(self) -> None:
        inventory = _usage_inventory()
        self.assert_reader_prose(inventory)
        self.assert_reader_prose(replace(
            inventory,
            hidden_clusters=("test-infra", "test-workload0"),
            library_charts=("operator-library",),
        ))

    def test_generated_prose_check_rejects_tool_wording_at_builder_sources(self) -> None:
        inventory = _usage_inventory()
        for module, attribute in (
            (chart_page, "_VALUES_PARAGRAPH"),
            (chart_page, "UNDEPLOYED_NOTE"),
            (chart_page, "_COVERAGE_NOTE"),
            (chart_reference, "_CHART_REFERENCE_NOTE"),
        ):
            for sentence in ("This view omits test clusters.", "Pass --all-clusters."):
                with self.subTest(attribute=attribute, sentence=sentence):
                    with patch.object(module, attribute, sentence):
                        with self.assertRaises(AssertionError):
                            self.assert_reader_prose(inventory)
        with patch.object(chart_page, "_VALUES_PARAGRAPH", "A literal `--flag` is allowed."):
            self.assert_reader_prose(inventory)
        for name in ("view", "--all-clusters"):
            reference = replace(
                inventory.reference,
                workload_features=(ChartList(name, ("beta",)),),
            )
            with self.subTest(usage=name):
                with self.assertRaises(AssertionError):
                    self.assert_reader_prose(replace(inventory, reference=reference))

    def test_upstream_tool_wording_is_rendered_without_page_specific_changes(self) -> None:
        inventory = _usage_inventory()
        entry = ChartEntry(
            "alpha", "A view with --overwrite.", (),
            ValuesReference(
                True,
                rows=(ValueRow(
                    "role", "view", description="Use view or --enable-client-registration.",
                    example="role: view\nargs: --overwrite",
                ),),
                other_comments=("A view with --overwrite.",),
            ),
        )
        inventory = replace(
            inventory, reference=replace(inventory.reference, charts=(entry,))
        )
        self.assert_reader_prose(inventory)
        page_entries = chart_page._page_chart_entries(inventory, inventory.reference)
        expected = "\n".join(chart_reference.chart_entries_markdown(
            page_entries, escape_addresses=True
        ))
        self.assertIn(expected, "\n".join(chart_page._reference_section(inventory)))
        self.assertEqual(page_entries[0].description, entry.description)
        self.assertEqual(page_entries[0].values, entry.values)

    def test_hub_group_charts_link_only_to_existing_reference_headings(self) -> None:
        inventory = _usage_inventory()
        hub = inventory.clusters[0]
        hub = replace(hub, rows=(*hub.rows, {
            "chart": "no-reference", "application_set": "hub-components"
        }))
        page = render_chart_page(replace(
            inventory, clusters=(hub, *inventory.clusters[1:])
        ))
        section = _section(page, "### Hub groups")
        ids = [heading_id(text) for _, text in _headings(page)]
        self.assertIn("[alpha](#alpha)", section)
        self.assertIn("[keycloak-oauth](#keycloak-oauth)", section)
        self.assertIn("no-reference", section)
        self.assertNotIn("[no-reference]", section)
        for line in section.splitlines()[4:]:
            if not line.startswith("|"):
                continue
            for cell in _split_row(line)[1].split(", "):
                if cell == "no-reference":
                    continue
                match = re.fullmatch(r"\[([^]]+)\]\(#([^)]+)\)", cell)
                self.assertIsNotNone(match, cell)
                self.assertEqual(ids.count(match.group(2)), 1)

    def test_other_views_all_formats_are_byte_identical_to_10df959(self) -> None:
        hashes = {
            "summary": (
                "9877d4758b65d67f8db860c3df78a266dc51cecc1e9076f9cfb2129f40b22d97",
                "327b6c11616441d89fcd76403cf415e6d07c387ea7bf821f80f4a0a730c2cce6",
                "16d3597cd26179cee5c451df5784592a75c0019a86800fc39b4adb70e48da6af",
            ),
            "cluster": (
                "d57980fe88284b7739e71aa13b0625be07f3547d20c1c8ae5000b789b5f227c7",
                "9d31bef3b5d818f367011ef65dcd8fb6cd785efc768d2d0fc6296c7f8fd53c99",
                "f2c80ec1f3df324b04948a5690d92337ea7c1f20471b58ad1a41ca1c6e79d6c1",
            ),
            "reference": (
                "b9b92a26484d66fb1653dcbc13e63db67b2b62434e1691e37bdf1c2b76c1402d",
                "5f8deac0e8ba9a7686ac91217d52d61c9ac37f21da46c40c303c3808d13ea520",
                "bf94da8ea45119d2b704984928c6e0e597abd891c3185c615425db4e22d83d79",
            ),
            "overrides": (
                "4a82e13b5c5e79479bb67e40b6d346699365ebdb5cb33f41cddd945dab7b7ba4",
                "bf2901ca5db6fc8464dae41cee06374d1d887f2bcf39813809afc3a2effa2662",
                "9226e866968a5a92a2c799bf12812c025299e4e7af0762f6cf9ff7b54c507e4f",
            ),
        }
        for view, expected in hashes.items():
            for fmt, digest in zip(("text", "markdown", "json"), expected):
                with self.subTest(view=view, format=fmt):
                    code, output, stderr = _run_cli(
                        ChartPageFakeGitHubClient(),
                        ["charts", "demo", "--view", view, "--format", fmt],
                    )
                    self.assertEqual(code, 0, stderr)
                    self.assertEqual(hashlib.sha256(output.encode()).hexdigest(), digest)

    def test_front_matter_h1_and_final_newline(self) -> None:
        page = _page()

        self.assertTrue(
            page.startswith(
                "---\ntitle: oac-apps charts and values by cluster\n---\n\n"
            )
        )
        self.assertFalse(
            any(line.startswith("# ") for line in page.splitlines())
        )
        self.assertTrue(page.endswith("\n"))
        self.assertFalse(page.endswith("\n\n"))

    def test_top_level_headings_are_exact_and_in_order(self) -> None:
        page = _page()

        self.assertEqual(
            [text for level, text in _headings(page) if level == 2],
            [
                "Which clusters get which charts",
                "Values set for each cluster",
                "Chart values reference",
                "What this page does not cover",
            ],
        )
        self.assertTrue(all(level <= 3 for level, _ in _headings(page)))

    def test_headings_are_unique_and_anchor_targets_match_once(self) -> None:
        page = _page()
        headings = _headings(page)
        ids = [heading_id(text) for _, text in headings]

        self.assertEqual(len(ids), len(set(ids)))
        targets = re.findall(r"\]\(#([^)\s]+)\)", page)
        self.assertTrue(targets)
        for target in targets:
            self.assertEqual(ids.count(target), 1, target)

    def test_blank_lines_and_trailing_whitespace(self) -> None:
        page = _page()
        lines = page.splitlines()

        self.assertTrue(all(line == line.rstrip() for line in lines))
        self.assertNotIn("\n\n\n", page)
        for index, line in enumerate(lines):
            if re.match(r"^#{2,3} ", line):
                if index:
                    self.assertEqual(lines[index - 1], "", line)
                if index + 1 < len(lines):
                    self.assertEqual(lines[index + 1], "", line)
        table_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("|")
            and (index == 0 or not lines[index - 1].startswith("|"))
        ]
        for start in table_starts:
            end = start
            while end + 1 < len(lines) and lines[end + 1].startswith("|"):
                end += 1
            self.assertEqual(lines[start - 1], "")
            self.assertEqual(lines[end + 1], "")
        list_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("- ")
            and (index == 0 or not lines[index - 1].startswith("- "))
        ]
        for start in list_starts:
            end = start
            while end + 1 < len(lines) and lines[end + 1].startswith("- "):
                end += 1
            self.assertEqual(lines[start - 1], "")
            self.assertEqual(lines[end + 1], "")
        for index, line in enumerate(lines):
            if line.startswith("```"):
                self.assertEqual(lines[index - 1], "")
                self.assertEqual(lines[index + 1], "")

    def test_override_values_are_code_spans_and_urls_stay_inside_them(self) -> None:
        page = _page()
        rows = {
            _code_content(row[1]): row
            for row in _table_rows(_section(page, "### demo-infra (hub)"))
        }

        expected = {
            "quoted": '"true"',
            "contact": f'"{FIXTURE_EMAIL}"',
            "docs": '"https://example.com/docs"',
            "flag": '"--flag"',
            "piped": '"left\\|right"',
            "tick": '"tick`mark"',
        }
        for key, value in expected.items():
            self.assertIn(key, rows)
            content = _code_content(rows[key][4])
            self.assertIsNotNone(content, rows[key])
            self.assertEqual(content, value)
        self.assertNotIn("https://example.com/docs", _outside_code_and_links(page))
        self.assertNotIn(FIXTURE_EMAIL, _outside_code_and_links(page))

    def test_liquid_values_are_wrapped_in_raw_tags_only_when_needed(self) -> None:
        plain = _page()
        self.assertNotIn("{% raw %}", plain)
        self.assertNotIn("{% endraw %}", plain)

        templated = _page(ChartPageFakeGitHubClient(templated=True))
        self.assertTrue(
            templated.startswith(
                "---\ntitle: oac-apps charts and values by cluster\n---\n\n"
                "{% raw %}\n\n"
            )
        )
        self.assertTrue(templated.endswith("\n\n{% endraw %}\n"))

    def test_output_is_deterministic_and_has_no_date(self) -> None:
        first = _page()
        second = _page()

        self.assertEqual(first, second)
        self.assertIsNone(re.search(r"\b20\d\d-\d\d-\d\d\b", first))
        self.assertNotIn("Generated on", first)

    def test_page_rejects_other_formats_chart_and_workload(self) -> None:
        for arguments, message in (
            (["--format", "json"], "Markdown"),
            (["--format", "text"], "Markdown"),
            (["--chart", "alpha"], "--chart"),
            (["--workload", "demo-workload0"], "--workload"),
        ):
            exit_code, stdout, stderr = _run_cli(
                ChartPageFakeGitHubClient(),
                ["charts", "demo", "--view", "page", *arguments],
            )
            self.assertNotEqual(exit_code, 0, arguments)
            self.assertIn(message, stderr)
            self.assertEqual(stdout, "")

    def test_output_file_writes_the_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.md"
            exit_code, stdout, stderr = _run_cli(
                ChartPageFakeGitHubClient(),
                ["charts", "demo", "--view", "page", "--output", str(path)],
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(stdout, "")
            self.assertEqual(path.read_text(), _page())

    def test_overrides_markdown_uses_code_spans_and_other_formats_are_stable(self) -> None:
        exit_code, markdown, stderr = _run_cli(
            ChartPageFakeGitHubClient(),
            ["charts", "demo", "--view", "overrides", "--format", "markdown"],
        )
        self.assertEqual(exit_code, 0, stderr)
        self.assertIn(
            "| `quoted` | changed | `\"false\"` | `\"true\"` | "
            "`values/demo-infra/alpha.yaml` |",
            markdown,
        )
        self.assertIn("| `piped` | changed | `\"none\"` | `\"left\\|right\"` |", markdown)

        exit_code, text, stderr = _run_cli(
            ChartPageFakeGitHubClient(),
            ["charts", "demo", "--view", "overrides", "--format", "text"],
        )
        self.assertEqual(exit_code, 0, stderr)
        self.assertNotIn("`quoted`", text)
        self.assertIn("quoted", text)
        self.assertEqual(
            hashlib.sha256(text.encode()).hexdigest(),
            "4a82e13b5c5e79479bb67e40b6d346699365ebdb5cb33f41cddd945dab7b7ba4",
        )

        exit_code, json_output, stderr = _run_cli(
            ChartPageFakeGitHubClient(),
            ["charts", "demo", "--view", "overrides", "--format", "json"],
        )
        self.assertEqual(exit_code, 0, stderr)
        self.assertIn('"view": "overrides"', json_output)
        self.assertNotIn("`quoted`", json_output)
        self.assertEqual(
            hashlib.sha256(json_output.encode()).hexdigest(),
            "9226e866968a5a92a2c799bf12812c025299e4e7af0762f6cf9ff7b54c507e4f",
        )


if __name__ == "__main__":
    unittest.main()
