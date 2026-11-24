"""Offline acceptance tests using real PR transport and persistent caching."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from fakes import FakeGitHubClient
from moc_env import cli
from moc_env.github import GitHubClient, GitHubError


class PRTransportClient(FakeGitHubClient):
    pulls = GitHubClient.pulls
    pr_files = GitHubClient.pr_files


class PRFileCacheTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.heads = {237: "a" * 40, 238: "b" * 40}
        self.file_requests = []

    @staticmethod
    def response(data, next_url=None):
        response = io.BytesIO(json.dumps(data).encode())
        response.headers = Message()
        response.headers["ETag"] = '"test-etag"'
        if next_url:
            response.headers["Link"] = f'<{next_url}>; rel="next"'
        response.status = 200
        return response

    def transport(self, request, **kwargs):
        url = request.full_url
        if "/files?" in url:
            self.file_requests.append(url)
            return self.response([{"filename": "values/bu-ist-demo-infra/hcp-config.yaml"}])
        if "/oac-apps/pulls?" in url:
            return self.response([
                {
                    "number": number, "state": "open", "title": "test",
                    "head": {"sha": sha} if sha else {},
                }
                for number, sha in self.heads.items()
            ])
        return self.response([])

    def run_status(self, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "GitHubClient", PRTransportClient),
            patch.object(cli, "_resolve_github_token", return_value="test-token"),
            patch("moc_env.github.urlopen", side_effect=self.transport),
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(
                ["status", "bu-ist-demo", *options],
                clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(code, 0, stderr.getvalue())
        return stdout.getvalue(), stderr.getvalue()

    def test_unchanged_heads_reuse_without_requests_and_preserve_report(self):
        first, _ = self.run_status()
        self.assertEqual(len(self.file_requests), 2)
        self.file_requests.clear()
        second, summary = self.run_status()
        self.assertEqual(self.file_requests, [])
        self.assertEqual(second, first)
        self.assertIn("PR file lists: 0 fetched, 2 reused", summary)

    def test_changed_head_fetches_only_that_pr(self):
        self.run_status()
        self.file_requests.clear()
        self.heads[238] = "c" * 40
        _, summary = self.run_status()
        self.assertEqual(len(self.file_requests), 1)
        self.assertIn("/pulls/238/files?", self.file_requests[0])
        self.assertIn("PR file lists: 1 fetched, 1 reused", summary)

    def test_missing_head_is_fetched_each_run_and_not_sha_cached(self):
        self.heads[237] = None
        self.run_status()
        self.file_requests.clear()
        self.run_status()
        self.assertEqual(len(self.file_requests), 1)
        self.assertIn("/pulls/237/files?", self.file_requests[0])
        client = GitHubClient()
        self.assertFalse(any(
            key.startswith("pr-files:CCI-MOC/oac-apps:237:")
            for key in client.response_cache._read_document()
        ))

    def test_refresh_fetches_all_and_offline_preserves_result_without_requests(self):
        first, _ = self.run_status()
        self.file_requests.clear()
        refreshed, summary = self.run_status("--refresh")
        self.assertEqual(len(self.file_requests), 2)
        self.assertEqual(refreshed, first)
        self.assertIn("PR file lists: 2 fetched, 0 reused", summary)
        with patch.object(self, "transport", side_effect=AssertionError("offline request")):
            offline, summary = self.run_status("--offline")
        self.assertIn("GitHub API: 0 requests", summary)
        self.assertIn("RESULT:", offline)
        self.assertEqual(
            [line for line in offline.splitlines() if "RESULT:" in line],
            [line for line in first.splitlines() if "RESULT:" in line],
        )

    def test_paginated_file_lists_are_cached_as_a_complete_list_without_etags(self):
        client = GitHubClient()
        client._pull_heads[("owner/repo", 1)] = "a" * 40
        next_url = "https://api.github.com/repos/owner/repo/pulls/1/files?page=2"
        first = self.response([{"filename": "first"}], next_url)
        second = self.response([{"filename": "second"}])
        del first.headers["ETag"]
        del second.headers["ETag"]
        with patch("moc_env.github.urlopen", side_effect=[first, second]) as request:
            files = list(client.pr_files("owner/repo", 1))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(files, [{"filename": "first"}, {"filename": "second"}])
        offline = GitHubClient(offline=True)
        offline._pull_heads[("owner/repo", 1)] = "a" * 40
        with patch("moc_env.github.urlopen") as request:
            self.assertEqual(list(offline.pr_files("owner/repo", 1)), files)
        request.assert_not_called()
        offline._pull_heads[("owner/repo", 1)] = "b" * 40
        with self.assertRaisesRegex(GitHubError, "No cached PR file list"):
            list(offline.pr_files("owner/repo", 1))

    def test_two_timeouts_emit_two_retry_lines_with_path_and_attempts(self):
        for timeout in (TimeoutError("timed out"), URLError(TimeoutError("timed out"))):
            with self.subTest(timeout=type(timeout).__name__):
                stderr = io.StringIO()
                with (
                    patch("moc_env.github.urlopen", side_effect=[
                        timeout, timeout, self.response({"ok": True}),
                    ]) as request,
                    patch("moc_env.github.time.sleep") as sleep,
                    contextlib.redirect_stderr(stderr),
                ):
                    self.assertEqual(GitHubClient().get_json("/example/path"), {"ok": True})
                lines = stderr.getvalue().splitlines()
                self.assertEqual(len(lines), 2)
                for attempt, line in enumerate(lines, 1):
                    self.assertIn("/example/path", line)
                    self.assertIn("timeout", line)
                    self.assertIn(f"attempt {attempt}", line)
                self.assertEqual(request.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0])

    def test_http_and_connection_retry_reasons_are_visible(self):
        url = "https://api.github.com/example/path"
        errors = [
            HTTPError(url, 503, "unavailable", Message(), io.BytesIO()),
            URLError("connection reset"),
            ConnectionResetError("connection reset"),
        ]
        stderr = io.StringIO()
        with (
            patch("moc_env.github.urlopen", side_effect=[*errors, self.response({})]),
            patch("moc_env.github.time.sleep"), contextlib.redirect_stderr(stderr),
        ):
            GitHubClient().get_json(url)
        lines = stderr.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("HTTP 503", lines[0])
        for attempt, line in enumerate(lines, 1):
            self.assertIn("/example/path", line)
            self.assertIn(f"attempt {attempt}", line)
        self.assertTrue(all("connection error" in line for line in lines[1:]))
