"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .checks import KNOWN_ISSUES, StatusChecker, list_environments
from .chart_values import (
    documentation_directory,
    load_chart_values_manual,
    render_chart_values_markdown,
)
from .chart_value_discovery import (
    build_discovery_report,
    render_discovery_json,
    render_discovery_markdown,
    render_discovery_text,
)
from .credentials import (
    CredentialError,
    CredentialNotFoundError,
    CredentialResolver,
    credential_options_from_environment,
    load_credential_environment_file,
)
from .github import GitHubClient, GitHubError, RateLimitError
from .completion import (
    bash_completion_script,
    command_help_epilog,
    zsh_completion_script,
)
from .compare import (
    compare_infra,
    compare_environment,
    compare_workload,
    desired_environment,
    render_comparison_json,
    render_comparison_markdown,
    render_comparison_text,
)
from .doc_catalog import (
    DocumentCatalogError,
    load_catalog_sources,
    refresh_document_catalog,
    render_catalog_refresh_json,
    render_catalog_refresh_text,
)
from .export import (
    render_environment_export,
    render_infra_export,
    render_workload_export,
    workload_cluster_name,
)
from .environment_cache import read_environment_cache, write_environment_cache
from .model import Environment
from .observed import (
    read_apps_observation,
    read_chart_values_reference_observation,
    read_infra_observation,
    read_issue_observation,
)
from .plan import (
    build_infra_change_plan,
    render_change_plan_json,
    render_change_plan_markdown,
    render_change_plan_text,
)
from .report import (
    render_environment_list_json,
    render_environment_list_text,
    render_json,
    render_markdown,
    render_text,
)
from .validate import (
    load_environment_document,
    load_yaml_document,
    load_infra_cluster_document,
    load_validation_result,
    render_validation_markdown,
    render_validation_json,
    render_validation_text,
    validate_workload_cluster,
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


def _add_status_arguments(parser: argparse.ArgumentParser) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env",
        description="Report CCI-MOC environment configuration state from public GitHub repositories",
        epilog=command_help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_status_arguments(parser)
    return parser


def build_hub_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env hub-status",
        description="Report hub-cluster repository configuration state",
    )
    _add_status_arguments(parser)
    return parser


def build_work_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env work-status",
        description="Report workload-cluster repository configuration state",
    )
    _add_status_arguments(parser)
    return parser


def _render_status_report(args: argparse.Namespace, report: dict[str, Any]) -> int:
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


def build_completion_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env completion",
        description="Print a bash or zsh completion script",
    )
    parser.add_argument(
        "shell",
        choices=("bash", "zsh"),
        help="Shell for which to print a completion script",
    )
    return parser


def build_document_values_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env document-values",
        description=(
            "Generate an environment-independent Markdown guide to "
            "hub and workload chart values"
        ),
    )
    parser.add_argument(
        "--output",
        help="Write the Markdown guide to this file instead of stdout",
    )
    _add_credential_arguments(parser)
    return parser


def build_refresh_doc_catalog_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env refresh-doc-catalog",
        description="Refresh the local documentation catalog from local Git clones",
    )
    parser.add_argument(
        "--repository-root",
        default="../MOC",
        help="Directory containing local MOC repository clones (default: ../MOC)",
    )
    parser.add_argument(
        "--cache-root",
        default=".cache/doc-catalog",
        help="Local documentation cache directory (default: .cache/doc-catalog)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the refresh report to this file instead of stdout",
    )
    return parser


def build_discover_values_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env discover-values",
        description=(
            "Compare local oac-apps chart values with manual documentation"
        ),
    )
    parser.add_argument(
        "--repository-root",
        default="../MOC",
        help="Directory containing local MOC repository clones (default: ../MOC)",
    )
    parser.add_argument(
        "--cache-root",
        default=".cache/doc-catalog",
        help="Local documentation cache directory (default: .cache/doc-catalog)",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "text", "json"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the discovery report to this file instead of stdout",
    )
    return parser


def build_export_infra_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env export-infra",
        description=(
            "Export a deterministic draft hub-cluster snapshot from merged main"
        ),
    )
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument(
        "--output",
        help=(
            "Write the YAML snapshot to this file instead of stdout; "
            "the command never creates or updates GitHub content"
        ),
    )
    _add_credential_arguments(parser)
    return parser


def build_export_workload_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env export-workload",
        description=(
            "Export a deterministic draft WorkloadCluster snapshot from merged main"
        ),
    )
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument(
        "workload",
        help="Workload name, such as workload0 or bu-ist-demo-workload0",
    )
    parser.add_argument(
        "--output",
        help=(
            "Write the YAML snapshot to this file instead of stdout; "
            "the command never creates or updates GitHub content"
        ),
    )
    _add_credential_arguments(parser)
    return parser


