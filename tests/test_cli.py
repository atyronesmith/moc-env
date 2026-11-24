from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from moc_env import cli, cli_support
from moc_env.github import GitHubClient, GitHubError, RateLimitError

from fakes import (
    CrossRepoFakeGitHubClient,
    FakeGitHubClient,
    FullyConfiguredFakeGitHubClient,
    MultiWorkloadFakeGitHubClient,
)


class CliDispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        cache_directory = tempfile.TemporaryDirectory()
        self.addCleanup(cache_directory.cleanup)
        environment = patch.dict(
            os.environ,
            {"MOC_ENV_CACHE_DIR": cache_directory.name},
        )
        environment.start()
        self.addCleanup(environment.stop)

    def run_cli(
        self,
        arguments: list[str],
        client_class=FakeGitHubClient,
        clock=None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli, "_resolve_github_token", return_value=None),
            patch.object(cli, "GitHubClient", client_class),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(arguments, clock=clock)
        diagnostic = stderr.getvalue()
        accounting = "GitHub API: 0 requests, 0 counted against quota, 0 from cache\n"
        if "GitHub API:" in diagnostic:
            self.assertTrue(diagnostic.endswith(accounting), diagnostic)
            diagnostic = diagnostic.removesuffix(accounting)
        return exit_code, stdout.getvalue(), diagnostic

    def test_list_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["list"])
        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo", stdout)
        self.assertIn("moc-env status-hub bu-ist-demo", stdout)
        self.assertIn(
            "moc-env status-workload bu-ist-demo --workload workload0",
            stdout,
        )
        self.assertEqual(stderr, "")

    def test_diff_complete_and_incomplete_fixture_exits_zero(self) -> None:
        class AlternatingDiffClient(FullyConfiguredFakeGitHubClient):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.report_count = 0
                self.oac_apps_trees = 0

            def get_json(self, path_or_url):
                self.report_count += 1
                return super().get_json(path_or_url)

            @property
            def complete_report(self) -> bool:
                return self.report_count == 1

            def get_tree(self, repository: str, ref: str = "main"):
                tree = super().get_tree(repository, ref)
                if repository == "CCI-MOC/oac-apps":
                    self.oac_apps_trees += 1
                if (
                    repository == "CCI-MOC/oac-apps"
                    and self.oac_apps_trees > 1
                ):
                    return {}
                return tree

        exit_code, stdout, stderr = self.run_cli(
            ["diff", "bu-ist-demo", "bu-ist-demo"],
            client_class=AlternatingDiffClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("bu-ist-demo → bu-ist-demo", stdout)
        self.assertIn("Passing only in bu-ist-demo:", stdout)
        self.assertIn("Files only in bu-ist-demo:", stdout)
        self.assertIn("hub.component_values", stdout)

    def test_diff_ref_applies_only_to_second_environment_and_keeps_sources_distinct(self) -> None:
        selected_refs: list[str] = []

        class RefTrackingClient(CrossRepoFakeGitHubClient):
            def get_tree(self, repository: str, ref: str = "main"):
                if repository == "CCI-MOC/oac-apps":
                    selected_refs.append(self.ref_for(repository))
                return super().get_tree(repository, ref)

        exit_code, stdout, stderr = self.run_cli(
            [
                "diff",
                "bu-ist-demo",
                "bu-ist-demo",
                "--format",
                "json",
                "--ref",
                "oac-apps=pull/246/head",
            ],
            client_class=RefTrackingClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("main", selected_refs)
        self.assertIn("pull/246/head", selected_refs)
        self.assertLess(selected_refs.index("main"), selected_refs.index("pull/246/head"))

        diff = json.loads(stdout)
        apps_sources = {
            source["ref"]
            for source in diff["metadata"]["sources"]
            if source["repository"] == "CCI-MOC/oac-apps"
        }
        self.assertEqual(apps_sources, {"main", "pull/246/head"})

    def test_diff_invalid_ref_fails_before_credentials_or_client(self) -> None:
        with (
            patch.object(cli, "_resolve_github_token", side_effect=AssertionError("credentials must not resolve")),
            patch.object(cli, "GitHubClient", side_effect=AssertionError("client must not initialize")),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["diff", "bu-ist-demo", "bu-ist-demo", "--ref", "not-a-ref"])
        self.assertEqual(raised.exception.code, 2)

    def test_top_level_help_lists_every_command(self) -> None:
        rendered = cli.build_parser().format_help()

        self.assertIn("Commands:", rendered)
        for command in (
            "status",
            "status-hub",
            "status-workload",
            "list",
            "export-infra",
            "export-workload",
            "export-environment",
            "validate",
            "check-infra",
            "check-workload",
            "check-environment",
            "plan-infra",
            "document-values",
            "refresh-doc-catalog",
            "discover-values",
            "completion",
        ):
            with self.subTest(command=command):
                self.assertIn(command, rendered)

    def test_no_arguments_prints_command_help(self) -> None:
        for arguments in ([], ["--help"], ["-h"]):
            with self.subTest(arguments=arguments):
                exit_code, stdout, stderr = self.run_cli(arguments)

                self.assertEqual(exit_code, 0)
                self.assertIn("Commands:", stdout)
                self.assertIn("status", stdout)
                self.assertIn("status-hub", stdout)
                self.assertIn("status-workload", stdout)
                self.assertEqual(stderr, "")

    def test_environment_without_command_is_rejected(self) -> None:
        exit_code, _, stderr = self.run_cli(
            ["bu-ist-demo", "--format", "json", "--no-prs"]
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("unknown command: bu-ist-demo", stderr)
        self.assertIn("Commands:", stderr)

    def test_old_status_command_names_are_rejected(self) -> None:
        for command in ("hub-status", "work-status"):
            with self.subTest(command=command):
                exit_code, _, stderr = self.run_cli(
                    [command, "bu-ist-demo", "--format", "json", "--no-prs"]
                )

                self.assertEqual(exit_code, 2)
                self.assertIn(f"unknown command: {command}", stderr)

    def test_list_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(["list", "--format", "json"])
        self.assertEqual(exit_code, 0)
        clusters = json.loads(stdout)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["environment"], "bu-ist-demo")
        self.assertEqual(clusters[0]["cluster"], "bu-ist-demo-infra")
        self.assertEqual(clusters[0]["type"], "hub")
        self.assertEqual(clusters[1]["cluster"], "bu-ist-demo-workload0")
        self.assertEqual(clusters[1]["type"], "workload")

    def test_list_workload_command_targets_exact_cluster(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["list", "--format", "json"],
            client_class=MultiWorkloadFakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)
        rows = json.loads(stdout)
        row = next(item for item in rows if item["cluster"] == "oac-dev-workload1")
        self.assertEqual(
            row["status_command"],
            "moc-env status-workload oac-dev --workload workload1",
        )

    def test_no_auth_forces_unauthenticated_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "selectors.env"
            arguments = cli.build_list_parser().parse_args(
                ["--no-auth", "--env-file", str(env_file)]
            )
            with (
                patch.dict(os.environ, {"GITHUB_TOKEN": "direct-token-fixture"}),
                patch.object(
                    cli,
                    "CredentialResolver",
                    side_effect=AssertionError("resolver must not run"),
                ),
            ):
                self.assertIsNone(cli._resolve_github_token(arguments))

    def test_linux_without_token_or_gh_resolves_unauthenticated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "selectors.env"
            arguments = cli.build_list_parser().parse_args(
                ["--env-file", str(env_file)]
            )
            resolver = cli.CredentialResolver(
                platform="linux", environment={}, gh_executable=None
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(cli_support, "CredentialResolver", return_value=resolver),
            ):
                self.assertIsNone(cli._resolve_github_token(arguments))

    def test_unauthenticated_list_warns_once_with_remaining_quota(self) -> None:
        class QuotaReportingClient(FakeGitHubClient):
            def get_tree(self, repository: str, ref: str = "main"):
                if self.on_response:
                    self._record_headers({"X-RateLimit-Remaining": "59"})
                    self._record_headers({"X-RateLimit-Remaining": "58"})
                return super().get_tree(repository, ref)

        exit_code, _, stderr = self.run_cli(
            ["list", "--no-auth"],
            client_class=QuotaReportingClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stderr,
            "moc-env: no GitHub credential found; continuing unauthenticated "
            "(remaining request quota: 59)\n",
        )

    def test_status_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--format", "json", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["environment"]["name"], "bu-ist-demo")
        self.assertGreater(len(report["checks"]), 0)

    def test_status_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text", "--no-prs", "--verbose"]
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo · hub + workload ·", stdout)
        self.assertIn("Step 1:", stderr)
        self.assertIn("Step 14:", stderr)
        self.assertNotIn("Step 15:", stderr)
        self.assertNotIn("Action:", stderr)
        # NEXT now includes each gap's observed/expected evidence, not just an
        # imperative. The detailed ledger must still remain opt-in.
        self.assertLessEqual(len(stdout.splitlines()), 115)
        self.assertNotIn("DETAILED CHECKS", stdout)

    def test_verbose_prints_the_quota_counted_endpoints(self) -> None:
        class EndpointClient(FakeGitHubClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.counted_endpoints = [
                    "/repos/CCI-MOC/oac-apps/commits/main"
                ]

        exit_code, _, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text", "--no-prs", "--verbose"],
            client_class=EndpointClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("GitHub API quota-counted endpoints:", stderr)
        self.assertIn("GET /repos/CCI-MOC/oac-apps/commits/main", stderr)

    def test_status_fail_on_severity(self) -> None:
        cases = (
            ("never", 0),
            ("blocking", 1),
            ("advisory", 1),
        )
        for severity, expected_exit_code in cases:
            with self.subTest(severity=severity):
                exit_code, _, _ = self.run_cli(
                    ["status", "bu-ist-demo", "--no-prs", "--fail-on", severity]
                )
                self.assertEqual(exit_code, expected_exit_code)

        exit_code, _, _ = self.run_cli(
            ["status", "bu-ist-demo", "--no-prs", "--fail-on", "advisory"],
            client_class=FullyConfiguredFakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)

    def test_status_without_environment_prints_fleet_view(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["status"])

        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo", stdout)
        self.assertIn("moc-env status-hub bu-ist-demo", stdout)
        self.assertEqual(stderr, "")

    def test_text_golden_files(self) -> None:
        def fixed_clock():
            return datetime(2026, 11, 16, 12, 34, 56, tzinfo=timezone.utc)

        cases = (
            (
                ["status", "bu-ist-demo", "--format", "text", "--no-prs"],
                FakeGitHubClient,
                "environment-gaps.txt",
            ),
            (
                ["status", "bu-ist-demo", "--format", "text", "--no-prs"],
                FullyConfiguredFakeGitHubClient,
                "fully-configured.txt",
            ),
            (
                ["status", "dizzy", "--format", "text", "--no-prs"],
                MultiWorkloadFakeGitHubClient,
                "hub-no-workload.txt",
            ),
            (
                ["status", "bu-ist-demo", "--format", "text", "--no-prs", "--details"],
                FakeGitHubClient,
                "details.txt",
            ),
        )
        for arguments, client_class, filename in cases:
            with self.subTest(filename=filename):
                exit_code, stdout, _ = self.run_cli(
                    arguments,
                    client_class=client_class,
                    clock=fixed_clock,
                )
                golden = Path(__file__).parent / "fixtures" / "text" / filename
                self.assertEqual(exit_code, 0)
                self.assertEqual(stdout, golden.read_text(encoding="utf-8"))

    def test_file_overlap_alone_does_not_claim_a_fix(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text", "--prs"],
            client_class=CrossRepoFakeGitHubClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("fixed by open PR oac-apps#237", stdout)
        self.assertNotIn("fix in open PR", stdout)

    def test_markdown_golden_files(self) -> None:
        def fixed_clock():
            return datetime(2026, 11, 16, 12, 34, 56, tzinfo=timezone.utc)

        cases = (
            (
                ["status", "bu-ist-demo", "--format", "markdown", "--no-prs"],
                FakeGitHubClient,
                "environment-gaps.md",
            ),
            (
                ["status", "bu-ist-demo", "--format", "markdown", "--no-prs"],
                FullyConfiguredFakeGitHubClient,
                "fully-configured.md",
            ),
            (
                ["status", "dizzy", "--format", "markdown", "--no-prs"],
                MultiWorkloadFakeGitHubClient,
                "hub-no-workload.md",
            ),
            (
                ["status", "bu-ist-demo", "--format", "markdown", "--no-prs", "--details"],
                FakeGitHubClient,
                "details.md",
            ),
        )
        for arguments, client_class, filename in cases:
            with self.subTest(filename=filename):
                exit_code, stdout, _ = self.run_cli(
                    arguments,
                    client_class=client_class,
                    clock=fixed_clock,
                )
                golden = Path(__file__).parent / "fixtures" / "markdown" / filename
                self.assertEqual(exit_code, 0)
                self.assertEqual(stdout, golden.read_text(encoding="utf-8"))

    def test_hub_status_json_dispatch(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status-hub", "bu-ist-demo", "--format", "json", "--no-prs"]
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["scope"], "hub")
        checks = {check["check"] for check in report["checks"]}
        self.assertIn("Hub image variables", checks)
        self.assertNotIn("Workload hosted-cluster values", checks)

    def test_status_ref_selection_and_header(self) -> None:
        calls = []

        class RefTrackingClient(CrossRepoFakeGitHubClient):
            def get_tree(self, repository: str, ref: str = "main"):
                ref = self.ref_for(repository)
                calls.append((repository, ref))
                return super().get_tree(repository, ref)

        exit_code, stdout, _ = self.run_cli(
            [
                "status",
                "bu-ist-demo",
                "--format",
                "text",
                "--no-prs",
                "--ref",
                "oac-apps=pull/246/head",
            ],
            client_class=RefTrackingClient,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(("CCI-MOC/oac-apps", "pull/246/head"), calls)
        self.assertIn("NOT A REPORT ON MAIN", stdout)
        self.assertIn("oac-apps", stdout)
        self.assertIn("pull/246/head", stdout)

        exit_code, markdown, _ = self.run_cli(
            [
                "status",
                "bu-ist-demo",
                "--format",
                "markdown",
                "--no-prs",
                "--ref",
                "oac-apps=pull/246/head",
            ],
            client_class=RefTrackingClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("This is not a report on main", markdown)
        self.assertIn("pull/246/head", markdown)

    def test_work_status_text_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "status-workload",
                "bu-ist-demo",
                "--format",
                "text",
                "--no-prs",
                "--verbose",
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("bu-ist-demo · workload ·", stdout)
        self.assertIn("WORKLOAD PHASES", stdout)
        self.assertIn("WORKLOAD bu-ist-demo-workload0", stdout)
        self.assertNotIn("HUB bu-ist-demo-infra", stdout)
        self.assertIn("Step 1:", stderr)

    def test_status_reports_every_discovered_workload(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            [
                "status",
                "oac-dev",
                "--issue",
                "666",
                "--format",
                "json",
                "--no-prs",
            ],
            client_class=MultiWorkloadFakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertEqual(
            report["environment"]["workload_clusters"],
            ["oac-dev-workload0", "oac-dev-workload1"],
        )
        checks = {check["check"] for check in report["checks"]}
        self.assertIn("oac-dev-workload0 host inventory", checks)
        self.assertIn("oac-dev-workload1 host inventory", checks)
        self.assertIn("Workload hosted-cluster values", checks)

    def test_full_status_without_prs_uses_at_most_twelve_api_calls(self) -> None:
        class CountingClient(FakeGitHubClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.api_requests = 0

            def get_json(self, path_or_url):
                self.api_requests += 1
                parts = path_or_url.split("/")
                if len(parts) >= 6 and parts[1] == "repos":
                    repository = "/".join(parts[2:4])
                    if parts[4] == "commits":
                        return {"sha": self.SOURCE_SHAS[repository]}
                    if parts[4:6] == ["git", "trees"]:
                        paths = FakeGitHubClient.get_tree(self, repository)
                        return {
                            "sha": "f" * 40,
                            "tree": [{**item, "type": "blob"} for item in paths.values()],
                        }
                return super().get_json(path_or_url)

            def get_tree(self, repository, ref="main"):
                return GitHubClient.get_tree(self, repository, ref)

        client_class = CountingClient
        instances = []
        original = client_class

        class CountingClientWithInstances(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                instances.append(self)

        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--format", "json", "--no-prs"],
            client_class=CountingClientWithInstances,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(instances)
        # Trees are needed only for oac-infra, oac-apps, and moc-dns (zonefile
        # discovery); fixed-path repositories read files directly from raw at
        # the resolved commit. The MOC issue adds one request. Repeated reads
        # reuse pinned snapshots instead of resolving mutable refs again.
        self.assertEqual(instances[0].api_requests, 12)

    def test_unauthenticated_status_skips_pull_requests_by_default(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text"],
            client_class=FakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Pull requests: skipped because this run is unauthenticated", stdout
        )

    def test_unavailable_pull_request_lookup_still_exits_zero(self) -> None:
        class UnavailablePullsClient(FakeGitHubClient):
            def pulls(self, repository, state="all"):
                raise GitHubError("502 bad gateway")

        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--prs", "--format", "json"],
            client_class=UnavailablePullsClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("502 bad gateway", json.loads(stdout)["pull_requests_unavailable"])

    def test_explicit_no_prs_is_marked_skipped_for_authenticated_run(self) -> None:
        class AuthenticatedClient(FakeGitHubClient):
            @property
            def authenticated(self):
                return True

        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--no-prs", "--format", "json"],
            client_class=AuthenticatedClient,
        )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout)
        self.assertTrue(report["pull_requests_skipped"])
        self.assertEqual(report["pull_requests_skip_reason"], "skipped (--no-prs)")

    def test_optional_pr_budget_does_not_block_status_preflight(self) -> None:
        class LimitedQuotaClient(FakeGitHubClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.rate_limit_remaining = 20

            def pulls(self, repository, state="all"):
                raise RateLimitError("optional PR quota exhausted")

        exit_code, stdout, _ = self.run_cli(
            ["status", "bu-ist-demo", "--prs", "--format", "json"],
            client_class=LimitedQuotaClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("optional PR quota exhausted", json.loads(stdout)["pull_requests_unavailable"])

    def test_mid_run_rate_limit_renders_unknown_checks_and_exits_two(self) -> None:
        class RateLimitedClient(FakeGitHubClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.rate_limit_remaining = 100

            def get_json(self, path_or_url):
                raise RateLimitError("GitHub API rate limit exhausted")

        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-demo", "--format", "text", "--no-prs", "--details"],
            client_class=RateLimitedClient,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("UNKNOWN:", stdout)
        self.assertIn("unknown (rate limited)", stdout)
        self.assertIn("rate limit", stderr)

    def test_hub_without_workload_reports_no_workload_checks(self) -> None:
        exit_code, stdout, _ = self.run_cli(
            ["status", "dizzy", "--format", "text", "--no-prs"],
            client_class=MultiWorkloadFakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("dizzy · hub ·", stdout)
        self.assertNotIn("WORKLOAD", stdout)

    def test_status_workload_accepts_short_and_full_names(self) -> None:
        for workload in ("workload1", "oac-dev-workload1"):
            with self.subTest(workload=workload):
                exit_code, stdout, _ = self.run_cli(
                    [
                        "status-workload",
                        "oac-dev",
                        "--workload",
                        workload,
                        "--format",
                        "json",
                        "--no-prs",
                    ],
                    client_class=MultiWorkloadFakeGitHubClient,
                )
                self.assertEqual(exit_code, 0)
                report = json.loads(stdout)
                self.assertEqual(
                    report["environment"]["workload_clusters"],
                    ["oac-dev-workload1"],
                )
                checks = {check["check"] for check in report["checks"]}
                self.assertIn("oac-dev-workload1 host inventory", checks)
                self.assertNotIn("oac-dev-workload0 host inventory", checks)

    def test_unknown_environment_exits_with_suggestions(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["status", "bu-ist-dem", "--format", "json", "--no-prs"]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unknown environment: bu-ist-dem", stderr)
        self.assertIn("Did you mean: bu-ist-demo", stderr)
        self.assertIn("Known environments:", stderr)
        self.assertIn("bu-ist-demo", stderr)

    def test_issue_overrides_unknown_inventory_environment(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            [
                "status",
                "new-environment",
                "--issue",
                "666",
                "--format",
                "json",
                "--no-prs",
            ],
            client_class=MultiWorkloadFakeGitHubClient,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("continuing with the supplied MOC issue", stderr)
        report = json.loads(stdout)
        self.assertEqual(report["environment"]["name"], "new-environment")
        self.assertEqual(report["environment"]["workload_clusters"], [])

    def test_registry_issue_is_used_and_command_line_issue_overrides_it(self) -> None:
        class RegistryIssueClient(FakeGitHubClient):
            def get_json(self, path_or_url):
                if path_or_url == "/repos/CCI-MOC/MOC-issues/issues/123":
                    return {
                        "state": "open",
                        "title": "Registry issue",
                        "html_url": (
                            "https://github.com/CCI-MOC/MOC-issues/issues/123"
                        ),
                    }
                return super().get_json(path_or_url)

        with tempfile.TemporaryDirectory() as temporary_directory:
            registry_path = Path(temporary_directory) / "environments.yaml"
            registry_path.write_text(
                "defaults:\n"
                "  required_local_cluster_components: []\n"
                "  optional_local_cluster_components: []\n"
                "environments:\n"
                "  bu-ist-demo:\n"
                "    issue: 123\n",
                encoding="utf-8",
            )
            with patch.object(cli, "DEFAULT_REGISTRY_PATH", registry_path):
                exit_code, stdout, _ = self.run_cli(
                    [
                        "status",
                        "bu-ist-demo",
                        "--format",
                        "json",
                        "--no-prs",
                    ],
                    client_class=RegistryIssueClient,
                )
                self.assertEqual(exit_code, 0)
                report = json.loads(stdout)
                self.assertEqual(report["environment"]["issue_number"], 123)

                exit_code, stdout, _ = self.run_cli(
                    [
                        "status",
                        "bu-ist-demo",
                        "--issue",
                        "666",
                        "--format",
                        "json",
                        "--no-prs",
                    ],
                    client_class=RegistryIssueClient,
                )
            self.assertEqual(exit_code, 0)
            report = json.loads(stdout)
            self.assertEqual(report["environment"]["issue_number"], 666)

    def test_malformed_registry_exits_two_and_names_bad_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            registry_path = Path(temporary_directory) / "environments.yaml"
            registry_path.write_text(
                "defaults:\n  issue: 666\n  bad-key: []\n",
                encoding="utf-8",
            )
            with patch.object(cli, "DEFAULT_REGISTRY_PATH", registry_path):
                exit_code, stdout, stderr = self.run_cli(["list"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("defaults.bad-key", stderr)

    def test_status_json_is_byte_stable_with_fixed_client_and_clock(self) -> None:
        def fixed_clock():
            return datetime(2026, 11, 16, 12, 34, 56, tzinfo=timezone.utc)

        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            exit_code, stdout, _ = self.run_cli(
                [
                    "status",
                    "bu-ist-demo",
                    "--format",
                    "json",
                ],
                clock=fixed_clock,
            )

        self.assertEqual(exit_code, 0)
        golden = Path(__file__).parent / "fixtures" / "status-report.json"
        self.assertEqual(stdout, golden.read_text(encoding="utf-8"))

    def test_metadata_command_redacts_credential_values(self) -> None:
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            exit_code, stdout, _ = self.run_cli(
                [
                    "status",
                    "bu-ist-demo",
                    "--bws-secret-id",
                    "super-secret-value",
                    "--bws-secret-id-keychain-service=chain-secret-value",
                    "--format",
                    "json",
                    "--no-prs",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("super-secret-value", stdout)
        self.assertNotIn("chain-secret-value", stdout)
        report = json.loads(stdout)
        self.assertEqual(
            report["metadata"]["command"],
            [
                "status",
                "bu-ist-demo",
                "--bws-secret-id",
                "<redacted>",
                "--bws-secret-id-keychain-service=<redacted>",
                "--format",
                "json",
                "--no-prs",
            ],
        )

    def test_status_markdown_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "report.md"
            exit_code, stdout, stderr = self.run_cli(
                [
                    "status",
                    "bu-ist-demo",
                    "--format",
                    "markdown",
                    "--no-prs",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote markdown report to {output}", stderr)
            report = output.read_text(encoding="utf-8")
        self.assertIn("# bu-ist-demo — environment configuration status", report)

    def test_export_infra_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["export-infra", "bu-ist-demo"])
        self.assertEqual(exit_code, 0)
        document = yaml.safe_load(stdout)
        self.assertEqual(document["kind"], "InfraCluster")
        self.assertEqual(document["metadata"]["name"]["value"], "bu-ist-demo-infra")
        self.assertEqual(stderr, "")

    def test_export_infra_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "desired-state" / "infra-cluster.yaml"
            exit_code, stdout, stderr = self.run_cli(
                ["export-infra", "bu-ist-demo", "--output", str(output)]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote InfraCluster YAML to {output}", stderr)
            document = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(document["apiVersion"], "moc-env/v1alpha1")

    def test_export_workload_dispatch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["export-workload", "bu-ist-demo", "workload0"]
        )
        self.assertEqual(exit_code, 0)
        document = yaml.safe_load(stdout)
        self.assertEqual(document["kind"], "WorkloadCluster")
        self.assertEqual(
            document["metadata"]["name"]["value"],
            "bu-ist-demo-workload0",
        )
        self.assertEqual(stderr, "")

    def test_export_workload_dispatch_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = (
                Path(temporary_directory)
                / "desired-state"
                / "bu-ist-demo-workload0.yaml"
            )
            exit_code, stdout, stderr = self.run_cli(
                [
                    "export-workload",
                    "bu-ist-demo",
                    "workload0",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertIn(f"wrote WorkloadCluster YAML to {output}", stderr)
            document = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(document["kind"], "WorkloadCluster")
