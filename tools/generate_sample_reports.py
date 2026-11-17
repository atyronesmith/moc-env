#!/usr/bin/env python3
"""Regenerate deterministic, network-free sample reports."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from moc_env import cli  # noqa: E402
from fakes import FakeGitHubClient, FullyConfiguredFakeGitHubClient  # noqa: E402


FIXED_CLOCK = lambda: datetime(  # noqa: E731
    2026, 11, 16, 12, 34, 56, tzinfo=timezone.utc
)
BANNER = "SAMPLE — generated from a synthetic fixture, not a live environment."


def synthetic(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("bu_ist_demo", "example_env").replace(
            "bu-ist-demo", "example-env"
        )
    if isinstance(value, list):
        return [synthetic(item) for item in value]
    if isinstance(value, tuple):
        return tuple(synthetic(item) for item in value)
    if isinstance(value, dict):
        return {synthetic(key): synthetic(item) for key, item in value.items()}
    return value


def fixture(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("example_env", "bu_ist_demo").replace(
            "example-env", "bu-ist-demo"
        )
    return value


class SyntheticGitHubClient(FakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        return synthetic(super().get_tree(repository, ref))

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        return synthetic(super().get_file(repository, fixture(path), ref))

    def pulls(self, repository: str, state: str = "all"):
        for pull in super().pulls(repository, state):
            yield synthetic(pull)

    def pr_files(self, repository: str, number: int):
        for file in super().pr_files(repository, number):
            yield synthetic(file)


class SyntheticFullyConfiguredClient(FullyConfiguredFakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        return synthetic(super().get_tree(repository, ref))

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        return synthetic(super().get_file(repository, fixture(path), ref))


class SyntheticEnvironmentAppsClient(SyntheticGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "hosted-clusters/example-env-infra/example-env-workload0/values.yaml",
                "values/example-env-infra/example-env-workload0/cert-manager.yaml",
                "apps/example-env-infra/example-env-workload0/example.yaml",
            }
            tree.update({path: {"path": path} for path in paths})
        return tree


def run(
    arguments: list[str],
    client_class=SyntheticGitHubClient,
    allowed_exit_codes: set[int] = {0},
) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.object(cli, "_resolve_github_token", return_value=None),
        patch.object(cli, "GitHubClient", client_class),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(arguments, clock=FIXED_CLOCK)
    if exit_code not in allowed_exit_codes:
        raise SystemExit(
            f"sample command failed ({exit_code}): {' '.join(arguments)}\n"
            f"{stderr.getvalue()}"
        )


def add_banner(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.startswith(BANNER):
        return
    prefix = "# " if path.suffix in {".yaml", ".yml"} else ""
    path.write_text(f"{prefix}{BANNER}\n\n{text}", encoding="utf-8")


def main() -> None:
    # CLI provenance must be portable, including the validation input paths.
    os.chdir(ROOT)
    samples = Path("docs/samples")
    samples.mkdir(parents=True, exist_ok=True)
    for path in samples.iterdir():
        if path.is_file():
            path.unlink()
    with tempfile.TemporaryDirectory() as cache_directory:
        os.environ["MOC_ENV_CACHE_DIR"] = cache_directory

        run([
            "status", "example-env", "--format", "text", "--no-prs",
            "--output", str(samples / "example-env.txt"),
        ])
        run([
            "status", "example-env", "--format", "markdown", "--no-prs",
            "--output", str(samples / "example-env.md"),
        ])
        run([
            "status", "example-env", "--format", "markdown", "--no-prs",
            "--output", str(samples / "example-env-fully-configured.md"),
        ], client_class=SyntheticFullyConfiguredClient)

        infra = samples / "example-env-infra.yaml"
        workload = samples / "example-env-workload0.yaml"
        environment = samples / "example-env-environment.yaml"
        run(["export-infra", "example-env", "--output", str(infra)])
        run(["export-workload", "example-env", "workload0", "--output", str(workload)])
        run([
            "export-environment", "example-env", "--issue", "666",
            "--output", str(environment)
        ], client_class=SyntheticEnvironmentAppsClient)

        for document, label in (
            (infra, "infra"), (workload, "workload"), (environment, "environment")
        ):
            run([
                "validate", str(document), "--format", "markdown",
                "--output", str(samples / f"example-env-{label}-validation.md"),
            ])
            command = {
                "infra": "check-infra",
                "workload": "check-workload",
                "environment": "check-environment",
            }[label]
            run([
                command, str(document), "--no-prs", "--format", "markdown",
                "--output", str(samples / f"example-env-{label}-comparison.md"),
            ], client_class=SyntheticEnvironmentAppsClient, allowed_exit_codes={0, 1})

        run([
            "plan-infra", str(infra), "--no-prs", "--format", "markdown",
            "--output", str(samples / "example-env-infra-plan.md"),
        ])
        run([
            "document-values", "--output", str(samples / "chart-values.md"),
        ], client_class=SyntheticFullyConfiguredClient)

    for path in samples.iterdir():
        if path.is_file():
            add_banner(path)


if __name__ == "__main__":
    main()
