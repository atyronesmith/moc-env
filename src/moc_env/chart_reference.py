"""Read chart values and comments for the ``charts --view reference`` view.

This module only parses chart text.  Repository and GitHub access belongs to
``charts``; keeping the reader pure lets tests exercise every comment rule
without a network client.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import yaml

MISSING_DEFAULT = "(not in values.yaml)"
_DEFAULT_WIDTH = 60

_ACTION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_TEMPLATE_COMMENT = re.compile(r"\{\{-?\s*/\*.*?\*/\s*-?\}\}", re.DOTALL)
_REQUIRED = re.compile(
    r'required\s+"([^"]*)"\s+\$?\.Values\.([A-Za-z0-9_.]+)'
)


@dataclass(frozen=True)
class ValueRow:
    """One row in a chart's values table."""

    key: str
    default: Any
    required: str = ""
    description: str = ""
    example: str | None = None
    has_default: bool = True


@dataclass(frozen=True)
class ValuesReference:
    """Rows and unattached comments read from one values.yaml file."""

    present: bool
    rows: tuple[ValueRow, ...] = ()
    other_comments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartEntry:
    """One deployed chart and the values that can be set for it."""

    name: str
    description: str
    used_by: tuple[str, ...]
    values: ValuesReference


@dataclass(frozen=True)
class ChartList:
    """A named list of charts used by one kind section."""

    name: str
    charts: tuple[str, ...]
    detail: str = ""


@dataclass(frozen=True)
class ChartReference:
    """Everything the reference view renders, independent of GitHub."""

    ref: str
    sha: str
    footer: str
    hub_always: tuple[str, ...]
    hub_gated: tuple[ChartList, ...]
    hub_drop_ins: tuple[str, ...]
    workload_creators: tuple[ChartList, ...]
    workload_baseline: tuple[str, ...]
    workload_features: tuple[ChartList, ...]
    charts: tuple[ChartEntry, ...]
    undeployed_count: int
    library_count: int


def compact_json(value: Any) -> str:
    """Return the compact JSON spelling used for a default value."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def truncated_default(value: Any) -> str:
    """Render a default and shorten it to 60 characters when necessary."""

    text = compact_json(value)
    return text if len(text) <= _DEFAULT_WIDTH else text[: _DEFAULT_WIDTH - 1] + "…"


def required_value_sets(template: str) -> tuple[set[str], set[str]]:
    """Return ``(unconditional, conditional)`` required ``.Values`` paths.

    A path is conditional when every ``required`` call that mentions it is
    inside an ``if``, ``with`` or ``range``.  Helm template comments are
    removed first.  ``define`` blocks do not make a value conditional.
    """

    stripped = _TEMPLATE_COMMENT.sub("", template)
    stack: list[str] = []
    unconditional: set[str] = set()
    conditional: set[str] = set()
    for match in _ACTION.finditer(stripped):
        action = match.group(1)
        keyword = _action_keyword(action)
        if keyword == "end":
            if stack:
                stack.pop()
            continue
        paths = [path for _, path in _REQUIRED.findall(action)]
        if paths:
            if any(kind in {"if", "with", "range"} for kind in stack):
                conditional.update(paths)
            else:
                unconditional.update(paths)
        if keyword in {"if", "with", "range", "define"}:
            stack.append(keyword)
    conditional -= unconditional
    return unconditional, conditional


def _action_keyword(action: str) -> str:
    text = action.strip().strip("-").strip()
    return text.split(None, 1)[0] if text else ""


def _is_comment_line(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_blank(line: str) -> bool:
    return not line.strip()


def _strip_comment_prefix(line: str) -> str:
    text = line.lstrip()
    if not text.startswith("#"):
        return text.rstrip()
    text = text[1:]
    if text.startswith((" ", "\t")):
        text = text[1:]
    return text.rstrip()


def _comment_text(text: str) -> str:
    text = text.lstrip()
    if not text.startswith("#"):
        return text.strip()
    text = text[1:]
    if text.startswith((" ", "\t")):
        text = text[1:]
    return text.strip()


def _split_comment(line: str) -> tuple[str, str | None]:
    """Split a YAML line at an unquoted ``#`` that starts a comment."""

    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(line) and line[index + 1] == "'":
                    index += 2
                    continue
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip(), _comment_text(line[index:])
        index += 1
    return line.rstrip(), None


