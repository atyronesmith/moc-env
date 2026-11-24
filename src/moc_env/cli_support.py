"""Shared helpers for moc-env command handlers."""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .credentials import (
    CredentialError,
    CredentialResolver,
    credential_options_from_environment,
    load_credential_environment_file,
)
from .checks import Clock, StatusChecker
from .completion import mark_environment_argument, mark_file_argument
from .diff_observed import hosted_dns_facts
from .github import GitHubClient
from .model import Environment
from .registry import EnvironmentRegistry
from .report import build_environment_diff, render_diff_markdown, render_diff_text, render_json


def add_credential_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=("tarball", "api"), default="tarball",
                        help="Repository reader backend (default: tarball)")
    parser.add_argument("--no-auth", action="store_true", help="Force unauthenticated GitHub access")
    parser.add_argument("--bws-secret-id", help="Bitwarden Secrets Manager UUID whose key is GITHUB_TOKEN")
    parser.add_argument(
        "--bws-secret-id-keychain-service",
        help="macOS Keychain service containing the Bitwarden secret UUID (default: moc-env-github-token)",
    )
    parser.add_argument(
        "--bws-secret-id-keychain-account",
        help="macOS Keychain account for the Bitwarden secret UUID (default: current user)",
    )
    mark_file_argument(
        parser.add_argument(
            "--env-file",
            default=".env",
            help="Optional KEY=VALUE file for non-secret credential selectors (default: .env; absent file is ignored)",
        )
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="GitHub request timeout in seconds")
    cache_mode = parser.add_mutually_exclusive_group()
    cache_mode.add_argument("--offline", action="store_true", help="Serve GitHub responses only from the local response cache")
    cache_mode.add_argument("--refresh", action="store_true", help="Ignore cached GitHub responses and request current data")


def add_output(
    parser: argparse.ArgumentParser, help: str, *, infers_format: bool = False
) -> None:
    if infers_format:
        help = (
            f"{help}; when --format is omitted, infer the format from "
            "a .md, .markdown, .json, or .txt file extension"
        )
    mark_file_argument(
        parser.add_argument("--output", help=help)
    )


_OUTPUT_EXTENSION_FORMATS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".txt": "text",
}


def add_format_argument(
    parser: argparse.ArgumentParser,
    choices: Sequence[str] = ("text", "json", "markdown"),
) -> None:
    parser.add_argument(
        "--format",
        choices=choices,
        default=None,
        help=(
            "Output format; when omitted with --output, infer it from a "
            ".md, .markdown, .json, or .txt file extension"
        ),
    )


def resolve_output_format(
    args: argparse.Namespace,
    *,
    default: str,
    supported: Sequence[str],
) -> str:
    """Resolve an explicit, inferred, or default output format."""

    explicit = getattr(args, "format", None)
    if explicit:
        return explicit
    output = getattr(args, "output", None)
    if not output:
        return default
    inferred = _OUTPUT_EXTENSION_FORMATS.get(Path(output).suffix.lower())
    if inferred is None:
        return default
    if inferred in supported:
        return inferred
    print(
        f"moc-env: warning: {output}: {inferred} output is not supported "
        f"by this command; using {default}.",
        file=sys.stderr,
    )
    return default


def configure_status(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(
        parser.add_argument(
            "environment",
            nargs="?",
            help="Environment name, such as bu-ist-demo; omit it for the fleet view",
        )
    )
    parser.add_argument("--issue", type=int, help="MOC-issues number; overrides the packaged environment registry")
    add_format_argument(parser)
    pull_requests = parser.add_mutually_exclusive_group()
    pull_requests.add_argument("--no-prs", action="store_true", help="Do not inspect pull requests")
    pull_requests.add_argument("--prs", action="store_true", help="Inspect pull requests even when unauthenticated")
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="REPO=REF",
        help="Read a repository at a branch or pull-request head, for example --ref oac-apps=pull/246/head (repeatable)",
    )
    parser.add_argument("--details", action="store_true", help="Append full per-check findings after the one-screen summary")
    parser.add_argument(
        "--fail-on",
        choices=("blocking", "advisory", "never"),
        default="never",
        help="Exit 1 when a status report has this severity or higher (default: never)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show progress on stderr even when stderr is not a terminal")
    add_credential_arguments(parser)
    add_output(
        parser,
        "Write the rendered report to this file instead of stdout; useful with --format markdown",
        infers_format=True,
    )


