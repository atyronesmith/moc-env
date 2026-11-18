from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from email.message import Message
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from moc_env.github import GitHubClient, GitHubError, RateLimitError
from moc_env.github_cache import github_response_cache_path


class GitHubClientTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        environment = patch.dict(
            os.environ,
            {"MOC_ENV_CACHE_DIR": temporary_directory.name},
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_unauthenticated_warning_callback_runs_once(self) -> None:
        client = GitHubClient()
        warnings: list[int] = []
        client.on_response = warnings.append

        client._record_headers({"X-RateLimit-Remaining": "59"})
        client._record_headers({"X-RateLimit-Remaining": "58"})

        self.assertEqual(warnings, [59])
        self.assertEqual(client.rate_limit_remaining, 58)

    def test_counted_endpoints_exclude_free_and_not_modified_responses(self) -> None:
        client = GitHubClient()
        client._count_quota(
            "https://api.github.com/repos/CCI-MOC/oac-apps/commits/main", 200
        )
        client._count_quota(
            "https://api.github.com/repos/CCI-MOC/oac-apps/commits/main", 304
        )
        client._count_quota("https://api.github.com/rate_limit", 200)
        client._count_quota(
            "https://raw.githubusercontent.com/CCI-MOC/oac-apps/sha/values.yaml",
            200,
        )
        self.assertEqual(
            client.counted_endpoints,
            ["/repos/CCI-MOC/oac-apps/commits/main"],
        )

    def test_rate_limit_error_names_reset_and_quick_fixes(self) -> None:
        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = "1800000000"
        error = HTTPError(
            "https://api.github.com/example",
            429,
            "rate limited",
            headers,
            io.BytesIO(b"{}"),
        )
        client = GitHubClient()

        with patch("moc_env.github.urlopen", side_effect=error):
            with self.assertRaises(RateLimitError) as raised:
                client.get_json("/example")

        message = str(raised.exception)
        self.assertIn("resets around", message)
        self.assertIn("Set GITHUB_TOKEN or run gh auth login.", message)

    @staticmethod
    def _response(body: dict, etag: str | None = None):
        headers = Message()
        if etag:
            headers["ETag"] = etag

        class Response:
            def __init__(self) -> None:
                self.headers = headers

            def read(self) -> bytes:
                return json.dumps(body).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        return Response()

    def test_304_serves_cached_body(self) -> None:
        url = "https://api.github.com/example"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "cached"}, '"etag-1"'),
        ):
            self.assertEqual(GitHubClient().get_json(url), {"value": "cached"})

        not_modified = HTTPError(url, 304, "not modified", Message(), io.BytesIO(b""))
        with patch("moc_env.github.urlopen", side_effect=not_modified) as request:
            client = GitHubClient()
            self.assertEqual(client.get_json(url), {"value": "cached"})
            self.assertEqual(request.call_args.args[0].headers["If-none-match"], '"etag-1"')
        # A conditional request still consumes transport, but a 304 must not
        # be counted as a quota-consuming GitHub API call.
        self.assertEqual(client.requests_made, 1)
        self.assertEqual(client.api_calls_used, 0)
        self.assertEqual(client.cache_hits, 1)

    def test_the_same_url_is_requested_only_once_per_client(self) -> None:
        url = "https://api.github.com/example"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "data"}, '"etag-1"'),
        ) as request:
            client = GitHubClient()
            self.assertEqual(client.get_json(url), {"value": "data"})
            self.assertEqual(client.get_json(url), {"value": "data"})

        self.assertEqual(request.call_count, 1)

    def test_offline_serves_hit_and_fails_clearly_on_miss(self) -> None:
        cached_url = "https://api.github.com/cached"
        missing_url = "https://api.github.com/missing"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "cached"}, '"etag-1"'),
        ):
            GitHubClient().get_json(cached_url)

        offline_client = GitHubClient(offline=True)
        self.assertEqual(offline_client.get_json(cached_url), {"value": "cached"})
        with patch("moc_env.github.urlopen") as request:
            with self.assertRaisesRegex(
                GitHubError,
                "No cached GitHub response is available for https://api.github.com/missing",
            ):
                offline_client.get_json(missing_url)
            request.assert_not_called()

    def test_refresh_ignores_disk_cache(self) -> None:
        url = "https://api.github.com/example"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "old"}, '"etag-old"'),
        ):
            GitHubClient().get_json(url)

        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "new"}, '"etag-new"'),
        ) as request:
            self.assertEqual(
                GitHubClient(refresh=True).get_json(url), {"value": "new"}
            )
            sent_headers = request.call_args.args[0].headers
            self.assertNotIn("If-none-match", sent_headers)

        not_modified = HTTPError(url, 304, "not modified", Message(), io.BytesIO(b""))
        with patch("moc_env.github.urlopen", side_effect=not_modified) as request:
            self.assertEqual(GitHubClient().get_json(url), {"value": "new"})
            self.assertEqual(request.call_args.args[0].headers["If-none-match"], '"etag-new"')

    def test_cache_does_not_store_authorization_or_token(self) -> None:
        url = "https://api.github.com/example"
        token = "github-token-value"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "data"}, '"etag-1"'),
        ):
            GitHubClient(token=token).get_json(url)

        cache_text = github_response_cache_path().read_text(encoding="utf-8")
        self.assertNotIn("Authorization", cache_text)
        self.assertNotIn(token, cache_text)

    def test_get_file_uses_raw_download_at_commit_sha(self) -> None:
        class RawResponse:
            headers = Message()

            def read(self) -> bytes:
                return b"file body"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        client = GitHubClient()
        client.record_source("CCI-MOC/oac-infra", "main", "2222222")
        with patch(
            "moc_env.github.urlopen", return_value=RawResponse()
        ) as request:
            body = client.get_file(
                "CCI-MOC/oac-infra", "hub-images/inventory.yml"
            )

        self.assertEqual(body, "file body")
        raw_url = request.call_args.args[0].full_url
        self.assertEqual(
            raw_url,
            "https://raw.githubusercontent.com/CCI-MOC/oac-infra/2222222/hub-images/inventory.yml",
        )
        self.assertNotIn("Authorization", request.call_args.args[0].headers)

    def test_reserve_quota_stops_before_spending_calls(self) -> None:
        client = GitHubClient()
        client.rate_limit_remaining = 11
        with patch("moc_env.github.urlopen") as request:
            with self.assertRaisesRegex(
                RateLimitError, "12 calls needed, 11 available"
            ):
                client.reserve_quota(12)
            request.assert_not_called()

    def test_zero_quota_unauthenticated_run_uses_cached_api_response(self) -> None:
        url = "https://api.github.com/repos/example/repo/git/trees/main"
        with patch(
            "moc_env.github.urlopen",
            return_value=self._response({"value": "cached"}, '"etag-1"'),
        ):
            GitHubClient().get_json(url)

        client = GitHubClient()
        client.rate_limit_remaining = 0
        with patch("moc_env.github.urlopen") as request:
            self.assertEqual(client.get_json(url), {"value": "cached"})
            request.assert_not_called()

    def test_transient_failures_retry_three_times_with_backoff(self) -> None:
        url = "https://api.github.com/example"
        failures = [
            HTTPError(url, 503, "unavailable", Message(), io.BytesIO(b"retry")),
            URLError("connection reset"),
            ConnectionResetError("connection reset"),
        ]
        with patch(
            "moc_env.github.urlopen",
            side_effect=[*failures, self._response({"ok": True})],
        ) as request, patch("moc_env.github.time.sleep") as sleep:
            self.assertEqual(GitHubClient().get_json(url), {"ok": True})
        self.assertEqual(request.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0, 2.0])

    def test_exhausted_server_errors_fail_after_three_retries(self) -> None:
        url = "https://api.github.com/example"
        errors = [
            HTTPError(url, 502, "bad gateway", Message(), io.BytesIO(b"bad gateway"))
            for _ in range(4)
        ]
        with patch("moc_env.github.urlopen", side_effect=errors) as request, patch(
            "moc_env.github.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(GitHubError, "502.*bad gateway"):
                GitHubClient().get_json(url)
        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_client_errors_are_not_retried(self) -> None:
        url = "https://api.github.com/example"
        error = HTTPError(url, 404, "missing", Message(), io.BytesIO(b"missing"))
        with patch("moc_env.github.urlopen", side_effect=error) as request, patch(
            "moc_env.github.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(GitHubError, "404"):
                GitHubClient().get_json(url)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_raw_download_retries_connection_and_server_errors(self) -> None:
        url = "https://raw.githubusercontent.com/CCI-MOC/oac-apps/sha/values.yaml"
        error = HTTPError(url, 500, "error", Message(), io.BytesIO(b"retry"))
        with patch(
            "moc_env.github.urlopen",
            side_effect=[URLError("disconnected"), error, self._response({"ok": True})],
        ) as request, patch("moc_env.github.time.sleep") as sleep:
            self.assertEqual(json.loads(GitHubClient()._raw_request(url, None)), {"ok": True})
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_unrevalidated_tree_marks_source_with_cached_fetch_time(self) -> None:
        repository = "CCI-MOC/oac-apps"
        sha = "a" * 40
        url = f"https://api.github.com/repos/{repository}/git/trees/{sha}?recursive=1"
        commit_url = f"https://api.github.com/repos/{repository}/commits/main"
        client = GitHubClient()
        client.response_cache.write(commit_url, '"commit"', json.dumps({"sha": sha}))
        fetched_at = client.response_cache.read(commit_url)["fetched_at"]
        client.response_cache.write(url, '"tree"', '{"sha": "different-tree-sha", "tree": []}')
        for mode in ("offline", "quota"):
            with self.subTest(mode=mode):
                reader = GitHubClient(offline=mode == "offline")
                if mode == "quota":
                    reader.rate_limit_remaining = 0
                with patch("moc_env.github.urlopen") as request:
                    reader.get_tree(repository)
                request.assert_not_called()
                self.assertEqual(
                    reader.sources(),
                    [{"repository": repository, "ref": "main", "sha": sha, "from_cache": True, "fetched_at": fetched_at}],
                )

    def test_revalidated_tree_does_not_mark_source_as_unrevalidated(self) -> None:
        repository = "CCI-MOC/oac-apps"
        sha = "a" * 40
        url = f"https://api.github.com/repos/{repository}/git/trees/{sha}?recursive=1"
        commit_url = f"https://api.github.com/repos/{repository}/commits/main"
        client = GitHubClient()
        client.response_cache.write(commit_url, '"commit"', json.dumps({"sha": sha}))
        client.response_cache.write(url, '"tree"', '{"sha": "different-tree-sha", "tree": []}')
        errors = [
            HTTPError(address, 304, "not modified", Message(), io.BytesIO(b""))
            for address in (commit_url, url)
        ]
        with patch("moc_env.github.urlopen", side_effect=errors):
            client.get_tree(repository)
        self.assertEqual(client.sources(), [{"repository": repository, "ref": "main", "sha": sha}])

    def test_commit_sha_not_tree_sha_pins_raw_download_and_sources(self) -> None:
        repository = "CCI-MOC/oac-apps"
        commit_sha = "625765a" + "1" * 33
        tree_sha = "f" * 40
        client = GitHubClient(refs={repository: "pull/246/head"})
        responses = [
            self._response({"sha": commit_sha}),
            self._response({"sha": tree_sha, "tree": [{"path": "values.yaml", "type": "blob"}]}),
            self._response({"value": "pinned file"}),
        ]
        with patch("moc_env.github.urlopen", side_effect=responses) as request:
            self.assertIn("values.yaml", client.get_tree(repository))
            client.get_file(repository, "values.yaml")
            client.get_tree(repository)
            client.get_file(repository, "values.yaml")
        self.assertEqual(
            [call.args[0].full_url for call in request.call_args_list],
            [
                f"https://api.github.com/repos/{repository}/commits/pull/246/head",
                f"https://api.github.com/repos/{repository}/git/trees/{commit_sha}?recursive=1",
                f"https://raw.githubusercontent.com/{repository}/{commit_sha}/values.yaml",
            ],
        )
        self.assertEqual(client.sources(), [{"repository": repository, "ref": "pull/246/head", "sha": commit_sha}])

    def test_full_commit_ref_needs_no_resolution_request(self) -> None:
        sha = "a" * 40
        client = GitHubClient(refs={"CCI-MOC/oac-apps": sha})
        with patch("moc_env.github.urlopen", return_value=self._response({"sha": "tree", "tree": []})) as request:
            client.get_tree("CCI-MOC/oac-apps")
        self.assertEqual(request.call_count, 1)
        self.assertIn(f"/git/trees/{sha}?recursive=1", request.call_args.args[0].full_url)
        self.assertEqual(client.sources()[0]["sha"], sha)

    def test_short_commit_ref_is_resolved_to_full_commit(self) -> None:
        sha = "625765a" + "1" * 33
        client = GitHubClient(refs={"CCI-MOC/oac-apps": "625765a"})
        with patch("moc_env.github.urlopen", side_effect=[self._response({"sha": sha}), self._response({"sha": "tree", "tree": []})]) as request:
            client.get_tree("CCI-MOC/oac-apps")
        self.assertTrue(request.call_args_list[0].args[0].full_url.endswith("/commits/625765a"))
        self.assertEqual(client.sources()[0]["sha"], sha)

    def test_incomplete_response_retries_then_normalizes_api_and_raw_errors(self) -> None:
        for raw in (False, True):
            with self.subTest(raw=raw):
                client = GitHubClient()
                url = "https://api.github.com/example"
                failures = [IncompleteRead(b"partial", 100) for _ in range(4)]
                with patch("moc_env.github.urlopen", side_effect=failures) as request, patch("moc_env.github.time.sleep") as sleep:
                    with self.assertRaisesRegex(GitHubError, "IncompleteRead"):
                        if raw:
                            client._raw_request(url, None)
                        else:
                            client.get_json(url)
                self.assertEqual(request.call_count, 4)
                self.assertEqual(sleep.call_count, 3)

    def test_raw_unrevalidated_cache_marks_repository_even_with_fresh_tree(self) -> None:
        client = GitHubClient(offline=True)
        client.record_source("CCI-MOC/oac-apps", "pull/246/head", "abc123")
        url = "https://raw.githubusercontent.com/CCI-MOC/oac-apps/abc123/values.yaml"
        client.response_cache.write(url, '"values"', "value: cached")
        with patch("moc_env.github.urlopen") as request:
            self.assertEqual(client.get_file("CCI-MOC/oac-apps", "values.yaml", "pull/246/head"), "value: cached")
        request.assert_not_called()
        self.assertTrue(client.sources()[0]["from_cache"])
        self.assertIn("fetched_at", client.sources()[0])


if __name__ == "__main__":
    unittest.main()
