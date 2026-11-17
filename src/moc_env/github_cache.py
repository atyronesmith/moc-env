"""On-disk cache for read-only GitHub API response bodies and ETags."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .environment_cache import environment_cache_directory


CACHE_VERSION = 1
CACHE_FILENAME = "github-responses.json"


def github_response_cache_path() -> Path:
    return environment_cache_directory() / CACHE_FILENAME


class GitHubResponseCache:
    """Store response bodies and ETags by URL; never store credentials."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or github_response_cache_path()

    def read(self, url: str) -> dict[str, Any] | None:
        document = self._read_document()
        if document is None:
            return None
        entry = document.get(url)
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("etag"), str)
            or not isinstance(entry.get("body"), str)
        ):
            return None
        return {
            "etag": entry["etag"],
            "body": entry["body"],
            "fetched_at": entry.get("fetched_at", "unknown"),
        }

    def write(self, url: str, etag: str, body: str) -> None:
        document = self._read_document() or {}
        document[url] = {
            "etag": etag,
            "body": body,
            "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(
                json.dumps({"version": CACHE_VERSION, "responses": document}, indent=2)
                + "\n"
            )
            temporary_name = temporary.name
        os.replace(temporary_name, self.path)

    def _read_document(self) -> dict[str, Any] | None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(document, dict)
            or document.get("version") != CACHE_VERSION
            or not isinstance(document.get("responses"), dict)
        ):
            return None
        return document["responses"]