def _find_key_colon(text: str) -> int | None:
    quote: str | None = None
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth = max(depth - 1, 0)
        elif char == ":" and depth == 0:
            return index
        index += 1
    return None


def _unquote_key(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError:
            return text[1:-1]
        return str(loaded)
    return text


def _mapping_key_line(line: str) -> tuple[int, str, str | None] | None:
    """Return ``(indent, key, inline_comment)`` for a mapping-key line."""

    content, inline = _split_comment(line)
    if not content.strip():
        return None
    stripped = content.lstrip()
    if stripped.startswith("-") or stripped in {"---", "..."}:
        return None
    colon = _find_key_colon(content)
    if colon is None:
        return None
    key_text = content[:colon].strip()
    if not key_text or key_text.startswith(("?", "|", ">")):
        return None
    return len(content) - len(stripped), _unquote_key(key_text), inline


def _key_line_paths(text: str) -> dict[int, tuple[tuple[str, ...], str | None]]:
    """Map physical line numbers of mapping-key lines to their dotted path."""

    paths: dict[int, tuple[tuple[str, ...], str | None]] = {}
    stack: list[tuple[int, str]] = []
    list_indent: int | None = None
    for index, line in enumerate(text.splitlines()):
        if _is_comment_line(line) or _is_blank(line):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("-"):
            if list_indent is None or indent <= list_indent:
                list_indent = indent
            continue
        if list_indent is not None:
            if indent > list_indent:
                continue
            list_indent = None
        parsed = _mapping_key_line(line)
        if parsed is None:
            continue
        key_indent, key, inline = parsed
        while stack and stack[-1][0] >= key_indent:
            stack.pop()
        path = tuple(name for _, name in stack) + (key,)
        stack.append((key_indent, key))
        paths[index] = (path, inline)
    return paths


def _comment_blocks(
    lines: list[str],
) -> Iterable[tuple[int, int, list[str]]]:
    index = 0
    while index < len(lines):
        if not _is_comment_line(lines[index]):
            index += 1
            continue
        start = index
        parts: list[str] = []
        while index < len(lines) and _is_comment_line(lines[index]):
            parts.append(_strip_comment_prefix(lines[index]))
            index += 1
        yield start, index - 1, parts


def _comments(
    text: str,
) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str], list[str]]:
    """Return ``(descriptions, examples, other)`` keyed by dotted paths."""

    lines = text.splitlines()
    key_lines = _key_line_paths(text)
    descriptions: dict[tuple[str, ...], str] = {}
    examples: dict[tuple[str, ...], str] = {}
    other: list[str] = []
    for start, end, parts in _comment_blocks(lines):
        after = end + 1
        before = start - 1
        if after in key_lines:
            descriptions[key_lines[after][0]] = " ".join(parts)
        elif before in key_lines:
            examples[key_lines[before][0]] = "\n".join(parts)
        else:
            other.append("\n".join(parts))
    for path, inline in key_lines.values():
        if inline:
            description = descriptions.get(path, "")
            descriptions[path] = (
                f"{description} {inline}" if description else inline
            )
    return descriptions, examples, other


