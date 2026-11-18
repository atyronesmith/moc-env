"""Identity-provider sequencing and deferred-check regressions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import re
import tempfile
import unittest
from unittest.mock import patch
import os
from pathlib import Path

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.registry import EnvironmentRegistry, RegistryError
from moc_env.report import render_markdown, render_text

from fakes import (
    CrossRepoFakeGitHubClient,
    FakeGitHubClient,
    FullyConfiguredFakeGitHubClient,
    MultiWorkloadFakeGitHubClient,
)
from test_multi_workload_report import (
    TwoWorkloadBootImageClient,
    next_actions,
    result_counts,
)


WORKLOAD_VALUES = (
    "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
)


def _without_workload_client(text: str) -> str:
    return re.sub(
        r"(?ms)^bu_ist_demo_workload0 = \{.*?^\}\n?",
        "",
        text,
    )


def markdown_result_counts(text: str) -> tuple[int, int]:
    verdict = next(line for line in text.splitlines() if line.startswith("**"))
    if "No deployment gaps" in verdict:
        return 0, 0
    match = re.search(
        r"\*\*(\d+) blocking gaps, (\d+) advisories,", verdict
    )
    if match is None:
        raise AssertionError(f"unexpected Markdown verdict: {verdict}")
    return int(match.group(1)), int(match.group(2))


def markdown_next_actions(text: str) -> int:
    section = text.split("## Next actions", 1)[1].split("##", 1)[0]
    return len(re.findall(r"(?m)^\d+\. \*\*", section))


def registry_document(environment: str, entries: list[dict]) -> EnvironmentRegistry:
    return EnvironmentRegistry.from_document(
        {
            "defaults": {
                "required_local_cluster_components": [],
                "optional_local_cluster_components": [],
            },
            "environments": {
                environment: {"issue": 666, "deferred": entries}
            },
        }
    )


class DisabledMocssoClient(FullyConfiguredFakeGitHubClient):
    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/oac-apps" and path == WORKLOAD_VALUES:
            return text.replace("enabled: true", "enabled: false")
        return text


class AbsentMocssoClient(FullyConfiguredFakeGitHubClient):
    """Fully configured fixture with ``oauth.mocsso.enabled`` absent."""

    def __init__(self, identity_providers: list[dict] | None = None) -> None:
        super().__init__()
        self.identity_providers = identity_providers

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        text = super().get_file(repository, path, ref)
        if repository != "CCI-MOC/oac-apps" or path != WORKLOAD_VALUES:
            return text
        if self.identity_providers is None:
            replacement = ""
        else:
            replacement = "oauth:\n  identityProviders: " + json.dumps(
                self.identity_providers
            ) + "\n"
        return re.sub(r"(?m)^oauth:\n(?:  .*\n)+", replacement, text)


class MissingWorkloadClient(FullyConfiguredFakeGitHubClient):
    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        text = super().get_file(repository, path, ref)
        if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
            return _without_workload_client(text)
        return text


class DisabledMocssoWithoutClientClient(DisabledMocssoClient):
    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        text = FullyConfiguredFakeGitHubClient.get_file(self, repository, path, ref)
        if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
            return _without_workload_client(text)
        if repository == "CCI-MOC/oac-apps" and path == WORKLOAD_VALUES:
            return text.replace("enabled: true", "enabled: false")
        return text

    def pulls(self, repository: str, state: str = "all"):
        if repository == "CCI-MOC/moc-keycloak":
            yield {
                "number": 66,
                "title": "bu-ist-demo-infra workload0 client",
                "body": "Adds bu-ist-demo-workload0",
                "state": "open",
                "merged_at": None,
                "head": {"ref": "client", "sha": "a" * 40},
                "html_url": "https://github.com/CCI-MOC/moc-keycloak/pull/66",
            }

    def pr_files(self, repository: str, number: int):
        yield {"filename": "main.tf"}


class IdentityProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    def report(self, client, include_prs: bool = False):
        return StatusChecker(client, include_prs=include_prs).run(
            Environment(name="bu-ist-demo", issue_number=666)
        )

    def identity(self, report):
        return next(
            check
            for check in report.checks
            if check.id == "workload.identity_provider"
        )

    def test_disabled_mocsso_with_matching_client_is_advisory_and_re_enables(self):
        check = self.identity(self.report(DisabledMocssoClient()))
        self.assertEqual(check.state, "value_mismatch")
        self.assertEqual(check.severity, "advisory")
        self.assertIn("no identity provider", check.reason)
        self.assertIn("re-enable oauth.mocsso.enabled", check.next_action)

    def test_disabled_mocsso_without_client_names_open_pr(self):
        report = self.report(
            DisabledMocssoWithoutClientClient(), include_prs=True
        )
        check = self.identity(report)
        self.assertEqual(check.severity, "advisory")
        self.assertIn("add the client in moc-keycloak first", check.next_action)
        self.assertIn("moc-keycloak#66", check.next_action)

    def test_enabled_mocsso_without_client_has_one_blocking_gap_and_action(self):
        report = self.report(MissingWorkloadClient())
        identity = self.identity(report)
        keycloak = next(
            check
            for check in report.checks
            if check.id == "workload.keycloak_oidc_client"
        )
        self.assertEqual(identity.state, "blocked")
        self.assertEqual(identity.severity, "advisory")
        self.assertEqual(keycloak.severity, "blocking")
        self.assertIn("BEFORE", keycloak.next_action)
        self.assertIn("client secret", keycloak.next_action)
        self.assertIn("Merge and apply", keycloak.next_action)
        data = report.to_dict()
        text = render_text(data)
        self.assertEqual(result_counts(text), (1, 0))
        actions = next_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertIn("keycloak oidc client", actions[0].lower())
        self.assertIn("merge and apply", actions[0].lower())
        self.assertIn("before enabling", actions[0].lower())

    def test_enabled_mocsso_with_matching_client_passes(self):
        check = self.identity(self.report(FullyConfiguredFakeGitHubClient()))
        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.severity, "info")

    def test_absent_mocsso_with_empty_identity_providers_is_disabled_advisory(self):
        absent_report = self.report(AbsentMocssoClient(identity_providers=[]))
        absent = self.identity(absent_report)
        disabled = self.identity(self.report(DisabledMocssoClient()))

        self.assertEqual(absent.state, disabled.state)
        self.assertEqual(absent.severity, "advisory")
        self.assertEqual(absent.reason, disabled.reason)
        self.assertEqual(result_counts(render_text(absent_report.to_dict())), (0, 1))

    def test_absent_mocsso_with_explicit_identity_provider_passes(self):
        report = self.report(
            AbsentMocssoClient(
                identity_providers=[{"name": "local", "type": "Local"}]
            )
        )
        check = self.identity(report)

        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.severity, "info")
        self.assertIn("explicit identity provider is configured", check.reason)
        text = render_text(report.to_dict())
        self.assertEqual(result_counts(text), (0, 0))
        self.assertEqual(next_actions(text), [])

    def test_disabled_mocsso_without_client_is_one_advisory_and_no_blocking(self):
        data = self.report(DisabledMocssoWithoutClientClient()).to_dict()
        text = render_text(data)
        self.assertEqual(result_counts(text), (0, 1))
        self.assertEqual(len(next_actions(text)), 1)


class DeferredCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    @staticmethod
    def registry(check: str, reason: str = "waiting on the next review") -> EnvironmentRegistry:
        return registry_document(
            "bu-ist-demo",
            [{"check": check, "reason": reason}],
        )

    def report(self, registry: EnvironmentRegistry):
        return StatusChecker(
            CrossRepoFakeGitHubClient(), include_prs=False, registry=registry
        ).run(Environment(name="bu-ist-demo", issue_number=666))

    def test_deferred_gap_is_excluded_from_counts_and_reported(self):
        report = self.report(self.registry("hub.component_values"))
        data = report.to_dict()
        check = next(
            item
            for item in data["checks"]
            if item["id"] == "hub.component_values"
        )
        self.assertTrue(check["deferred"])
        self.assertEqual(check["defer_reason"], "waiting on the next review")
        self.assertEqual(data["summary"]["severity_counts"].get("blocking", 0), 4)
        text = render_text(data)
        markdown = render_markdown(data)
        self.assertIn("Deferred", text)
        self.assertIn("waiting on the next review", " ".join(text.split()))
        self.assertIn("## Deferred", markdown)
        self.assertIn("waiting on the next review", markdown)
        next_section = text.split("NEXT", 1)[1].split("Deferred", 1)[0]
        self.assertNotIn("[oac-apps] hub component", next_section)

    def test_resolved_deferred_item_is_reported_once(self):
        report = self.report(self.registry("workload.keycloak_oidc_client"))
        data = report.to_dict()
        check = next(
            item
            for item in data["checks"]
            if item["id"] == "workload.keycloak_oidc_client"
        )
        self.assertTrue(check["deferred_resolved"])
        for output in (render_text(data), render_markdown(data)):
            compact = " ".join(output.split())
            self.assertEqual(
                compact.count(
                    "deferred item resolved; remove it from the registry"
                ),
                1,
            )

    def test_deferred_json_flag_is_only_present_for_deferred_checks(self):
        data = json.loads(
            json.dumps(self.report(self.registry("hub.component_values")).to_dict())
        )
        flags = {
            item["id"]: item.get("deferred")
            for item in data["checks"]
        }
        self.assertTrue(flags["hub.component_values"])
        self.assertNotIn("deferred", next(
            item for item in data["checks"]
            if item["id"] == "workload.keycloak_oidc_client"
        ))

    def test_cluster_scoped_deferral_leaves_the_other_workload_gap(self):
        environment = Environment(
            name="oac-dev",
            workload_clusters=("oac-dev-workload0", "oac-dev-workload1"),
        )
        registry = registry_document(
            "oac-dev",
            [
                {
                    "check": "workload.boot_image",
                    "cluster": "oac-dev-workload1",
                    "reason": "workload1 image is still being built",
                }
            ],
        )
        data = StatusChecker(
            TwoWorkloadBootImageClient(), include_prs=False, registry=registry
        ).run(environment).to_dict()
        checks = {
            check["cluster"]: check
            for check in data["checks"]
            if check["id"] == "workload.boot_image"
        }
        self.assertFalse(checks["oac-dev-workload0"].get("deferred", False))
        self.assertTrue(checks["oac-dev-workload1"]["deferred"])
        text = render_text(data)
        actions = next_actions(text)
        self.assertTrue(
            any(
                "oac-dev-workload0" in action
                and "boot_image_url" in action
                for action in actions
            )
        )
        self.assertFalse(
            any(
                "oac-dev-workload1" in action
                and "boot_image_url" in action
                for action in actions
            )
        )
        blocking, advisory = result_counts(text)
        self.assertEqual(len(actions), blocking + advisory)

    def test_workload_deferral_without_cluster_is_rejected(self):
        environment = Environment(
            name="oac-dev",
            workload_clusters=("oac-dev-workload0", "oac-dev-workload1"),
        )
        registry = registry_document(
            "oac-dev",
            [{"check": "workload.boot_image", "reason": "ambiguous"}],
        )
        with self.assertRaisesRegex(RegistryError, "cluster"):
            StatusChecker(
                TwoWorkloadBootImageClient(),
                include_prs=False,
                registry=registry,
            ).run(environment)

    def test_expired_deferral_counts_again_and_is_reported(self):
        registry = registry_document(
            "bu-ist-demo",
            [
                {
                    "check": "hub.component_values",
                    "reason": "waiting on the next review",
                    "until": "2020-01-01",
                }
            ],
        )
        report = StatusChecker(
            CrossRepoFakeGitHubClient(),
            include_prs=False,
            registry=registry,
            clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc),
        ).run(Environment(name="bu-ist-demo", issue_number=666))
        data = report.to_dict()
        check = next(
            item
            for item in data["checks"]
            if item["id"] == "hub.component_values"
        )
        self.assertFalse(check.get("deferred", False))
        self.assertTrue(check.get("deferred_expired"))
        text = render_text(data)
        self.assertIn("deferral expired 2020-01-01", " ".join(text.split()))
        self.assertIn("hub.component_values", text.split("\nNEXT\n", 1)[1])
        self.assertEqual(result_counts(text), (5, 1))

    def test_next_action_count_matches_result_for_every_status_fixture(self):
        cases = (
            (FakeGitHubClient(), Environment(name="bu-ist-demo", issue_number=666)),
            (
                FullyConfiguredFakeGitHubClient(),
                Environment(name="bu-ist-demo", issue_number=666),
            ),
            (MultiWorkloadFakeGitHubClient(), Environment(name="dizzy")),
            (
                TwoWorkloadBootImageClient(),
                Environment(
                    name="oac-dev",
                    workload_clusters=(
                        "oac-dev-workload0",
                        "oac-dev-workload1",
                    ),
                ),
            ),
        )
        for client, environment in cases:
            with self.subTest(environment=environment.name):
                data = StatusChecker(client, include_prs=False).run(
                    environment
                ).to_dict()
                text = render_text(data)
                blocking, advisory = result_counts(text)
                self.assertEqual(len(next_actions(text)), blocking + advisory)
                markdown = render_markdown(data)
                blocking, advisory = markdown_result_counts(markdown)
                self.assertEqual(
                    markdown_next_actions(markdown), blocking + advisory
                )
        fixtures = Path(__file__).parent / "fixtures"
        for path in sorted((fixtures / "text").glob("*.txt")):
            with self.subTest(fixture=path.name):
                text = path.read_text(encoding="utf-8")
                blocking, advisory = result_counts(text)
                self.assertEqual(len(next_actions(text)), blocking + advisory)
        for path in sorted((fixtures / "markdown").glob("*.md")):
            with self.subTest(fixture=path.name):
                text = path.read_text(encoding="utf-8")
                blocking, advisory = markdown_result_counts(text)
                self.assertEqual(
                    markdown_next_actions(text), blocking + advisory
                )


if __name__ == "__main__":
    unittest.main()
