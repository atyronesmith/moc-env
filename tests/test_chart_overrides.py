"""Offline coverage for the ``charts --view overrides`` report."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fakes import FakeGitHubClient
from moc_env import chart_overrides, cli, feature_charts
from moc_env.charts import (
    HOSTED_CLUSTERS_REASON,
    ChartManifest,
    _cluster_overrides,
)

DEFAULTS = {
    "replicas": 1,
    "image": {"repo": "quay.io/x/demo", "tag": "1.0"},
    "nodes": [],
    "extra": {},
    "mode": "fast",
}
HUB_LAYER = {
    "replicas": 3,
    "image": {"tag": "1.0"},
    "mode": "slow",
}
WORKLOAD_LAYER = {
    "image": {"repo": "quay.io/y/demo"},
    "nodes": [{"name": "a"}],
    "extra": {"key": "v"},
    "newKey": 7,
    "mode": "fast",
}
HUB_PATH = "values/demo-infra/alpha.yaml"
LOCAL_PATH = "values/demo-infra/local-cluster/alpha.yaml"
WORKLOAD_PATH = "values/demo-infra/demo-workload0/alpha.yaml"


class OverridesFakeGitHubClient(FakeGitHubClient):
    """One hub and one workload with component and non-component charts."""

    TREE = {
        "applicationsets/templates/hub/hub-components.yaml",
        "applicationsets/templates/managed/workload-components.yaml",
        "applicationsets/templates/managed/hosted-ingress.yaml",
        "apps/demo-infra/login.yaml",
        "apps/demo-infra/legacy.yaml",
        "values/demo-infra/local-cluster/acm-placements.yaml",
        "values/demo-infra/keycloak-oauth.yaml",
        "values/demo-infra/local-cluster/keycloak-oauth.yaml",
        HUB_PATH,
        LOCAL_PATH,
        WORKLOAD_PATH,
        "values/demo-infra/demo-workload0/hosted-ingress.yaml",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml",
        "charts/alpha/values.yaml",
        "charts/beta/values.yaml",
        "charts/keycloak-oauth/values.yaml",
        "charts/hosted-ingress/values.yaml",
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
          - component: beta
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
        "applicationsets/templates/managed/hosted-ingress.yaml": """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: hosted-ingress
spec:
  template:
    metadata:
      annotations:
        cluster.open-cluster-management.io/placement: all-managed-clusters
    spec:
      source:
        path: "charts/hosted-ingress"
        helm:
          valueFiles:
            - "/hosted-clusters/{{ $hub }}/values.yaml"
            - "/hosted-clusters/{{ $hub }}/{{`{{name}}`}}/values.yaml"
""",
        "apps/demo-infra/login.yaml": """
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
        "apps/demo-infra/legacy.yaml": """
apiVersion: v1
kind: ConfigMap
metadata:
  name: legacy
""",
        "values/demo-infra/local-cluster/acm-placements.yaml": "placements: []\n",
        "hosted-clusters/demo-infra/demo-workload0/values.yaml": """
clusterName: demo-workload0
clusterLabels: {}
""",
        HUB_PATH: "replicas: 3\nimage:\n  tag: '1.0'\nmode: slow\n",
        LOCAL_PATH: "mode: fast\nnewKey: hub\n",
        "values/demo-infra/keycloak-oauth.yaml": """
tokenConfig:
  accessTokenMaxAgeSeconds: 600
mode: custom
""",
        "values/demo-infra/local-cluster/keycloak-oauth.yaml": "mode: custom\n",
        WORKLOAD_PATH: """
image:
  repo: quay.io/y/demo
nodes:
  - name: a
extra:
  key: v
newKey: 7
mode: fast
""",
        "values/demo-infra/demo-workload0/hosted-ingress.yaml": "enabled: true\n",
        "charts/alpha/values.yaml": """
replicas: 1
image:
  repo: quay.io/x/demo
  tag: '1.0'
nodes: []
extra: {}
mode: fast
""",
        "charts/beta/values.yaml": "replicas: 1\n",
        "charts/keycloak-oauth/values.yaml": """
tokenConfig:
  accessTokenMaxAgeSeconds: 300
  accessTokenInactivityTimeout: 1800
mode: default
""",
        "charts/hosted-ingress/values.yaml": "enabled: false\n",
    }

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            tree.update({path: {"path": path} for path in self.TREE})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            return self.FILES.get(path, "{}\n")
        return super().get_file(repository, path, ref)