def build_export_environment_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env export-environment",
        description=(
            "Export a deterministic draft Environment bundle from merged main"
        ),
    )
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument(
        "--issue",
        type=int,
        help="MOC-issues number; defaults to the known issue for the environment",
    )
    parser.add_argument(
        "--output",
        help=(
            "Write the YAML bundle to this file instead of stdout; "
            "the command never creates or updates GitHub content"
        ),
    )
    _add_credential_arguments(parser)
    return parser


def build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env validate",
        description="Validate a local desired-state YAML document",
    )
    parser.add_argument("file", help="Path to a desired-state YAML file")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the validation report to this file instead of stdout",
    )
    return parser


def build_check_infra_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env check-infra",
        description=(
            "Compare a desired-state hub-cluster document with merged main"
        ),
    )
    parser.add_argument("file", help="Path to a desired-state YAML file")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the comparison report to this file instead of stdout",
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Do not inspect pull requests",
    )
    _add_credential_arguments(parser)
    return parser


def build_plan_infra_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env plan-infra",
        description=(
            "Plan read-only repository changes from a desired-state "
            "hub-cluster document"
        ),
    )
    parser.add_argument("file", help="Path to a desired-state YAML file")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the rendered change plan to this file instead of stdout",
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Do not inspect pull requests",
    )
    _add_credential_arguments(parser)
    return parser


def build_check_workload_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env check-workload",
        description="Compare a desired-state WorkloadCluster document with merged main",
    )
    parser.add_argument("file", help="Path to a desired-state YAML file")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the comparison report to this file instead of stdout",
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Do not inspect pull requests",
    )
    _add_credential_arguments(parser)
    return parser


