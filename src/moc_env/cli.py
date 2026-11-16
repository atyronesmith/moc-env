"""Command-line entry point."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any, Callable

from .checks import Clock, StatusChecker, list_environments
from .chart_values import documentation_directory, load_chart_values_manual, render_chart_values_markdown
from .chart_value_discovery import build_discovery_report, render_discovery_json, render_discovery_markdown, render_discovery_text
from .credentials import CredentialResolver
from .compare import compare_environment, compare_infra, compare_workload, desired_environment, render_comparison_json, render_comparison_markdown, render_comparison_text
from .completion import COMMANDS, bash_completion_script, command_help_epilog, zsh_completion_script
from .cli_support import ProgressReporter, _print_unauthenticated_warning, resolve_github_token, sanitize_command, write_output
from .doc_catalog import DocumentCatalogError, load_catalog_sources, refresh_document_catalog, render_catalog_refresh_json, render_catalog_refresh_text
from .environment_cache import read_environment_cache, write_environment_cache
from .export import render_environment_export, render_infra_export, render_workload_export, workload_cluster_name
from .github import GitHubClient, GitHubError, RateLimitError
from .model import Environment
from .observed import read_apps_observation, read_chart_values_reference_observation, read_infra_observation, read_issue_observation
from .plan import build_infra_change_plan, render_change_plan_json, render_change_plan_markdown, render_change_plan_text
from .registry import DEFAULT_REGISTRY_PATH, EnvironmentRegistry, RegistryError
from .report import render_environment_list_json, render_environment_list_text, render_json, render_markdown, render_text
from .validate import load_environment_document, load_infra_cluster_document, load_validation_result, load_yaml_document, render_validation_json, render_validation_markdown, render_validation_text, validate_workload_cluster

Handler = Callable[..., int]


def _add_credential_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional KEY=VALUE file for non-secret credential selectors (default: .env; absent file is ignored)",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="GitHub request timeout in seconds")
    cache_mode = parser.add_mutually_exclusive_group()
    cache_mode.add_argument("--offline", action="store_true", help="Serve GitHub responses only from the local response cache")
    cache_mode.add_argument("--refresh", action="store_true", help="Ignore cached GitHub responses and request current data")


def _add_output(parser: argparse.ArgumentParser, help: str) -> None:
    parser.add_argument("--output", help=help)


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


def _configure_status(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument("--issue", type=int, help="MOC-issues number; overrides the packaged environment registry")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text", help="Output format")
    parser.add_argument("--no-prs", action="store_true", help="Do not inspect pull requests")
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="REPO=REF",
        help="Read a repository at a branch or pull-request head, for example --ref oac-apps=pull/246/head (repeatable)",
    )
    parser.add_argument("--details", action="store_true", help="Append full per-check findings after the one-screen summary")
    parser.add_argument("--ascii", action="store_true", help="Replace emoji with ASCII markers such as [ok] and [fail]")
    parser.add_argument("--verbose", action="store_true", help="Show progress on stderr even when stderr is not a terminal")
    _add_credential_arguments(parser)
    _add_output(
        parser,
        "Write the rendered report to this file instead of stdout; useful with --format markdown",
    )


def _configure_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    _add_credential_arguments(parser)


def _configure_completion(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("shell", choices=("bash", "zsh"), help="Shell for which to print a completion script")


def _configure_document_values(parser: argparse.ArgumentParser) -> None:
    _add_output(parser, "Write the Markdown guide to this file instead of stdout")
    _add_credential_arguments(parser)


def _configure_refresh_doc_catalog(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", default="../MOC", help="Directory containing local MOC repository clones (default: ../MOC)")
    parser.add_argument("--cache-root", default=".cache/doc-catalog", help="Local documentation cache directory (default: .cache/doc-catalog)")
    _add_report_arguments(parser, formats=("text", "json"), output_help="Write the refresh report to this file instead of stdout")


def _configure_discover_values(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", default="../MOC", help="Directory containing local MOC repository clones (default: ../MOC)")
    parser.add_argument("--cache-root", default=".cache/doc-catalog", help="Local documentation cache directory (default: .cache/doc-catalog)")
    _add_report_arguments(
        parser,
        formats=("markdown", "text", "json"),
        default="markdown",
        output_help="Write the discovery report to this file instead of stdout",
    )


def _configure_export_infra(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    _add_output(parser, "Write the YAML snapshot to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_export_workload(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument("workload", help="Workload name, such as workload0 or bu-ist-demo-workload0")
    _add_output(parser, "Write the YAML snapshot to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_export_environment(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("environment", help="Environment name, such as bu-ist-demo")
    parser.add_argument("--issue", type=int, help="MOC-issues number; defaults to the known issue for the environment")
    _add_output(parser, "Write the YAML bundle to this file instead of stdout; the command never creates or updates GitHub content")
    _add_credential_arguments(parser)


def _configure_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Path to a desired-state YAML file")
    _add_report_arguments(parser, output_help="Write the validation report to this file instead of stdout")


def _configure_check(parser: argparse.ArgumentParser, file_help: str, output_help: str = "Write the comparison report to this file instead of stdout") -> None:
    parser.add_argument("file", help=file_help)
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
        "status-hub": ("Report hub-cluster repository configuration state", _configure_status, _status_handler),
        "status-workload": ("Report workload-cluster repository configuration state", _configure_status, _status_handler),
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
            command_parser.add_argument("--workload", help="Workload name, such as workload1 or oac-dev-workload1")
        command_parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    return _build_parser()


def build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moc-env list", description="List environment names that can be passed to moc-env")
    _configure_list(parser)
    return parser


def _print_unknown_environment(environment_name: str, known_names: list[str]) -> None:
    print(f"moc-env: unknown environment: {environment_name}", file=sys.stderr)
    matches = difflib.get_close_matches(environment_name, known_names, n=1)
    if matches:
        print(f"Did you mean: {matches[0]}", file=sys.stderr)
    print("Known environments:", file=sys.stderr)
    for name in known_names:
        print(f"  {name}", file=sys.stderr)


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


def _resolve_workload_argument(environment_name: str, workload: str, workload_clusters: list[str]) -> str:
    for cluster in workload_clusters:
        if workload in {cluster, cluster.removeprefix(f"{environment_name}-")}:
            return cluster
    print(f"moc-env: unknown workload cluster: {workload}", file=sys.stderr)
    print("Known workload clusters:", file=sys.stderr)
    for cluster in workload_clusters:
        print(f"  {cluster}", file=sys.stderr)
    raise ValueError(workload)


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


def _status_handler(
    args: argparse.Namespace,
    registry: EnvironmentRegistry,
    clock: Clock | None,
    arguments: list[str],
) -> int:
    issue_number = args.issue if args.issue is not None else registry.issue(args.environment)
    environment = Environment(name=args.environment, issue_number=issue_number)
    repository_refs: dict[str, str] = {}
    for repository_ref in args.ref:
        repository, separator, ref = repository_ref.partition("=")
        if not separator or not repository or not ref:
            args.parser.error("--ref must have the form REPO=REF")
        repository_refs[f"CCI-MOC/{repository}"] = ref
    client = _new_github_client(args, _resolve_github_token(args), repository_refs)
    try:
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
            _print_unknown_environment(args.environment, known_names)
            return 2
    selected_workload = None
    if getattr(args, "workload", None) is not None:
        try:
            selected_workload = _resolve_workload_argument(args.environment, args.workload, workload_clusters)
        except ValueError:
            return 2
    environment = Environment(name=args.environment, issue_number=issue_number, workload_clusters=tuple(workload_clusters))
    checker = StatusChecker(
        client=client,
        include_prs=not args.no_prs,
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
    except (CredentialError, GitHubError, RateLimitError) as exc:
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    report_dict = report.to_dict()
    if args.format == "json":
        rendered = render_json(report_dict)
    elif args.format == "markdown":
        rendered = render_markdown(report_dict)
    else:
        rendered = render_text(report_dict, details=args.details, ascii_mode=args.ascii)
    return write_output(args, rendered, f"{args.format} report")


def _complete_environment(arguments: list[str]) -> int:
    prefix = arguments[1] if len(arguments) > 1 else ""
    mode = arguments[2] if len(arguments) > 2 else "environment"
    if mode not in {"environment", "workload"}:
        print("moc-env: unknown completion mode", file=sys.stderr)
        return 2
    clusters = read_environment_cache()
    if not clusters:
        try:
            clusters = list_environments(GitHubClient(token=os.environ.get("GITHUB_TOKEN")))
            write_environment_cache(clusters)
        except (GitHubError, RateLimitError, OSError):
            clusters = []
    key = "environment" if mode == "environment" else "cluster"
    if mode == "environment":
        values = sorted({cluster[key] for cluster in clusters if isinstance(cluster.get(key), str)})
    else:
        values = sorted(cluster[key] for cluster in clusters if cluster.get("type") == "workload" and isinstance(cluster.get(key), str))
    for value in values:
        if value.startswith(prefix):
            print(value)
    return 0


def main(argv: list[str] | None = None, clock: Clock | None = None) -> int:
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