def configure_diff(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=("tarball", "api"), default="tarball",
                        help="Repository reader backend (default: tarball)")
    mark_environment_argument(parser.add_argument("environment_a", help="First environment to compare"))
    mark_environment_argument(parser.add_argument("environment_b", help="Second environment to compare"))
    add_format_argument(parser, ("text", "markdown", "json"))
    add_output(
        parser,
        "Write the comparison to this file instead of stdout",
        infers_format=True,
    )
    parser.add_argument("--no-auth", action="store_true", help="Force unauthenticated GitHub access")
    parser.add_argument("--bws-secret-id", help="Bitwarden Secrets Manager UUID whose key is GITHUB_TOKEN")
    parser.add_argument("--bws-secret-id-keychain-service", help="macOS Keychain service containing the Bitwarden secret UUID (default: moc-env-github-token)")
    parser.add_argument("--bws-secret-id-keychain-account", help="macOS Keychain account for the Bitwarden secret UUID (default: current user)")
    mark_file_argument(
        parser.add_argument("--env-file", default=".env", help="Optional KEY=VALUE file for non-secret credential selectors (default: .env; absent file is ignored)")
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="GitHub request timeout in seconds")
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="REPO=REF",
        help="Read the second environment at a branch or pull-request head (repeatable; first environment stays on main)",
    )
    cache_mode = parser.add_mutually_exclusive_group()
    cache_mode.add_argument("--offline", action="store_true", help="Serve GitHub responses only from the local response cache")
    cache_mode.add_argument("--refresh", action="store_true", help="Ignore cached GitHub responses and request current data")


def diff_handler(
    args: argparse.Namespace,
    registry: EnvironmentRegistry,
    clock: Clock | None,
    arguments: list[str],
    client_factory=GitHubClient,
    token_resolver=None,
) -> int:
    args.format = resolve_output_format(
        args, default="text", supported=("text", "markdown", "json")
    )
    repository_refs: dict[str, str] = {}
    for repository_ref in getattr(args, "ref", ()):
        repository, separator, ref = repository_ref.partition("=")
        if not separator or not repository or not ref:
            message = "--ref must have the form REPO=REF"
            parser = getattr(args, "parser", None)
            if parser is not None:
                parser.error(message)
            raise ValueError(message)
        repository_refs[f"CCI-MOC/{repository}"] = ref

    client = client_factory(
        token=(token_resolver or resolve_github_token)(args),
        timeout=args.timeout,
        offline=args.offline,
        refresh=args.refresh,
    )
    reports = []
    for index, environment_name in enumerate((args.environment_a, args.environment_b)):
        # A diff compares main for the first side with the requested refs for
        # the second side. Reuse one client so response caching and quota
        # accounting remain shared across both observations.
        client.refs = repository_refs if index else {}
        checker = StatusChecker(
            client=client,
            include_prs=False,
            progress=ProgressReporter(False),
            registry=registry,
            command=sanitize_command(arguments),
            clock=clock,
        )
        report = checker.run(
            Environment(name=environment_name, issue_number=registry.issue(environment_name))
        )
        report_data = report.to_dict()
        report_data["diff_facts"] = hosted_dns_facts(client, report_data)
        # The client retains snapshots from both observations. Keep only the
        # refs selected for this side so the diff's source metadata cannot
        # attribute a baseline snapshot to the candidate (or vice versa).
        selected_sources = {
            repository: client.ref_for(repository)
            for repository in {
                source.get("repository")
                for source in (report_data.get("metadata") or {}).get("sources", [])
                if source.get("repository")
            }
        }
        metadata = report_data.get("metadata")
        if isinstance(metadata, dict):
            metadata["sources"] = [
                source
                for source in metadata.get("sources", [])
                if source.get("ref") == selected_sources.get(source.get("repository"))
            ]
        reports.append(report_data)
    diff = build_environment_diff(*reports)
    if args.format == "json":
        rendered = render_json(diff)
    elif args.format == "markdown":
        rendered = render_diff_markdown(diff)
    else:
        rendered = render_diff_text(diff)
    write_output(args, rendered, "environment diff")
    return 0