def read_values(
    text: str,
    *,
    unconditional_required: Iterable[str] = (),
    conditional_required: Iterable[str] = (),
) -> ValuesReference:
    """Parse one chart's values.yaml into table rows."""

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        data = None
    if not isinstance(data, dict):
        data = {}
    descriptions, examples, other = _comments(text)
    unconditional = set(unconditional_required)
    conditional = set(conditional_required)
    rows: list[ValueRow] = []

    def walk(mapping: dict[Any, Any], prefix: tuple[str, ...]) -> None:
        for raw_key, value in mapping.items():
            path = prefix + (str(raw_key),)
            dotted = ".".join(path)
            leaf = not isinstance(value, dict) or not value
            if leaf:
                rows.append(
                    ValueRow(
                        key=dotted,
                        default=value,
                        required=_required_label(
                            dotted, unconditional, conditional
                        ),
                        description=descriptions.get(path, ""),
                        example=examples.get(path),
                    )
                )
                continue
            if path in descriptions or path in examples:
                rows.append(
                    ValueRow(
                        key=dotted,
                        default="",
                        required=_required_label(
                            dotted, unconditional, conditional
                        ),
                        description=descriptions.get(path, ""),
                        example=examples.get(path),
                        has_default=False,
                    )
                )
            walk(value, path)

    walk(data, ())
    present = {row.key for row in rows}
    for path in sorted((unconditional | conditional) - present):
        rows.append(
            ValueRow(
                key=path,
                default=MISSING_DEFAULT,
                required=_required_label(path, unconditional, conditional),
            )
        )
    return ValuesReference(
        present=True, rows=tuple(rows), other_comments=tuple(other)
    )


def _required_label(
    path: str, unconditional: set[str], conditional: set[str]
) -> str:
    if path in unconditional:
        return "yes"
    if path in conditional:
        return "conditional"
    return ""


def default_cell(row: ValueRow, *, truncate: bool = True) -> str:
    """Render the Default column for a row."""

    if not row.has_default:
        return ""
    if truncate:
        return truncated_default(row.default)
    return compact_json(row.default)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _link(name: str, rendered: set[str]) -> str:
    return f"[{name}](#{name})" if name in rendered else name


def _markdown_table(entry: ChartEntry) -> list[str]:
    lines = [
        "| Key | Default | Required | Description |",
        "|---|---|---|---|",
    ]
    for row in entry.values.rows:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(cell)
                for cell in (
                    row.key,
                    default_cell(row),
                    row.required,
                    row.description,
                )
            )
            + " |"
        )
    return lines


def _rendered_names(charts: Sequence[ChartEntry]) -> set[str]:
    return {entry.name for entry in charts}


def _selected_charts(
    reference: ChartReference, selected: Sequence[str]
) -> tuple[ChartEntry, ...]:
    if not selected:
        return reference.charts
    wanted = set(selected)
    return tuple(entry for entry in reference.charts if entry.name in wanted)


