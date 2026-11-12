from __future__ import annotations

import copy
import io
import contextlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from moc_env import cli
from moc_env.export import build_infra_export
from moc_env.model import Environment
from moc_env.observed import read_infra_observation
from moc_env.validate import (
    load_validation_result,
    validate_infra_cluster,
)

from fakes import FakeGitHubClient


class ValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = Environment(name="bu-ist-demo", issue_number=666)
        observation = read_infra_observation(FakeGitHubClient(), environment)
        self.document = build_infra_export(environment, observation)

    def test_valid_exported_document(self) -> None:
        result = validate_infra_cluster(self.document)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_known_working_oac_prod_extraction_validates(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "oac-prod-infra.yaml"
        result = load_validation_result(fixture)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_invalid_network_values_and_naming(self) -> None:
        document = copy.deepcopy(self.document)
        document["metadata"]["name"]["value"] = "wrong-infra"
        fields = document["spec"]["variables"]["fields"]
        fields["machine_network"]["value"] = "10.20.26.0/33"
        fields["api_ip"]["value"] = "not-an-ip"
        fields["base_domain"]["value"] = "invalid_domain"
        document["spec"]["domain"]["value"] = "wrong.example.test"

        result = validate_infra_cluster(document)
        self.assertFalse(result.valid)
        self.assertIn(
            "metadata: infra-cluster name must be ENVIRONMENT-infra; "
            "expected bu-ist-demo-infra, got wrong-infra",
            result.errors,
        )
        self.assertIn(
            "spec.variables.fields.machine_network.value: invalid CIDR",
            result.errors,
        )
        self.assertIn(
            "spec.variables.fields.api_ip.value: invalid IP address",
            result.errors,
        )
        self.assertIn(
            "spec.variables.fields.base_domain.value: invalid domain",
            result.errors,
        )
        self.assertIn(
            "spec.domain.value: expected 'bu-ist-demo.invalid_domain', "
            "got 'wrong.example.test'",
            result.errors,
        )

    def test_missing_required_variable_field(self) -> None:
        document = copy.deepcopy(self.document)
        del document["spec"]["variables"]["fields"]["dns_ip"]

        result = validate_infra_cluster(document)
        self.assertFalse(result.valid)
        self.assertIn(
            "spec.variables.fields.dns_ip: missing required field",
            result.errors,
        )

    def test_unsupported_required_value_is_invalid(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["confidence"] = "unsupported"

        result = validate_infra_cluster(document)
        self.assertFalse(result.valid)
        self.assertIn(
            "spec.variables.fields.api_ip: unsupported values cannot be "
            "reviewed desired state",
            result.errors,
        )

    def test_unknown_field_is_warning_and_secret_field_is_error(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["extra"] = {"value": "unexpected"}
        document["metadata"]["clientSecretName"] = {
            "value": "cluster/bu-ist-demo-infra/keycloak-oidc",
        }

        result = validate_infra_cluster(document)
        self.assertFalse(result.valid)
        self.assertIn(
            "metadata.clientSecretName: secret-like fields are not allowed",
            result.errors,
        )
        self.assertIn(
            "spec.extra: unknown field (warning)",
            result.warnings,
        )

    def test_duplicate_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "duplicate.yaml"
            path.write_text(
                """
apiVersion: moc-env/v1alpha1
kind: InfraCluster
schemaVersion: "1"
metadata:
  name:
    value: bu-ist-demo-infra
  name:
    value: duplicate-infra
""",
                encoding="utf-8",
            )
            result = load_validation_result(path)

        self.assertFalse(result.valid)
        self.assertTrue(any("found duplicate key" in error for error in result.errors))

    def test_cli_validates_exported_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "infra.yaml"
            path.write_text(yaml.safe_dump(self.document), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main(["validate", str(path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Desired-state validation: VALID", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_returns_nonzero_and_json_for_invalid_document(self) -> None:
        document = copy.deepcopy(self.document)
        document["spec"]["variables"]["fields"]["api_ip"]["value"] = "not-an-ip"
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "infra.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = cli.main(["validate", str(path), "--format", "json"])

        self.assertEqual(exit_code, 2)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["valid"])
        self.assertIn(
            "spec.variables.fields.api_ip.value: invalid IP address",
            result["errors"],
        )
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
