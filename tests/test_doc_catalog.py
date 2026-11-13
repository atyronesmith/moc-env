from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moc_env import cli
from moc_env.doc_catalog import (
    CatalogSource,
    refresh_document_catalog,
    render_catalog_refresh_text,
)


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test Author",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


class DocCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "MOC" / "example-repo"
        self.repository.mkdir(parents=True)
        _run_git(self.repository, "init")
        self.document = self.repository / "docs" / "example.md"
        self.document.parent.mkdir()
        self.document.write_text("Initial documentation.\n", encoding="utf-8")
        _run_git(self.repository, "add", ".")
        _run_git(self.repository, "commit", "-m", "initial")
        self.initial_ref = subprocess.run(
            ("git", "-C", str(self.repository), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.source = CatalogSource(
            source_id="example",
            repository="example/example-repo",
            path="docs/example.md",
            ref=self.initial_ref,
            title="Example Documentation",
            kind="design",
            topics=("example",),
            summary="Example source.",
            url="https://example.com/example",
            short_id="EX-1",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_refresh_catalog_caches_current_source(self) -> None:
        cache = self.root / "cache"
        report = refresh_document_catalog(
            {"example": self.source},
            self.root / "MOC",
            cache,
        )

        self.assertEqual(len(report.entries), 1)
        entry = report.entries[0]
        self.assertEqual(entry.status, "current")
        self.assertEqual(entry.head_ref, self.initial_ref)
        self.assertEqual(entry.source.short_id, "EX-1")

        manifest = json.loads((cache / "manifest.json").read_text())
        self.assertEqual(manifest["schemaVersion"], "1")
        self.assertEqual(
            manifest["sources"]["example"]["registeredRef"],
            self.initial_ref,
        )
        self.assertEqual(
            manifest["sources"]["example"]["headRef"],
            self.initial_ref,
        )
        self.assertEqual(manifest["sources"]["example"]["status"], "current")
        cached_document = cache / manifest["sources"]["example"]["documentPath"]
        self.assertEqual(
            cached_document.read_text(),
            "Initial documentation.\n",
        )

    def test_refresh_catalog_records_updated_head(self) -> None:
        cache = self.root / "cache"
        self.document.write_text("Updated documentation.\n", encoding="utf-8")
        _run_git(self.repository, "add", ".")
        _run_git(self.repository, "commit", "-m", "update")
        updated_ref = subprocess.run(
            ("git", "-C", str(self.repository), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        report = refresh_document_catalog(
            {"example": self.source},
            self.root / "MOC",
            cache,
        )
        entry = report.entries[0]

        self.assertEqual(entry.status, "updated")
        self.assertEqual(entry.head_ref, updated_ref)
        manifest = json.loads((cache / "manifest.json").read_text())
        self.assertEqual(
            manifest["sources"]["example"]["registeredRef"],
            self.initial_ref,
        )
        self.assertEqual(manifest["sources"]["example"]["headRef"], updated_ref)
        cached_document = cache / manifest["sources"]["example"]["documentPath"]
        self.assertEqual(
            cached_document.read_text(),
            "Updated documentation.\n",
        )

    def test_refresh_catalog_text_report(self) -> None:
        report = refresh_document_catalog(
            {"example": self.source},
            self.root / "MOC",
            self.root / "cache",
        )
        rendered = render_catalog_refresh_text(report)

        self.assertIn("Documentation catalog refresh", rendered)
        self.assertIn("- EX-1 Example Documentation: current", rendered)

    def test_cli_refresh_doc_catalog_dispatch(self) -> None:
        cache = self.root / "cli-cache"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "load_catalog_sources",
                return_value={"example": self.source},
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                [
                    "refresh-doc-catalog",
                    "--repository-root",
                    str(self.root / "MOC"),
                    "--cache-root",
                    str(cache),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["entries"][0]["source"]["short_id"], "EX-1")
        self.assertTrue((cache / "manifest.json").is_file())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
