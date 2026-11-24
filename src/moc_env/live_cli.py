"""Argument parsing and report dispatch for the opt-in live workflow."""

from __future__ import annotations

import argparse
import shlex
import shutil
import sys
from pathlib import Path
from time import monotonic
from typing import Any

from .capture_live import LOGIN_MESSAGE, CaptureError, capture_live
from .charts import ChartInventoryError
from .checks import list_environments
from .cli_support import (add_credential_arguments, add_format_argument, add_output,
                        resolve_output_format, resolve_workload_argument, write_output)
from .completion import mark_environment_argument, mark_file_argument, mark_workload_argument
from .github import GitHubError
from .verify_live import LocalRepositories, render_live_report, verify_live


def _scope(parser: argparse.ArgumentParser) -> None:
    mark_environment_argument(parser.add_argument("environment", help="Environment name, such as oac-prod"))
    mark_workload_argument(parser.add_argument("--workload", required=True, help="Workload suffix or full cluster name"))


def configure_capture(parser: argparse.ArgumentParser) -> None:
    _scope(parser)
    mark_file_argument(parser.add_argument("--out", required=True, help="New or empty private snapshot directory"))
    parser.add_argument("--as", dest="as_user", help="Explicitly impersonate this user (otherwise never impersonate)")
    mark_file_argument(parser.add_argument("--repository-root", help="Read declared charts from local oac-apps/ and oac-infra/ directories"))
    parser.add_argument("--skip-identity-check", action="store_true",
                        help="Deliberately skip matching the cluster API host to its declaration")
    parser.add_argument("--progress", action="store_true",
                        help="Show capture progress on stderr even when it is not a terminal")
    parser.add_argument("--verbose", action="store_true",
                        help="Also show each file read and each chart checked")
    add_credential_arguments(parser)


def configure_verify(parser: argparse.ArgumentParser) -> None:
    _scope(parser)
    mark_file_argument(parser.add_argument("--snapshot", required=True, help="Captured snapshot directory"))
    mark_file_argument(parser.add_argument("--repository-root", help="Read local oac-apps/ and oac-infra/ directories without network access"))
    parser.add_argument("--progress", action="store_true",
                        help="Show verification progress on stderr even when it is not a terminal")
    parser.add_argument("--verbose", action="store_true",
                        help="Also show each file read and each chart checked")
    add_format_argument(parser)
    add_output(parser, "Write the verification report to this file instead of stdout", infers_format=True)
    add_credential_arguments(parser)


def _declared_workload(client: Any, environment: str, workload: str) -> str | None:
    rows = list_environments(client)
    workload_clusters = [row["cluster"] for row in rows
                        if row["environment"] == environment and row["type"] == "workload"]
    try:
        return resolve_workload_argument(environment, workload, workload_clusters)
    except ValueError:
        # The shared resolver already prints its error and known cluster list.
        return None