def build_check_environment_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env check-environment",
        description="Compare a desired-state Environment bundle with merged main",
    )
    parser.add_argument("file", help="Path to an Environment bundle YAML file")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write the comparison report to this file instead of stdout",
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Do not inspect pull requests",
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
    if arguments and arguments[0] == "__complete-environment":
        prefix = arguments[1] if len(arguments) > 1 else ""
        mode = arguments[2] if len(arguments) > 2 else "environment"
        if mode not in {"environment", "workload"}:
            print("moc-env: unknown completion mode", file=sys.stderr)
            return 2
        clusters = read_environment_cache()
        if mode == "environment":
            values = sorted(
                {
                    cluster["environment"]
                    for cluster in clusters
                    if isinstance(cluster.get("environment"), str)
                }
            )
        else:
            values = sorted(
                cluster["cluster"]
                for cluster in clusters
                if cluster.get("type") == "workload"
                and isinstance(cluster.get("cluster"), str)
            )
        for value in values:
            if value.startswith(prefix):
                print(value)
        return 0

    if arguments and arguments[0] == "completion":
        args = build_completion_parser().parse_args(arguments[1:])
        print(
            bash_completion_script()
            if args.shell == "bash"
            else zsh_completion_script(),
            end="",
        )
        return 0

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
        try:
            write_environment_cache(environments)
        except OSError as exc:
            print(
                f"moc-env: could not write environment cache: {exc}",
                file=sys.stderr,
            )
        if args.format == "json":
            print(render_environment_list_json(environments), end="")
        else:
            print(render_environment_list_text(environments), end="")
        return 0

    if arguments and arguments[0] == "refresh-doc-catalog":
        args = build_refresh_doc_catalog_parser().parse_args(arguments[1:])
        try:
            sources = load_catalog_sources(
                documentation_directory() / "sources.yaml"
            )
            report = refresh_document_catalog(
                sources,
                Path(args.repository_root),
                Path(args.cache_root),
            )
        except DocumentCatalogError as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        rendered = (
            render_catalog_refresh_json(report)
            if args.format == "json"
            else render_catalog_refresh_text(report)
        )
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
                f"moc-env: wrote {args.format} catalog refresh report to "
                f"{output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "discover-values":
        args = build_discover_values_parser().parse_args(arguments[1:])
        repository = Path(args.repository_root) / "oac-apps"
        try:
            manual = load_chart_values_manual()
            report = build_discovery_report(
                manual,
                repository,
                Path(args.cache_root),
            )
        except (OSError, ValueError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            rendered = render_discovery_json(report)
        elif args.format == "text":
            rendered = render_discovery_text(report)
        else:
            rendered = render_discovery_markdown(report)
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
                f"moc-env: wrote {args.format} discovery report to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "document-values":
        args = build_document_values_parser().parse_args(arguments[1:])
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_values_progress(
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

        try:
            observation = read_chart_values_reference_observation(
                client,
                progress=print_values_progress,
            )
            rendered = render_chart_values_markdown(observation)
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

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
                f"moc-env: wrote chart-values reference to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "export-infra":
        args = build_export_infra_parser().parse_args(arguments[1:])
        environment = Environment(name=args.environment)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_export_progress(
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

        try:
            observation = read_infra_observation(
                client,
                environment,
                progress=print_export_progress,
            )
            rendered = render_infra_export(environment, observation)
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

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
            print(f"moc-env: wrote InfraCluster YAML to {output_path}", file=sys.stderr)
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "export-workload":
        args = build_export_workload_parser().parse_args(arguments[1:])
        environment = Environment(name=args.environment)
        try:
            workload_cluster = workload_cluster_name(environment, args.workload)
        except ValueError as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_workload_export_progress(
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

        try:
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_workload_export_progress,
            )
            apps_observation = read_apps_observation(
                client,
                environment,
                progress=print_workload_export_progress,
                include_pull_requests=False,
            )
            rendered = render_workload_export(
                environment,
                workload_cluster,
                infra_observation,
                apps_observation,
            )
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

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
                f"moc-env: wrote WorkloadCluster YAML to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "export-environment":
        args = build_export_environment_parser().parse_args(arguments[1:])
        issue_number = args.issue
        if issue_number is None:
            issue_number = KNOWN_ISSUES.get(args.environment)
        if issue_number is None:
            print(
                "moc-env: environment has no known MOC issue; pass --issue",
                file=sys.stderr,
            )
            return 2
        environment = Environment(
            name=args.environment,
            issue_number=issue_number,
        )
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_environment_export_progress(
            stage: str,
            action: str,
            repository: str,
            path: str,
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

        try:
            issue = read_issue_observation(
                client,
                environment,
                progress=print_environment_export_progress,
            )
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_environment_export_progress,
            )
            apps_observation = read_apps_observation(
                client,
                environment,
                progress=print_environment_export_progress,
                include_pull_requests=False,
            )
            rendered = render_environment_export(
                environment,
                issue,
                infra_observation,
                apps_observation,
            )
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

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
            print(f"moc-env: wrote Environment YAML to {output_path}", file=sys.stderr)
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "validate":
        args = build_validate_parser().parse_args(arguments[1:])
        input_path = Path(args.file)
        result = load_validation_result(input_path)
        if args.format == "json":
            rendered = render_validation_json(result)
        elif args.format == "markdown":
            rendered = render_validation_markdown(result, input_path)
        else:
            rendered = render_validation_text(result)

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
                f"moc-env: wrote {args.format} validation report to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0 if result.valid else 2

    if arguments and arguments[0] == "check-infra":
        args = build_check_infra_parser().parse_args(arguments[1:])
        input_path = Path(args.file)
        document, validation = load_infra_cluster_document(input_path)
        if not validation.valid:
            print(
                f"moc-env: desired-state document is invalid: {input_path}",
                file=sys.stderr,
            )
            for error in validation.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2

        environment = desired_environment(document)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_comparison_progress(
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

        try:
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_comparison_progress,
            )
            apps_observation = None
            if not args.no_prs:
                apps_observation = read_apps_observation(
                    client,
                    environment,
                    progress=print_comparison_progress,
                    include_pull_requests=True,
                )
            comparison = compare_infra(
                document,
                environment,
                infra_observation,
                apps_observation,
            )
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            rendered = render_comparison_json(comparison)
        elif args.format == "markdown":
            rendered = render_comparison_markdown(comparison)
        else:
            rendered = render_comparison_text(comparison)

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
                f"moc-env: wrote {args.format} comparison report to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        differences = {
            "missing_from_main",
            "value_mismatch",
            "unexpected_in_main",
            "unsupported_check",
            "ambiguous",
        }
        return 1 if any(check.state in differences for check in comparison.checks) else 0

    if arguments and arguments[0] == "plan-infra":
        args = build_plan_infra_parser().parse_args(arguments[1:])
        input_path = Path(args.file)
        document, validation = load_infra_cluster_document(input_path)
        if not validation.valid:
            print(
                f"moc-env: desired-state document is invalid: {input_path}",
                file=sys.stderr,
            )
            for error in validation.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2

        environment = desired_environment(document)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_plan_progress(
            stage: str,
            action: str,
            repository: str,
            path: str,
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

        try:
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_plan_progress,
            )
            apps_observation = None
            if not args.no_prs:
                apps_observation = read_apps_observation(
                    client,
                    environment,
                    progress=print_plan_progress,
                    include_pull_requests=True,
                )
            comparison = compare_infra(
                document,
                environment,
                infra_observation,
                apps_observation,
            )
            plan = build_infra_change_plan(document, comparison)
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            rendered = render_change_plan_json(plan)
        elif args.format == "markdown":
            rendered = render_change_plan_markdown(plan)
        else:
            rendered = render_change_plan_text(plan)

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
                f"moc-env: wrote {args.format} change plan to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        return 0

    if arguments and arguments[0] == "check-workload":
        args = build_check_workload_parser().parse_args(arguments[1:])
        input_path = Path(args.file)
        document, load_result = load_yaml_document(input_path)
        if not load_result.valid:
            print(
                f"moc-env: could not load desired-state document: {input_path}",
                file=sys.stderr,
            )
            for error in load_result.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2
        validation = validate_workload_cluster(document)
        if not validation.valid:
            print(
                f"moc-env: desired-state document is invalid: {input_path}",
                file=sys.stderr,
            )
            for error in validation.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2

        environment = desired_environment(document)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_workload_comparison_progress(
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

        try:
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_workload_comparison_progress,
            )
            apps_observation = read_apps_observation(
                client,
                environment,
                progress=print_workload_comparison_progress,
                include_pull_requests=not args.no_prs,
            )
            comparison = compare_workload(
                document,
                infra_observation,
                apps_observation,
            )
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            rendered = render_comparison_json(comparison)
        elif args.format == "markdown":
            rendered = render_comparison_markdown(comparison)
        else:
            rendered = render_comparison_text(comparison)

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
                f"moc-env: wrote {args.format} comparison report to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        differences = {
            "missing_from_main",
            "value_mismatch",
            "unexpected_in_main",
            "unsupported_check",
            "ambiguous",
        }
        return 1 if any(check.state in differences for check in comparison.checks) else 0

    if arguments and arguments[0] == "check-environment":
        args = build_check_environment_parser().parse_args(arguments[1:])
        input_path = Path(args.file)
        document, validation = load_environment_document(input_path)
        if not validation.valid:
            print(
                f"moc-env: desired-state document is invalid: {input_path}",
                file=sys.stderr,
            )
            for error in validation.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2

        environment = desired_environment(document)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_environment_comparison_progress(
            stage: str,
            action: str,
            repository: str,
            path: str,
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

        try:
            issue = read_issue_observation(
                client,
                environment,
                progress=print_environment_comparison_progress,
            )
            infra_observation = read_infra_observation(
                client,
                environment,
                progress=print_environment_comparison_progress,
            )
            apps_observation = read_apps_observation(
                client,
                environment,
                progress=print_environment_comparison_progress,
                include_pull_requests=not args.no_prs,
            )
            comparison = compare_environment(
                document,
                environment,
                issue,
                infra_observation,
                apps_observation,
            )
        except (GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            rendered = render_comparison_json(comparison)
        elif args.format == "markdown":
            rendered = render_comparison_markdown(comparison)
        else:
            rendered = render_comparison_text(comparison)

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
                f"moc-env: wrote {args.format} comparison report to {output_path}",
                file=sys.stderr,
            )
        else:
            print(rendered, end="")
        differences = {
            "missing_from_main",
            "value_mismatch",
            "unexpected_in_main",
            "unsupported_check",
            "ambiguous",
        }
        return 1 if any(check.state in differences for check in comparison.checks) else 0

    if arguments and arguments[0] in {"hub-status", "work-status"}:
        parser = (
            build_hub_status_parser()
            if arguments[0] == "hub-status"
            else build_work_status_parser()
        )
        args = parser.parse_args(arguments[1:])
        issue_number = args.issue
        if issue_number is None:
            issue_number = KNOWN_ISSUES.get(args.environment)

        environment = Environment(name=args.environment, issue_number=issue_number)
        github_token = _resolve_github_token(args)
        client = GitHubClient(token=github_token, timeout=args.timeout)
        stage_step = 0

        def print_scoped_progress(
            stage: str,
            action: str,
            repository: str,
            path: str,
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
            progress=print_scoped_progress,
        )
        try:
            report = (
                checker.run_hub(environment)
                if arguments[0] == "hub-status"
                else checker.run_workload(environment)
            ).to_dict()
        except (CredentialError, GitHubError, RateLimitError) as exc:
            print(f"moc-env: {exc}", file=sys.stderr)
            return 2
        return _render_status_report(args, report)

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

    return _render_status_report(args, report)


if __name__ == "__main__":
    raise SystemExit(main())
