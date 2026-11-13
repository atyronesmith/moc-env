"""Local, non-repository cache for discovered environment clusters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CACHE_VERSION = 1
CACHE_FILENAME = "environment-clusters.json"


def environment_cache_directory() -> Path:
    """Return the user-local cache directory, honoring test/local overrides."""

    override = os.environ.get("MOC_ENV_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    cache_home = (
        Path(xdg_cache_home).expanduser()
        if xdg_cache_home
        else Path.home() / ".cache"
    )
    return cache_home / "moc-env"


def environment_cache_path() -> Path:
    return environment_cache_directory() / CACHE_FILENAME


def write_environment_cache(clusters: list[dict[str, Any]]) -> None:
    """Atomically write cluster records outside the repository."""

    path = environment_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps({"version": CACHE_VERSION, "clusters": clusters}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_environment_cache() -> list[dict[str, Any]]:
    """Read cached cluster records; return an empty list when unavailable."""

    path = environment_cache_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(document, dict) or document.get("version") != CACHE_VERSION:
        return []
    clusters = document.get("clusters")
    if not isinstance(clusters, list) or not all(
        isinstance(cluster, dict) for cluster in clusters
    ):
        return []
    return clusters
