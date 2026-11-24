"""Immutable repository snapshots, downloaded once and read locally."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from contextvars import ContextVar
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .environment_cache import environment_cache_directory
from .github import GitHubClient, GitHubError


selected_backend: ContextVar[str] = ContextVar("github_backend", default="tarball")


class SafeRedirectHandler(HTTPRedirectHandler):
    """Never send API credentials to an archive/redirect host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(newurl).netloc != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


class DownloadError(RuntimeError):
    """A terminal archive transport failure, handled once at the CLI boundary.

    Deliberately not a GitHubError: optional-file readers must not turn this
    repository-wide failure into a missing-file finding and a successful exit.
    """
    def __init__(
        self, repository: str, status: int | str, retry_after: str | None,
        fallback_allowed: bool,
    ) -> None:
        self.status = status
        self.fallback_allowed = fallback_allowed
        retry = f"; Retry-After: {retry_after}" if retry_after is not None else ""
        super().__init__(
            f"Tarball download failed for {repository} (status {status}{retry}); "
            "set a token or retry later to fix it"
        )


class TarballGitHubClient(GitHubClient):
    """Use the existing API client for metadata, but archives for file reads.

    Each SHA directory contains a tree and a generated Git blob index. Symlinks
    are stored as ordinary files containing the link text, exactly as raw GitHub
    serves them; no local file read ever follows an archive-supplied link.
    """

    backend_name = "tarball"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tarball_downloads = 0
        self.cached_trees = 0
        self._fallback_repositories: set[str] = set()
        self._snapshots: dict[tuple[str, str], Path] = {}
        self._opener = build_opener(SafeRedirectHandler())

    def snapshot_request_urls(
        self, repository: str, ref: str = "main", *, include_tree: bool = True,
    ) -> list[str]:
        # Archive downloads are accounted separately, not as per-file API work.
        return super().snapshot_request_urls(repository, ref, include_tree=False)

    def _download(self, repository: str, sha: str, destination: Path) -> None:
        url = f"{self.base_url}/repos/{repository}/tarball/{sha}"
        request = Request(url, headers=self._headers(), method="GET")
        self.tarball_downloads += 1
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            headers: Any = exc.headers or {}
            remaining = headers.get("X-RateLimit-Remaining")
            retry_after = headers.get("Retry-After")
            try:
                body = exc.read(4096).decode("utf-8", errors="replace")
            except (OSError, HTTPException):
                body = ""
            allowed = (
                exc.code == 429 or 500 <= exc.code < 600
                or (exc.code == 403 and (
                    remaining == "0" or retry_after is not None
                    or "rate limit" in body.lower()
                ))
            )
            exc.close()
            raise DownloadError(repository, exc.code, retry_after, allowed) from exc
        except (OSError, URLError, HTTPException) as exc:
            raise DownloadError(repository, "network error", None, True) from exc
        with response, destination.open("wb") as output:
            received = 0
            while True:
                try:
                    chunk = response.read(64 * 1024)
                except (OSError, URLError, HTTPException) as exc:
                    raise DownloadError(repository, "network error", None, True) from exc
                if not chunk:
                    break
                # Disk failures are not download failures and must not fallback.
                output.write(chunk)
                received += len(chunk)
            length = response.headers.get("Content-Length")
            if length is not None and length.isdigit() and received != int(length):
                raise DownloadError(repository, "network error (incomplete download)", None, True)

    @staticmethod
    def _unpack(archive: Path, destination: Path, repository: str) -> None:
        tree = destination / "tree"
        tree.mkdir()
        entries: dict[str, dict[str, Any]] = {}
        root: str | None = None
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle:
                original = PurePosixPath(member.name)
                if original.is_absolute() or ".." in original.parts or not original.parts:
                    raise GitHubError(f"Unsafe tarball member: {member.name}")
                if root is None:
                    root = original.parts[0]
                if original.parts[0] != root:
                    raise GitHubError("Tarball must contain a single top-level directory")
                if len(original.parts) == 1:
                    if not member.isdir():
                        raise GitHubError("Tarball root must be a directory")
                    continue
                stripped = copy.copy(member)
                stripped.name = str(PurePosixPath(*original.parts[1:]))
                target = tree / stripped.name
                if not target.resolve().is_relative_to(tree.resolve()):
                    raise GitHubError(f"Unsafe tarball member: {member.name}")
                if not (member.isdir() or member.isfile() or member.issym()):
                    raise GitHubError(f"Unsupported tarball member: {member.name}")
                if member.isdir():
                    bundle.extract(stripped, tree, filter="data")
                    continue
                if member.issym():
                    content = member.linkname.encode("utf-8", errors="surrogateescape")
                    stripped.type = tarfile.REGTYPE
                    stripped.linkname = ""
                    stripped.size = len(content)
                    stripped.mode = 0o644
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    mode = "120000"
                else:
                    bundle.extract(stripped, tree, filter="data")
                    content = target.read_bytes()
                    mode = "100755" if member.mode & 0o111 else "100644"
                sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
                entries[stripped.name] = {
                    "path": stripped.name, "mode": mode, "type": "blob", "sha": sha,
                    "size": len(content),
                    "url": f"https://api.github.com/repos/{repository}/git/blobs/{sha}",
                }
        (destination / "entries.json").write_text(json.dumps(entries), encoding="utf-8")
        (destination / "metadata.json").write_text(
            json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}),
            encoding="utf-8",
        )
        attributes: set[str] = set()
        for path in tree.rglob(".gitattributes"):
            if path.is_file():
                content = path.read_bytes()
                attributes.update(
                    name for name in ("export-ignore", "export-subst")
                    if name.encode("ascii") in content
                )
        if attributes:
            print(
                f"moc-env: warning: {repository}: .gitattributes contains "
                f"{', '.join(sorted(attributes))}; tarball contents may differ from Git blobs",
                file=sys.stderr,
            )

    def _snapshot(self, repository: str, ref: str) -> tuple[Path | None, str]:
        sha = self.resolve_commit(repository, ref)
        if repository in self._fallback_repositories:
            return None, sha
        parts = repository.split("/")
        if len(parts) != 2 or any(part in ("", ".", "..") for part in parts):
            raise GitHubError(f"Invalid repository: {repository}")
        parent = environment_cache_directory() / "trees" / parts[0] / parts[1]
        target = parent / sha
        key = repository, sha
        if key in self._snapshots and target.is_dir():
            os.utime(target, None)
            return target, sha
        parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            self.cached_trees += 1
        else:
            if self.offline:
                raise GitHubError(f"No cached tarball tree for {repository}@{sha}; run without --offline")
            try:
                with tempfile.TemporaryDirectory(dir=parent, prefix=f".{sha}.") as temporary:
                    staging = Path(temporary)
                    archive = staging / "archive.tar.gz"
                    self._download(repository, sha, archive)
                    unpacked = staging / "snapshot"
                    unpacked.mkdir()
                    self._unpack(archive, unpacked, repository)
                    try:
                        unpacked.rename(target)
                    except OSError:
                        if not target.is_dir():
                            raise
            except DownloadError as exc:
                if not self.token or not exc.fallback_allowed:
                    raise
                self._fallback_repositories.add(repository)
                print(
                    f"moc-env: warning: {repository}: tarball status {exc.status}; "
                    "using the API backend", file=sys.stderr,
                )
                return None, sha
            except (OSError, tarfile.TarError, EOFError) as exc:
                raise GitHubError(f"Invalid tarball for {repository}@{sha}: {exc}") from exc
        os.utime(target, None)
        if self.offline:
            metadata = target / "metadata.json"
            if metadata.is_file():
                fetched_at = json.loads(metadata.read_text(encoding="utf-8"))["fetched_at"]
            else:
                # Trees cached before fetch metadata was introduced remain usable.
                fetched_at = datetime.fromtimestamp(
                    (target / "entries.json").stat().st_mtime, timezone.utc,
                ).isoformat().replace("+00:00", "Z")
            self._mark_unrevalidated(
                f"{self.base_url}/repos/{repository}", {"fetched_at": fetched_at},
            )
        self._snapshots[key] = target
        # Directory mtime is the last use, not the archive's historical mtime.
        candidates = sorted(
            (path for path in parent.iterdir() if self._is_commit_sha(path.name) and path.is_dir()),
            key=lambda path: path.stat().st_mtime_ns, reverse=True,
        )
        for old in candidates[3:]:
            try:
                shutil.rmtree(old)
            except FileNotFoundError:
                pass
        return target, sha

    @contextmanager
    def _repository_lock(self, repository: str) -> Iterator[None]:
        # Serialize publication, LRU eviction and reads across processes. The
        # kernel releases the lock if a process exits during a download.
        parts = repository.split("/")
        if len(parts) != 2 or any(part in ("", ".", "..") for part in parts):
            raise GitHubError(f"Invalid repository: {repository}")
        owner = environment_cache_directory() / "trees" / parts[0]
        owner.mkdir(parents=True, exist_ok=True)
        with (owner / f".{parts[1]}.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def get_tree(self, repository: str, ref: str = "main") -> dict[str, dict[str, Any]]:
        with self._repository_lock(repository):
            snapshot, _sha = self._snapshot(repository, ref)
            if snapshot is None:
                return super().get_tree(repository, ref)
            return json.loads((snapshot / "entries.json").read_text(encoding="utf-8"))

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        with self._repository_lock(repository):
            snapshot, _sha = self._snapshot(repository, ref)
            if snapshot is None:
                return super().get_file(repository, path, ref)
            target = snapshot / "tree" / path
            if not target.resolve().is_relative_to((snapshot / "tree").resolve()):
                raise GitHubError(f"Invalid repository path: {path}")
            try:
                return target.read_bytes().decode("utf-8")
            except OSError as exc:
                raise GitHubError(f"GitHub raw download failed (404) for {repository}/{path}") from exc


def new_github_client(*args, **kwargs) -> GitHubClient:
    """Run-scoped backend factory; metadata calls always use the API reader."""
    if selected_backend.get() == "api":
        client = GitHubClient(*args, **kwargs)
        client.backend_name = "api"  # type: ignore[attr-defined]
        return client
    return TarballGitHubClient(*args, **kwargs)
