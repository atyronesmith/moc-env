"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .checks import Clock, StatusChecker, list_environments
from .chart_reference import missing_description_warnings
from .charts import (
    ChartInventoryError,
    collect_chart_inventory,
    render_chart_inventory,
)
from .chart_values import documentation_directory, load_chart_values_manual, render_chart_values_markdown
from .chart_value_discovery import build_discovery_report, render_discovery_json, render_discovery_markdown, render_discovery_text
from .credentials import CredentialError, CredentialResolver  # noqa: F401
from .compare import compare_environment, compare_infra, compare_workload, desired_environment, render_comparison_json, render_comparison_markdown, render_comparison_text
from .completion import (
    COMMANDS,
    ENVIRONMENT_COMPLETION,
    FILE_COMPLETION,
    WORKLOAD_COMPLETION,
    argument_completion,
    bash_completion_script,
    command_help_epilog,
    command_option_strings,
    command_parser,
    mark_environment_argument,
    mark_file_argument,
    mark_workload_argument,
    option_action,
    positional_actions,
    positional_index,
    zsh_completion_script,
)
from .doc_catalog import DocumentCatalogError, load_catalog_sources, refresh_document_catalog, render_catalog_refresh_json, render_catalog_refresh_text
from .environment_cache import read_environment_cache, write_environment_cache
from .export import render_environment_export, render_infra_export, render_workload_export, workload_cluster_name
from .github import GitHubClient, GitHubError, RateLimitError
from .model import Environment
from .observed import read_apps_observation, read_chart_values_reference_observation, read_infra_observation, read_issue_observation
from .plan import build_infra_change_plan, render_change_plan_json, render_change_plan_markdown, render_change_plan_text
from .registry import DEFAULT_REGISTRY_PATH, EnvironmentRegistry, RegistryError
from .repositories import status_request_urls
from .report import render_environment_list_json, render_environment_list_text, render_json, render_markdown, render_text
from .cli_support import ProgressReporter, _print_unauthenticated_warning, add_credential_arguments, add_output, configure_diff, configure_status, diff_handler, print_unknown_environment, resolve_github_token, resolve_workload_argument, sanitize_command, write_output
from .validate import load_environment_document, load_infra_cluster_document, load_validation_result, load_yaml_document, render_validation_json, render_validation_markdown, render_validation_text, validate_workload_cluster

Handler = Callable[..., int]

_add_credential_arguments = add_credential_arguments
_add_output = add_output
_configure_status = configure_status


def _add_report_arguments(
    parser: argparse.ArgumentParser,
    *,
    no_prs: bool = False,
    credentials: bool = False,
    output_help: str = "Write the report to this file instead of stdout",
    formats: tuple[str, ...] = ("text", "json", "markdown"),
    default: str = "text",
) -> None:
    parser.add_argument("--format", choices=formats, default=default, help="Output format")
    _add_output(parser, output_help)
    if no_prs:
        parser.add_argument("--no-prs", action="store_true", help="Do not inspect pull requests")
    if credentials:
        _add_credential_arguments(parser)


def _configure_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    _add_credential_arguments(parser)


