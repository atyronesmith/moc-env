"""Shared boot-image specificity rules.

The accepted filename grammar is ``<cluster-alias>`` followed by the end of
the filename or one of ``-``, ``_``, or ``.`` (for example,
``prod-infra-agent-discovery.iso``).  Matching is against the final segment
of the URL path only; query strings and fragments are never considered.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlsplit


_FILENAME_SUFFIX_SEPARATORS = frozenset("-_.")


def _filename_starts_with_alias(filename: str, alias: str) -> bool:
    """Match an alias only as the complete leading filename component.

    Image names are conventionally ``<cluster>-agent*.iso`` (and some
    historical names use ``_`` or a direct extension).  A separator or the
    end of the filename must follow the alias, preventing ``workload1`` from
    matching ``workload10`` or an unrelated longer name.
    """

    if not alias or not filename.startswith(alias):
        return False
    return len(filename) == len(alias) or (
        filename[len(alias)] in _FILENAME_SUFFIX_SEPARATORS
    )


def image_is_specific(url: Any, cluster: str, hub_cluster: str | None = None) -> bool:
    """Return whether a boot image names the workload or its parent hub."""

    if not isinstance(url, str) or not isinstance(cluster, str) or not cluster:
        return False
    # Parse only the URL path: query and fragment values are not filenames.
    try:
        path = urlsplit(url).path
    except ValueError:
        return False
    raw_name = path.rsplit("/", 1)[-1]
    image_name = unquote(raw_name)
    # An encoded slash remains a path boundary, not part of a filename.
    if "/" in image_name or "\\" in image_name:
        return False
    if image_name == "discovery.iso":
        return False
    aliases = [cluster, cluster.removeprefix("oac-")]
    if isinstance(hub_cluster, str) and hub_cluster:
        aliases.extend((hub_cluster, hub_cluster.removeprefix("oac-")))
    return any(_filename_starts_with_alias(image_name, alias) for alias in aliases)
