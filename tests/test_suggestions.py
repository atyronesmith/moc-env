"""Commit-pinned, read-only Terraform suggestion acceptance tests."""

from __future__ import annotations

from pathlib import Path
import textwrap
import unittest
from unittest.mock import patch

from moc_env.checks import StatusChecker
from moc_env.model import Environment
from moc_env.report import render_json, render_markdown, render_text
from moc_env.suggestions import SUPPORTED, apply_suggestion, entries

from test_review_regressions import RealPrClient


FIXTURES = Path(__file__).parent / "fixtures"
AWS = "CCI-MOC/moc-aws"
KEYCLOAK = "CCI-MOC/moc-keycloak"


class PinnedClient(RealPrClient):
    SOURCE_SHAS = {
        **RealPrClient.SOURCE_SHAS,
        AWS: "574a840db689350caf25b62266bb5f5d04f3476b",
        KEYCLOAK: "d2da351c3abe7926324443f2df0ffdf41e8db47f",
    }

    def __init__(self):
        super().__init__()
        self.overrides = {}

    def get_file(self, repository, path, ref="main"):
        if (repository, path) in self.overrides:
            return self.overrides[repository, path]
        if repository == AWS:
            return (FIXTURES / f"moc-aws-574a840-{path}").read_text()
        if repository == KEYCLOAK and self.ref_for(repository) == "main":
            return (FIXTURES / "moc-keycloak-d2da351-main.tf").read_text()
        return super().get_file(repository, path, ref)


def code(text):
    return textwrap.indent(textwrap.dedent(text).strip(), "    ")


