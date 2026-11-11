"""Small read-only GitHub REST API client."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class GitHubError(RuntimeError):
    """A GitHub API request failed."""


class RateLimitError(GitHubError):
    """GitHub refused the request because the API quota was exhausted."""


class GitHubClient:
    """Minimal GitHub REST client with pagination and token support."""

    def __init__(self, token: str | None = None, timeout: float = 20.0) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout
        self.base_url = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "moc-env",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, url: str) -> tuple[Any, Any]:
        request = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body), response.headers
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            remaining = exc.headers.get("X-RateLimit-Remaining")
            if exc.code in (403, 429) and remaining == "0":
                reset = int(exc.headers.get("X-RateLimit-Reset", "0"))
                reset_at = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(reset))
                raise RateLimitError(
                    f"GitHub API rate limit exhausted; resets around {reset_at}"
                ) from exc
            raise GitHubError(
                f"GitHub API request failed ({exc.code}) for {url}: {body[:500]}"
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GitHubError(f"GitHub API request failed for {url}: {exc}") from exc

    def get_json(self, path_or_url: str) -> Any:
        url = path_or_url if path_or_url.startswith("https://") else self.base_url + path_or_url
        data, _ = self._request(url)
        return data

    def list(self, path: str, params: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
        query = ""
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            query = "?" + query
        url = self.base_url + path + query

        while url:
            data, headers = self._request(url)
            if not isinstance(data, list):
                raise GitHubError(f"Expected a GitHub list response from {url}")
            yield from data

            next_url = None
            link = headers.get("Link", "")
            for part in link.split(","):
                fields = part.split(";", 1)
                if len(fields) == 2 and 'rel="next"' in fields[1]:
                    next_url = fields[0].strip().strip("<>")
                    break
            url = next_url

    def get_tree(self, repository: str, ref: str = "main") -> dict[str, dict[str, Any]]:
        data = self.get_json(f"/repos/{repository}/git/trees/{ref}?recursive=1")
        if not isinstance(data, dict) or data.get("truncated") is True:
            raise GitHubError(f"GitHub tree response was truncated for {repository}@{ref}")
        return {
            item["path"]: item
            for item in data.get("tree", [])
            if isinstance(item, dict) and item.get("type") == "blob"
        }

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        data = self.get_json(f"/repos/{repository}/contents/{path}?ref={ref}")
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            raise GitHubError(f"Unexpected GitHub contents response for {repository}:{path}")
        return base64.b64decode(data["content"]).decode("utf-8")

    def pulls(self, repository: str, state: str = "all") -> Iterator[dict[str, Any]]:
        yield from self.list(
            f"/repos/{repository}/pulls", {"state": state, "per_page": "100"}
        )

    def pr_files(self, repository: str, number: int) -> Iterator[dict[str, Any]]:
        yield from self.list(f"/repos/{repository}/pulls/{number}/files", {"per_page": "100"})


def github_url(repository: str, path: str, ref: str = "main") -> str:
    owner_repo = urlsplit(repository).path.strip("/") or repository
    return f"https://github.com/{owner_repo}/blob/{ref}/{path}"