def render_markdown(
    reference: ChartReference, selected: Sequence[str] = ()
) -> str:
    charts = _selected_charts(reference, selected)
    rendered = _rendered_names(charts)
    lines = [
        "# oac-apps chart reference",
        "",
        "## Hub cluster",
        "",
        "Set values in values/<hub>/<chart>.yaml, then",
        "values/<hub>/local-cluster/<chart>.yaml. The second file wins.",
        "",
        f"### Charts every hub receives ({len(reference.hub_always)})",
        "",
    ]
    lines.extend(f"- {_link(name, rendered)}" for name in reference.hub_always)
    lines.append("")
    lines.append("### Charts compliant hubs also receive")
    lines.append("")
    if reference.hub_gated:
        for item in reference.hub_gated:
            marker = f" (marker {item.detail})" if item.detail else ""
            charts_text = ", ".join(
                _link(name, rendered) for name in item.charts
            )
            lines.append(
                f"- {item.name} -> {charts_text}{marker}"
            )
    else:
        lines.append("- None.")
    lines.append("")
    lines.append("### Per-hub drop-ins")
    lines.append("")
    lines.extend(
        f"- {_link(name, rendered)}" for name in reference.hub_drop_ins
    )
    lines.extend(
        [
            "",
            "## Workload cluster",
            "",
            "A workload cluster is created by the hosted-cluster chart from",
            "hosted-clusters/<hub>/values.yaml and",
            "hosted-clusters/<hub>/<cluster>/values.yaml. Feature labels are set there",
            "under clusterLabels. Chart values go in values/<hub>/<chart>.yaml, then",
            "values/<hub>/<cluster>/<chart>.yaml. The second file wins.",
            "",
            "### Charts that create the cluster",
            "",
        ]
    )
    for item in reference.workload_creators:
        detail = f" ({item.detail})" if item.detail else ""
        lines.append(f"- {_link(item.name, rendered)}{detail}")
    lines.extend(
        [
            "",
            f"### Baseline ({len(reference.workload_baseline)})",
            "",
        ]
    )
    lines.extend(
        f"- {_link(name, rendered)}" for name in reference.workload_baseline
    )
    for feature in reference.workload_features:
        lines.extend(
            [
                "",
                f"### Feature: {feature.name} ({len(feature.charts)})",
                "",
            ]
        )
        if feature.detail:
            lines.append(f"Label: {feature.detail}")
            lines.append("")
        lines.extend(f"- {_link(name, rendered)}" for name in feature.charts)
    lines.extend(["", "## Chart reference", ""])
    for entry in charts:
        lines.append(f"### {entry.name}")
        lines.append("")
        if entry.description:
            lines.append(entry.description)
            lines.append("")
        if entry.used_by:
            lines.append("Used by: " + "; ".join(entry.used_by))
            lines.append("")
        if not entry.values.present:
            lines.append("No values.yaml.")
            lines.append("")
            continue
        lines.extend(_markdown_table(entry))
        lines.append("")
        for row in entry.values.rows:
            if row.example is None:
                continue
            lines.append(f"Example for `{row.key}`:")
            lines.append("")
            lines.append("```yaml")
            lines.extend(row.example.splitlines())
            lines.append("```")
            lines.append("")
        if entry.values.other_comments:
            lines.append("Other comments in values.yaml:")
            lines.append("")
            lines.append("```yaml")
            for comment in entry.values.other_comments:
                lines.extend(comment.splitlines())
            lines.append("```")
            lines.append("")
    lines.append(
        f"{reference.undeployed_count} undeployed and "
        f"{reference.library_count} library charts are not shown. "
        "Run `moc-env charts --view summary` for the full inventory."
    )
    lines.extend(["", reference.footer])
    return "\n".join(lines) + "\n"


