"""Offline commit-history links reuse observed paths and never fetch commits."""

from __future__ import annotations

from contextlib import ExitStack
import copy
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

from moc_env import observed
from moc_env.checks import StatusChecker
from moc_env.github import GitHubClient, GitHubError
from moc_env.model import Environment, StatusReport
from moc_env.report import render_json, render_markdown, render_text


APPS = "example-lab/aurora-apps"
INFRA = "example-lab/aurora-infra"
IDENTITY = "example-lab/aurora-identity"
HUB = "aurora-infra"
WORKLOAD = "aurora-workload0"
OTHER_WORKLOAD = "aurora-workload1"
ENVIRONMENT = Environment(name="aurora", workload_clusters=(WORKLOAD, OTHER_WORKLOAD))


class LocalRepositoryClient(GitHubClient):
    def __init__(self, paths, **kwargs):
        super().__init__(**kwargs)
        self.paths = paths
        self.tree_reads = []
        self.pull_failure = False

    def get_tree(self, repository, ref="main"):
        self.tree_reads.append(repository)
        return dict.fromkeys(self.paths, {})

    def get_file(self, repository, path, ref="main"):
        return "nodePools: []\n"

    def pulls(self, repository, state="all"):
        if self.pull_failure:
            raise GitHubError("Listing unavailable")
        return iter(())


class HistoryLinksTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": directory.name}))
        stack.enter_context(patch.multiple(
            observed, OAC_APPS_REPOSITORY=APPS,
            OAC_INFRA_REPOSITORY=INFRA, MOC_KEYCLOAK_REPOSITORY=IDENTITY,
        ))
        self.http = stack.enter_context(patch(
            "moc_env.github.urlopen", side_effect=AssertionError("Unexpected HTTP request")
        ))
        self.paths = [
            f"{prefix}/{HUB}/{suffix}"
            for prefix in ("hosted-clusters", "values", "apps")
            for suffix in (
                "hub-settings.yaml", f"{WORKLOAD}/settings.yaml",
                f"{OTHER_WORKLOAD}/settings.yaml",
            )
        ] + ["values/other-aurora-infra/settings.yaml"]

    def read(self, scope="environment", *, paths=None, environment=ENVIRONMENT, **kwargs):
        client = LocalRepositoryClient(self.paths if paths is None else paths, **kwargs)
        apps = observed.read_apps_observation(
            client, environment, include_pull_requests=False, path_scope=scope,
        )
        self.assertEqual(client.tree_reads, [APPS])
        return client, apps

    @staticmethod
    def report(apps, **kwargs):
        return StatusReport(
            environment=ENVIRONMENT, checks=[], overall_state="declared_in_main",
            history_links=apps.history_links, **kwargs,
        ).to_dict()

    @staticmethod
    def app_paths(apps):
        return [link["path"] for link in apps.history_links if link["repository"] == APPS]

    def test_hub_scope_includes_only_existing_hub_directories(self):
        _, apps = self.read("hub")
        self.assertEqual(self.app_paths(apps), [
            f"hosted-clusters/{HUB}/", f"values/{HUB}/", f"apps/{HUB}/",
        ])
        _, sparse = self.read("hub", paths=[
            f"hosted-clusters/{HUB}/{WORKLOAD}/settings.yaml",
            f"values/{HUB}-other/settings.yaml", f"apps/{HUB}",
        ])
        self.assertEqual(self.app_paths(sparse), [f"hosted-clusters/{HUB}/"])

    def test_workload_scope_links_only_the_selected_workload(self):
        environment = Environment(name="aurora", workload_clusters=(WORKLOAD,))
        _, apps = self.read("workload", environment=environment)
        self.assertEqual(self.app_paths(apps), [
            f"hosted-clusters/{HUB}/{WORKLOAD}/",
            f"values/{HUB}/{WORKLOAD}/", f"apps/{HUB}/{WORKLOAD}/",
        ])

    def test_workload_scope_includes_each_selected_workload_without_hub_duplicates(self):
        _, apps = self.read("workload")
        self.assertEqual(self.app_paths(apps), [
            f"{prefix}/{HUB}/{workload}/"
            for workload in (WORKLOAD, OTHER_WORKLOAD)
            for prefix in ("hosted-clusters", "values", "apps")
        ])

    def test_environment_scope_links_hub_directories_not_individual_workloads(self):
        _, apps = self.read()
        self.assertEqual(self.app_paths(apps), [
            f"hosted-clusters/{HUB}/", f"values/{HUB}/", f"apps/{HUB}/",
        ])
        self.assertTrue(all(not link["shared"] for link in apps.history_links[:3]))

    def test_shared_files_are_always_present_and_marked_in_text_and_markdown(self):
        _, apps = self.read(paths=[])
        self.assertEqual([
            (link["repository"], link["path"], link["shared"])
            for link in apps.history_links
        ], [
            (INFRA, observed.INVENTORY_PATH, True),
            (INFRA, observed.HUB_INVENTORY_PATH, True),
            (IDENTITY, observed.KEYCLOAK_PATH, True),
        ])
        for output in (render_text(self.report(apps)), render_markdown(self.report(apps))):
            self.assertEqual(output.count("(shared by all clusters)"), 3)
            for link in apps.history_links:
                self.assertIn(link["path"], output)
                self.assertIn(link["url"], output)

    def test_urls_are_well_formed_and_always_use_main_even_for_a_pull_ref(self):
        client, apps = self.read(refs={APPS: "pull/17/head"})
        self.assertEqual(client.ref_for(APPS), "pull/17/head")
        for link in apps.history_links:
            self.assertEqual(
                link["url"],
                f"https://github.com/{link['repository']}/commits/main/{link['path']}",
            )
            parsed = urlsplit(link["url"])
            self.assertEqual((parsed.scheme, parsed.netloc), ("https", "github.com"))
            self.assertNotIn("//", parsed.path)
            self.assertNotIn("pull/17/head", link["url"])

    def test_all_renderers_use_the_stored_list_without_http_or_mutation(self):
        client, apps = self.read(offline=True)
        report = self.report(apps)
        before = copy.deepcopy(report)
        self.assertEqual(json.loads(render_json(report))["history_links"], list(apps.history_links))
        for output in (render_text(report), render_markdown(report)):
            self.assertIn("These are GitHub commit histories on main.", output)
            for link in report["history_links"]:
                self.assertIn(link["url"], output)
        self.assertEqual(report, before)
        self.assertEqual(client.requests_made, 0)
        self.http.assert_not_called()

    def test_offline_unauthenticated_skipped_and_unavailable_prs_still_show_history(self):
        for include_prs, unavailable in ((False, False), (True, True)):
            with self.subTest(include_prs=include_prs):
                client = LocalRepositoryClient(self.paths, offline=True)
                client.pull_failure = unavailable
                self.assertFalse(client.authenticated)
                apps = observed.read_apps_observation(
                    client, ENVIRONMENT, include_pull_requests=include_prs,
                )
                report = self.report(
                    apps, pull_requests_skipped=not include_prs,
                    pull_requests_unavailable=apps.pull_requests_unavailable,
                )
                text, markdown = render_text(report), render_markdown(report)
                self.assertIn("RECENT CHANGES", text)
                self.assertIn("## Recent changes", markdown)
                self.assertLess(text.index("RECENT CHANGES"), text.index("\nSources"))
                self.assertLess(markdown.index("## Recent changes"), markdown.index("## Sources"))
                self.assertLess(text.index("Pull requests:"), text.index("RECENT CHANGES"))
                self.http.assert_not_called()

    def test_status_checker_carries_observed_links_into_the_report_dictionary(self):
        client, apps = self.read()
        observation = SimpleNamespace(
            environment=ENVIRONMENT, issue=None, infra=None, keycloak=None, apps=apps,
        )
        checker = StatusChecker(client, include_prs=False)
        with (
            patch("moc_env.checks.read_environment_observation", return_value=observation),
            patch.object(checker, "_infra_checks", return_value=([], ENVIRONMENT)),
            patch.object(checker, "_keycloak_checks", return_value=[]),
            patch.object(checker, "_apps_checks", return_value=[]),
            patch.object(checker, "_description_context", return_value=None),
            patch("moc_env.checks.cross_repository_checks", return_value=[]),
            patch("moc_env.checks.attach_suggestions"),
        ):
            report = checker.run(ENVIRONMENT).to_dict()
        self.assertEqual(report["history_links"], list(apps.history_links))
        self.http.assert_not_called()
