"""Explicit, read-only GitHub token resolution.

Resolution order:

1. ``GITHUB_TOKEN`` in the process environment.
2. A Bitwarden Secrets Manager secret UUID from the environment or CLI.
3. A macOS Keychain item containing that Bitwarden secret UUID.

The Keychain never stores the GitHub token itself. After selecting a UUID, the
resolver asks Bitwarden Secrets Manager for the secret whose key is
``GITHUB_TOKEN``.

No credential value is accepted as a command-line argument. Configured lookup
failures are terminal so a stale or inaccessible fallback cannot be silently
masked by another source.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


SECRET_UUID = re.compile(
    r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$"
)
MAX_OUTPUT_BYTES = 1024 * 1024
KEYCHAIN_TIMEOUT_SECONDS = 15.0
BITWARDEN_TIMEOUT_SECONDS = 30.0
CREDENTIAL_ENV_FILE_KEYS = {
    "GITHUB_BWS_SECRET_ID",
    "MOC_ENV_BWS_SECRET_ID",
    "GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE",
    "GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT",
    "BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE",
    "BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT",
}


class CredentialError(RuntimeError):
    """A configured credential source could not be resolved."""


class CredentialNotFoundError(CredentialError):
    """The optional default Keychain UUID selector was not present."""


@dataclass(frozen=True)
class CredentialOptions:
    """Explicit credential selectors; no value here is a secret."""

    direct_token: str | None = None
    bws_secret_id: str | None = None
    bws_access_token: str | None = None
    bws_secret_id_keychain_service: str = "moc-env-github-token"
    bws_secret_id_keychain_account: str | None = None
    bws_keychain_service: str = "moc-env-bws-access-token"
    bws_keychain_account: str | None = None

    def _bws_secret_id_keychain_account(self) -> str:
        return self.bws_secret_id_keychain_account or getpass.getuser()

    def _bws_keychain_account(self) -> str:
        return self.bws_keychain_account or getpass.getuser()


class CredentialResolver:
    """Resolve a GitHub token without exposing it in diagnostics or argv."""

    def __init__(
        self,
        *,
        platform: str = sys.platform,
        environment: Mapping[str, str] | None = None,
        run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.platform = platform
        self.environment = dict(os.environ if environment is None else environment)
        self._run = run

    def resolve(self, options: CredentialOptions) -> str:
        if options.direct_token:
            return self._valid_token(options.direct_token, "GITHUB_TOKEN")

        secret_id = options.bws_secret_id
        if not secret_id:
            secret_id = self._keychain_secret_id(options)

        return self._resolve_bitwarden(options, secret_id)

    def _keychain_secret_id(self, options: CredentialOptions) -> str:
        secret_id = self._keychain(
            service=options.bws_secret_id_keychain_service,
            account=options._bws_secret_id_keychain_account(),
            label="Bitwarden secret UUID",
        )
        if not SECRET_UUID.fullmatch(secret_id):
            raise CredentialError(
                "macOS Keychain item must contain a Bitwarden secret UUID"
            )
        return secret_id

    def _resolve_bitwarden(
        self, options: CredentialOptions, secret_id: str
    ) -> str:
        if not SECRET_UUID.fullmatch(secret_id):
            raise CredentialError("GITHUB_BWS_SECRET_ID must be a Bitwarden secret UUID")

        machine_token = options.bws_access_token
        if machine_token:
            machine_token = self._valid_token(machine_token, "BWS_ACCESS_TOKEN")
        else:
            try:
                machine_token = self._keychain(
                    service=options.bws_keychain_service,
                    account=options._bws_keychain_account(),
                    label="Bitwarden machine access token",
                )
            except CredentialNotFoundError as exc:
                raise CredentialError(str(exc)) from exc

        bws = self._bws_executable()
        environment = self._sanitized_environment()
        environment["BWS_ACCESS_TOKEN"] = machine_token
        output = self._capture(
            [bws, "secret", "get", secret_id],
            environment=environment,
            timeout=BITWARDEN_TIMEOUT_SECONDS,
            label="Bitwarden",
        )
        return self._decode_github_secret(output)

    def _keychain(self, *, service: str, account: str, label: str) -> str:
        self._validate_selector(service, f"{label} Keychain service")
        self._validate_selector(account, f"{label} Keychain account")

        if self.platform != "darwin":
            raise CredentialError(
                "macOS Keychain credential lookup requires macOS; "
                "set GITHUB_TOKEN or GITHUB_BWS_SECRET_ID instead"
            )
        if not self._is_executable_file("/usr/bin/security"):
            raise CredentialError("macOS Keychain utility is unavailable")

        try:
            output = self._capture(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                ],
                environment=self._sanitized_environment(),
                timeout=KEYCHAIN_TIMEOUT_SECONDS,
                label="macOS Keychain",
                keychain_not_found=True,
            )
        except CredentialError:
            raise
        return output.rstrip("\r\n")

    def _bws_executable(self) -> str:
        path = self.environment.get("PATH", "")
        if not path:
            raise CredentialError("Bitwarden CLI is unavailable: PATH is empty")
        for entry in path.split(os.pathsep):
            if not entry or not os.path.isabs(entry):
                raise CredentialError(
                    "Bitwarden credential lookup requires nonempty absolute PATH entries"
                )

        bws = shutil.which("bws", path=path)
        if not bws or not os.path.isabs(bws) or not self._is_executable_file(bws):
            raise CredentialError("Bitwarden CLI is unavailable on PATH")
        return bws

    def _capture(
        self,
        command: Sequence[str],
        *,
        environment: dict[str, str],
        timeout: float,
        label: str,
        keychain_not_found: bool = False,
    ) -> str:
        try:
            completed = self._run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CredentialError(f"{label} credential lookup timed out") from exc
        except OSError as exc:
            raise CredentialError(f"{label} credential lookup failed") from exc

        if completed.returncode != 0:
            if keychain_not_found and completed.returncode == 44:
                raise CredentialNotFoundError(
                    "macOS Keychain item was not found in this process's access context; "
                    "check service/account and Terminal versus GUI access"
                )
            raise CredentialError(
                f"{label} credential lookup failed; check tool installation and access"
            )

        output = completed.stdout
        if len(output) > MAX_OUTPUT_BYTES:
            raise CredentialError(f"{label} returned too much output")
        try:
            return output.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CredentialError(f"{label} returned invalid UTF-8") from exc

    def _decode_github_secret(self, output: str) -> str:
        try:
            document = json.loads(output)
        except json.JSONDecodeError as exc:
            raise CredentialError("Bitwarden returned invalid secret JSON") from exc

        if not isinstance(document, dict):
            raise CredentialError("Bitwarden returned invalid secret JSON")
        if document.get("key") != "GITHUB_TOKEN":
            raise CredentialError("Bitwarden secret key must be GITHUB_TOKEN")
        return self._valid_token(document.get("value"), "Bitwarden GitHub token")

    def _sanitized_environment(self) -> dict[str, str]:
        return {
            name: value
            for name, value in self.environment.items()
            if name not in {"GITHUB_TOKEN", "BWS_ACCESS_TOKEN"}
        }

    @staticmethod
    def _valid_token(value: object, label: str) -> str:
        if not isinstance(value, str) or not value:
            raise CredentialError(f"{label} is empty")
        for character in value:
            if character.isspace() or unicodedata.category(character).startswith("C"):
                raise CredentialError(f"{label} is invalid")
        return value

    @staticmethod
    def _validate_selector(value: str, label: str) -> None:
        if not value.strip():
            raise CredentialError(f"{label} must be nonempty")
        for character in value:
            if unicodedata.category(character).startswith("C"):
                raise CredentialError(f"{label} is invalid")

    @staticmethod
    def _is_executable_file(path: str) -> bool:
        try:
            return Path(path).is_file() and os.access(path, os.X_OK)
        except OSError:
            return False


def credential_options_from_environment(
    environment: Mapping[str, str] | None = None,
) -> CredentialOptions:
    """Build explicit credential options from the process environment."""

    values = dict(os.environ if environment is None else environment)
    secret_id = values.get("GITHUB_BWS_SECRET_ID") or values.get(
        "MOC_ENV_BWS_SECRET_ID"
    )
    secret_id_keychain_service = values.get(
        "GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE"
    ) or values.get("GITHUB_TOKEN_KEYCHAIN_SERVICE")
    secret_id_keychain_account = values.get(
        "GITHUB_BWS_SECRET_ID_KEYCHAIN_ACCOUNT"
    ) or values.get("GITHUB_TOKEN_KEYCHAIN_ACCOUNT")
    bws_account = values.get("BWS_ACCESS_TOKEN_KEYCHAIN_ACCOUNT")
    if not secret_id_keychain_account:
        secret_id_keychain_account = values.get("USER") or getpass.getuser()
    if not bws_account:
        bws_account = values.get("USER") or getpass.getuser()

    return CredentialOptions(
        direct_token=values.get("GITHUB_TOKEN"),
        bws_secret_id=secret_id,
        bws_access_token=values.get("BWS_ACCESS_TOKEN"),
        bws_secret_id_keychain_service=secret_id_keychain_service
        or "moc-env-github-token",
        bws_secret_id_keychain_account=secret_id_keychain_account,
        bws_keychain_service=values.get(
            "BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE", "moc-env-bws-access-token"
        ),
        bws_keychain_account=bws_account,
    )


def load_credential_environment_file(
    path: str | Path, base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Load only non-secret credential selectors from an optional dotenv file.

    Values already present in ``base`` win, matching ordinary dotenv behavior.
    Secret-bearing keys are deliberately rejected so a local ``.env`` remains a
    selector file rather than plaintext token storage.
    """

    environment = dict(os.environ if base is None else base)
    env_path = Path(path)
    if not env_path.exists():
        return environment
    if not env_path.is_file():
        raise CredentialError(f"Credential environment file is not a regular file: {env_path}")

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CredentialError(f"Could not read credential environment file: {env_path}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CredentialError(
                f"Invalid credential environment line {line_number}: expected KEY=VALUE"
            )

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise CredentialError(
                f"Invalid credential environment line {line_number}: KEY and VALUE must be nonempty"
            )
        if key in {"GITHUB_TOKEN", "BWS_ACCESS_TOKEN"}:
            raise CredentialError(
                f"Credential environment file must not contain {key}; "
                "export direct tokens or store them in an approved secret manager"
            )
        if key not in CREDENTIAL_ENV_FILE_KEYS:
            raise CredentialError(f"Unsupported credential environment key: {key}")

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if any(unicodedata.category(character).startswith("C") for character in value):
            raise CredentialError(
                f"Invalid credential environment value on line {line_number}"
            )

        environment.setdefault(key, value)

    return environment
