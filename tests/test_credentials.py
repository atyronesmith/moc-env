from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from moc_env_status.credentials import (
    CredentialNotFoundError,
    CredentialError,
    CredentialOptions,
    CredentialResolver,
    credential_options_from_environment,
)


class CredentialResolverTest(unittest.TestCase):
    def test_direct_token_takes_precedence(self) -> None:
        options = CredentialOptions(
            direct_token="direct-token-fixture",
            bws_secret_id="00000000-0000-0000-0000-000000000000",
        )
        resolver = CredentialResolver(
            platform="darwin",
            environment={},
            run=self._fail_if_called,
        )
        self.assertEqual(resolver.resolve(options), "direct-token-fixture")

    def test_bitwarden_secret_uses_access_token_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bws = Path(temporary_directory) / "bws"
            bws.write_text("#!/bin/sh\nexit 0\n")
            bws.chmod(bws.stat().st_mode | stat.S_IXUSR)
            secret_id = "00000000-0000-0000-0000-000000000000"
            calls: list[tuple[list[str], dict[str, str]]] = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append((command, kwargs["env"]))  # type: ignore[arg-type]
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"key": "GITHUB_TOKEN", "value": "github-token-fixture"}
                    ).encode(),
                    stderr=b"",
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory, "GITHUB_TOKEN": "must-not-leak"},
                run=run,
            )
            token = resolver.resolve(
                CredentialOptions(
                    bws_secret_id=secret_id,
                    bws_access_token="machine-token-fixture",
                )
            )

        self.assertEqual(token, "github-token-fixture")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][1:4], ["secret", "get", secret_id])
        self.assertNotIn("GITHUB_TOKEN", calls[0][1])
        self.assertEqual(calls[0][1]["BWS_ACCESS_TOKEN"], "machine-token-fixture")

    def test_bitwarden_machine_token_comes_from_keychain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bws = Path(temporary_directory) / "bws"
            bws.write_text("#!/bin/sh\nexit 0\n")
            bws.chmod(bws.stat().st_mode | stat.S_IXUSR)
            calls: list[tuple[list[str], dict[str, str]]] = []

            def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                calls.append((command, kwargs["env"]))  # type: ignore[arg-type]
                if command[0] == "/usr/bin/security":
                    self.assertEqual(
                        command[1:],
                        [
                            "find-generic-password",
                            "-s",
                            "moc-env-status-bws-access-token",
                            "-a",
                            "fixture-user",
                            "-w",
                        ],
                    )
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"machine-token-fixture\n", stderr=b""
                    )
                self.assertEqual(command[0], str(bws))
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"key": "GITHUB_TOKEN", "value": "github-token-fixture"}
                    ).encode(),
                    stderr=b"",
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory},
                run=run,
            )
            token = resolver.resolve(
                CredentialOptions(
                    bws_secret_id="00000000-0000-0000-0000-000000000000",
                    bws_keychain_account="fixture-user",
                )
            )

        self.assertEqual(token, "github-token-fixture")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("BWS_ACCESS_TOKEN", calls[0][1])
        self.assertEqual(calls[1][1]["BWS_ACCESS_TOKEN"], "machine-token-fixture")

    def test_keychain_supplies_bitwarden_secret_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bws = Path(temporary_directory) / "bws"
            bws.write_text("#!/bin/sh\nexit 0\n")
            bws.chmod(bws.stat().st_mode | stat.S_IXUSR)
            calls: list[list[str]] = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append(command)
                if len(calls) == 1:
                    self.assertEqual(
                        command[1:],
                        [
                            "find-generic-password",
                            "-s",
                            "moc-env-status-github-token",
                            "-a",
                            "fixture-user",
                            "-w",
                        ],
                    )
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=b"00000000-0000-0000-0000-000000000000\n",
                        stderr=b"",
                    )
                if len(calls) == 2:
                    self.assertEqual(
                        command[1:],
                        [
                            "find-generic-password",
                            "-s",
                            "moc-env-status-bws-access-token",
                            "-a",
                            "fixture-user",
                            "-w",
                        ],
                    )
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"machine-token-fixture\n", stderr=b""
                    )
                self.assertEqual(command[0], str(bws))
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {"key": "GITHUB_TOKEN", "value": "github-token-fixture"}
                    ).encode(),
                    stderr=b"",
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory},
                run=run,
            )
            token = resolver.resolve(
                CredentialOptions(
                    bws_secret_id_keychain_account="fixture-user",
                    bws_keychain_account="fixture-user",
                )
            )

        self.assertEqual(token, "github-token-fixture")
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            calls[2][1:4],
            ["secret", "get", "00000000-0000-0000-0000-000000000000"],
        )

    def test_missing_default_keychain_item_is_reported(self) -> None:
        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(command, 44, stdout=b"", stderr=b"")

        resolver = CredentialResolver(
            platform="darwin", environment={"PATH": "/usr/bin:/bin"}, run=run
        )
        with self.assertRaises(CredentialNotFoundError):
            resolver.resolve(
                CredentialOptions(bws_secret_id_keychain_account="fixture-user")
            )

    def test_invalid_keychain_uuid_is_rejected(self) -> None:
        def run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(
                command, 0, stdout=b"not-a-uuid\n", stderr=b""
            )

        resolver = CredentialResolver(
            platform="darwin", environment={"PATH": "/usr/bin:/bin"}, run=run
        )
        with self.assertRaisesRegex(
            CredentialError, "Keychain item must contain a Bitwarden secret UUID"
        ):
            resolver.resolve(
                CredentialOptions(bws_secret_id_keychain_account="fixture-user")
            )

    def test_invalid_secret_uuid_is_rejected(self) -> None:
        resolver = CredentialResolver(
            platform="darwin", environment={}, run=self._fail_if_called
        )
        with self.assertRaisesRegex(CredentialError, "secret UUID"):
            resolver.resolve(CredentialOptions(bws_secret_id="not-a-uuid"))

    def test_environment_options_include_defaults_and_aliases(self) -> None:
        options = credential_options_from_environment(
            {
                "GITHUB_BWS_SECRET_ID": "00000000-0000-0000-0000-000000000000",
                "GITHUB_BWS_SECRET_ID_KEYCHAIN_SERVICE": "uuid-service-fixture",
                "BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE": "bws-service-fixture",
                "USER": "fixture-user",
            }
        )
        self.assertEqual(
            options.bws_secret_id, "00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(
            options.bws_secret_id_keychain_service, "uuid-service-fixture"
        )
        self.assertEqual(options.bws_keychain_service, "bws-service-fixture")
        self.assertEqual(options.bws_secret_id_keychain_account, "fixture-user")
        self.assertEqual(options.bws_keychain_account, "fixture-user")

    @staticmethod
    def _fail_if_called(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(f"credential subprocess unexpectedly called: {command}")


if __name__ == "__main__":
    unittest.main()