class ProgressReporter:
    def __init__(self, verbose: bool = False) -> None:
        self.step = 0
        self.verbose = verbose

    def __call__(self, stage: str, action: str, repository: str, path: str) -> None:
        self.step += 1
        if self.verbose or sys.stderr.isatty():
            print(f"▶ Step {self.step}: {stage} — {action} ({repository}/{path})", file=sys.stderr)


def write_output(args: argparse.Namespace, rendered: str, label: str) -> int:
    if not args.output:
        print(rendered, end="")
        return 0
    output_path = Path(args.output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        print(f"moc-env: could not write {output_path}: {exc}", file=sys.stderr)
        return 2
    print(f"moc-env: wrote {label} to {output_path}", file=sys.stderr)
    return 0


_CREDENTIAL_VALUE_OPTIONS = {"--bws-secret-id", "--bws-secret-id-keychain-service", "--bws-secret-id-keychain-account"}


def sanitize_command(arguments: list[str]) -> tuple[str, ...]:
    """Remove credential values while preserving the command shape."""
    sanitized: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in _CREDENTIAL_VALUE_OPTIONS:
            sanitized.append(argument)
            index += 1
            if index < len(arguments):
                sanitized.append("<redacted>")
                index += 1
            continue
        option, separator, _value = argument.partition("=")
        if separator and option in _CREDENTIAL_VALUE_OPTIONS:
            sanitized.append(f"{option}=<redacted>")
        else:
            sanitized.append(argument)
        index += 1
    return tuple(sanitized)


def resolve_github_token(args: argparse.Namespace) -> str | None:
    if args.no_auth or args.offline:
        return None
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
    explicit_bitwarden = bool(
        credential_options.bws_secret_id
        or credential_environment.get("GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE")
        or credential_environment.get("GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT")
        or credential_environment.get("GITHUB_TOKEN_KEYCHAIN_SERVICE")
        or credential_environment.get("GITHUB_TOKEN_KEYCHAIN_ACCOUNT")
        or args.bws_secret_id_keychain_service
        or args.bws_secret_id_keychain_account
    )
    try:
        return CredentialResolver().resolve(credential_options, explicit_bitwarden=explicit_bitwarden)
    except CredentialError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _print_unauthenticated_warning(remaining: int) -> None:
    print(
        f"moc-env: no GitHub credential found; continuing unauthenticated "
        f"(remaining request quota: {remaining})",
        file=sys.stderr,
    )


def print_unknown_environment(environment_name: str, known_names: list[str]) -> None:
    print(f"moc-env: unknown environment: {environment_name}", file=sys.stderr)
    matches = difflib.get_close_matches(environment_name, known_names, n=1)
    if matches:
        print(f"Did you mean: {matches[0]}", file=sys.stderr)
    print("Known environments:", file=sys.stderr)
    for name in known_names:
        print(f"  {name}", file=sys.stderr)


def resolve_workload_argument(
    environment_name: str, workload: str, workload_clusters: list[str]
) -> str:
    for cluster in workload_clusters:
        if workload in {cluster, cluster.removeprefix(f"{environment_name}-")}:
            return cluster
    print(f"moc-env: unknown workload cluster: {workload}", file=sys.stderr)
    print("Known workload clusters:", file=sys.stderr)
    for cluster in workload_clusters:
        print(f"  {cluster}", file=sys.stderr)
    raise ValueError(workload)


