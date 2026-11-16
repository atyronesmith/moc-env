"""Shared helpers for moc-env command handlers."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .credentials import (
    CredentialError,
    CredentialResolver,
    credential_options_from_environment,
    load_credential_environment_file,
)


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
    if args.no_auth:
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


