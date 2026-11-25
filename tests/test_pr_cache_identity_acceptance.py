"""Adversarial acceptance coverage for PR-file cache identity transitions."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch

from moc_env.github import GitHubClient, GitHubError


class PRCacheIdentityAcceptanceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": directory.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.head = "a" * 40
        self.base_old = "b" * 40
        self.base_new = "c" * 40
        self.calls: list[str] = []

    @staticmethod
    def response(data, *, etag: str, next_url: str | None = None):
        response = io.BytesIO(json.dumps(data).encode())
        response.headers = Message()
        response.headers["ETag"] = etag
        if next_url:
            response.headers["Link"] = f'<{next_url}>; rel="next"'
        response.status = 200
        return response

    def transport(self, request, **kwargs):
        url = request.full_url
        self.calls.append(url)
        if "/pulls?state=open&per_page=100" in url:
            return self.response(
                [
                    {
                        "number": 1,
                        "head": {"sha": self.head},
                        "base": {
                            "sha": self.base_old,
                            "ref": "main",
                            "repo": {"full_name": "owner/repo"},
                        },
                    }
                ],
                etag='"pull-open"',
            )
        if "/pulls?state=all&per_page=100" in url:
            return self.response(
                [
                    {
                        "number": 1,
                        "head": {"sha": self.head},
                        "base": {
                            "sha": self.base_new,
                            "ref": "main",
                            "repo": {"full_name": "owner/repo"},
                        },
                    }
                ],
                etag='"pull-all"',
            )
        if "/pulls?state=closed&per_page=100" in url:
            return self.response(
                [
                    {
                        "number": 1,
                        "head": {"sha": self.head},
                        "base": {
                            "sha": self.base_new,
                            "ref": "main",
                            "repo": {"full_name": "owner/repo"},
                        },
                    }
                ],
                etag='"pull-closed"',
            )
        if "/pulls/1/files?page=2" in url:
            return self.response(
                [
                    {
                        "filename": (
                            "head-new-page.yaml"
                            if self.head.startswith("d")
                            else "new-page.yaml"
                        )
                    }
                ],
                etag='"files-page-2-new"',
            )
        if "/pulls/1/files?per_page=100" in url:
            return self.response(
                [
                    {
                        "filename": (
                            "head-new.yaml" if self.head.startswith("d") else "new.yaml"
                        )
                    }
                ],
                etag='"files-page-1-new"',
                next_url="https://api.github.com/repos/owner/repo/pulls/1/files?page=2",
            )
        raise AssertionError(f"unexpected URL: {url}")

    def test_identity_change_invalidates_all_in_memory_pages_and_disk_identity(self):
        client = GitHubClient(token="test-token")
        with patch("moc_env.github.urlopen", side_effect=self.transport):
            list(client.pulls("owner/repo", state="open"))
            # Seed the old identity's complete list and both paginated transport pages.
            old_page_1 = self.response(
                [{"filename": "old.yaml"}],
                etag='"files-page-1-old"',
                next_url="https://api.github.com/repos/owner/repo/pulls/1/files?page=2",
            )
            old_page_2 = self.response(
                [{"filename": "old-page-2.yaml"}], etag='"files-page-2-old"'
            )
            with patch("moc_env.github.urlopen", side_effect=[old_page_1, old_page_2]):
                self.assertEqual(
                    list(client.pr_files("owner/repo", 1)),
                    [{"filename": "old.yaml"}, {"filename": "old-page-2.yaml"}],
                )

            list(client.pulls("owner/repo", state="all"))
            files = list(client.pr_files("owner/repo", 1))
            self.assertEqual(
                files,
                [{"filename": "new.yaml"}, {"filename": "new-page.yaml"}],
            )

            # A subsequent head transition must invalidate the same in-memory pages.
            self.head = "d" * 40
            list(client.pulls("owner/repo", state="closed"))
            self.assertEqual(
                list(client.pr_files("owner/repo", 1)),
                [{"filename": "head-new.yaml"}, {"filename": "head-new-page.yaml"}],
            )

        fresh = GitHubClient(token="test-token")
        with patch("moc_env.github.urlopen", side_effect=self.transport):
            list(fresh.pulls("owner/repo", state="all"))
            self.assertEqual(
                list(fresh.pr_files("owner/repo", 1)),
                [{"filename": "head-new.yaml"}, {"filename": "head-new-page.yaml"}],
            )

    def test_unchanged_identity_reuses_complete_list(self):
        client = GitHubClient(token="test-token")
        client._pull_identities[("owner/repo", 1)] = (
            self.head,
            self.base_old,
            "owner/repo",
            "main",
        )
        with patch(
            "moc_env.github.urlopen",
            side_effect=[
                self.response(
                    [{"filename": "stable.yaml"}], etag='"stable"'
                )
            ],
        ) as request:
            self.assertEqual(
                list(client.pr_files("owner/repo", 1)),
                [{"filename": "stable.yaml"}],
            )
        request.assert_called_once()
        client._pull_identities[("owner/repo", 1)] = (
            self.head,
            self.base_old,
            "owner/repo",
            "main",
        )
        with patch("moc_env.github.urlopen") as request:
            self.assertEqual(
                list(client.pr_files("owner/repo", 1)),
                [{"filename": "stable.yaml"}],
            )
        request.assert_not_called()

    def test_incomplete_identity_offline_is_a_safe_cache_miss(self):
        client = GitHubClient(offline=True)
        client._pull_identities[("owner/repo", 1)] = None
        with self.assertRaisesRegex(GitHubError, "without a complete head/base identity"):
            list(client.pr_files("owner/repo", 1))

    def test_rate_limited_new_client_does_not_promote_old_url_page_to_new_identity(self):
        old_client = GitHubClient()
        old_client._pull_identities[("owner/repo", 1)] = (
            self.head,
            self.base_old,
            "owner/repo",
            "main",
        )
        old_response = self.response(
            [{"filename": "old.yaml"}], etag='"old-files"'
        )
        with patch("moc_env.github.urlopen", return_value=old_response):
            self.assertEqual(
                list(old_client.pr_files("owner/repo", 1)),
                [{"filename": "old.yaml"}],
            )

        new_client = GitHubClient()
        pull_response = self.response(
            [
                {
                    "number": 1,
                    "head": {"sha": "d" * 40},
                    "base": {
                        "sha": self.base_old,
                        "ref": "main",
                        "repo": {"full_name": "owner/repo"},
                    },
                }
            ],
            etag='"pull-new"',
        )
        pull_response.headers["X-RateLimit-Remaining"] = "0"
        with patch("moc_env.github.urlopen", return_value=pull_response):
            list(new_client.pulls("owner/repo", state="all"))
        with patch("moc_env.github.urlopen") as request:
            with self.assertRaisesRegex(GitHubError, "identity-specific"):
                list(new_client.pr_files("owner/repo", 1))
        request.assert_not_called()

    def test_rate_limit_after_fresh_page_does_not_reuse_old_later_page(self):
        old_client = GitHubClient()
        old_client._pull_identities[("owner/repo", 1)] = (
            self.head,
            self.base_old,
            "owner/repo",
            "main",
        )
        old_page_2_url = "https://api.github.com/repos/owner/repo/pulls/1/files?page=2"
        old_page_1 = self.response(
            [{"filename": "old-page-1.yaml"}],
            etag='"old-page-1"',
            next_url=old_page_2_url,
        )
        old_page_2 = self.response(
            [{"filename": "old-page-2.yaml"}], etag='"old-page-2"'
        )
        with patch("moc_env.github.urlopen", side_effect=[old_page_1, old_page_2]):
            self.assertEqual(
                list(old_client.pr_files("owner/repo", 1)),
                [{"filename": "old-page-1.yaml"}, {"filename": "old-page-2.yaml"}],
            )

        new_client = GitHubClient()
        pull_response = self.response(
            [
                {
                    "number": 1,
                    "head": {"sha": "d" * 40},
                    "base": {
                        "sha": self.base_old,
                        "ref": "main",
                        "repo": {"full_name": "owner/repo"},
                    },
                }
            ],
            etag='"pull-new-page"',
        )
        pull_response.headers["X-RateLimit-Remaining"] = "1"
        fresh_page_1 = self.response(
            [{"filename": "fresh-page-1.yaml"}],
            etag='"fresh-page-1"',
            next_url=old_page_2_url,
        )
        fresh_page_1.headers["X-RateLimit-Remaining"] = "0"
        with patch(
            "moc_env.github.urlopen", side_effect=[pull_response, fresh_page_1]
        ) as request:
            list(new_client.pulls("owner/repo", state="all"))
            with self.assertRaisesRegex(GitHubError, "identity-specific"):
                list(new_client.pr_files("owner/repo", 1))
        self.assertEqual(request.call_count, 2)
        new_key = ":".join(
            [
                "pr-files",
                "owner/repo",
                "1",
                "d" * 40,
                self.base_old,
                "owner/repo",
                "main",
            ]
        )
        self.assertIsNone(new_client.response_cache.read(new_key))

    def test_identity_specific_aggregate_cache_hit_remains_safe_at_zero_quota(self):
        client = GitHubClient(offline=True)
        client.rate_limit_remaining = 0
        client._pull_identities[("owner/repo", 1)] = (
            self.head,
            self.base_old,
            "owner/repo",
            "main",
        )
        key = ":".join(
            [
                "pr-files",
                "owner/repo",
                "1",
                self.head,
                self.base_old,
                "owner/repo",
                "main",
            ]
        )
        client._store_response(key, "", json.dumps([{"filename": "cached.yaml"}]))
        with patch("moc_env.github.urlopen") as request:
            self.assertEqual(
                list(client.pr_files("owner/repo", 1)),
                [{"filename": "cached.yaml"}],
            )
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
