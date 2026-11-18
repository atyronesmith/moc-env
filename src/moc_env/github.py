"""Small read-only GitHub REST API client."""

from __future__ import annotations

import json
import re
import time
from contextvars import ContextVar
from collections.abc import Iterator
from collections.abc import Callable
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .github_cache import GitHubResponseCache


run_clients: ContextVar[list | None] = ContextVar("github_run_clients", default=None)


class GitHubError(RuntimeError):
    """A GitHub API request failed."""


class RateLimitError(GitHubError):
    """GitHub refused the request because the API quota was exhausted."""


class GitHubClient:
    """Minimal GitHub REST client with pagination and token support."""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 20.0,
        refs: dict[str, str] | None = None,
        offline: bool = False,
        refresh: bool = False,
    ) -> None:
        self.token = token
        self.timeout = timeout
        self.refs = refs or {}
        self.base_url = "https://api.github.com"
        self.source_snapshots: dict[tuple[str, str], str] = {}
        self.rate_limit_remaining: int | None = None
        self.on_response: Callable[[int], None] | None = None
        self._rate_limit_warning_sent = False
        self.api_calls_used = 0
        self.counted_endpoints: list[str] = []
        self.requests_made = 0
        self.cache_hits = 0
        clients = run_clients.get()
        if clients is not None:
            clients.append(self)
        self.offline = offline
        self.refresh = refresh
        self.response_cache = GitHubResponseCache()
        self._responses: dict[str, tuple[Any, Any]] = {}
        self._raw_responses: dict[str, str] = {}
        self._unrevalidated_sources: dict[str, str] = {}
        self._trees: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    def record_source(self, repository: str, ref: str, sha: str | None) -> None:
        """Record a repository snapshot without making another API request."""

        if sha:
            self.source_snapshots[(repository, ref)] = sha

    def sources(self) -> list[dict[str, Any]]:
        return [
            {
                "repository": repository,
                "ref": ref,
                "sha": sha,
                **(
                    {
                        "from_cache": True,
                        "fetched_at": self._unrevalidated_sources[repository],
                    }
                    if repository in self._unrevalidated_sources
                    else {}
                ),
            }
            for (repository, ref), sha in sorted(self.source_snapshots.items())
        ]

    def ref_for(self, repository: str) -> str:
        return self.refs.get(repository, "main")

    @staticmethod
    def _is_commit_sha(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40}", value) is not None

    def snapshot_request_urls(
        self,
        repository: str,
        ref: str = "main",
        *,
        include_tree: bool = True,
    ) -> list[str]:
        """Estimate commit and tree requests without resolving refs remotely.

        Fixed-path readers resolve only the commit; passing ``include_tree``
        as false keeps their speculative tree out of the quota estimate.
        """

        ref = self.refs.get(repository, ref)
        prefix = f"{self.base_url}/repos/{repository}"
        if self._is_commit_sha(ref):
            if not include_tree:
                return []
            return [f"{prefix}/git/trees/{ref}?recursive=1"]
        commit_url = f"{prefix}/commits/{quote(ref, safe='/')}"
        if not include_tree:
            return [commit_url]
        cached = None if self.refresh else self.response_cache.read(commit_url)
        try:
            data = json.loads(cached["body"]) if cached else None
        except json.JSONDecodeError:
            data = None
        sha = data.get("sha") if isinstance(data, dict) else None
        tree_ref = sha if self._is_commit_sha(sha) else ref
        return [commit_url, f"{prefix}/git/trees/{tree_ref}?recursive=1"]

    def resolve_commit(self, repository: str, ref: str = "main") -> str:
        """Resolve a mutable ref once, keeping commits distinct from Git trees."""

        ref = self.refs.get(repository, ref)
        sha = self.source_snapshots.get((repository, ref))
        if sha is not None:
            return sha
        if self._is_commit_sha(ref):
            sha = ref
        else:
            data = self.get_json(f"/repos/{repository}/commits/{quote(ref, safe='/')}")
            sha = data.get("sha") if isinstance(data, dict) else None
            if not self._is_commit_sha(sha):
                raise GitHubError(f"GitHub did not resolve a commit SHA for {repository}@{ref}")
        self.record_source(repository, ref, sha)
        return sha

    def _record_headers(self, headers: Any) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None and remaining.isdigit():
            self.rate_limit_remaining = int(remaining)
            if self.on_response and not self._rate_limit_warning_sent:
                self._rate_limit_warning_sent = True
                self.on_response(self.rate_limit_remaining)

    def _headers(self, etag: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "moc-env",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if etag:
            headers["If-None-Match"] = etag
        return headers

    def _request(self, url: str, etag: str | None = None) -> tuple[Any, Any]:
        request = Request(url, headers=self._headers(etag), method="GET")
        try:
            body, headers, status = self._read_response(request)
            self._record_headers(headers)
            if status == 304 and etag is not None:
                cached = self.response_cache.read(url)
                if cached is not None:
                    self.cache_hits += 1
                    return (
                        json.loads(cached["body"]),
                        self._headers_with_cached_link(headers, cached),
                    )
                raise GitHubError(f"GitHub returned 304 without a usable cached response for {url}")
            data = json.loads(body)
            response_etag = headers.get("ETag")
            if response_etag:
                self._store_response(
                    url,
                    response_etag,
                    body,
                    self._next_link(headers),
                )
            return data, headers
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            exc.close()
            self._record_headers(exc.headers)
            if exc.code == 304 and etag is not None:
                cached = self.response_cache.read(url)
                if cached is not None:
                    self.cache_hits += 1
                    return (
                        json.loads(cached["body"]),
                        self._headers_with_cached_link(exc.headers, cached),
                    )
                raise GitHubError(
                    f"GitHub returned 304 without a usable cached response for {url}"
                ) from exc
            remaining = exc.headers.get("X-RateLimit-Remaining")
            if exc.code in (403, 429) and remaining == "0":
                reset = int(exc.headers.get("X-RateLimit-Reset", "0"))
                reset_at = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(reset))
                raise RateLimitError(
                    f"GitHub API rate limit exhausted; resets around {reset_at}. "
                    "Set GITHUB_TOKEN or run gh auth login."
                ) from exc
            raise GitHubError(
                f"GitHub API request failed ({exc.code}) for {url}: {body[:500]}"
            ) from exc
        except (OSError, URLError, HTTPException, json.JSONDecodeError) as exc:
            raise GitHubError(f"GitHub API request failed for {url}: {exc}") from exc

    def _read_response(self, request: Request) -> tuple[str, Any, int]:
        """Read a response, retrying transient failures three times."""

        for attempt in range(4):
            try:
                if self.offline:
                    raise AssertionError("HTTP requests are forbidden in offline mode")
                self.requests_made += 1
                with urlopen(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    self._count_quota(request.full_url, status)
                    return (
                        response.read().decode("utf-8"),
                        response.headers,
                        status,
                    )
            except HTTPError as exc:
                self._count_quota(request.full_url, exc.code)
                if not 500 <= exc.code < 600 or attempt == 3:
                    raise
                exc.close()
            except (OSError, URLError, HTTPException):
                if attempt == 3:
                    raise
            time.sleep(0.5 * (2 ** attempt))
        raise AssertionError("unreachable retry state")

    def _count_quota(self, url: str, status: int) -> None:
        if url.startswith(self.base_url + "/") and not url.endswith("/rate_limit") and status != 304:
            self.api_calls_used += 1
            self.counted_endpoints.append(url.removeprefix(self.base_url))

    def _mark_unrevalidated(self, url: str, cached: dict[str, Any]) -> None:
        """Keep the oldest cached fetch time used for each repository."""

        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        if parsed.netloc == "api.github.com" and len(parts) >= 3 and parts[0] == "repos":
            repository = "/".join(parts[1:3])
        elif parsed.netloc == "raw.githubusercontent.com" and len(parts) >= 3:
            repository = "/".join(parts[:2])
        else:
            return
        fetched_at = cached.get("fetched_at") or "unknown"
        previous = self._unrevalidated_sources.get(repository)
        self._unrevalidated_sources[repository] = (
            min(previous, fetched_at) if previous is not None else fetched_at
        )

    def get_json(self, path_or_url: str) -> Any:
        url = path_or_url if path_or_url.startswith("https://") else self.base_url + path_or_url
        return self._get_response(url)[0]

    def reserve_quota(
        self, estimated_calls: int, candidate_urls: list[str] | None = None
    ) -> None:
        """Stop before REST work when the known quota cannot cover it."""

        if self.offline:
            return
        if self.rate_limit_remaining is None:
            data = self.get_json("/rate_limit")
            resources = data.get("resources", {}).get("core", {}) if isinstance(data, dict) else {}
            remaining = resources.get("remaining")
            if isinstance(remaining, int):
                self.rate_limit_remaining = remaining
        cached_candidates = sum(
            1
            for url in candidate_urls or []
            if self.response_cache.read(url) is not None
        )
        effective_calls = max(0, estimated_calls - cached_candidates)
        if (
            self.rate_limit_remaining is not None
            and self.rate_limit_remaining < effective_calls
        ):
            raise RateLimitError(
                f"GitHub API quota is too small for this run: "
                f"{effective_calls} calls needed, {self.rate_limit_remaining} available. "
                "Pull-request discovery is skipped by default when unauthenticated."
            )

    def _get_response(self, url: str) -> tuple[Any, Any]:
        if url in self._responses:
            return self._responses[url]
        if self.offline:
            cached = self.response_cache.read(url)
            if cached is None:
                raise GitHubError(
                    f"No cached GitHub response is available for {url}; "
                    "run the command without --offline to populate the cache"
                )
            data = json.loads(cached["body"])
            self.cache_hits += 1
            self._mark_unrevalidated(url, cached)
            response = (data, self._cached_headers(cached))
            self._responses[url] = response
            return response

        cached = None if self.refresh else self.response_cache.read(url)
        if (
            not self.authenticated
            and self.rate_limit_remaining == 0
            and cached is not None
        ):
            self.cache_hits += 1
            self._mark_unrevalidated(url, cached)
            response = (
                json.loads(cached["body"]),
                self._cached_headers(cached),
            )
            self._responses[url] = response
            return response
        response = self._request(url, cached["etag"] if cached else None)
        self._responses[url] = response
        return response

    @staticmethod
    def _next_link(headers: Any) -> str | None:
        link = (headers or {}).get("Link", "")
        for part in link.split(","):
            fields = part.split(";", 1)
            if len(fields) == 2 and 'rel="next"' in fields[1]:
                return fields[0].strip().strip("<>")
        return None

    @staticmethod
    def _cached_headers(cached: dict[str, Any]) -> dict[str, str]:
        next_url = cached.get("next")
        return (
            {"Link": f'<{next_url}>; rel="next"'}
            if next_url
            else {}
        )

    @staticmethod
    def _headers_with_cached_link(
        headers: Any, cached: dict[str, Any]
    ) -> Any:
        if headers is not None and headers.get("Link"):
            return headers
        next_url = cached.get("next")
        if not next_url:
            return headers
        merged = dict(headers.items()) if headers is not None else {}
        merged["Link"] = f'<{next_url}>; rel="next"'
        return merged

    def _store_response(
        self,
        url: str,
        etag: str,
        body: str,
        next_url: str | None = None,
    ) -> None:
        try:
            self.response_cache.write(url, etag, body, next_url)
        except OSError:
            # A read-only or unwritable cache must not prevent a read-only report.
            pass

    def list(self, path: str, params: dict[str, str] | None = None) -> Iterator[dict[str, Any]]:
        query = ""
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            query = "?" + query
        url = self.base_url + path + query

        while url:
            data, headers = self._get_response(url)
            if not isinstance(data, list):
                raise GitHubError(f"Expected a GitHub list response from {url}")
            yield from data

            url = self._next_link(headers)

    def get_tree(self, repository: str, ref: str = "main") -> dict[str, dict[str, Any]]:
        ref = self.refs.get(repository, ref)
        key = (repository, ref)
        if key in self._trees:
            return self._trees[key]
        commit_sha = self.resolve_commit(repository, ref)
        data = self.get_json(f"/repos/{repository}/git/trees/{commit_sha}?recursive=1")
        if not isinstance(data, dict) or data.get("truncated") is True:
            raise GitHubError(f"GitHub tree response was truncated for {repository}@{ref}")
        tree = {
            item["path"]: item
            for item in data.get("tree", [])
            if isinstance(item, dict) and item.get("type") == "blob"
        }
        self._trees[key] = tree
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        ref = self.refs.get(repository, ref)
        sha = self.source_snapshots.get((repository, ref))
        if sha is None:
            sha = self.resolve_commit(repository, ref)
        return self._get_raw_file(repository, sha, path)

    def _get_raw_file(self, repository: str, sha: str, path: str) -> str:
        url = (
            f"https://raw.githubusercontent.com/{repository}/{sha}/"
            f"{quote(path)}"
        )
        if url in self._raw_responses:
            return self._raw_responses[url]
        if self.offline:
            cached = self.response_cache.read(url)
            if cached is None:
                raise GitHubError(
                    f"No cached GitHub response is available for {url}; "
                    "run the command without --offline to populate the cache"
                )
            self._raw_responses[url] = cached["body"]
            self.cache_hits += 1
            self._mark_unrevalidated(url, cached)
            return cached["body"]
        cached = None if self.refresh else self.response_cache.read(url)
        body = self._raw_request(url, cached["etag"] if cached else None)
        self._raw_responses[url] = body
        return body

    def _raw_request(self, url: str, etag: str | None) -> str:
        headers = {"User-Agent": "moc-env"}
        if etag:
            headers["If-None-Match"] = etag
        request = Request(url, headers=headers, method="GET")
        try:
            body, response_headers, status = self._read_response(request)
            if status == 304 and etag is not None:
                cached = self.response_cache.read(url)
                if cached is None:
                    raise GitHubError(f"GitHub returned 304 without a usable cached response for {url}")
                self.cache_hits += 1
                return cached["body"]
            response_etag = response_headers.get("ETag")
            if response_etag:
                self._store_response(url, response_etag, body)
            return body
        except HTTPError as exc:
            if exc.code == 304 and etag is not None:
                cached = self.response_cache.read(url)
                if cached is not None:
                    self.cache_hits += 1
                    exc.close()
                    return cached["body"]
            body = exc.read().decode("utf-8", errors="replace")
            exc.close()
            raise GitHubError(
                f"GitHub raw download failed ({exc.code}) for {url}: {body[:500]}"
            ) from exc
        except (OSError, URLError, HTTPException) as exc:
            raise GitHubError(f"GitHub raw download failed for {url}: {exc}") from exc

    def pulls(self, repository: str, state: str = "all") -> Iterator[dict[str, Any]]:
        yield from self.list(
            f"/repos/{repository}/pulls", {"state": state, "per_page": "100"}
        )

    def pr_files(self, repository: str, number: int) -> Iterator[dict[str, Any]]:
        yield from self.list(f"/repos/{repository}/pulls/{number}/files", {"per_page": "100"})


def github_url(repository: str, path: str, ref: str = "main") -> str:
    owner_repo = urlsplit(repository).path.strip("/") or repository
    return f"https://github.com/{owner_repo}/blob/{ref}/{path}"