class LiveProgressReporter:
    """Live workflow lines on stderr, enabled for terminals or explicitly."""

    def __init__(self, force: bool = False, verbose: bool = False) -> None:
        self.terminal = sys.stderr.isatty()
        self.verbose = verbose
        self.enabled = force or verbose or self.terminal
        self.files = 0
        self._inline_width = 0

    def finish(self) -> None:
        """Clear an in-place update before a new line or an error message."""
        if self._inline_width:
            print("\r" + " " * self._inline_width + "\r", end="", file=sys.stderr, flush=True)
            self._inline_width = 0

    def __call__(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        kind = event["event"]
        if not self.verbose and kind in {"chart", "chart_start", "chart_end"}:
            if kind == "chart" and self.terminal:
                self.files += 1
                line = f"▶ Reading chart declarations ... {self.files} files"
                print(f"\r{line}", end="", file=sys.stderr, flush=True)
                self._inline_width = len(line)
            return
        self.finish()
        if kind == "oc_start":
            total = event["total"] if event["total"] is not None else "?"
            scope = " (all namespaces)" if event["all_namespaces"] else ""
            print(f"▶ {event['position']}/{total} {event['resource']}{scope} ... ",
                    end="", file=sys.stderr, flush=True)
        elif kind == "oc_end":
            outcome = event["outcome"]
            if outcome == "captured":
                count = event["count"]
                outcome += f" {count} object" + ("" if count == 1 else "s")
            timing = "after" if outcome == "timed out" else "in"
            print(f"{outcome} {timing} {event['elapsed']:.1f}s", file=sys.stderr, flush=True)
        elif kind in {"declarations", "manifest", "inventory", "workload"}:
            if kind in {"declarations", "inventory"}:
                self.files = 0
            print(f"▶ {event['message']}", file=sys.stderr, flush=True)
        elif kind == "inventory_end":
            print(f"▶ Chart declarations read: {event['files']} files in {event['elapsed']:.1f}s",
                    file=sys.stderr, flush=True)
        elif kind == "charts_end":
            print(f"▶ {event['total']} charts checked in {event['elapsed']:.1f}s", file=sys.stderr, flush=True)
        elif kind == "chart_start":
            print(f"▶ {event['position']}/{event['total']} chart {event['chart']} ... ",
                    end="", file=sys.stderr, flush=True)
        elif kind == "chart_end":
            print(event["verdict"], file=sys.stderr, flush=True)
        elif kind == "section":
            print(f"▶ {event['section']}", file=sys.stderr, flush=True)
        elif kind == "chart":
            print(f"▶ {event['stage']} — {event['action']} ({event['repository']}/{event['path']})",
                    file=sys.stderr, flush=True)
        elif kind == "identity":
            outcome = "verified" if event["verified"] else f"not verified: {event['reason']}"
            print(f"▶ Cluster identity: {outcome}", file=sys.stderr, flush=True)


def capture_handler(args: argparse.Namespace, **_context: Any) -> int:
    from .cli import _new_github_client, _resolve_github_token

    started = monotonic()
    reporter = LiveProgressReporter(args.progress, args.verbose)
    try:
        if shutil.which("oc") is None:
            raise CaptureError(LOGIN_MESSAGE)
        client = LocalRepositories(Path(args.repository_root)) if args.repository_root else _new_github_client(args, _resolve_github_token(args))
        reporter({"event": "workload", "message": f"Resolving workload clusters for {args.environment}"})
        workload = _declared_workload(client, args.environment, args.workload)
        if workload is None:
            return 2
        output = Path(args.out).resolve()
        manifest = capture_live(args.environment, workload, output, args.as_user,
                                client=client, skip_identity_check=args.skip_identity_check,
                                progress=reporter)
    except (OSError, ValueError, CaptureError, GitHubError, ChartInventoryError) as exc:
        reporter.finish()
        message = str(exc)
        print(message if message.startswith("moc-env:") else f"moc-env: {message}", file=sys.stderr)
        return 2
    print(f"Snapshot: {output} · {len(manifest['resources'])} kinds · {len(manifest['forbidden'])} forbidden · {monotonic() - started:.0f}s")
    command = shlex.join(["moc-env", "verify-live", args.environment, "--workload", workload,
                            "--snapshot", str(output)])
    print(f"Next: {command}")
    return 0


def verify_handler(args: argparse.Namespace, **_context: Any) -> int:
    # Import the factories lazily to preserve the entry point's test seams.
    from .cli import _new_github_client, _resolve_github_token

    args.format = resolve_output_format(args, default="text", supported=("text", "json", "markdown"))
    reporter = LiveProgressReporter(args.progress, args.verbose)
    try:
        client = LocalRepositories(Path(args.repository_root)) if args.repository_root else _new_github_client(args, _resolve_github_token(args))
        reporter({"event": "workload", "message": f"Resolving workload clusters for {args.environment}"})
        workload = _declared_workload(client, args.environment, args.workload)
        if workload is None:
            return 2
        report = verify_live(client, args.environment, workload, Path(args.snapshot), progress=reporter)
    except (OSError, ValueError, GitHubError, ChartInventoryError) as exc:
        reporter.finish()
        print(f"moc-env: {exc}", file=sys.stderr)
        return 2
    result = write_output(args, render_live_report(report, args.format), f"{args.format} verification report")
    return result or (1 if report["summary"]["drift"] or report["summary"]["unverifiable"] else 0)