class OverrideRowsTest(unittest.TestCase):
    def test_acceptance_inputs(self) -> None:
        rows = chart_overrides.override_rows(
            DEFAULTS,
            [
                ("values/h-infra/demo.yaml", HUB_LAYER),
                ("values/h-infra/h-workload0/demo.yaml", WORKLOAD_LAYER),
            ],
        )

        changed = [row for row in rows if row["status"] != "restated"]
        self.assertEqual(
            [(row["key"], row["status"]) for row in changed],
            [
                ("extra.key", "added"),
                ("image.repo", "changed"),
                ("newKey", "added"),
                ("nodes", "changed"),
                ("replicas", "changed"),
            ],
        )
        by_key = {row["key"]: row for row in rows}
        self.assertNotIn("default", by_key["extra.key"])
        self.assertEqual(by_key["extra.key"]["value"], "v")
        self.assertEqual(
            by_key["extra.key"]["source"], "values/h-infra/h-workload0/demo.yaml"
        )
        self.assertEqual(by_key["image.repo"]["default"], "quay.io/x/demo")
        self.assertEqual(by_key["image.repo"]["value"], "quay.io/y/demo")
        self.assertEqual(
            by_key["image.repo"]["source"], "values/h-infra/h-workload0/demo.yaml"
        )
        self.assertEqual(by_key["nodes"]["default"], [])
        self.assertEqual(by_key["nodes"]["value"], [{"name": "a"}])
        self.assertEqual(by_key["replicas"]["default"], 1)
        self.assertEqual(by_key["replicas"]["value"], 3)
        self.assertEqual(by_key["replicas"]["source"], "values/h-infra/demo.yaml")
        self.assertEqual(
            sum(1 for row in rows if row["status"] == "restated"), 2
        )
        self.assertEqual(by_key["mode"]["source"], "values/h-infra/h-workload0/demo.yaml")
        self.assertEqual(by_key["image.tag"]["source"], "values/h-infra/demo.yaml")

    def test_no_layers_produce_no_rows(self) -> None:
        self.assertEqual(chart_overrides.override_rows(DEFAULTS, []), [])

    def test_non_mapping_overrides_a_default_mapping(self) -> None:
        rows = chart_overrides.override_rows(
            {"image": {"repo": "quay.io/x/demo"}},
            [("values/hub/a.yaml", {"image": "disabled"})],
        )

        self.assertEqual(
            rows,
            [
                {
                    "key": "image",
                    "status": "changed",
                    "default": {"repo": "quay.io/x/demo"},
                    "value": "disabled",
                    "source": "values/hub/a.yaml",
                }
            ],
        )

    def test_value_files_are_parsed_and_resolved(self) -> None:
        workload = feature_charts.parse_application_set(
            """
spec:
  template:
    spec:
      source:
        helm:
          valueFiles:
            - "/values/{{ $hub }}/{{`{{component}}`}}.yaml"
            - "/values/{{ $hub }}/{{`{{name}}`}}/{{`{{component}}`}}.yaml"
""",
            "demo",
            "applicationsets/templates/managed/demo.yaml",
        )
        hub = feature_charts.parse_application_set(
            """
spec:
  template:
    spec:
      source:
        helm:
          valueFiles:
            - "/values/{{ $hub }}/local-cluster/{{`{{component}}`}}.yaml"
""",
            "demo",
            "applicationsets/templates/hub/demo.yaml",
        )

        self.assertEqual(
            [
                feature_charts.resolve_value_file(
                    entry, "h-infra", "h-workload0", "demo"
                )
                for entry in workload.value_files
            ],
            ["values/h-infra/demo.yaml", "values/h-infra/h-workload0/demo.yaml"],
        )
        self.assertEqual(
            feature_charts.resolve_value_file(
                hub.value_files[0], "h-infra", "h-workload0", "demo"
            ),
            "values/h-infra/local-cluster/demo.yaml",
        )

    def test_hosted_cluster_values_are_not_compared(self) -> None:
        parsed = feature_charts.parse_application_set(
            """
spec:
  template:
    spec:
      source:
        helm:
          valueFiles:
            - "/hosted-clusters/{{ $hub }}/values.yaml"
            - "/hosted-clusters/{{ $hub }}/{{`{{name}}`}}/values.yaml"
""",
            "hosted-ingress",
            "applicationsets/templates/managed/hosted-ingress.yaml",
        )
        entries, not_compared = _cluster_overrides(
            {},
            "h-infra",
            "h-workload0",
            [{"chart": "hosted-ingress", "application_set": "hosted-ingress"}],
            {
                "hosted-ingress": ChartManifest(
                    "hosted-ingress",
                    "applicationsets/templates/managed/hosted-ingress.yaml",
                    parsed.value_files,
                )
            },
            lambda path: (None, None),
        )

        self.assertEqual(entries, ())
        self.assertEqual(
            not_compared,
            ({"chart": "hosted-ingress", "reason": HOSTED_CLUSTERS_REASON},),
        )

    def test_unresolved_value_file_names_the_manifest(self) -> None:
        manifest = "applicationsets/templates/managed/broken.yaml"
        parsed = feature_charts.parse_application_set(
            """
spec:
  template:
    spec:
      source:
        helm:
          valueFiles:
            - "/{{`{{.path.path}}`}}/values.yaml"
""",
            "broken",
            manifest,
        )
        entries, not_compared = _cluster_overrides(
            {},
            "h-infra",
            "h-workload0",
            [{"chart": "broken", "application_set": "broken"}],
            {"broken": ChartManifest("broken", manifest, parsed.value_files)},
            lambda path: (None, None),
        )

        self.assertEqual(entries, ())
        self.assertEqual(
            not_compared,
            (
                {
                    "chart": "broken",
                    "reason": f"value files could not be resolved from {manifest}",
                },
            ),
        )

    def test_missing_value_files_are_unresolved(self) -> None:
        manifest = "applicationsets/templates/managed/no-values.yaml"
        parsed = feature_charts.parse_application_set(
            "spec:\n  template:\n    spec:\n      source:\n        path: charts/demo\n",
            "no-values",
            manifest,
        )

        self.assertEqual(parsed.value_files, ())
        entries, not_compared = _cluster_overrides(
            {},
            "h-infra",
            "h-workload0",
            [{"chart": "demo", "application_set": "no-values"}],
            {"demo": ChartManifest("demo", manifest, parsed.value_files)},
            lambda path: (None, None),
        )
        self.assertEqual(entries, ())
        self.assertEqual(not_compared[0]["chart"], "demo")
        self.assertIn(manifest, not_compared[0]["reason"])


