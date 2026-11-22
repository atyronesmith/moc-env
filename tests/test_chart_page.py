"""Offline acceptance tests for ``moc-env charts --view page``."""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fakes import FakeGitHubClient
from moc_env import cli
from moc_env.chart_page import heading_id

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


class ChartPageTest(unittest.TestCase):
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