def _configure_completion(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("shell", choices=("bash", "zsh"), help="Shell for which to print a completion script")


def _configure_document_values(parser: argparse.ArgumentParser) -> None:
    _add_output(parser, "Write the Markdown guide to this file instead of stdout")
    _add_credential_arguments(parser)


def _configure_refresh_doc_catalog(parser: argparse.ArgumentParser) -> None:
    mark_file_argument(parser.add_argument("--repository-root", default="../MOC", help="Directory containing local MOC repository clones (default: ../MOC)"))
    mark_file_argument(parser.add_argument("--cache-root", default=".cache/doc-catalog", help="Local documentation cache directory (default: .cache/doc-catalog)"))
    _add_report_arguments(parser, formats=("text", "json"), output_help="Write the refresh report to this file instead of stdout")


def _configure_discover_values(parser: argparse.ArgumentParser) -> None:
    mark_file_argument(parser.add_argument("--repository-root", default="../MOC", help="Directory containing local MOC repository clones (default: ../MOC)"))
    mark_file_argument(parser.add_argument("--cache-root", default=".cache/doc-catalog", help="Local documentation cache directory (default: .cache/doc-catalog)"))
    _add_report_arguments(
        parser,
        formats=("markdown", "text", "json"),
        default="markdown",
        output_help="Write the discovery report to this file instead of stdout",
    )


def _configure_export_infra(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(parser.add_argument("environment", help="Environment name, such as bu-ist-demo"))
    _add_output(parser, "Write the YAML snapshot to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_export_workload(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(parser.add_argument("environment", help="Environment name, such as bu-ist-demo"))
    mark_workload_argument(parser.add_argument("workload", help="Workload name, such as workload0 or bu-ist-demo-workload0"))
    _add_output(parser, "Write the YAML snapshot to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_export_environment(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(parser.add_argument("environment", help="Environment name, such as bu-ist-demo"))
    parser.add_argument("--issue", type=int, help="MOC-issues number; defaults to the known issue for the environment")
    _add_output(parser, "Write the YAML bundle to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_validate(parser: argparse.ArgumentParser) -> None:
    mark_file_argument(parser.add_argument("file", help="Path to a desired-state YAML file"))
    _add_report_arguments(parser, output_help="Write the validation report to this file instead of stdout")


def _configure_charts(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(
        parser.add_argument(
            "environment",
            nargs="?",
            help="Environment name, such as bu-ist-demo; omit it for deployment hubs and workload clusters",
        )
    )
    parser.add_argument(
        "--all-clusters",
        action="store_true",
        help="Include test clusters when no environment is named",
    )
    mark_workload_argument(
        parser.add_argument(
            "--workload",
            help="Workload name, such as workload0 or bu-ist-demo-workload0",
        )
    )
    parser.add_argument(
        "--view",
        choices=("summary", "cluster", "reference"),
        default="summary",
        help="Feature summary tables, one section per cluster, or the chart reference (default: summary)",
    )
    parser.add_argument(
        "--chart",
        action="append",
        default=[],
        metavar="NAME",
        help="Limit the reference chart section to the named chart; repeatable",
    )
    parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default=None,
        help="Output format (default: markdown for reference, text otherwise)",
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="REPO=REF",
        help="Read oac-apps at a branch or pull-request head, for example --ref oac-apps=pull/246/head",
    )
    add_credential_arguments(parser)
    add_output(
        parser,
        "Write the rendered chart inventory to this file instead of stdout",
    )


def _configure_check(parser: argparse.ArgumentParser, file_help: str, output_help: str = "Write the comparison report to this file instead of stdout") -> None:
    mark_file_argument(parser.add_argument("file", help=file_help))
    _add_report_arguments(
        parser,
        no_prs=True,
        credentials=True,
        output_help=output_help,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moc-env",
        description="Report and manage CCI-MOC environment configuration state from public GitHub repositories",
        epilog=command_help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    commands: dict[str, tuple[str, Callable[[argparse.ArgumentParser], None], Handler]] = {
        "status": ("Report combined hub and workload repository configuration state", _configure_status, _status_handler),
        "diff": ("Compare repository configuration state for two environments", configure_diff, _diff_handler),
        "status-hub": ("Report hub-cluster repository configuration state", _configure_status, _status_handler),
        "status-workload": ("Report workload-cluster repository configuration state", _configure_status, _status_handler),
        "charts": ("Print which charts each hub and workload cluster receives from oac-apps", _configure_charts, _charts_handler),
        "list": ("List environment names that can be passed to moc-env", _configure_list, _list_handler),
        "completion": ("Print a bash or zsh completion script", _configure_completion, _completion_handler),
        "document-values": ("Generate an environment-independent Markdown guide to hub and workload chart values", _configure_document_values, _document_values_handler),
        "refresh-doc-catalog": ("Refresh the local documentation catalog from local Git clones", _configure_refresh_doc_catalog, _refresh_doc_catalog_handler),
        "discover-values": ("Compare local oac-apps chart values with manual documentation", _configure_discover_values, _discover_values_handler),
        "export-infra": ("Export a deterministic draft hub-cluster snapshot from merged main", _configure_export_infra, _export_infra_handler),
        "export-workload": ("Export a deterministic draft WorkloadCluster snapshot from merged main", _configure_export_workload, _export_workload_handler),
        "export-environment": ("Export a deterministic draft Environment bundle from merged main", _configure_export_environment, _export_environment_handler),
        "validate": ("Validate a local desired-state YAML document", _configure_validate, _validate_handler),
        "check-infra": ("Compare a desired-state hub-cluster document with merged main", lambda parser: _configure_check(parser, "Path to a desired-state hub-cluster YAML file"), _check_infra_handler),
        "check-workload": ("Compare a desired-state WorkloadCluster document with merged main", lambda parser: _configure_check(parser, "Path to a desired-state WorkloadCluster YAML file"), _check_workload_handler),
        "check-environment": ("Compare a desired-state Environment bundle with merged main", lambda parser: _configure_check(parser, "Path to an Environment bundle YAML file"), _check_environment_handler),
        "plan-infra": ("Plan read-only repository changes from a desired-state hub-cluster document", lambda parser: _configure_check(parser, "Path to a desired-state YAML file", "Write the rendered change plan to this file instead of stdout"), _plan_infra_handler),
    }
    for name, (description, configure, handler) in commands.items():
        command_parser = subparsers.add_parser(name, description=description, help=description)
        configure(command_parser)
        if name == "status-workload":
            mark_workload_argument(
                command_parser.add_argument("--workload", help="Workload name, such as workload1 or oac-dev-workload1")
            )
        command_parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    return _build_parser()


def build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moc-env list", description="List environment names that can be passed to moc-env")
    _configure_list(parser)
    return parser


def _resolve_github_token(args: argparse.Namespace) -> str | None:
    return resolve_github_token(args)


def _new_github_client(args: argparse.Namespace, github_token: str | None, refs: dict[str, str] | None = None) -> GitHubClient:
    client = GitHubClient(
        token=github_token,
        timeout=args.timeout,
        refs=refs,
        offline=args.offline,
        refresh=args.refresh,
    )
    if github_token is None:
        client.on_response = _print_unauthenticated_warning
    return client


def _completion_handler(args: argparse.Namespace, **_context: Any) -> int:
    print(bash_completion_script() if args.shell == "bash" else zsh_completion_script(), end="")
    return 0


def _list_handler(args: argparse.Namespace, **_context: Any) -> int:
    client = _new_github_client(args, _resolve_github_token(args))
    try:
        environments = list_environments(client)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    try:
        write_environment_cache(environments)
    except OSError as exc:
        print(f"moc-env: could not write environment cache: {exc}", file=sys.stderr)
    rendered = render_environment_list_json(environments) if args.format == "json" else render_environment_list_text(environments)
    print(rendered, end="")
    return 0


def _refresh_doc_catalog_handler(args: argparse.Namespace, **_context: Any) -> int:
    try:
        report = refresh_document_catalog(
            load_catalog_sources(documentation_directory() / "sources.yaml"),
            Path(args.repository_root),
            Path(args.cache_root),
        )
    except DocumentCatalogError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    rendered = render_catalog_refresh_json(report) if args.format == "json" else render_catalog_refresh_text(report)
    return write_output(args, rendered, f"{args.format} catalog refresh report")


def _discover_values_handler(args: argparse.Namespace, **_context: Any) -> int:
    try:
        report = build_discovery_report(
            load_chart_values_manual(),
            Path(args.repository_root) / "oac-apps",
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
    return write_output(args, rendered, f"{args.format} discovery report")


def _document_values_handler(args: argparse.Namespace, **_context: Any) -> int:
    client = _new_github_client(args, _resolve_github_token(args))
    try:
        observation = read_chart_values_reference_observation(client, progress=ProgressReporter())
        rendered = render_chart_values_markdown(observation)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    return write_output(args, rendered, "chart-values reference")


def _render_export(args: argparse.Namespace, render: Callable[[GitHubClient, ProgressReporter], str], label: str) -> int:
    client = _new_github_client(args, _resolve_github_token(args))
    try:
        return write_output(args, render(client, ProgressReporter()), label)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2


def _export_infra_handler(args: argparse.Namespace, **_context: Any) -> int:
    environment = Environment(name=args.environment)
    return _render_export(args, lambda client, progress: render_infra_export(environment, read_infra_observation(client, environment, progress=progress)), "InfraCluster YAML")


def _export_workload_handler(args: argparse.Namespace, **_context: Any) -> int:
    environment = Environment(name=args.environment)
    try:
        workload_cluster = workload_cluster_name(environment, args.workload)
    except ValueError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    def render(client: GitHubClient, progress: ProgressReporter) -> str:
        infra = read_infra_observation(client, environment, progress=progress)
        apps = read_apps_observation(client, environment, progress=progress, include_pull_requests=False)
        return render_workload_export(environment, workload_cluster, infra, apps)

    return _render_export(args, render, "WorkloadCluster YAML")


def _export_environment_handler(args: argparse.Namespace, registry: EnvironmentRegistry, **_context: Any) -> int:
    issue_number = args.issue if args.issue is not None else registry.issue(args.environment)
    if issue_number is None:
        print("moc-env: environment has no known MOC issue; pass --issue", file=sys.stderr)
        return 2
    environment = Environment(name=args.environment, issue_number=issue_number)
    def render(client: GitHubClient, progress: ProgressReporter) -> str:
        issue = read_issue_observation(client, environment, progress=progress)
        if issue is None:
            raise GitHubError("MOC issue observation is unavailable")
        infra = read_infra_observation(client, environment, progress=progress)
        apps = read_apps_observation(client, environment, progress=progress, include_pull_requests=False)
        return render_environment_export(environment, issue, infra, apps)

    return _render_export(args, render, "Environment YAML")


def _validate_handler(args: argparse.Namespace, **_context: Any) -> int:
    input_path = Path(args.file)
    result = load_validation_result(input_path)
    if args.format == "json":
        rendered = render_validation_json(result)
    elif args.format == "markdown":
        rendered = render_validation_markdown(result, input_path)
    else:
        rendered = render_validation_text(result)
    exit_code = write_output(args, rendered, f"{args.format} validation report")
    return exit_code if exit_code else (0 if result.valid else 2)


def _render_comparison(comparison: Any, args: argparse.Namespace) -> str:
    if args.format == "json":
        return render_comparison_json(comparison)
    if args.format == "markdown":
        return render_comparison_markdown(comparison)
    return render_comparison_text(comparison)


_DIFFERENCES = {"missing_from_main", "value_mismatch", "unexpected_in_main", "unsupported_check", "ambiguous"}


def _comparison_exit(comparison: Any) -> int:
    return 1 if any(check.state in _DIFFERENCES for check in comparison.checks) else 0


def _load_infra_comparison(args: argparse.Namespace) -> tuple[Any, Any, Any] | None:
    input_path = Path(args.file)
    document, validation = load_infra_cluster_document(input_path)
    if not validation.valid:
        _print_validation_error(input_path, validation.errors)
        return None
    environment = desired_environment(document)
    client = _new_github_client(args, _resolve_github_token(args))
    progress = ProgressReporter()
    try:
        infra = read_infra_observation(client, environment, progress=progress)
        apps = None if args.no_prs else read_apps_observation(client, environment, progress=progress)
        return document, environment, compare_infra(document, environment, infra, apps)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return None


def _write_comparison(args: argparse.Namespace, comparison: Any) -> int:
    exit_code = write_output(args, _render_comparison(comparison, args), f"{args.format} comparison report")
    return exit_code if exit_code else _comparison_exit(comparison)


def _check_infra_handler(args: argparse.Namespace, **_context: Any) -> int:
    loaded = _load_infra_comparison(args)
    return 2 if loaded is None else _write_comparison(args, loaded[2])


def _plan_infra_handler(args: argparse.Namespace, **_context: Any) -> int:
    loaded = _load_infra_comparison(args)
    if loaded is None:
        return 2
    document, _environment, comparison = loaded
    plan = build_infra_change_plan(document, comparison)
    if args.format == "json":
        rendered = render_change_plan_json(plan)
    elif args.format == "markdown":
        rendered = render_change_plan_markdown(plan)
    else:
        rendered = render_change_plan_text(plan)
    return write_output(args, rendered, f"{args.format} change plan")


def _check_workload_handler(args: argparse.Namespace, **_context: Any) -> int:
    input_path = Path(args.file)
    document, load_result = load_yaml_document(input_path)
    if not load_result.valid:
        _print_validation_error(input_path, load_result.errors, "could not load desired-state document")
        return 2
    validation = validate_workload_cluster(document)
    if not validation.valid:
        _print_validation_error(input_path, validation.errors)
        return 2
    environment = desired_environment(document)
    client = _new_github_client(args, _resolve_github_token(args))
    progress = ProgressReporter()
    try:
        infra = read_infra_observation(client, environment, progress=progress)
        apps = read_apps_observation(client, environment, progress=progress, include_pull_requests=not args.no_prs)
        comparison = compare_workload(document, infra, apps)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    return _write_comparison(args, comparison)


def _check_environment_handler(args: argparse.Namespace, **_context: Any) -> int:
    input_path = Path(args.file)
    document, validation = load_environment_document(input_path)
    if not validation.valid:
        _print_validation_error(input_path, validation.errors)
        return 2
    environment = desired_environment(document)
    client = _new_github_client(args, _resolve_github_token(args))
    progress = ProgressReporter()
    try:
        issue = read_issue_observation(client, environment, progress=progress)
        if issue is None:
            raise GitHubError("MOC issue observation is unavailable")
        infra = read_infra_observation(client, environment, progress=progress)
        apps = read_apps_observation(client, environment, progress=progress, include_pull_requests=not args.no_prs)
        comparison = compare_environment(document, environment, issue, infra, apps)
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    return _write_comparison(args, comparison)


def _print_validation_error(input_path: Path, errors: list[str], prefix: str = "desired-state document is invalid") -> None:
    print(f"moc-env: {prefix}: {input_path}", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)


def _charts_handler(
    args: argparse.Namespace,
    registry: EnvironmentRegistry,
    *,
    arguments: list[str] | None = None,
    **_context: Any,
) -> int:
    repository_refs: dict[str, str] = {}
    for repository_ref in args.ref:
        repository, separator, ref = repository_ref.partition("=")
        if not separator or not repository or not ref:
            args.parser.error("--ref must have the form REPO=REF")
        repository_refs[f"CCI-MOC/{repository}"] = ref
    client = _new_github_client(args, _resolve_github_token(args), repository_refs)
    output_format = args.format or (
        "markdown" if args.view == "reference" else "text"
    )
    try:
        inventory = collect_chart_inventory(
            client,
            environment=args.environment,
            workload=args.workload,
            progress=ProgressReporter(),
            include_reference=args.view == "reference",
            deployment_patterns=registry.deployment_hub_patterns,
            all_clusters=args.all_clusters,
        )
    except ChartInventoryError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    rendered = render_chart_inventory(
        inventory,
        view=args.view,
        format=output_format,
        charts=args.chart,
        command=arguments or (),
    )
    exit_code = write_output(
        args, rendered, f"{output_format} chart inventory"
    )
    if exit_code:
        return exit_code
    if args.view == "reference" and inventory.reference is not None:
        for line in missing_description_warnings(
            inventory.reference, args.chart
        ):
            print(line, file=sys.stderr)
    return 1 if inventory.has_errors or inventory.unrecognized else 0


def _status_handler(
    args: argparse.Namespace,
    registry: EnvironmentRegistry,
    clock: Clock | None,
    arguments: list[str],
) -> int:
    if args.environment is None:
        if args.format == "markdown":
            args.parser.error("--format markdown requires an environment name")
        return _list_handler(args)
    issue_number = args.issue if args.issue is not None else registry.issue(args.environment)
    environment = Environment(name=args.environment, issue_number=issue_number)
    repository_refs: dict[str, str] = {}
    for repository_ref in args.ref:
        repository, separator, ref = repository_ref.partition("=")
        if not separator or not repository or not ref:
            args.parser.error("--ref must have the form REPO=REF")
        repository_refs[f"CCI-MOC/{repository}"] = ref
    client = _new_github_client(args, _resolve_github_token(args), repository_refs)
    include_prs = args.prs or (client.authenticated and not args.no_prs)
    candidate_urls = status_request_urls(client, issue_number)
    # Optional PR discovery must not prevent the configuration report merely
    # because its speculative request budget exceeds the remaining quota.
    estimated_calls = len(candidate_urls)
    try:
        client.reserve_quota(estimated_calls, candidate_urls)
        rows = list_environments(client)
        known_names = sorted({row["environment"] for row in rows if row["type"] == "hub"})
        workload_clusters = [row["cluster"] for row in rows if row["environment"] == args.environment and row["type"] == "workload"]
    except (GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    if args.environment not in known_names:
        if args.issue is not None:
            print("moc-env: warning: environment is not in the oac-infra inventory; continuing with the supplied MOC issue", file=sys.stderr)
        else:
            print_unknown_environment(args.environment, known_names)
            return 2
    selected_workload = None
    if getattr(args, "workload", None) is not None:
        try:
            selected_workload = resolve_workload_argument(args.environment, args.workload, workload_clusters)
        except ValueError:
            return 2
    environment = Environment(name=args.environment, issue_number=issue_number, workload_clusters=tuple(workload_clusters))
    checker = StatusChecker(
        client=client,
        include_prs=include_prs,
        progress=ProgressReporter(args.verbose),
        registry=registry,
        command=sanitize_command(arguments),
        clock=clock,
    )
    try:
        if args.command == "status":
            report = checker.run(environment)
        elif args.command == "status-hub":
            report = checker.run_hub(environment)
        else:
            report = checker.run_workload(environment, workload=selected_workload)
    except (CredentialError, GitHubError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    report = replace(
        report,
        pull_requests_skipped=not include_prs,
        pull_requests_skip_reason=(
            "skipped (--no-prs)"
            if args.no_prs
            else "skipped because this run is unauthenticated; use --prs to inspect them"
            if not include_prs
            else None
        ),
    )
    if report.rate_limited:
        print(
            "moc-env: GitHub API rate limit was hit; unread checks are unknown",
            file=sys.stderr,
        )
    report_dict = report.to_dict()
    if args.format == "json":
        rendered = render_json(report_dict)
    elif args.format == "markdown":
        rendered = render_markdown(report_dict)
    else:
        rendered = render_text(report_dict, details=args.details, ascii_mode=args.ascii)
    exit_code = write_output(args, rendered, f"{args.format} report")
    if exit_code:
        return exit_code
    if report.rate_limited:
        return 2
    if args.fail_on == "blocking" and any(check.severity == "blocking" for check in report.checks):
        return 1
    if args.fail_on == "advisory" and any(check.severity in {"blocking", "advisory"} for check in report.checks):
        return 1
    return 0


def _diff_handler(
    args: argparse.Namespace,
    registry: EnvironmentRegistry,
    clock: Clock | None,
    arguments: list[str],
) -> int:
    try:
        return diff_handler(args, registry, clock, arguments, client_factory=GitHubClient,
                            token_resolver=_resolve_github_token)
    except GitHubError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2


def _environment_completion_values(mode: str) -> list[str]:
    clusters = read_environment_cache()
    if not clusters:
        try:
            clusters = list_environments(GitHubClient(token=os.environ.get("GITHUB_TOKEN")))
            write_environment_cache(clusters)
        except (GitHubError, RateLimitError, OSError):
            clusters = []
    key = "environment" if mode == "environment" else "cluster"
    if mode == "environment":
        return sorted({cluster[key] for cluster in clusters if isinstance(cluster.get(key), str)})
    return sorted(cluster[key] for cluster in clusters if cluster.get("type") == "workload" and isinstance(cluster.get(key), str))


def _complete_environment(arguments: list[str]) -> int:
    prefix = arguments[1] if len(arguments) > 1 else ""
    mode = arguments[2] if len(arguments) > 2 else "environment"
    if mode not in {"environment", "workload"}:
        print("moc-env: unknown completion mode", file=sys.stderr)
        return 2
    values = _environment_completion_values(mode)
    for value in values:
        if value.startswith(prefix):
            print(value)
    return 0


def _completion_command_parser(arguments: list[str], mode: str) -> tuple[argparse.ArgumentParser | None, int]:
    command = arguments[1] if len(arguments) > 1 else ""
    parser = command_parser(_build_parser(), command)
    if parser is None:
        print(f"moc-env: unknown completion command for {mode}: {command}", file=sys.stderr)
        return None, 2
    return parser, 0


def _complete_options(arguments: list[str]) -> int:
    parser, exit_code = _completion_command_parser(arguments, "__complete-options")
    if parser is None:
        return exit_code
    prefix = arguments[2] if len(arguments) > 2 else ""
    for option in command_option_strings(parser):
        if option.startswith(prefix):
            print(option)
    return 0


def _complete_option(arguments: list[str]) -> int:
    parser, exit_code = _completion_command_parser(arguments, "__complete-option")
    if parser is None:
        return exit_code
    option = arguments[2] if len(arguments) > 2 else ""
    prefix = arguments[3] if len(arguments) > 3 else ""
    action = option_action(parser, option)
    completion = argument_completion(action) if action is not None else None
    if completion == FILE_COMPLETION:
        # The shell completes a filesystem path for this value.
        return 4
    if action is None or action.nargs == 0:
        # The shell treats a non-zero status as "not an option value" and keeps
        # completing positional arguments or files.
        return 3
    if completion == ENVIRONMENT_COMPLETION:
        values = _environment_completion_values("environment")
    elif completion == WORKLOAD_COMPLETION:
        values = _environment_completion_values("workload")
    else:
        values = [str(choice) for choice in action.choices or ()]
    for value in values:
        if value.startswith(prefix):
            print(value)
    return 0


def _complete_positional(arguments: list[str]) -> int:
    parser, exit_code = _completion_command_parser(arguments, "__complete-positional")
    if parser is None:
        return exit_code
    try:
        cword = int(arguments[2])
    except (IndexError, ValueError):
        print("moc-env: invalid completion position", file=sys.stderr)
        return 2
    words = arguments[3:]
    tokens = words[2:cword] if cword > 2 else []
    positionals = positional_actions(parser)
    index = positional_index(parser, tokens)
    if index >= len(positionals):
        return 3
    action = positionals[index]
    prefix = words[cword] if cword < len(words) else ""
    completion = argument_completion(action)
    if completion == FILE_COMPLETION:
        return 4
    if completion == ENVIRONMENT_COMPLETION:
        values = _environment_completion_values("environment")
    elif completion == WORKLOAD_COMPLETION:
        values = _environment_completion_values("workload")
    elif action.choices:
        values = [str(choice) for choice in action.choices]
    else:
        return 3
    for value in values:
        if value.startswith(prefix):
            print(value)
    return 0


def main(argv: list[str] | None = None, clock: Clock | None = None) -> int:
    from .github import run_clients

    clients: list[GitHubClient] = []
    token = run_clients.set(clients)
    try:
        return _main(argv, clock)
    finally:
        run_clients.reset(token)
        if clients:
            arguments = argv if argv is not None else sys.argv[1:]
            if "--verbose" in arguments:
                endpoints = [
                    endpoint
                    for client in clients
                    for endpoint in client.counted_endpoints
                ]
                if endpoints:
                    print(
                        "GitHub API quota-counted endpoints:",
                        file=sys.stderr,
                    )
                    for endpoint in endpoints:
                        print(f"  GET {endpoint}", file=sys.stderr)
            print(
                f"GitHub API: {sum(c.requests_made for c in clients)} requests, "
                f"{sum(c.api_calls_used for c in clients)} counted against quota, "
                f"{sum(c.cache_hits for c in clients)} from cache",
                file=sys.stderr,
            )


def _main(argv: list[str] | None = None, clock: Clock | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        registry = EnvironmentRegistry.load(DEFAULT_REGISTRY_PATH)
    except RegistryError as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    if not arguments:
        print(_build_parser().format_help(), end="")
        return 0
    if arguments[0] == "__complete-environment":
        return _complete_environment(arguments)
    if arguments[0] == "__complete-options":
        return _complete_options(arguments)
    if arguments[0] == "__complete-option":
        return _complete_option(arguments)
    if arguments[0] == "__complete-positional":
        return _complete_positional(arguments)
    if arguments[0] in {"-h", "--help"}:
        print(_build_parser().format_help(), end="")
        return 0
    if arguments[0] not in COMMANDS:
        print(f"moc-env: unknown command: {arguments[0]}", file=sys.stderr)
        print(command_help_epilog(), file=sys.stderr)
        return 2
    parser = _build_parser()
    args = parser.parse_args(arguments)
    args.parser = parser
    return args.handler(args, registry=registry, clock=clock, arguments=arguments)


if __name__ == "__main__":
    raise SystemExit(main())