class OverridesCommandTest(unittest.TestCase):
    def run_cli(
        self,
        arguments: list[str],
        client: FakeGitHubClient | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "GitHubClient",
                lambda **kwargs: client or OverridesFakeGitHubClient(),
            ),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_text_lists_hub_and_workload_overrides(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("demo-infra · hub", stdout)
        self.assertIn("demo-workload0 · workload", stdout)
        self.assertIn("Chart: alpha", stdout)
        self.assertIn("image.repo", stdout)
        self.assertIn("quay.io/x/demo", stdout)
        self.assertIn("quay.io/y/demo", stdout)
        self.assertIn("values/demo-infra/demo-workload0/alpha.yaml", stdout)
        self.assertIn("Charts with no overrides: beta", stdout)
        self.assertIn("Restated values not shown: 2", stdout)
        self.assertIn("Not compared: hosted-ingress", stdout)
        self.assertIn(
            f"Not compared: hosted-ingress ({HOSTED_CLUSTERS_REASON})",
            stdout,
        )
        self.assertIn("Source: CCI-MOC/oac-apps @ main", stdout)
        self.assertIn("does not cover", stdout)

    def test_markdown_has_a_table_only_for_changed_or_added_rows(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--workload",
                "demo-workload0",
                "--view",
                "overrides",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        self.assertIn("## demo-workload0 (workload)", stdout)
        self.assertIn("### alpha", stdout)
        self.assertIn("| Key | Status | Default | Value | Set in |", stdout)
        self.assertIn(
            "| `nodes` | changed | `[]` | `[{\"name\":\"a\"}]` | "
            "`values/demo-infra/demo-workload0/alpha.yaml` |",
            stdout,
        )
        self.assertIn("Not compared: hosted-ingress", stdout)
        self.assertIn(
            f"Not compared: hosted-ingress ({HOSTED_CLUSTERS_REASON})",
            stdout,
        )
        self.assertNotIn("### beta", stdout)
        self.assertNotIn("### hosted-ingress", stdout)

    def test_json_keeps_full_values_and_per_chart_files(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
                "--format",
                "json",
            ]
        )

        self.assertEqual(exit_code, 0, stderr)
        document = json.loads(stdout)
        self.assertEqual(document["view"], "overrides")
        self.assertEqual(document["repository"], "CCI-MOC/oac-apps")
        self.assertEqual(document["ref"], "main")
        self.assertTrue(document["sha"])
        self.assertIn("scope", document)
        self.assertIn("footer", document)
        workload = document["clusters"]["demo-workload0"]
        self.assertEqual(
            workload["not_compared"],
            [{"chart": "hosted-ingress", "reason": HOSTED_CLUSTERS_REASON}],
        )
        alpha = workload["charts"]["alpha"]
        self.assertEqual(
            alpha["files"],
            [HUB_PATH, WORKLOAD_PATH],
        )
        self.assertEqual(
            alpha["manifest"],
            "applicationsets/templates/managed/workload-components.yaml",
        )
        self.assertEqual(alpha["restated"], 2)
        by_key = {row["key"]: row for row in alpha["overrides"]}
        self.assertNotIn("default", by_key["extra.key"])
        self.assertEqual(by_key["nodes"]["value"], [{"name": "a"}])
        self.assertEqual(by_key["nodes"]["default"], [])
        hub_alpha = document["clusters"]["demo-infra"]["charts"]["alpha"]
        self.assertEqual(hub_alpha["files"], [HUB_PATH, LOCAL_PATH])
        self.assertEqual(
            hub_alpha["manifest"],
            "applicationsets/templates/hub/hub-components.yaml",
        )
        self.assertEqual(hub_alpha["restated"], 2)

    def test_drop_ins_use_source_chart_and_report_non_applications(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["charts", "demo", "--view", "overrides", "--format", "json"]
        )

        self.assertEqual(exit_code, 0, stderr)
        hub = json.loads(stdout)["clusters"]["demo-infra"]
        self.assertNotIn("login", hub["charts"])
        keycloak = hub["charts"]["keycloak-oauth"]
        self.assertEqual(keycloak["manifest"], "apps/demo-infra/login.yaml")
        self.assertEqual(
            keycloak["files"],
            [
                "values/demo-infra/keycloak-oauth.yaml",
                "values/demo-infra/local-cluster/keycloak-oauth.yaml",
            ],
        )
        by_key = {row["key"]: row for row in keycloak["overrides"]}
        self.assertEqual(
            by_key["tokenConfig.accessTokenMaxAgeSeconds"]["value"], 600
        )
        self.assertEqual(by_key["mode"]["value"], "custom")
        self.assertEqual(
            hub["not_compared"],
            [
                {
                    "chart": "legacy",
                    "reason": "not a Helm chart source in apps/demo-infra/legacy.yaml",
                }
            ],
        )

    def test_hub_value_files_come_from_a_nonstandard_manifest_path(self) -> None:
        appset_path = "applicationsets/templates/hub/custom-values.yaml"
        custom_values = "values/demo-infra/custom/custom.yaml"
        misleading_local = "values/demo-infra/local-cluster/custom.yaml"

        class CustomValuesClient(OverridesFakeGitHubClient):
            extras = {
                appset_path: """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: custom-values
spec:
  generators:
    - list:
        elements:
          - component: custom
  template:
    spec:
      source:
        path: "charts/{{component}}"
        helm:
          valueFiles:
            - "/values/{{ $hub }}/custom/{{`{{component}}`}}.yaml"
""",
                "charts/custom/values.yaml": "mode: default\n",
                custom_values: "mode: custom\n",
                misleading_local: "mode: local\n",
            }

            def get_tree(self, repository: str, ref: str = "main"):
                tree = super().get_tree(repository, ref)
                if repository == "CCI-MOC/oac-apps":
                    tree.update(
                        {path: {"path": path} for path in self.extras}
                    )
                return tree

            def get_file(self, repository: str, path: str, ref: str = "main") -> str:
                if repository == "CCI-MOC/oac-apps" and path in self.extras:
                    return self.extras[path]
                return super().get_file(repository, path, ref)

        exit_code, stdout, stderr = self.run_cli(
            ["charts", "demo", "--view", "overrides", "--format", "json"],
            CustomValuesClient(),
        )

        self.assertEqual(exit_code, 0, stderr)
        custom = json.loads(stdout)["clusters"]["demo-infra"]["charts"]["custom"]
        self.assertEqual(custom["manifest"], appset_path)
        self.assertEqual(custom["files"], [custom_values])
        by_key = {row["key"]: row for row in custom["overrides"]}
        self.assertEqual(by_key["mode"]["value"], "custom")

    def test_chart_filter_limits_the_overrides_view(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            [
                "charts",
                "demo",
                "--view",
                "overrides",
                "--chart",
                "alpha",
                "--format",
                "json",
            ]
        )

        self.assertEqual(exit_code, 0)
        document = json.loads(stdout)
        self.assertEqual(list(document["clusters"]["demo-infra"]["charts"]), ["alpha"])
        self.assertEqual(
            list(document["clusters"]["demo-workload0"]["charts"]), ["alpha"]
        )
        self.assertEqual(document["clusters"]["demo-workload0"]["not_compared"], [])

    def test_output_extension_infers_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for suffix, expected in (
                (".md", "## demo-workload0 (workload)"),
                (".json", '"view": "overrides"'),
            ):
                path = Path(directory) / f"overrides{suffix}"
                exit_code, stdout, stderr = self.run_cli(
                    [
                        "charts",
                        "demo",
                        "--workload",
                        "demo-workload0",
                        "--view",
                        "overrides",
                        "--output",
                        str(path),
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)
                self.assertEqual(stdout, "")
                self.assertIn(expected, path.read_text())


if __name__ == "__main__":
    unittest.main()