def render_text(reference: ChartReference, selected: Sequence[str] = ()) -> str:
    charts = _selected_charts(reference, selected)
    lines = [
        "oac-apps chart reference",
        "",
        "Hub cluster",
        "",
        "Set values in values/<hub>/<chart>.yaml, then",
        "values/<hub>/local-cluster/<chart>.yaml. The second file wins.",
        "",
        f"Charts every hub receives ({len(reference.hub_always)})",
        "",
    ]
    lines.extend(f"  {name}" for name in reference.hub_always)
    lines.extend(["", "Charts compliant hubs also receive", ""])
    if reference.hub_gated:
        for item in reference.hub_gated:
            marker = f" (marker {item.detail})" if item.detail else ""
            lines.append(f"  {item.name} -> {', '.join(item.charts)}{marker}")
    else:
        lines.append("  None.")
    lines.extend(["", "Per-hub drop-ins", ""])
    lines.extend(f"  {name}" for name in reference.hub_drop_ins)
    lines.extend(
        [
            "",
            "Workload cluster",
            "",
            "A workload cluster is created by the hosted-cluster chart from",
            "hosted-clusters/<hub>/values.yaml and",
            "hosted-clusters/<hub>/<cluster>/values.yaml. Feature labels are set there",
            "under clusterLabels. Chart values go in values/<hub>/<chart>.yaml, then",
            "values/<hub>/<cluster>/<chart>.yaml. The second file wins.",
            "",
            "Charts that create the cluster",
            "",
        ]
    )
    for item in reference.workload_creators:
        detail = f" ({item.detail})" if item.detail else ""
        lines.append(f"  {item.name}{detail}")
    lines.extend(
        ["", f"Baseline ({len(reference.workload_baseline)})", ""]
    )
    lines.extend(f"  {name}" for name in reference.workload_baseline)
    for feature in reference.workload_features:
        lines.extend(
            ["", f"Feature: {feature.name} ({len(feature.charts)})", ""]
        )
        if feature.detail:
            lines.append(f"  Label: {feature.detail}")
        lines.extend(f"  {name}" for name in feature.charts)
    lines.extend(["", "Chart reference", ""])
    for entry in charts:
        lines.append(entry.name)
        if entry.description:
            lines.append(f"  {entry.description}")
        if entry.used_by:
            lines.append("  Used by: " + "; ".join(entry.used_by))
        if not entry.values.present:
            lines.append("  No values.yaml.")
            lines.append("")
            continue
        lines.append("  Key | Default | Required | Description")
        for row in entry.values.rows:
            cells = (
                row.key,
                default_cell(row),
                row.required,
                row.description,
            )
            lines.append("  " + " | ".join(cells))
        lines.append("")
        for row in entry.values.rows:
            if row.example is None:
                continue
            lines.append(f"  Example for `{row.key}`:")
            lines.extend(f"    {line}" for line in row.example.splitlines())
            lines.append("")
        if entry.values.other_comments:
            lines.append("  Other comments in values.yaml:")
            for comment in entry.values.other_comments:
                lines.extend(f"    {line}" for line in comment.splitlines())
            lines.append("")
    lines.append(
        f"{reference.undeployed_count} undeployed and "
        f"{reference.library_count} library charts are not shown. "
        "Run `moc-env charts --view summary` for the full inventory."
    )
    lines.extend(["", reference.footer])
    return "\n".join(lines) + "\n"


def render_json(reference: ChartReference, selected: Sequence[str] = ()) -> str:
    charts = _selected_charts(reference, selected)
    document = {
        "view": "reference",
        "ref": reference.ref,
        "sha": reference.sha,
        "short_sha": reference.sha[:7],
        "hub": {
            "charts_every_hub_receives": list(reference.hub_always),
            "compliant_hubs": [
                {
                    "application_set": item.name,
                    "marker_path": item.detail,
                    "charts": list(item.charts),
                }
                for item in reference.hub_gated
            ],
            "drop_ins": list(reference.hub_drop_ins),
        },
        "workload": {
            "cluster_creation": [
                {
                    "chart": item.name,
                    "application_set": item.detail,
                }
                for item in reference.workload_creators
            ],
            "baseline": list(reference.workload_baseline),
            "features": [
                {
                    "name": item.name,
                    "label": item.detail,
                    "charts": list(item.charts),
                }
                for item in reference.workload_features
            ],
        },
        "chart_count": len(charts),
        "charts": {
            entry.name: {
                "description": entry.description,
                "used_by": list(entry.used_by),
                "values_file": entry.values.present,
                "rows": [
                    {
                        "key": row.key,
                        "default": (
                            row.default if row.has_default else ""
                        ),
                        "required": row.required,
                        "description": row.description,
                        "example": row.example,
                    }
                    for row in entry.values.rows
                ],
                "other_comments": list(entry.values.other_comments),
            }
            for entry in charts
        },
        "undeployed_count": reference.undeployed_count,
        "library_count": reference.library_count,
        "footer": reference.footer,
    }
    return json.dumps(document, indent=2) + "\n"


def render_chart_reference(
    reference: ChartReference,
    *,
    format: str = "markdown",
    selected: Sequence[str] = (),
) -> str:
    """Render a reference view in markdown, text, or JSON."""

    if format == "json":
        return render_json(reference, selected)
    if format == "text":
        return render_text(reference, selected)
    return render_markdown(reference, selected)
