"""Local documentation catalog refresh."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


class DocumentCatalogError(RuntimeError):
    """Raised when the local documentation catalog cannot be refreshed."""


@dataclass(frozen=True)
class CatalogSource:
    """One source registered in docs/sources.yaml."""

    source_id: str
    repository: str
    path: str
    ref: str
    title: str
    kind: str
    topics: tuple[str, ...]
    summary: str
    url: str | None
    short_id: str


@dataclass(frozen=True)
class CatalogEntry:
    """One cached source and its repository provenance."""

    source: CatalogSource
    head_ref: str
    content_sha256: str
    document_path: str
    status: str


@dataclass(frozen=True)
class CatalogReport:
    """The result of refreshing the local documentation catalog."""

    repository_root: str
    cache_root: str
    entries: tuple[CatalogEntry, ...]


def load_catalog_sources(path: Path) -> dict[str, CatalogSource]:
    """Load and validate docs/sources.yaml."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DocumentCatalogError(f"could not load {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise DocumentCatalogError(f"{path} must be a mapping")
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, dict):
        raise DocumentCatalogError(f"{path} must contain a sources mapping")

    sources: dict[str, CatalogSource] = {}
    for source_id, raw_source in raw_sources.items():
        if not isinstance(raw_source, dict):
            raise DocumentCatalogError(f"source {source_id!r} must be a mapping")
        required = ("repository", "path", "ref", "title", "kind")
        for field_name in required:
            if not isinstance(raw_source.get(field_name), str):
                raise DocumentCatalogError(
                    f"source {source_id!r} field {field_name!r} must be a string"
                )
        topics = raw_source.get("topics", [])
        if not isinstance(topics, list):
            raise DocumentCatalogError(
                f"source {source_id!r} topics must be a list"
            )
        sources[source_id] = CatalogSource(
            source_id=source_id,
            repository=raw_source["repository"],
            path=raw_source["path"],
            ref=raw_source["ref"],
            title=raw_source["title"],
            kind=raw_source["kind"],
            topics=tuple(str(topic) for topic in topics),
            summary=str(raw_source.get("summary", "")),
            url=raw_source.get("url"),
            short_id=str(raw_source.get("shortId", source_id)),
        )
    return sources


def _repository_path(repository_root: Path, repository: str) -> Path:
    return repository_root / repository.rsplit("/", 1)[-1]


def _git(repository: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DocumentCatalogError("git executable could not be found") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "git command failed"
        raise DocumentCatalogError(detail) from exc
    return completed.stdout


def _cache_document(cache_root: Path, source: CatalogSource, content: str) -> str:
    documents = cache_root / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    suffix = Path(source.path).suffix or ".txt"
    relative_path = f"documents/{source.source_id}{suffix}"
    destination = cache_root / relative_path
    destination.write_text(content, encoding="utf-8")
    return relative_path


def refresh_document_catalog(
    sources: dict[str, CatalogSource],
    repository_root: Path,
    cache_root: Path,
) -> CatalogReport:
    """Refresh cached source documents from local Git clones."""

    repository_root = repository_root.resolve()
    cache_root = cache_root.resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    (cache_root / "documents").mkdir(parents=True, exist_ok=True)
    (cache_root / "extracts").mkdir(parents=True, exist_ok=True)
    (cache_root / "values").mkdir(parents=True, exist_ok=True)

    entries: list[CatalogEntry] = []
    for source_id in sorted(sources):
        source = sources[source_id]
        repository_path = _repository_path(repository_root, source.repository)
        if not repository_path.is_dir():
            raise DocumentCatalogError(
                f"local repository not found for {source_id!r}: {repository_path}"
            )
        head_ref = _git(repository_path, "rev-parse", "HEAD").strip()
        content = _git(repository_path, "show", f"HEAD:{source.path}")
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document_path = _cache_document(cache_root, source, content)
        status = "current" if head_ref == source.ref else "updated"
        entries.append(
            CatalogEntry(
                source=source,
                head_ref=head_ref,
                content_sha256=content_sha256,
                document_path=document_path,
                status=status,
            )
        )

    report = CatalogReport(
        repository_root=str(repository_root),
        cache_root=str(cache_root),
        entries=tuple(entries),
    )
    manifest = {
        "schemaVersion": "1",
        "repositoryRoot": report.repository_root,
        "cacheRoot": report.cache_root,
        "sources": {
            entry.source.source_id: {
                "repository": entry.source.repository,
                "path": entry.source.path,
                "registeredRef": entry.source.ref,
                "headRef": entry.head_ref,
                "contentSha256": entry.content_sha256,
                "documentPath": entry.document_path,
                "status": entry.status,
                "title": entry.source.title,
                "kind": entry.source.kind,
                "topics": list(entry.source.topics),
                "summary": entry.source.summary,
                "url": entry.source.url,
                "shortId": entry.source.short_id,
            }
            for entry in report.entries
        },
    }
    manifest_path = cache_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def render_catalog_refresh_text(report: CatalogReport) -> str:
    """Render a concise local catalog refresh report."""

    lines = [
        "Documentation catalog refresh",
        f"Repository root: {report.repository_root}",
        f"Cache root: {report.cache_root}",
        f"Sources: {len(report.entries)}",
        "",
    ]
    for entry in report.entries:
        lines.append(
            f"- {entry.source.short_id} {entry.source.title}: "
            f"{entry.status} ({entry.head_ref})"
        )
    lines.append("")
    return "\n".join(lines)


def render_catalog_refresh_json(report: CatalogReport) -> str:
    """Render the local catalog refresh report as JSON."""

    return json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
