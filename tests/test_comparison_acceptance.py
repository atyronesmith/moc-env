"""Adversarial set and inventory-evidence acceptance tests."""

from __future__ import annotations

import contextlib
import copy
from dataclasses import replace
import io
import unittest
from unittest.mock import patch

import yaml

from moc_env import cli
from moc_env.compare import compare_environment, compare_workload
from moc_env.export import build_environment_export, build_workload_export
from moc_env.model import Environment
from moc_env.observed import (
    read_apps_observation,
    read_infra_observation,
    read_issue_observation,
)
from moc_env.validate import validate_environment
from test_desired_state_review_fixes import InventoryClient, inventory_client


class NoHubInventoryClient(InventoryClient):
    workloads = ("workload1",)

    def get_file(self, repository, path, ref="main"):
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            data = yaml.safe_load(text)
            del data["all"]["children"]["bu_ist_demo_clusters"]["children"]["bu_ist_demo_infra"]
            return yaml.safe_dump(data)
        return text


class NoWorkloadInventoryClient(InventoryClient):
    """Retain GitOps declarations while removing the inventory workload."""

    workloads = ("workload0",)

    def get_file(self, repository, path, ref="main"):
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            data = yaml.safe_load(text)
            del data["all"]["children"]["bu_ist_demo_clusters"]["children"]["bu_ist_demo_workload0"]
            return yaml.safe_dump(data)
        return text


class EmptyHubInventoryClient(InventoryClient):
    workloads = ("workload1",)

    def get_file(self, repository, path, ref="main"):
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            data = yaml.safe_load(text)
            data["all"]["children"]["bu_ist_demo_clusters"]["children"]["bu_ist_demo_infra"] = {
                "vars": {"cluster": "bu-ist-demo-infra"}, "children": {},
            }
            return yaml.safe_dump(data)
        return text


class ComparisonAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.environment = Environment("bu-ist-demo", 666)

    def observe(self, client):
        infra = read_infra_observation(client, self.environment)
        apps = read_apps_observation(client, self.environment, include_pull_requests=False)
        issue = read_issue_observation(client, self.environment)
        return infra, apps, issue

    def bundle(self, client):
        infra, apps, issue = self.observe(client)
        return build_environment_export(self.environment, issue, infra, apps)

    def compare(self, document, client):
        infra, apps, issue = self.observe(client)
        return compare_environment(document, self.environment, issue, infra, apps)

    def test_additional_actual_workloads_do_not_match_even_when_desired_is_empty(self):
        for desired in ((), ("workload0",)):
            with self.subTest(desired=desired):
                document = self.bundle(inventory_client(desired)())
                self.assertTrue(validate_environment(document).valid)
                report = self.compare(document, InventoryClient())
                self.assertEqual(report.overall_state, "DIFFERENCES FOUND")
                self.assertIn("unexpected_in_main", {item.state for item in report.checks})

    def test_missing_actual_workload_is_reported_as_missing(self):
        document = self.bundle(inventory_client(("workload1",))())
        report = self.compare(document, inventory_client(())())
        self.assertEqual(report.overall_state, "DIFFERENCES FOUND")
        self.assertIn("missing_from_main", {item.state for item in report.checks})

    def test_missing_and_unexpected_workloads_are_both_reported(self):
        document = self.bundle(inventory_client(("workload1",))())
        report = self.compare(document, inventory_client(("workload0",))())
        states = {item.state for item in report.checks}
        self.assertIn("missing_from_main", states)
        self.assertIn("unexpected_in_main", states)

    def test_workload_set_order_does_not_matter(self):
        document = self.bundle(InventoryClient())
        document["spec"]["workloadClusters"].reverse()
        self.assertEqual(self.compare(document, InventoryClient()).overall_state, "MATCHES MAIN")

    def test_selected_observations_cannot_hide_other_discovered_workloads(self):
        document = self.bundle(inventory_client(("workload0",))())
        selected = replace(self.environment, workload_clusters=("bu-ist-demo-workload0",))
        client = InventoryClient()
        infra = read_infra_observation(client, selected)
        self.assertNotIn("bu-ist-demo-workload1", infra.clusters)
        self.assertIn("bu-ist-demo-workload1", infra.discovered_workload_clusters)
        _, apps, issue = self.observe(client)
        report = compare_environment(document, selected, issue, infra, apps)
        self.assertIn("unexpected_in_main", {item.state for item in report.checks})

    def test_real_hub_only_environment_still_matches(self):
        client = inventory_client(())()
        document = self.bundle(client)
        self.assertTrue(validate_environment(document).valid)
        self.assertEqual(self.compare(document, client).overall_state, "MATCHES MAIN")

    def test_absent_hub_placeholder_does_not_establish_inventory_presence(self):
        client = NoHubInventoryClient()
        infra, apps, issue = self.observe(client)
        self.assertFalse(infra.clusters[self.environment.infra_cluster].group_found.value)
        document = build_environment_export(self.environment, issue, infra, apps)
        report = compare_environment(document, self.environment, issue, infra, apps)
        present = next(item for item in report.checks if item.field == "spec.hubCluster.inventoryPresent")
        self.assertNotEqual(present.state, "matches_main")
        self.assertFalse(present.current)
        self.assertEqual(report.overall_state, "DIFFERENCES FOUND")

    def test_workload_comparison_rejects_absent_parent_hub_placeholder(self):
        infra, apps, _ = self.observe(NoHubInventoryClient())
        document = build_workload_export(self.environment, "bu-ist-demo-workload1", infra, apps)
        report = compare_workload(document, infra, apps)
        parent = next(item for item in report.checks if item.field == "metadata.parentInfraCluster")
        self.assertEqual(parent.state, "missing_from_main")
        self.assertEqual(report.overall_state, "DIFFERENCES FOUND")

    def test_real_hub_with_zero_hosts_still_establishes_presence(self):
        infra, apps, issue = self.observe(EmptyHubInventoryClient())
        hub = infra.clusters[self.environment.infra_cluster]
        self.assertTrue(hub.group_found.value)
        self.assertFalse(hub.hosts.value)
        bundle = build_environment_export(self.environment, issue, infra, apps)
        self.assertEqual(
            compare_environment(bundle, self.environment, issue, infra, apps).overall_state,
            "MATCHES MAIN",
        )
        workload = build_workload_export(self.environment, "bu-ist-demo-workload1", infra, apps)
        self.assertEqual(compare_workload(workload, infra, apps).overall_state, "MATCHES MAIN")

    def test_cli_missing_hub_produces_a_comparison_failure(self):
        document = self.bundle(NoHubInventoryClient())
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubClient", NoHubInventoryClient),
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "load_environment_document", return_value=(document, validate_environment(document))),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(["check-environment", "in-memory.yaml", "--no-prs"])
        self.assertEqual(code, 1, stderr.getvalue())

    def test_environment_workload_placeholder_is_not_present(self):
        document = self.bundle(inventory_client(("workload0",))())
        report = self.compare(document, NoWorkloadInventoryClient())
        present = next(
            item for item in report.checks
            if item.field == "spec.workloadClusters[0].inventoryPresent"
        )
        self.assertFalse(present.current)
        self.assertNotEqual(present.state, "matches_main")

    def test_workload_placeholder_is_reported_missing_not_present(self):
        infra, apps, _ = self.observe(inventory_client(("workload0",))())
        document = build_workload_export(self.environment, "bu-ist-demo-workload0", infra, apps)
        absent, _, _ = self.observe(NoWorkloadInventoryClient())
        report = compare_workload(document, absent, apps)
        name = next(item for item in report.checks if item.field == "metadata.name")
        self.assertEqual(name.state, "missing_from_main")
        self.assertNotEqual(
            next(item for item in report.checks if item.field == "metadata.name.value").state,
            "matches_main",
        )

    def test_cli_reports_omitted_workloads_as_failure(self):
        document = self.bundle(InventoryClient())
        for desired_count in (0, 1):
            with self.subTest(desired_count=desired_count):
                changed = copy.deepcopy(document)
                changed["spec"]["workloadClusters"] = changed["spec"]["workloadClusters"][:desired_count]
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch.object(cli, "GitHubClient", InventoryClient),
                    patch.object(cli, "_resolve_github_token", return_value=None),
                    patch.object(cli, "load_environment_document", return_value=(changed, validate_environment(changed))),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    code = cli.main(["check-environment", "in-memory.yaml", "--no-prs"])
                self.assertEqual(code, 1, stderr.getvalue())
