"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

from .checks import KNOWN_ISSUES, StatusChecker
from .credentials import (
    CredentialError,
    CredentialNotFoundError,
    CredentialResolver,
    credential_options_from_environment,
)
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
        "--bws-secret-id",
        help="Bitwarden Secrets Manager UUID whose key is GITHUB_TOKEN",
    )
    parser.add_argument(
        "--github-keychain-service",
        help="macOS Keychain service for the GitHub token (default: moc-env-status-github-token)",
    )
    parser.add_argument(
        "--github-keychain-account",
        help="macOS Keychain account for the GitHub token (default: current user)",
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
    credential_options = credential_options_from_environment()
    credential_overrides = {
        key: value
        for key, value in {
            "bws_secret_id": args.bws_secret_id,
            "github_keychain_service": args.github_keychain_service,
            "github_keychain_account": args.github_keychain_account,
        }.items()
        if value is not None
    }
    if credential_overrides:
        credential_options = replace(
            credential_options,
            **credential_overrides,
        )

    resolver = CredentialResolver()
    explicit_keychain_selector = bool(
        os.environ.get("GITHUB_TOKEN_KEYCHAIN_SERVICE")
        or os.environ.get("GITHUB_TOKEN_KEYCHAIN_ACCOUNT")
        or args.github_keychain_service
        or args.github_keychain_account
    )
    try:
        try:
            github_token = resolver.resolve(credential_options)
        except CredentialNotFoundError:
            if (
                credential_options.direct_token
                or credential_options.bws_secret_id
                or explicit_keychain_selector
            ):
                raise
            print(
                "moc-env-status: no GitHub credential found; continuing unauthenticated",
                file=sys.stderr,
            )
            github_token = None
    except CredentialError as exc:
        print(f"moc-env-status: {exc}", file=sys.stderr)
        return 2

    client = GitHubClient(token=github_token, timeout=args.timeout)
    checker = StatusChecker(client=client, include_prs=not args.no_prs)

    try:
        report = checker.run(environment).to_dict()
    except (CredentialError, GitHubError, RateLimitError) as exc:
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
