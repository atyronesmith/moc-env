from __future__ import annotations

import copy
import json
import unittest

from moc_env.compare import compare_infra
from moc_env.export import build_infra_export
from moc_env.model import Environment
from moc_env.observed import read_apps_observation, read_infra_observation
from moc_env.plan import build_infra_change_plan

from fakes import FakeGitHubClient


class InfraChangePlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = Environment(name="bu-ist-demo", issue_number=666)
        self.client = FakeGitHubClient()
        self.observation = read_infra_observation(self.client, self.environment)
        self.apps = read_apps_observation(self.client, self.environment)
        self.document = build_infra_export(
            self.environment,
            self.observation,
        )

    def report(self, document=None):
        return compare_infra(
            document or self.document,
            self.environment,
            self.observation,
            self.apps,
        )

    def test_matching_state_with_open_pr_requires_no_changes(self) -> None:
        plan = build_infra_change_plan(self.document, self.report())

        self.assertEqual(plan.overall_state, "NO CHANGES REQUIRED")
        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.to_dict()["summary"]["change_count"], 0)

    def test_value_mismatch_becomes_an_update_with_source_provenance(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["value"] = "10.20.27.99"

        plan = build_infra_change_plan(document, self.report(document))

        self.assertEqual(len(plan.changes), 1)
        change = plan.changes[0]
        self.assertEqual(change.repository, "CCI-MOC/oac-infra")
        self.assertEqual(
            change.path,
            "hub-images/group_vars/bu-ist-demo-infra/vars.yml",
        )
        self.assertEqual(change.base_ref, "main")
        self.assertEqual(change.branch, "moc-env/bu-ist-demo-infra-oac-infra")
        self.assertEqual(change.field, "spec.variables.fields.api_ip.value")
        self.assertEqual(change.operation, "update")
        self.assertEqual(change.desired, "10.20.27.99")
        self.assertEqual(change.current, "10.20.27.11")
        self.assertEqual(change.depends_on, ())

    def test_missing_cluster_becomes_a_create(self) -> None:
        document = copy.deepcopy(self.document)
        cluster = document["spec"]["inventory"]["clusters"]["bu-ist-demo-infra"]
        document["spec"]["inventory"]["clusters"]["new-cluster-infra"] = cluster

        report = compare_infra(
            document,
            Environment(name="new-cluster"),
            self.observation,
            None,
        )
        plan = build_infra_change_plan(document, report)

        creates = [change for change in plan.changes if change.operation == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(
            creates[0].field,
            "spec.inventory.clusters.new-cluster-infra",
        )
        self.assertEqual(creates[0].repository, "CCI-MOC/oac-infra")
        self.assertEqual(creates[0].path, "infra/inventory/00hosts.yaml")

    def test_unexpected_cluster_becomes_a_delete(self) -> None:
        document = copy.deepcopy(self.document)
        del document["spec"]["inventory"]["clusters"]["bu-ist-demo-workload0"]

        report = compare_infra(
            document,
            self.environment,
            self.observation,
            None,
        )
        plan = build_infra_change_plan(document, report)

        deletes = [change for change in plan.changes if change.operation == "delete"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(
            deletes[0].field,
            "spec.inventory.clusters.bu-ist-demo-workload0",
        )
        self.assertEqual(deletes[0].path, "infra/inventory/00hosts.yaml")

    def test_unsupported_value_becomes_manual_review(self) -> None:
        document = copy.deepcopy(self.document)
        del document["spec"]["variables"]["fields"]["dns_ip"]["value"]

        report = compare_infra(
            document,
            self.environment,
            self.observation,
            None,
        )
        plan = build_infra_change_plan(document, report)

        reviews = [
            change for change in plan.changes if change.operation == "manual_review"
        ]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(
            reviews[0].field,
            "spec.variables.fields.dns_ip.value",
        )
        self.assertEqual(reviews[0].path, "hub-images/group_vars/bu-ist-demo-infra/vars.yml")

    def test_plan_serializes_to_json(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["value"] = "10.20.27.99"

        plan = build_infra_change_plan(document, self.report(document))
        data = json.loads(json.dumps(plan.to_dict()))

        self.assertEqual(data["kind"], "Infra")
        self.assertEqual(data["overall_state"], "CHANGES PLANNED")
        self.assertEqual(data["summary"]["operation_counts"], {"update": 1})
        self.assertEqual(data["summary"]["repository_counts"], {"CCI-MOC/oac-infra": 1})
        self.assertEqual(data["changes"][0]["depends_on"], [])
