from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from moc_env.credentials import (
    CredentialError,
    CredentialOptions,
    CredentialResolver,
    credential_options_from_environment,
    load_credential_environment_file,
)


class CredentialResolverTest(unittest.TestCase):
    def test_direct_token_precedes_bitwarden_and_gh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

            resolver = CredentialResolver(
                platform="linux",
                environment={},
                run=self._fail_if_called,
                gh_executable=str(gh),
            )
            token = resolver.resolve(
                CredentialOptions(
                    direct_token="direct-token-fixture",
                    bws_secret_id="00000000-0000-0000-0000-000000000000",
                )
            )

        self.assertEqual(token, "direct-token-fixture")

    def test_invalid_direct_token_is_fatal(self) -> None:
        resolver = CredentialResolver(
            platform="linux", environment={}, run=self._fail_if_called
        )
        with self.assertRaisesRegex(CredentialError, "GITHUB_TOKEN is invalid"):
            resolver.resolve(CredentialOptions(direct_token="invalid token"))

    def test_explicit_bitwarden_failure_is_fatal_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=self._fail_if_called,
                gh_executable=str(gh),
            )
            with self.assertRaisesRegex(CredentialError, "secret UUID"):
                resolver.resolve(
                    CredentialOptions(bws_secret_id="not-a-uuid"),
                    explicit_bitwarden=True,
                )

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

    def test_explicit_bitwarden_precedes_gh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bws = Path(temporary_directory) / "bws"
            bws.write_text("#!/bin/sh\nexit 0\n")
            bws.chmod(bws.stat().st_mode | stat.S_IXUSR)
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            calls: list[list[str]] = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append(command)
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
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                gh_executable=str(gh),
            )
            token = resolver.resolve(
                CredentialOptions(
                    bws_secret_id="00000000-0000-0000-0000-000000000000",
                    bws_access_token="machine-token-fixture",
                )
            )

        self.assertEqual(token, "github-token-fixture")
        self.assertEqual(calls, [[str(bws), "secret", "get", "00000000-0000-0000-0000-000000000000"]])

    def test_gh_token_precedes_default_keychain_on_macos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)
            calls: list[list[str]] = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append(command)
                self.assertEqual(command[:3], [str(gh), "auth", "token"])
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"gh-token-fixture\n", stderr=b""
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory},
                run=run,
                keychain_executable=str(security),
                gh_executable=str(gh),
            )
            token = resolver.resolve(CredentialOptions())

        self.assertEqual(token, "gh-token-fixture")
        self.assertEqual(len(calls), 1)

    def test_gh_token_works_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"gh-token-fixture\n", stderr=b""
                )

            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                gh_executable=str(gh),
            )
            token = resolver.resolve(CredentialOptions())

        self.assertEqual(token, "gh-token-fixture")

    def test_nonzero_gh_is_skipped_silently_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                self.assertEqual(command[:3], [str(gh), "auth", "token"])
                return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"not logged in")

            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                gh_executable=str(gh),
            )
            self.assertIsNone(resolver.resolve(CredentialOptions()))

    def test_invalid_gh_output_is_skipped_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"invalid token\n", stderr=b""
                )

            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                gh_executable=str(gh),
            )
            self.assertIsNone(resolver.resolve(CredentialOptions()))

    def test_explicit_bitwarden_machine_token_failure_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                self.assertEqual(command[0], str(security))
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b"00000000-0000-0000-0000-000000000000\n",
                    stderr=b"",
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory},
                run=run,
                keychain_executable=str(security),
                gh_executable=None,
            )
            with self.assertRaisesRegex(
                CredentialError, "BWS_ACCESS_TOKEN is invalid"
            ):
                resolver.resolve(
                    CredentialOptions(bws_access_token="invalid token")
                )

    def test_gh_timeout_is_skipped_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            gh = Path(temporary_directory) / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n")
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                raise subprocess.TimeoutExpired(command, 10)

            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                gh_executable=str(gh),
            )
            self.assertIsNone(resolver.resolve(CredentialOptions()))

    def test_linux_skips_default_keychain_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                raise AssertionError("Keychain lookup unexpectedly attempted on Linux")

            resolver = CredentialResolver(
                platform="linux",
                environment={"PATH": temporary_directory},
                run=run,
                keychain_executable=str(security),
                gh_executable=None,
            )
            self.assertIsNone(resolver.resolve(CredentialOptions()))

    def test_missing_gh_falls_back_to_default_keychain_on_macos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)
            calls: list[list[str]] = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append(command)
                self.assertEqual(command[0], str(security))
                return subprocess.CompletedProcess(command, 44, stdout=b"", stderr=b"")

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": temporary_directory},
                run=run,
                keychain_executable=str(security),
            )
            self.assertIsNone(resolver.resolve(CredentialOptions()))

        self.assertEqual(len(calls), 1)

    def test_bitwarden_machine_token_comes_from_keychain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bws = Path(temporary_directory) / "bws"
            bws.write_text("#!/bin/sh\nexit 0\n")
            bws.chmod(bws.stat().st_mode | stat.S_IXUSR)
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)
            calls: list[tuple[list[str], dict[str, str]]] = []

            def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                calls.append((command, kwargs["env"]))  # type: ignore[arg-type]
                if command[0] == str(security):
                    self.assertEqual(
                        command[1:],
                        [
                            "find-generic-password",
                            "-s",
                            "moc-env-bws-access-token",
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
                keychain_executable=str(security),
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
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)
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
                            "moc-env-github-token",
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
                            "moc-env-bws-access-token",
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
                keychain_executable=str(security),
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

    def test_missing_default_keychain_item_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 44\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.CompletedProcess(command, 44, stdout=b"", stderr=b"")

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": "/usr/bin:/bin"},
                run=run,
                keychain_executable=str(security),
                gh_executable=None,
            )
            self.assertIsNone(
                resolver.resolve(
                    CredentialOptions(bws_secret_id_keychain_account="fixture-user")
                )
            )

    def test_invalid_default_keychain_uuid_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"not-a-uuid\n", stderr=b""
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": "/usr/bin:/bin"},
                run=run,
                keychain_executable=str(security),
                gh_executable=None,
            )
            self.assertIsNone(
                resolver.resolve(
                    CredentialOptions(bws_secret_id_keychain_account="fixture-user")
                )
            )

    def test_explicit_keychain_selector_failure_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            security = Path(temporary_directory) / "security"
            security.write_text("#!/bin/sh\nexit 0\n")
            security.chmod(security.stat().st_mode | stat.S_IXUSR)

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"not-a-uuid\n", stderr=b""
                )

            resolver = CredentialResolver(
                platform="darwin",
                environment={"PATH": "/usr/bin:/bin"},
                run=run,
                keychain_executable=str(security),
                gh_executable=None,
            )
            with self.assertRaisesRegex(
                CredentialError, "Keychain item must contain a Bitwarden secret UUID"
            ):
                resolver.resolve(
                    CredentialOptions(
                        bws_secret_id_keychain_service="explicit-uuid-service"
                    ),
                    explicit_bitwarden=True,
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
                "MOC_ENV_BWS_SECRET_ID": "00000000-0000-0000-0000-000000000000",
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

    def test_credential_environment_file_loads_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "selectors.env"
            env_file.write_text(
                "\n"
                "# selectors only\n"
                "GITHUB_BWS_SECRET_ID='00000000-0000-0000-0000-000000000000'\n"
                'BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE="jira-bws-access-token"\n',
                encoding="utf-8",
            )
            environment = load_credential_environment_file(
                env_file, base={"OTHER_VALUE": "kept"}
            )

        self.assertEqual(
            environment["GITHUB_BWS_SECRET_ID"],
            "00000000-0000-0000-0000-000000000000",
        )
        self.assertEqual(
            environment["BWS_ACCESS_TOKEN_KEYCHAIN_SERVICE"],
            "jira-bws-access-token",
        )
        self.assertEqual(environment["OTHER_VALUE"], "kept")

    def test_environment_file_does_not_override_process_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "selectors.env"
            env_file.write_text(
                "GITHUB_BWS_SECRET_ID=00000000-0000-0000-0000-000000000000\n",
                encoding="utf-8",
            )
            environment = load_credential_environment_file(
                env_file,
                base={
                    "GITHUB_BWS_SECRET_ID": "11111111-1111-1111-1111-111111111111"
                },
            )

        self.assertEqual(
            environment["GITHUB_BWS_SECRET_ID"],
            "11111111-1111-1111-1111-111111111111",
        )

    def test_environment_file_rejects_plaintext_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "selectors.env"
            env_file.write_text(
                "GITHUB_TOKEN=must-not-be-stored-here\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CredentialError, "must not contain GITHUB_TOKEN"
            ):
                load_credential_environment_file(env_file, base={})

    def test_missing_environment_file_is_ignored(self) -> None:
        environment = load_credential_environment_file(
            "/path/does/not/exist", base={"KEEP": "value"}
        )
        self.assertEqual(environment, {"KEEP": "value"})

    @staticmethod
    def _fail_if_called(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(f"credential subprocess unexpectedly called: {command}")


if __name__ == "__main__":
    unittest.main()
