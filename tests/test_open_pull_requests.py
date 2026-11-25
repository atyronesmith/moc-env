"""Offline open-only PR discovery, cache reuse, and partial-failure rendering."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from email.message import Message
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import yaml

from moc_env import observed
from moc_env.checks import StatusChecker
from moc_env.github import GitHubClient, GitHubError
from moc_env.model import Environment, StatusReport
from moc_env.report import render_markdown, render_text
from moc_env.report_fields import failing_field_rows

from fakes import FakeGitHubClient


APPS = "example-lab/aurora-apps"
INFRA = "example-lab/aurora-infra"
IDENTITY = "example-lab/aurora-identity"
CLUSTER = "aurora-workload0"
VALUES_PATH = f"hosted-clusters/aurora-infra/{CLUSTER}/values.yaml"


class SyntheticRepositoryClient(GitHubClient):
    """Supply local repository contents; retain real PR transport and caching."""

    def get_tree(self, repository, ref="main"):
        return {VALUES_PATH: {"type": "blob"}}

    def get_file(self, repository, path, ref="main"):
        return f"clusterName: {CLUSTER}\nnodePools: []\n"


class AgentInputPullRequestsTest(unittest.TestCase):
    def test_annotation_only_lists_missing_inputs_as_failures(self):
        missing_hosts = ("quartz-0", "quartz-1")
        advisory_hosts = ("opal-0", "opal-1")
        documented_classes = ("reference-cpu", "reference-accelerator")

        class InventoryPullClient(FakeGitHubClient):
            def get_file(self, repository, path, ref="main"):
                content = super().get_file(repository, path, ref)
                if repository != "CCI-MOC/oac-infra":
                    return content
                if path == "infra/inventory/00hosts.yaml":
                    inventory = yaml.safe_load(content)
                    group = inventory["all"]["children"]["bu_ist_demo_clusters"]["children"]["bu_ist_demo_workload0"]
                    hosts = {
                        host: {
                            "node_name": host.upper(),
                            "bm_management": "bmc",
                            "mac_addr": f"02:00:00:00:00:{index:02x}",
                            **({"resource_class": "custom-accelerator"} if host in advisory_hosts else {}),
                        }
                        for index, host in enumerate((*missing_hosts, *advisory_hosts))
                    }
                    # Change an input in the PR, without fixing any missing class
                    # or advisory documentation difference.
                    if self.ref_for(repository) == "pull/73/head":
                        hosts[missing_hosts[0]]["mac_addr"] = "02:00:00:00:01:00"
                    group["children"]["compute"]["hosts"] = hosts
                    return yaml.safe_dump(inventory)
                if path == "docs/hardware-and-network-configuration.md":
                    return "| Node Name | Resource Class |\n|---|---|\n" + "".join(
                        f"| {host.upper()} | {documented} |\n"
                        for hosts, documented in zip((missing_hosts, advisory_hosts), documented_classes)
                        for host in hosts
                    )
                return content

            def pulls(self, repository, state="all"):
                if repository == "CCI-MOC/oac-infra":
                    yield {
                        "number": 73, "state": "open",
                        "title": "Update workload inventory", "body": "",
                        "head": {"ref": "inventory-change"},
                    }

            def pr_files(self, repository, number):
                yield {"filename": "infra/inventory/00hosts.yaml", "patch": "+bu-ist-demo-workload0"}

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": directory}):
            report = StatusChecker(InventoryPullClient()).run(
                Environment(name="bu-ist-demo", issue_number=666),
            ).to_dict()
        check = next(check for check in report["checks"] if check["id"] == "workload.agent_labels_inputs")
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["severity"], "blocking")
        self.assertEqual(len(check["evidence"]["resource_class_mismatches"]), 2)
        annotations = check["evidence"]["pr_evaluations"]
        self.assertEqual(len(annotations), 1)
        annotation = annotations[0]
        self.assertIn("open PR oac-infra#73 touches this but the check still fails there:", annotation)
        for host in missing_hosts:
            self.assertIn(f"{host}.resource_class is not found; expected present", annotation)
        for documented in documented_classes:
            self.assertNotIn(f"expected {documented}", annotation)
        for host in advisory_hosts:
            self.assertNotIn(host, annotation)

        advisory_only = copy.deepcopy(check)
        advisory_only["evidence"].pop("missing_variables")
        self.assertEqual(failing_field_rows(advisory_only), [])


class OpenPullRequestsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        repositories = patch.multiple(
            observed, OAC_APPS_REPOSITORY=APPS,
            OAC_INFRA_REPOSITORY=INFRA, MOC_KEYCLOAK_REPOSITORY=IDENTITY,
        )
        repositories.start()
        self.addCleanup(repositories.stop)
        self.records = [self.pull(41), self.pull(42)] + [
            self.pull(number, state="closed") for number in range(30, 35)
        ]
        self.other_records = {INFRA: [], IDENTITY: []}
        self.requests = []
        self.fault = None

    @staticmethod
    def pull(number, state="open", repository=APPS):
        return {
            "number": number,
            "state": state,
            "title": f"Aurora configuration {number}",
            "body": None,
            "updated_at": "2026-01-01T00:00:00Z",
            "merged_at": "2026-01-01T00:00:00Z" if state == "closed" else None,
            "head": {"sha": f"{number:040x}", "ref": f"aurora-change-{number}"},
            "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": repository}},
            "html_url": f"https://github.com/{repository}/pull/{number}",
        }

    @staticmethod
    def response(data, *, etag=None, next_url=None):
        response = io.BytesIO(json.dumps(data).encode())
        response.headers = Message()
        if etag is not None:
            response.headers["ETag"] = etag
        if next_url is not None:
            response.headers["Link"] = f'<{next_url}>; rel="next"'
        response.status = 200
        return response

    def transport(self, request, **kwargs):
        url = request.full_url
        self.requests.append(url)
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        repository = "/".join(parsed.path.split("/")[2:4])
        if "/files" in parsed.path:
            number = int(parsed.path.split("/")[-2])
            if self.fault == ("files", repository, number):
                raise GitHubError("File list unavailable")
            path = {
                APPS: f"values/aurora-infra/{CLUSTER}/settings.yaml",
                INFRA: observed.INVENTORY_PATH,
                IDENTITY: observed.KEYCLOAK_PATH,
            }[repository]
            return self.response(
                [{"filename": path, "patch": f"+ aurora-infra {CLUSTER}"}],
                etag='"aurora-files"',
            )
        if self.fault == "all-listings":
            raise GitHubError("Listing unavailable")
        state = query.get("state", ["all"])[0]
        upstream = self.records if repository == APPS else self.other_records[repository]
        records = copy.deepcopy([
            pull for pull in upstream if state == "all" or pull["state"] == state
        ])
        if self.fault == ("page-two", repository):
            if query.get("page") == ["2"]:
                raise GitHubError("Second page unavailable")
            return self.response(records[:1], etag='"partial"', next_url=f"{url}&page=2")
        return self.response(records, etag='"aurora-pulls"')

    def read(self):
        stderr = io.StringIO()
        client = SyntheticRepositoryClient(token="invented-test-token")
        with (
            patch("moc_env.github.urlopen", side_effect=self.transport),
            patch("moc_env.github.time.sleep"),
            contextlib.redirect_stderr(stderr),
        ):
            result = observed.read_apps_observation(
                client,
                Environment(name="aurora", workload_clusters=(CLUSTER,)),
            )
        return result, stderr.getvalue(), client.response_cache.path

    @staticmethod
    def open_numbers(result):
        return {
            pull.number.value for pull in result.pull_requests if pull.state.value == "open"
        }

    @staticmethod
    def render(result):
        report = StatusReport(
            environment=Environment(name="aurora", workload_clusters=(CLUSTER,)),
            checks=[], overall_state="declared_in_main",
            pull_requests=StatusChecker._pull_request_evidence(result.pull_requests),
            pull_requests_unavailable=result.pull_requests_unavailable,
        ).to_dict()
        return render_text(report), render_markdown(report)

    def add_other_repositories(self):
        self.other_records = {
            INFRA: [self.pull(51, repository=INFRA)],
            IDENTITY: [self.pull(61, repository=IDENTITY)],
        }

    def test_only_open_listings_and_two_file_lists_cold_zero_warm(self):
        result, _, _ = self.read()
        self.assertEqual(self.open_numbers(result), {41, 42})
        self.assertEqual(len([url for url in self.requests if "/files?" in url]), 2)
        listings = [url for url in self.requests if "/pulls?" in url]
        self.assertEqual(len(listings), 3)
        self.assertTrue(all("state=open&" in url for url in listings))
        self.assertFalse(any("state=all" in url or "state=closed" in url for url in self.requests))
        self.requests.clear()
        self.read()
        self.assertEqual([url for url in self.requests if "/files?" in url], [])

    def test_comment_only_update_reuses_file_lists(self):
        first, _, _ = self.read()
        self.assertEqual(self.open_numbers(first), {41, 42})
        self.requests.clear()
        self.records[0]["updated_at"] = "2026-01-02T00:00:00Z"
        self.records[0]["comments"] = 1
        result, _, _ = self.read()
        self.assertEqual(self.open_numbers(result), {41, 42})
        self.assertTrue(any("/pulls?" in url for url in self.requests))
        self.assertEqual([url for url in self.requests if "/files?" in url], [])

    def test_page_two_failure_drops_whole_repository_but_renders_other_repositories(self):
        self.add_other_repositories()
        self.read()
        self.requests.clear()
        self.fault = ("page-two", APPS)
        result, _, _ = self.read()
        self.assertEqual(self.open_numbers(result), {51, 61})
        self.assertFalse(any(f"{APPS}/pulls/" in url for url in self.requests))
        for output in self.render(result):
            self.assertIn(f"Pull requests unavailable for {APPS}: Second page unavailable", output)
            self.assertNotIn("Pull requests: unavailable", output)
            for number in (51, 61):
                self.assertIn(f"Aurora configuration {number}", output)
            for number in (41, 42):
                self.assertNotIn(f"Aurora configuration {number}", output)

    def test_file_list_failure_skips_only_that_pr_and_names_it(self):
        self.fault = ("files", APPS, 41)
        result, _, _ = self.read()
        self.assertEqual(self.open_numbers(result), {42})
        for output in self.render(result):
            self.assertIn("Aurora configuration 42", output)
            self.assertNotIn("Aurora configuration 41", output)
            self.assertIn(f"Pull requests unavailable for {APPS}#41: File list unavailable", output)
            self.assertNotIn("Pull requests: unavailable", output)

    def test_all_listing_failures_use_whole_section_unavailable(self):
        self.fault = "all-listings"
        result, _, _ = self.read()
        self.assertEqual(result.pull_requests, ())
        for output in self.render(result):
            self.assertIn("Pull requests: unavailable", output)
            self.assertNotIn("0 open pull requests", output)
            for repository in (APPS, INFRA, IDENTITY):
                self.assertIn(f"{repository}: Listing unavailable", output)

    def test_no_merged_or_closed_rows_or_counts_are_rendered(self):
        result, _, _ = self.read()
        for output in self.render(result):
            self.assertIn("2 open pull requests", output)
            for phrase in ("Merged and closed", "Merged PRs", "Closed-unmerged PRs"):
                self.assertNotIn(phrase, output)
            for number in range(30, 35):
                self.assertNotIn(f"Aurora configuration {number}", output)
