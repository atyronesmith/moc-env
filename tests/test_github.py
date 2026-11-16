from __future__ import annotations

import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from moc_env.github import GitHubClient, RateLimitError


class GitHubClientTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
