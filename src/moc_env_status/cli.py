"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys

from .checks import KNOWN_ISSUES, StatusChecker
from .github import GitHubClient, GitHubError, RateLimitError
from .model import Environment
from .report import render_json, render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env-status",
        description="Report CCI-MOC environment configuration state from public GitHub repositories",
    )
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument(
        "--issue",
        type=int,
        help="MOC-issues number; defaults to 666 for bu-ist-demo",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Do not inspect pull requests",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="GitHub request timeout in seconds",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    issue_number = args.issue
    if issue_number is None:
        issue_number = KNOWN_ISSUES.get(args.environment)

    environment = Environment(name=args.environment, issue_number=issue_number)
    client = GitHubClient(timeout=args.timeout)
    checker = StatusChecker(client=client, include_prs=not args.no_prs)

    try:
        report = checker.run(environment).to_dict()
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env-status: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_json(report), end="")
    elif args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
