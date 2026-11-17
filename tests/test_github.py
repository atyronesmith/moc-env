from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

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
            self.assertEqual(GitHubClient().get_json(url), {"value": "cached"})
            self.assertEqual(request.call_args.args[0].headers["If-none-match"], '"etag-1"')

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


if __name__ == "__main__":
    unittest.main()
