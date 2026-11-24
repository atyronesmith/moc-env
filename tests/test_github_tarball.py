"""Offline archive transport, reader parity, cache, and CLI acceptance tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.parse import urlsplit

from moc_env import cli
from moc_env.github import GitHubClient, GitHubError
from moc_env.github_tarball import DownloadError, SafeRedirectHandler, TarballGitHubClient

from fakes import FakeGitHubClient, FullyConfiguredFakeGitHubClient


REPO = "CCI-MOC/oac-apps"
SHA = "a" * 40
FILES = {
    "values.yaml": b"value: yes\r\n",
    "nested/file.yaml": b"nested: true\n",
    "link": b"nested/file.yaml",
    "binary": b"\x00\xff\x80",
    "executable": b"#!/bin/sh\n",
}


def blob_entry(repository, path, content):
    sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    return {
        "path": path, "mode": "120000" if path == "link" else
        "100755" if path == "executable" else "100644",
        "type": "blob", "sha": sha, "size": len(content),
        "url": f"https://api.github.com/repos/{repository}/git/blobs/{sha}",
    }


def archive_bytes(files=FILES, extra_members=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        root = tarfile.TarInfo("owner-repo-sha")
        root.type = tarfile.DIRTYPE
        bundle.addfile(root)
        # An empty submodule directory is not a blob in the Git trees API.
        submodule = tarfile.TarInfo("owner-repo-sha/submodule")
        submodule.type = tarfile.DIRTYPE
        bundle.addfile(submodule)
        for path, content in files.items():
            member = tarfile.TarInfo(f"owner-repo-sha/{path}")
            member.mode = 0o755 if path == "executable" else 0o644
            if path == "link":
                member.type = tarfile.SYMTYPE
                member.linkname = content.decode()
                bundle.addfile(member)
            else:
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
        for member in extra_members:
            bundle.addfile(member)
    return stream.getvalue()


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class RepositoryTransport:
    """Both HTTP representations are generated from one byte-for-byte file set."""

    def __init__(self, files=None):
        self.files = files or {REPO: FILES}
        self.api_urls = []
        self.download_urls = []
        self.failure = None
        self.metadata = None

    def api(self, request, **kwargs):
        url = request.full_url
        self.api_urls.append(url)
        if url.endswith("/rate_limit"):
            return Response(b'{"resources":{"core":{"remaining":5000}}}')
        for repository, files in self.files.items():
            if f"/repos/{repository}/commits/" in url:
                sha = self.metadata.SOURCE_SHAS[repository] if self.metadata else SHA
                return Response(json.dumps({"sha": sha}).encode())
            if f"/repos/{repository}/git/trees/" in url:
                entries = [blob_entry(repository, path, content) for path, content in files.items()]
                entries.extend([
                    {"path": "nested", "type": "tree", "mode": "040000"},
                    {"path": "submodule", "type": "commit", "mode": "160000"},
                ])
                return Response(json.dumps({"tree": entries}).encode())
            prefix = f"https://raw.githubusercontent.com/{repository}/"
            if url.startswith(prefix):
                path = url.removeprefix(prefix).split("/", 1)[1]
                if path in files:
                    return Response(files[path])
        if self.metadata:
            parts = urlsplit(url).path.strip("/").split("/")
            repository = "/".join(parts[1:3])
            if parts[3] == "commits":
                data = {"sha": self.metadata.SOURCE_SHAS[repository]}
            elif parts[3] == "pulls":
                data = list(self.metadata.pr_files(repository, int(parts[4]))) if len(parts) > 4 else list(self.metadata.pulls(repository))
            else:
                data = self.metadata.get_json(urlsplit(url).path)
            return Response(json.dumps(data).encode())
        raise AssertionError(f"Unexpected API request: {url}")

    def download(self, request, **kwargs):
        self.download_urls.append(request.full_url)
        if self.failure:
            if isinstance(self.failure, HTTPError):
                raise HTTPError(request.full_url, self.failure.code, self.failure.reason,
                                self.failure.headers, io.BytesIO(b"rate limit" if self.failure.code == 429 else self.failure.fp.getvalue()))
            raise self.failure
        for repository, files in self.files.items():
            if f"/repos/{repository}/tarball/" in request.full_url:
                return Response(archive_bytes(files))
        raise AssertionError(request.full_url)


class TarballReaderTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": str(self.cache)})
        environment.start()
        self.addCleanup(environment.stop)
        self.transport = RepositoryTransport()
        api = patch("moc_env.github.urlopen", side_effect=self.transport.api)
        api.start()
        self.addCleanup(api.stop)
        archive = patch("urllib.request.OpenerDirector.open", side_effect=self.transport.download)
        archive.start()
        self.addCleanup(archive.stop)

    def test_reader_contract_parameterized_over_both_backends(self):
        for backend in (GitHubClient, TarballGitHubClient):
            with self.subTest(backend=backend.__name__):
                reader = backend()
                expected = {path: blob_entry(REPO, path, content) for path, content in FILES.items()}
                self.assertEqual(reader.get_tree(REPO), expected)
                for path, content in FILES.items():
                    if path == "binary":
                        with self.assertRaises(UnicodeDecodeError):
                            reader.get_file(REPO, path)
                    else:
                        self.assertEqual(reader.get_file(REPO, path), content.decode())
                self.assertEqual(reader.resolve_commit(REPO), SHA)
                self.assertEqual(sum("/commits/" in url for url in self.transport.api_urls), 1)
                self.transport.api_urls.clear()

    def test_cached_sha_needs_no_network_even_with_refresh(self):
        TarballGitHubClient().get_tree(REPO, SHA)
        self.transport.api_urls.clear()
        self.transport.download_urls.clear()
        reader = TarballGitHubClient(refresh=True)
        self.assertEqual(reader.get_file(REPO, "link", SHA), "nested/file.yaml")
        self.assertEqual(self.transport.api_urls, [])
        self.assertEqual(self.transport.download_urls, [])
        self.assertEqual(reader.cached_trees, 1)

    def test_unsafe_members_rejected_without_writing_outside_cache(self):
        for name in ("../escape", str(self.cache.parent / "escape"), "root/../../escape"):
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                with patch.object(self.transport, "download", return_value=Response(archive_bytes(extra_members=[member]))):
                    reader = TarballGitHubClient()
                    reader._opener.open = self.transport.download
                    with self.assertRaises(GitHubError):
                        reader.get_tree(REPO, SHA)
                self.assertFalse((self.cache.parent / "escape").exists())
                self.assertFalse((self.cache / "trees/CCI-MOC/oac-apps" / SHA).exists())

    def test_symlink_targets_are_recorded_without_following_them(self):
        with tempfile.TemporaryDirectory() as outside:
            for index, target in enumerate(("/etc/passwd", "../../x", str(Path(outside) / "never-created"))):
                with self.subTest(target=target):
                    member = tarfile.TarInfo("owner-repo-sha/escape")
                    member.type = tarfile.SYMTYPE
                    member.linkname = target
                    reader = TarballGitHubClient()
                    sha = str(index + 1) * 40
                    with patch.object(reader._opener, "open", return_value=Response(archive_bytes(extra_members=[member]))):
                        tree = reader.get_tree(REPO, sha)
                    self.assertEqual(tree["escape"]["mode"], "120000")
                    self.assertEqual(reader.get_file(REPO, "escape", sha), target)
                    local = self.cache / "trees/CCI-MOC/oac-apps" / sha / "tree/escape"
                    self.assertTrue(local.is_file())
                    self.assertFalse(local.is_symlink())
                    self.assertEqual(list(Path(outside).iterdir()), [])
                    self.assertFalse((local.parent / "../../x").resolve().exists())

    def test_export_ignore_warns_once_with_repository_and_attribute(self):
        self.transport.files = {REPO: {
            ".gitattributes": b"private/* export-ignore\n",
            "nested/.gitattributes": b"*.secret export-ignore\n",
        }}
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic):
            TarballGitHubClient().get_tree(REPO, SHA)
        self.assertEqual(len(diagnostic.getvalue().splitlines()), 1)
        self.assertIn(REPO, diagnostic.getvalue())
        self.assertIn("export-ignore", diagnostic.getvalue())

    def test_nested_export_subst_warns_once_with_repository_and_attribute(self):
        self.transport.files = {REPO: {"nested/.gitattributes": b"version.txt export-subst\n"}}
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic):
            TarballGitHubClient().get_tree(REPO, SHA)
        self.assertEqual(len(diagnostic.getvalue().splitlines()), 1)
        self.assertIn(REPO, diagnostic.getvalue())
        self.assertIn("export-subst", diagnostic.getvalue())

    def test_gitattributes_without_export_attributes_does_not_warn(self):
        self.transport.files = {REPO: {".gitattributes": b"*.yaml text eol=lf\n"}}
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic):
            TarballGitHubClient().get_tree(REPO, SHA)
        self.assertEqual(diagnostic.getvalue(), "")

    def test_offline_pinned_sha_records_original_fetch_time(self):
        TarballGitHubClient().get_tree(REPO, SHA)
        target = self.cache / "trees/CCI-MOC/oac-apps" / SHA
        fetched_at = json.loads((target / "metadata.json").read_text())["fetched_at"]
        reader = TarballGitHubClient(offline=True)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")):
            reader.get_tree(REPO, SHA)
        self.assertTrue(reader.sources()[0]["from_cache"])
        self.assertEqual(reader.sources()[0]["fetched_at"], fetched_at)

    def test_half_download_leaves_no_sha_or_temporary_directory(self):
        class Interrupted(Response):
            def read(self, size=-1):
                if self.tell():
                    raise IncompleteRead(b"partial")
                return super().read(10)
        reader = TarballGitHubClient()
        with patch.object(reader._opener, "open", return_value=Interrupted(b"incomplete archive")):
            with self.assertRaises(DownloadError):
                reader.get_tree(REPO, SHA)
        self.assertEqual(list((self.cache / "trees/CCI-MOC/oac-apps").iterdir()), [])

    def test_premature_eof_never_publishes_a_tree(self):
        reader = TarballGitHubClient()
        payload = archive_bytes()
        with patch.object(reader._opener, "open", return_value=Response(payload[:len(payload) // 2], {"Content-Length": str(len(payload))})):
            with self.assertRaises(DownloadError):
                reader.get_tree(REPO, SHA)
        self.assertEqual(list((self.cache / "trees/CCI-MOC/oac-apps").iterdir()), [])

    def test_invalid_archive_with_token_does_not_fallback(self):
        reader = TarballGitHubClient(token="token")
        diagnostic = io.StringIO()
        with contextlib.redirect_stderr(diagnostic), patch.object(reader._opener, "open", return_value=Response(b"not an archive")):
            with self.assertRaises(GitHubError):
                reader.get_tree(REPO, SHA)
        self.assertEqual(diagnostic.getvalue(), "")
        self.assertEqual(self.transport.api_urls, [])

    def test_only_three_most_recently_used_shas_remain(self):
        reader = TarballGitHubClient()
        shas = [str(number) * 40 for number in range(1, 5)]
        for sha in shas[:3]:
            reader.get_tree(REPO, sha)
        reader.get_tree(REPO, shas[0])  # Reuse the oldest; evict SHA 2 instead.
        reader.get_tree(REPO, shas[3])
        directories = {path.name for path in (self.cache / "trees/CCI-MOC/oac-apps").iterdir()}
        self.assertEqual(directories, {shas[0], shas[2], shas[3]})

    def test_redirect_strips_token_from_every_foreign_host(self):
        handler = SafeRedirectHandler()
        request = Request(
            "https://api.github.com/repos/owner/repo/tarball/sha",
            headers={"Authorization": "Bearer private-token"},
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://codeload.github.com/owner/repo/archive",
        )
        self.assertNotIn("Authorization", redirected.headers)
        self.assertEqual(request.get_header("Authorization"), "Bearer private-token")

    def test_download_sends_token_only_to_api(self):
        reader = TarballGitHubClient(token="private-token")
        with patch.object(reader._opener, "open", return_value=Response(archive_bytes())) as opener:
            reader.get_tree(REPO, SHA)
        self.assertEqual(opener.call_args.args[0].get_header("Authorization"), "Bearer private-token")

    def test_concurrent_downloads_publish_one_complete_tree(self):
        def download(request, **kwargs):
            return Response(archive_bytes())
        with patch("urllib.request.OpenerDirector.open", side_effect=download) as downloads:
            with ThreadPoolExecutor(max_workers=2) as pool:
                trees = list(pool.map(lambda _: TarballGitHubClient().get_tree(REPO, SHA), range(2)))
        self.assertEqual(trees[0], trees[1])
        self.assertEqual(set(trees[0]), set(FILES))
        self.assertEqual(downloads.call_count, 1)
        self.assertEqual([path.name for path in (self.cache / "trees/CCI-MOC/oac-apps").iterdir()], [SHA])

    def test_fallback_only_on_eligible_download_failures(self):
        for code, headers, body, allowed in (
            (429, {}, b"", True), (403, {"X-RateLimit-Remaining": "0"}, b"", True),
            (403, {}, b"secondary rate limit", True), (503, {}, b"", True),
            (403, {}, b"forbidden", False), (404, {}, b"missing", False),
            (401, {}, b"unauthorized", False),
        ):
            with self.subTest(code=code, allowed=allowed):
                self.transport.failure = HTTPError("https://api.github.com/archive", code, "failure", headers, io.BytesIO(body))
                reader = TarballGitHubClient(token="token")
                diagnostics = io.StringIO()
                with contextlib.redirect_stderr(diagnostics):
                    if allowed:
                        self.assertIn("link", reader.get_tree(REPO, SHA))
                        self.assertEqual(reader.get_file(REPO, "link", SHA), "nested/file.yaml")
                        self.assertEqual(len(diagnostics.getvalue().splitlines()), 1)
                    else:
                        with self.assertRaises(DownloadError):
                            reader.get_tree(REPO, SHA)
                        self.assertEqual(diagnostics.getvalue(), "")
                self.assertEqual(reader.tarball_downloads, 1)
                self.transport.failure.close()

    def test_network_error_falls_back_once_with_token(self):
        self.transport.failure = URLError("connection reset")
        diagnostics = io.StringIO()
        reader = TarballGitHubClient(token="token")
        with contextlib.redirect_stderr(diagnostics):
            self.assertIn("link", reader.get_tree(REPO, SHA))
        self.assertIn("network error", diagnostics.getvalue())
        self.assertEqual(reader.tarball_downloads, 1)

    def test_offline_cache_hit_and_miss(self):
        TarballGitHubClient().get_tree(REPO, SHA)
        self.assertIn("link", TarballGitHubClient(offline=True).get_tree(REPO, SHA))
        with self.assertRaisesRegex(GitHubError, "No cached tarball tree"):
            TarballGitHubClient(offline=True).get_tree(REPO, "b" * 40)
        self.assertEqual(len(self.transport.download_urls), 1)

    def run_cli(self, arguments, token=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, "_resolve_github_token", return_value=token), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments, clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_429_without_token_fails_cleanly_without_per_file_requests(self):
        self.transport.files["CCI-MOC/oac-infra"] = FILES
        self.transport.failure = HTTPError("https://api.github.com/archive", 429, "rate limit", {"Retry-After": "120"}, io.BytesIO())
        code, output, diagnostic = self.run_cli(["status", "bu-ist-demo", "--no-auth"])
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("429", diagnostic)
        self.assertIn("120", diagnostic)
        self.assertIn("token or retry later", diagnostic)
        self.assertNotIn("Traceback", diagnostic)
        self.assertFalse(any("/git/trees/" in url or "raw.githubusercontent.com" in url for url in self.transport.api_urls))
        self.transport.failure.close()

    def test_pull_ref_resolves_once_and_downloads_exact_sha(self):
        reader = TarballGitHubClient(refs={REPO: "pull/246/head"})
        reader.get_tree(REPO)
        reader.get_file(REPO, "nested/file.yaml")
        self.assertEqual(self.transport.api_urls, [f"https://api.github.com/repos/{REPO}/commits/pull/246/head"])
        self.assertEqual(self.transport.download_urls, [f"https://api.github.com/repos/{REPO}/tarball/{SHA}"])

    def test_429_with_token_completes_cli_through_api_with_identical_output(self):
        fake = FullyConfiguredFakeGitHubClient()
        self.transport.metadata = fake
        self.transport.files = {
            repository: {path: fake.get_file(repository, path).encode() for path in fake.get_tree(repository)}
            for repository in fake.SOURCE_SHAS if repository != "CCI-MOC/MOC-issues"
        }
        arguments = ["status", "bu-ist-demo", "--no-prs"]
        success_code, expected, _ = self.run_cli(arguments, token="token")
        self.assertEqual(success_code, 0)
        def download(request, **kwargs):
            if "/oac-infra/tarball/" in request.full_url:
                raise HTTPError(request.full_url, 429, "rate limit", {"Retry-After": "120"}, io.BytesIO())
            return self.transport.download(request, **kwargs)
        # Use another cache root so no successful archive can mask the failure.
        with tempfile.TemporaryDirectory() as cold, patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": cold}), patch("urllib.request.OpenerDirector.open", side_effect=download):
            code, actual, diagnostic = self.run_cli(arguments, token="token")
        self.assertEqual(code, 0)
        self.assertEqual(actual, expected)
        warnings = [line for line in diagnostic.splitlines() if "warning:" in line]
        self.assertEqual(len(warnings), 1)
        self.assertIn("CCI-MOC/oac-infra", warnings[0])
        self.assertIn("429", warnings[0])
        self.assertIn("API backend", warnings[0])

    def test_cli_pull_ref_downloads_resolved_sha(self):
        fake = FullyConfiguredFakeGitHubClient()
        self.transport.metadata = fake
        self.transport.files = {
            repository: {path: fake.get_file(repository, path).encode() for path in fake.get_tree(repository)}
            for repository in fake.SOURCE_SHAS if repository != "CCI-MOC/MOC-issues"
        }
        code, _, diagnostic = self.run_cli(["status", "bu-ist-demo", "--no-prs", "--ref", "oac-apps=pull/246/head"])
        self.assertEqual(code, 0, diagnostic)
        self.assertIn(f"https://api.github.com/repos/{REPO}/commits/pull/246/head", self.transport.api_urls)
        self.assertIn(f"https://api.github.com/repos/{REPO}/tarball/{fake.SOURCE_SHAS[REPO]}", self.transport.download_urls)

    def test_default_backend_cli_offline_round_trip(self):
        fake = FullyConfiguredFakeGitHubClient()
        self.transport.metadata = fake
        self.transport.files = {
            repository: {path: fake.get_file(repository, path).encode() for path in fake.get_tree(repository)}
            for repository in fake.SOURCE_SHAS if repository != "CCI-MOC/MOC-issues"
        }
        def cached_api(request, **kwargs):
            response = self.transport.api(request, **kwargs)
            response.headers["ETag"] = '"fixture"'
            return response
        arguments = ["status", "bu-ist-demo", "--no-auth"]
        with patch("moc_env.github.urlopen", side_effect=cached_api):
            online_code, online, online_diagnostic = self.run_cli(arguments)
        self.assertEqual(online_code, 0, online_diagnostic)
        self.assertIn("7 tarball downloads", online_diagnostic)
        self.transport.download_urls.clear()
        with (
            patch("moc_env.github.urlopen", side_effect=AssertionError("HTTP forbidden")) as api,
            patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP forbidden")) as archive,
        ):
            offline_code, offline, diagnostic = self.run_cli([*arguments, "--offline"])
        self.assertEqual(offline_code, 0, diagnostic)
        self.assertEqual(
            next(line for line in online.splitlines() if line.startswith("RESULT:")),
            next(line for line in offline.splitlines() if line.startswith("RESULT:")),
        )
        self.assertIn("0 tarball downloads", diagnostic)
        self.assertEqual(self.transport.download_urls, [])
        for repository in fake.SOURCE_SHAS:
            self.assertIn(f"{repository.removeprefix('CCI-MOC/')}: from cache, fetched ", offline)
        api.assert_not_called()
        archive.assert_not_called()

    def test_existing_readers_parameterized_over_both_backends(self):
        # Replay existing assertions without changing their expected values or
        # tests/fakes.py. Both transports use exactly the fake's served file set.
        import test_status_checker

        names = (
            "test_check_refs_and_urls_use_repository_override",
            "test_bu_ist_demo_milestone_one_states",
            "test_workload_checks_are_mapped_to_workload_phase_rows",
            "test_boot_image_checks_state_the_matching_rule",
            "test_hub_status_includes_hub_checks_and_excludes_workload_checks",
            "test_work_status_includes_workload_checks_and_excludes_hub_checks",
            "test_check_metadata_and_next_actions_are_machine_readable",
            "test_list_environments_returns_hub_and_workload_clusters",
            "test_read_infra_observation_normalizes_repository_inputs",
            "test_read_environment_observation_normalizes_all_phase_one_sources",
        )
        fake = FakeGitHubClient()
        self.transport.metadata = fake
        self.transport.files = {
            repository: {path: fake.get_file(repository, path).encode() for path in fake.get_tree(repository)}
            for repository in fake.SOURCE_SHAS if repository != "CCI-MOC/MOC-issues"
        }
        for backend in (GitHubClient, TarballGitHubClient):
            for name in names:
                with self.subTest(backend=backend.__name__, existing_test=name):
                    case = test_status_checker.StatusCheckerTest(name)
                    case.setUp()
                    try:
                        with patch.object(test_status_checker, "FakeGitHubClient", backend):
                            getattr(case, name)()
                    finally:
                        case.tearDown()
                        case.doCleanups()


if __name__ == "__main__":
    unittest.main()