class SuggestionTest(unittest.TestCase):
    def report(self, client=None, include_prs=False):
        return StatusChecker(client or PinnedClient(), include_prs=include_prs).run(
            Environment("bu-ist-demo", 666)
        )

    def verify(self, check_id, expected_code, after_line, reference, location):
        client = PinnedClient()
        report = self.report(client)
        check = next(item for item in report.checks if item.id == check_id)
        suggestion = check.suggestion
        self.assertIsNotNone(suggestion, check.suggestion_skipped_reason)
        self.assertEqual(suggestion["code"], expected_code)
        self.assertEqual(suggestion["after_line"], after_line)
        self.assertEqual(suggestion["reference"], reference)
        self.assertEqual(suggestion["location"], location)
        self.assertEqual(set(suggestion), {"repository", "path", "commit", "after_line", "location", "reference", "code"})
        original = client.get_file(check.repository, check.path)
        updated = apply_suggestion(original, suggestion)
        # Re-run the identical ordinary checker, not a suggestion-specific predicate.
        client.overrides[check.repository, check.path] = updated
        verified = next(item for item in self.report(client).checks if item.id == check_id)
        self.assertEqual(verified.state, "declared_in_main")
        # No HCL parser is a dependency; deliberately do not add one.
        self.assertEqual(original, PinnedClient().get_file(check.repository, check.path))
        self.assertNotIn("suggestion", verified.to_dict())
        self.assertEqual(suggestion["commit"], next(
            source.sha for source in report.metadata.sources if source.repository == check.repository
        ))

    def test_hosted_secret_prefix(self):
        self.verify("hub.moc_aws_hosted_secret_prefix", textwrap.indent(textwrap.dedent("""
            # HyperShift's kubeconfig and etcd encryption key for each hosted cluster.
            eso_writable_secret_prefixes = [
              "cluster/bu-ist-demo-infra/hostedcluster/",
            ]
        """).strip(), "      "), 195, "nist_dev_infra", "inside the bu_ist_demo_infra block, after line 195")

    def test_aws_oidc_entry(self):
        self.verify("workload.moc_aws_oidc_cluster", code("""
            bu_ist_demo_workload0 = merge(local.openshift_oidc_cluster_defaults, {
              cluster_name            = "bu-ist-demo-workload0"
              oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
              cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_bu_ist_demo_workload0"].policy_arn
            })
        """), 196, "oac_prod_workload0", "after the bu_ist_demo_infra block, line 196")

    def test_cert_manager_policy(self):
        self.verify("workload.moc_aws_cert_manager_policy", code("""
            "cert_manager_policy_bu_ist_demo_workload0" = {
              zone_name          = "hcp.bu-ist-demo.int.massopen.cloud",
              cluster_subdomain  = "bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud"
              policy_name        = "cert-manager-bu-ist-demo-workload0"
              policy_description = "modify records in hcp.bu-ist-demo.int.massopen.cloud for dns01 challenges"
            }
        """), 146, "cert_manager_policy_oac_prod_workload0", "after the cert_manager_policy_bu_ist_demo_infra block, line 146")

    def test_keycloak_entry(self):
        self.verify("workload.keycloak_oidc_client", code("""
            bu_ist_demo_workload0 = {
              cluster_name           = "bu-ist-demo-workload0"
              openshift_redirect_uri = "https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso"
              client_secret_name     = "cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc"
              keycloak_client_uuid   = "bu-ist-demo-workload0"
            }
        """), 76, "oac_prod_workload0", "after the bu_ist_demo_infra block, line 76")

    def test_deliberately_wrong_substitution_is_suppressed(self):
        from moc_env.suggestions import _candidate
        def wrong(text, check, environment):
            candidate = _candidate(text, check, environment)
            candidate["code"] = candidate["code"].replace("bu-ist-demo", "wrong-environment")
            return candidate
        with patch("moc_env.suggestions._candidate", side_effect=wrong):
            report = self.report()
        for check in report.checks:
            if check.id in SUPPORTED:
                self.assertIsNone(check.suggestion)
                self.assertEqual(check.suggestion_skipped_reason, "no suggestion: generated code did not satisfy the check")
                self.assertIsNotNone(check.next_action)
                self.assertIn(check.suggestion_skipped_reason, render_markdown(report.to_dict()))

    def test_unknown_reference_field_suppresses_suggestion(self):
        client = PinnedClient()
        client.overrides[AWS, "main.tf"] = client.get_file(AWS, "main.tf").replace(
            'cluster_name            = "oac-prod-workload0"',
            'cluster_name            = "oac-prod-workload0"\n      tenant_id = "unknown-tenant"'
        )
        check = next(item for item in self.report(client).checks if item.id == "workload.moc_aws_oidc_cluster")
        self.assertIsNone(check.suggestion)
        self.assertEqual(check.suggestion_skipped_reason, "no suggestion: tenant_id cannot be derived")
        self.assertIn('"suggestion": null', render_json(self.report(client).to_dict()))

    def test_missing_domain_is_not_guessed(self):
        client = PinnedClient()
        path = "hosted-clusters/bu-ist-demo-infra/values.yaml"
        client.overrides["CCI-MOC/oac-apps", path] = "baseDomain: int.massopen.cloud\n"
        check = next(item for item in self.report(client).checks if item.id == "workload.moc_aws_cert_manager_policy")
        self.assertIsNone(check.suggestion)
        self.assertEqual(check.suggestion_skipped_reason, "no suggestion: zone_name cannot be derived")

    def test_reference_fallback_and_map_local_insertion(self):
        client = PinnedClient()
        original = client.get_file(AWS, "main.tf")
        for key in ("oac_prod_workload0", "bu_ist_demo_infra"):
            entry = next(item for item in entries(original, "openshift_oidc_clusters") if item.key == key)
            lines = original.splitlines(keepends=True)
            del lines[entry.start:entry.end]
            original = "".join(lines)
        client.overrides[AWS, "main.tf"] = original
        check = next(item for item in self.report(client).checks if item.id == "workload.moc_aws_oidc_cluster")
        self.assertIsNotNone(check.suggestion, check.suggestion_skipped_reason)
        self.assertEqual(check.suggestion["reference"], "oac_dev_workload0")
        self.assertIn("after the moc_infra block", check.suggestion["location"])

    def test_output_modes_and_commit_anchors(self):
        report = self.report().to_dict()
        terse = render_text(report)
        verbose = render_text(report, details=True)
        markdown = render_markdown(report)
        self.assertEqual(terse.count("suggested code available: re-run with --details"), 4)
        self.assertNotIn("Suggested code (", terse)
        self.assertEqual(verbose.count("Suggested code ("), 4)
        self.assertEqual(markdown.count("```hcl"), 4)
        self.assertNotIn("terraform plan run):\n```", markdown)
        for check in report["checks"]:
            if check.get("suggestion"):
                suggestion = check["suggestion"]
                url = f"https://github.com/{suggestion['repository']}/blob/{suggestion['commit']}/{suggestion['path']}#L{suggestion['after_line']}"
                self.assertIn(url, markdown)
                self.assertIn(url, verbose)
            elif check["id"] not in SUPPORTED:
                self.assertNotIn("suggestion", check)

    def test_open_pr_is_presented_as_a_correction(self):
        report = self.report(include_prs=True).to_dict()
        check = next(item for item in report["checks"] if item["id"] == "workload.keycloak_oidc_client")
        self.assertIn("corrects open PR moc-keycloak#66", check["suggestion"]["location"])
        for output in (render_markdown(report), render_text(report, details=True)):
            self.assertIn("corrects open PR moc-keycloak#66", output)
            self.assertIn(":443/oauth2callback/mocsso", output)

    def test_correction_copies_pr_comments_and_does_not_change_baseline_sources(self):
        class CommentedPrClient(PinnedClient):
            def get_file(self, repository, path, ref="main"):
                text = super().get_file(repository, path, ref)
                if repository == KEYCLOAK and self.ref_for(repository) == "pull/66/head":
                    return text.replace('    bu_ist_demo_workload0 = {',
                                        '    # PR-specific context retained.\n    bu_ist_demo_workload0 = {')
                return text
        client = CommentedPrClient()
        report = self.report(client, include_prs=True)
        check = next(item for item in report.checks if item.id == "workload.keycloak_oidc_client")
        self.assertIsNotNone(check.suggestion, check.suggestion_skipped_reason)
        self.assertIn("# PR-specific context retained.", check.suggestion["code"])
        self.assertIn("bu_ist_demo_workload0 in open PR moc-keycloak#66", check.suggestion["reference"])
        self.assertEqual(client.refs, {})
        self.assertFalse(any(ref.startswith("pull/") for _, ref in client.source_snapshots))

    def test_existing_attribute_does_not_generate_duplicate_hcl(self):
        client = PinnedClient()
        client.overrides[AWS, "main.tf"] = client.get_file(AWS, "main.tf").replace(
            '      cluster_name            = "bu-ist-demo-infra"',
            '      cluster_name            = "bu-ist-demo-infra"\n      eso_writable_secret_prefixes = []'
        )
        check = next(item for item in self.report(client).checks if item.id == "hub.moc_aws_hosted_secret_prefix")
        self.assertIsNone(check.suggestion)
        self.assertIn("manual edit", check.suggestion_skipped_reason)

    def test_pr_correction_with_real_client_cached_tree_and_restored_sources(self):
        from moc_env.github import GitHubClient
        from moc_env.suggestions import _pr_correction
        client = GitHubClient()
        sha = "2b4f242" + "0" * 33
        ref = "pull/66/head"
        client._trees[KEYCLOAK, ref] = {"main.tf": {"path": "main.tf"}}
        client._responses[f"https://api.github.com/repos/{KEYCLOAK}/commits/{ref}"] = ({"sha": sha}, None)
        client._raw_responses[f"https://raw.githubusercontent.com/{KEYCLOAK}/{sha}/main.tf"] = (
            FIXTURES / "pr66-2b4f242-main.tf"
        ).read_text()
        check = next(item for item in self.report(include_prs=True).checks if item.id == "workload.keycloak_oidc_client")
        with patch.object(GitHubClient, "_request", side_effect=AssertionError("unexpected transport")):
            corrected = _pr_correction(client, check, check.suggestion.copy())
        self.assertIn(":443/oauth2callback/mocsso", corrected)
        self.assertEqual(client.source_snapshots, {})
        self.assertEqual(client.refs, {})

    def test_existing_key_does_not_generate_duplicate_hcl(self):
        client = PinnedClient()
        client.overrides[AWS, "main.tf"] = client.get_file(AWS, "main.tf").replace(
            '    oac_dev_workload0 = merge', '    bu_ist_demo_workload0 = merge'
        )
        check = next(item for item in self.report(client).checks if item.id == "workload.moc_aws_oidc_cluster")
        self.assertIsNone(check.suggestion)
        self.assertIn("manual edit", check.suggestion_skipped_reason)

    def test_gap_free_recording_has_no_suggestions(self):
        import json
        report = json.loads((FIXTURES / "oac-prod-full-status.json").read_text())
        self.assertEqual(report["summary"]["severity_counts"], {"info": len(report["checks"])})
        self.assertNotIn("unknown", report["summary"]["state_counts"])
        for output in (render_markdown(report), render_text(report, details=True)):
            self.assertNotIn("Suggested code", output)
            self.assertNotIn("suggested code available", output)
