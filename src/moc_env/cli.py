"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from .checks import KNOWN_ISSUES, StatusChecker, list_environments
from .credentials import (
    CredentialError,
    CredentialNotFoundError,
    CredentialResolver,
    credential_options_from_environment,
    load_credential_environment_file,
)
from .github import GitHubClient, GitHubError, RateLimitError
from .model import Environment
from .report import (
    render_environment_list_json,
    render_environment_list_text,
    render_json,
    render_markdown,
    render_text,
)


def _add_credential_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bws-secret-id",
        help="Bitwarden Secrets Manager UUID whose key is GITHUB_TOKEN",
    )
    parser.add_argument(
        "--bws-secret-id-keychain-service",
        help=(
            "macOS Keychain service containing the Bitwarden secret UUID "
            "(default: moc-env-github-token)"
        ),
    )
    parser.add_argument(
        "--bws-secret-id-keychain-account",
        help="macOS Keychain account for the Bitwarden secret UUID (default: current user)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help=(
            "Optional KEY=VALUE file for non-secret credential selectors "
            "(default: .env; absent file is ignored)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="GitHub request timeout in seconds",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env",
        description="Report CCI-MOC environment configuration state from public GitHub repositories",
        epilog="Run 'moc-env list' to discover environment names that can be checked.",
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
    _add_credential_arguments(parser)
    parser.add_argument(
        "--output",
        help=(
            "Write the rendered report to this file instead of stdout; "
            "useful with --format markdown"
        ),
    )
    return parser


def build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env list",
        description="List environment names that can be passed to moc-env",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )
    _add_credential_arguments(parser)
    return parser


def _resolve_github_token(args: argparse.Namespace) -> str | None:
    try:
        credential_environment = load_credential_environment_file(args.env_file)
        credential_options = credential_options_from_environment(credential_environment)
    except CredentialError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        raise SystemExit(2)

    credential_overrides = {
        key: value
        for key, value in {
            "bws_secret_id": args.bws_secret_id,
            "bws_secret_id_keychain_service": args.bws_secret_id_keychain_service,
            "bws_secret_id_keychain_account": args.bws_secret_id_keychain_account,
        }.items()
        if value is not None
    }
    if credential_overrides:
        credential_options = replace(credential_options, **credential_overrides)

    resolver = CredentialResolver()
    explicit_keychain_selector = bool(
        os.environ.get("GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE")
        or os.environ.get("GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT")
        or os.environ.get("GITHUB_TOKEN_KEYCHAIN_SERVICE")
        or os.environ.get("GITHUB_TOKEN_KEYCHAIN_ACCOUNT")
        or args.bws_secret_id_keychain_service
        or args.bws_secret_id_keychain_account
    )
    try:
        try:
            return resolver.resolve(credential_options)
        except CredentialNotFoundError:
            if (
                credential_options.direct_token
                or credential_options.bws_secret_id
                or explicit_keychain_selector
            ):
                raise
            print(
                "moc-env: no GitHub credential found; continuing unauthenticated",
                file=sys.stderr,
            )
            return None
    except CredentialError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "list":
        argv = arguments
        args = build_list_parser().parse_args(argv[1:])
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        try:
            environments = list_environments(client)
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(render_environment_list_json(environments), end="")
        else:
            print(render_environment_list_text(environments), end="")
        return 0

    args = build_parser().parse_args(argv)
    issue_number = args.issue
    if issue_number is None:
        issue_number = KNOWN_ISSUES.get(args.environment)

    environment = Environment(name=args.environment, issue_number=issue_number)
    github_token = _resolve_github_token(args)

    client = GitHubClient(token=github_token, timeout=args.timeout)
    stage_step = 0

    def print_progress(
        stage: str, action: str, repository: str, path: str
    ) -> None:
        nonlocal stage_step
        stage_step += 1
        print(
            f"▶ Step {stage_step}: {stage}\n"
            f"    Action:     {action}\n"
            f"    Repository: {repository}\n"
            f"    Source:     {path}",
            file=sys.stderr,
        )

    checker = StatusChecker(
        client=client,
        include_prs=not args.no_prs,
        progress=print_progress,
    )

    try:
        report = checker.run(environment).to_dict()
    except (CredentialError, GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        rendered = render_json(report)
    elif args.format == "markdown":
        rendered = render_markdown(report)
    else:
        rendered = render_text(report)

    if args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(
                f"moc-env: could not write {output_path}: {exc}",
                file=sys.stderr,
            )
            return 2
        print(
            f"moc-env: wrote {args.format} report to {output_path}",
            file=sys.stderr,
        )
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
