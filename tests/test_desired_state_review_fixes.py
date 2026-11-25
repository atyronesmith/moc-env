"""Offline regressions for multi-workload desired state and fleet output."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from fakes import FakeGitHubClient
from moc_env import cli
from moc_env.boot_image import image_is_specific
from moc_env.checks import _boot_image_state
from moc_env.compare import compare_environment, compare_infra, compare_workload
from moc_env.environment_cache import read_environment_cache
from moc_env.export import (
    build_environment_export,
    build_infra_export,
    build_workload_export,
    workload_cluster_name,
)
from moc_env.model import Environment
from moc_env.observed import (
    read_apps_observation,
    read_infra_observation,
    read_issue_observation,
)
from moc_env.validate import validate_environment


class InventoryClient(FakeGitHubClient):
    workloads = ("workload0", "workload1")

    def get_tree(self, repository, ref="main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {"hosted-clusters/bu-ist-demo-infra/values.yaml"}
            for suffix in self.workloads:
                cluster = f"bu-ist-demo-{suffix}"
                paths.update({
                    f"hosted-clusters/bu-ist-demo-infra/{cluster}/values.yaml",
                    f"values/bu-ist-demo-infra/{cluster}/component.yaml",
                    f"apps/bu-ist-demo-infra/{cluster}/application.yaml",
                })
            tree.update({path: {"path": path} for path in paths})
        return tree

    def get_file(self, repository, path, ref="main"):
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            data = yaml.safe_load(super().get_file(repository, path, ref))
            groups = data["all"]["children"]["bu_ist_demo_clusters"]["children"]
            template = yaml.safe_dump(groups.pop("bu_ist_demo_workload0"))
            for suffix in self.workloads:
                text = template.replace("bu-ist-demo-workload0", f"bu-ist-demo-{suffix}")
                text = text.replace("discovery.iso", "bu-ist-demo-infra-agent-discovery.iso")
                groups[f"bu_ist_demo_{suffix}"] = yaml.safe_load(text)
            return yaml.safe_dump(data)
        if repository == "CCI-MOC/oac-apps":
            for suffix in self.workloads:
                if path.endswith(f"bu-ist-demo-{suffix}/values.yaml"):
                    original = path.replace(f"bu-ist-demo-{suffix}", "bu-ist-demo-workload0")
                    return super().get_file(repository, original, ref).replace(
                        "bu-ist-demo-workload0", f"bu-ist-demo-{suffix}"
                    )
        return super().get_file(repository, path, ref)


def inventory_client(workloads):
    return type("SelectedInventoryClient", (InventoryClient,), {"workloads": workloads})


class DesiredStateReviewFixesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment("bu-ist-demo", 666)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        cache_environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": str(self.root / "cache")})
        cache_environment.start()
        self.addCleanup(cache_environment.stop)

    def observations(self, workloads):
        client = inventory_client(workloads)()
        infra = read_infra_observation(client, self.environment)
        apps = read_apps_observation(client, self.environment, include_pull_requests=False)
        issue = read_issue_observation(client, self.environment)
        return infra, apps, issue

    def run_cli(self, arguments, workloads=("workload0", "workload1")):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubClient", inventory_client(workloads)),
            patch.object(cli, "_resolve_github_token", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_workload_resolution_full_short_and_empty_discovery(self) -> None:
        discovered = ("bu-ist-demo-workload1",)
        for name in ("workload1", "bu-ist-demo-workload1"):
            self.assertEqual(
                workload_cluster_name(self.environment, name, discovered), discovered[0]
            )
        for name, workloads in (("workload9", discovered), ("workload0", ())):
            with self.subTest(name=name, workloads=workloads), self.assertRaises(ValueError):
                workload_cluster_name(self.environment, name, workloads)

    def test_cli_exports_discovered_workload1_by_full_and_short_name(self) -> None:
        for name in ("workload1", "bu-ist-demo-workload1"):
            with self.subTest(name=name):
                code, stdout, stderr = self.run_cli(
                    ["export-workload", "bu-ist-demo", name], ("workload1",)
                )
                self.assertEqual(code, 0, stderr)
                self.assertEqual(
                    yaml.safe_load(stdout)["metadata"]["name"]["value"],
                    "bu-ist-demo-workload1",
                )

    def test_cli_rejects_unknown_or_nonexistent_workload(self) -> None:
        for name, workloads in (("workload9", ("workload1",)), ("workload0", ())):
            with self.subTest(name=name, workloads=workloads):
                code, stdout, _ = self.run_cli(
                    ["export-workload", "bu-ist-demo", name], workloads
                )
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")

    def test_environment_and_infra_exports_use_all_actual_workloads(self) -> None:
        for workloads in (("workload1", "workload0"), ("workload1",), ()):
            with self.subTest(workloads=workloads):
                infra, apps, issue = self.observations(workloads)
                expected = sorted(f"bu-ist-demo-{name}" for name in workloads)
                infra = replace(infra, discovered_workload_clusters=tuple(reversed(expected)))
                bundle = build_environment_export(self.environment, issue, infra, apps)
                self.assertEqual(
                    [item["name"]["value"] for item in bundle["spec"]["workloadClusters"]],
                    expected,
                )
                validation = validate_environment(bundle)
                self.assertTrue(validation.valid, validation.errors)
                hub = build_infra_export(self.environment, infra)
                self.assertEqual(
                    list(hub["spec"]["inventory"]["clusters"]),
                    ["bu-ist-demo-infra", *expected],
                )
                self.assertEqual(
                    compare_infra(hub, self.environment, infra).overall_state, "MATCHES MAIN"
                )

    def test_environment_comparison_checks_each_workload(self) -> None:
        for workloads in (("workload0", "workload1"), ("workload1",), ()):
            with self.subTest(workloads=workloads):
                infra, apps, issue = self.observations(workloads)
                document = build_environment_export(self.environment, issue, infra, apps)
                comparison = compare_environment(document, self.environment, issue, infra, apps)
                self.assertEqual(comparison.overall_state, "MATCHES MAIN", comparison.checks)
                self.assertEqual(
                    comparison.to_dict()["environment"]["workload_clusters"],
                    [f"bu-ist-demo-{name}" for name in workloads],
                )

    def test_workload1_comparison_uses_its_own_inventory_and_gitops_paths(self) -> None:
        infra, apps, _ = self.observations(("workload1",))
        document = build_workload_export(self.environment, "bu-ist-demo-workload1", infra, apps)
        report = compare_workload(document, infra, apps)
        self.assertEqual(report.overall_state, "MATCHES MAIN", report.checks)
        self.assertEqual(report.to_dict()["environment"]["workload_cluster"], "bu-ist-demo-workload1")
        document["spec"]["gitOps"]["componentValues"]["prefix"]["value"] = (
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/"
        )
        changed = compare_workload(document, infra, apps)
        self.assertTrue(any(
            check.field == "spec.gitOps.componentValues.prefix.value"
            and check.state == "value_mismatch"
            for check in changed.checks
        ))

    def test_missing_workload_still_produces_a_comparison_difference(self) -> None:
        infra, apps, _ = self.observations(("workload1",))
        document = build_workload_export(self.environment, "bu-ist-demo-workload1", infra, apps)
        absent = replace(infra, clusters={"bu-ist-demo-infra": infra.clusters["bu-ist-demo-infra"]})
        report = compare_workload(document, absent, apps)
        self.assertTrue(any(check.state == "missing_from_main" for check in report.checks))

    def test_boot_image_rules_match_status_and_comparison(self) -> None:
        for filename, expected in (
            ("oac-prod-workload1-agent.iso", True),
            ("prod-workload1-agent.iso", True),
            ("oac-prod-infra-agent.iso", True),
            ("prod-infra-agent.iso", True),
            ("discovery.iso", False),
            ("unrelated.iso", False),
        ):
            with self.subTest(filename=filename):
                url = f"https://example.invalid/{filename}"
                self.assertEqual(
                    image_is_specific(url, "oac-prod-workload1", "oac-prod-infra"), expected
                )
                self.assertEqual(
                    _boot_image_state(url, "oac-prod-workload1", "oac-prod-infra")
                    == "declared_in_main", expected,
                )
        infra, apps, _ = self.observations(("workload1",))
        document = build_workload_export(self.environment, "bu-ist-demo-workload1", infra, apps)
        check = next(
            item for item in compare_workload(document, infra, apps).checks
            if item.field.endswith(".clusterSpecific")
        )
        self.assertEqual(check.state, "matches_main")

    def test_fleet_output_writes_inferred_json_and_text_without_stdout(self) -> None:
        for suffix in ("json", "txt"):
            with self.subTest(suffix=suffix):
                output = self.root / f"fleet.{suffix}"
                code, stdout, stderr = self.run_cli(["status", "--output", str(output)])
                self.assertEqual(code, 0, stderr)
                self.assertEqual(stdout, "")
                rendered = output.read_text(encoding="utf-8")
                if suffix == "json":
                    self.assertTrue(json.loads(rendered))
                else:
                    self.assertIn("bu-ist-demo", rendered)
                self.assertTrue(read_environment_cache())

    def test_fleet_output_failure_returns_two(self) -> None:
        code, stdout, stderr = self.run_cli(["status", "--output", str(self.root)])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("could not write", stderr)

    def test_direct_list_still_prints_and_writes_completion_cache(self) -> None:
        code, stdout, stderr = self.run_cli(["list", "--format", "json"])
        self.assertEqual(code, 0, stderr)
        self.assertTrue(json.loads(stdout))
        self.assertTrue(read_environment_cache())
