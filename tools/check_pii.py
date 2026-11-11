#!/usr/bin/env python3
"""Reject personal identifiers in Git-tracked project files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAC_HOME_PATH = re.compile(r"/Users/[A-Za-z0-9_.-]+")
UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
PLACEHOLDER_UUID = re.compile(
    r"^(?:0{8}-0{4}-0{4}-0{4}-0{12}|1{8}-1{4}-1{4}-1{4}-1{12})$"
)
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
PYPROJECT_AUTHORS = re.compile(r"(?m)^\s*authors\s*=")


def tracked_files(repository: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repository / path for path in result.stdout.splitlines() if path]


def find_pii(repository: Path) -> list[str]:
    findings: list[str] = []
    for path in tracked_files(repository):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        checks = (
            ("email address", EMAIL),
            ("macOS home path", MAC_HOME_PATH),
            ("phone number", PHONE),
        )
        for label, pattern in checks:
            for match in pattern.finditer(text):
                findings.append(
                    f"{path.relative_to(repository)}: {label}: {match.group(0)}"
                )

        for match in UUID.finditer(text):
            if not PLACEHOLDER_UUID.match(match.group(0)):
                findings.append(
                    f"{path.relative_to(repository)}: non-placeholder UUID: "
                    f"{match.group(0)}"
                )

        if path.name == "pyproject.toml" and PYPROJECT_AUTHORS.search(text):
            findings.append(
                f"{path.relative_to(repository)}: author metadata can contain personal data"
            )
    return findings


def main() -> int:
    repository = Path(__file__).resolve().parent.parent
    findings = find_pii(repository)
    if findings:
        print("Personal identifiers found in tracked files:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("No personal identifiers found in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
