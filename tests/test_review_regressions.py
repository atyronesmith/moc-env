"""Pinned PR evidence and transport-denying offline/portability regressions."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from moc_env import cli, cli_support
from moc_env.checks import StatusChecker
from moc_env.github import GitHubClient
from moc_env.model import Environment
from moc_env.report import _phase_cell, render_markdown, render_text
from moc_env.cross_repo import _feature_chart_values_next_action
from moc_env.report_fields import failing_field_rows, field_rows

from fakes import FullyConfiguredFakeGitHubClient
from test_pr246_report import Pr246ReportClient, FIXTURES, WORKLOAD_PATH


class RealPrClient(Pr246ReportClient):
    def get_file(self, repository, path, ref="main"):
        if repository == "CCI-MOC/oac-infra":
            if path == "infra/inventory/00hosts.yaml":
                text = (FIXTURES / "pr31-73bda33-00hosts.yaml").read_text()
                if self.ref_for(repository) != "pull/31/head":
                    before, workload = text.split("        bu_ist_demo_workload0:", 1)
                    workload = workload.replace("                  resource_class: fc430\n", "")
                    text = before + "        bu_ist_demo_workload0:" + workload
                return text
            if path == "docs/hardware-and-network-configuration.md":
                return "| Node Name | Resource Class |\n|---|---|\n| MOC-R4PAC10U31-S1B | fc430 |\n| MOC-R4PAC10U31-S1C | fc430 |\n"
        if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
            text = (FIXTURES / "pr66-2b4f242-main.tf").read_text()
            if self.ref_for(repository) != "pull/66/head":
                text = re.sub(r"    bu_ist_demo_workload0 = \{.*?\n    \}", "", text, flags=re.S)
            return text
        return super().get_file(repository, path, ref)

    def pulls(self, repository, state="all"):
        number = {"CCI-MOC/oac-apps": 246, "CCI-MOC/oac-infra": 31, "CCI-MOC/moc-keycloak": 66}.get(repository)
        if number:
            yield {"number": number, "state": "open", "title": "bu-ist-demo-infra and bu-ist-demo-workload0", "body": "", "head": {"ref": "test"}}

    def pr_files(self, repository, number):
        yield {"filename": {246: WORKLOAD_PATH, 31: "infra/inventory/00hosts.yaml", 66: "main.tf"}[number], "patch": "+bu-ist-demo-infra"}


class ReviewRegressionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {"MOC_ENV_CACHE_DIR": temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_real_pr_annotations_and_severity(self):
        client = RealPrClient(refs={"CCI-MOC/oac-apps": "pull/246/head"})
        report = StatusChecker(client, tool_version="test").run(Environment("bu-ist-demo", 666)).to_dict()
        checks = {check["id"]: check for check in report["checks"]}
        agent = checks["workload.agent_labels_inputs"]
        self.assertEqual(agent["evidence"]["pr_evaluations"], ["fixed by open PR oac-infra#31"])
        # PR #31 changes the same inventory file used by the hub boot-image
        # check, but does not change that check's relevant boot-image field.
        # File overlap alone must not create a misleading annotation.
        self.assertIn("infra/inventory/00hosts.yaml", [
            item["filename"] for item in client.pr_files("CCI-MOC/oac-infra", 31)
        ])
        self.assertNotIn("pr_evaluations", checks["hub.boot_image"]["evidence"])
        for check in checks.values():
            self.assertNotIn("oac-apps#246", str(check.get("evidence", {}).get("pr_evaluations", [])))
        keycloak = checks["workload.keycloak_oidc_client"]["evidence"]["pr_evaluations"][0]
        for text in ("open PR moc-keycloak#66 touches this but the check still fails there", "openshift_redirect_uri is https://oauth-bu-ist-demo-workload0.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso", "client_secret_name is cluster/bu-ist-demo-workload0/keycloak-oidc", ":443/oauth2callback/mocsso", "cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc"):
            self.assertIn(text, keycloak)
        self.assertNotIn("cluster_name is", keycloak)
        self.assertEqual(client.refs, {"CCI-MOC/oac-apps": "pull/246/head"})
        self.assertFalse(any(ref in {"pull/31/head", "pull/66/head"} for _, ref in client.source_snapshots))
        self.assertTrue(_phase_cell([c for c in checks.values() if c["scope"] == "workload" and c.get("phase") == 6]).startswith("FAIL"))
        self.assertTrue(_phase_cell([c for c in checks.values() if c["scope"] == "hub" and c.get("phase") == 3]).startswith("WARNING"))
        for renderer in (render_text, render_markdown):
            output = renderer(report)
            actions = output.split("NEXT", 1)[1].split("NOT CHECKED", 1)[0] if renderer is render_text else output.split("## Next actions", 1)[1].split("##", 1)[0]
            if renderer is render_text:
                action_lines = actions.splitlines()
                start = next(index for index, line in enumerate(action_lines) if line.startswith("  2."))
                end = next(index for index in range(start + 1, len(action_lines)) if action_lines[index].startswith("  3."))
                agent_action = "\n".join(action_lines[start:end])
            else:
                agent_action = next(line for line in actions.splitlines() if line.startswith("2. **oac-infra**"))
            self.assertIn("resource_class", agent_action)
            self.assertNotIn("mac_addr", agent_action)
            self.assertNotIn("expected present", " ".join(actions.split()))
        details = render_text(report, details=True)
        self.assertIn("FAIL: Workload API address network", details)
        self.assertIn("WARNING: Workload GPU feature support", details)

    def test_mixed_dns_records_only_report_invalid_hostnames(self):
        check = {
            "id": "workload.dns_base_domain",
            "expected": {"domains": ["hcp.bu-ist-demo.int.massopen.cloud"]},
            "actual": [
                "api.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud",
                "s3.bu-ist-demo-workload0.hcp.oac.int.massopen.cloud",
            ],
            "missing": {
                "hostnames": [
                    "s3.bu-ist-demo-workload0.hcp.oac.int.massopen.cloud"
                ]
            },
        }
        rows = failing_field_rows(check)
        self.assertEqual(
            rows,
            [[
                "dns.records[1].hostname",
                "under hcp.bu-ist-demo.int.massopen.cloud",
                "s3.bu-ist-demo-workload0.hcp.oac.int.massopen.cloud",
            ]],
        )
        self.assertNotIn("api.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud", str(rows))

    def test_ref_wording_footer_and_no_redundant_details_hint(self):
        report = StatusChecker(RealPrClient(refs={"CCI-MOC/oac-apps": "pull/246/head"}), include_prs=False,
                               command=["status", "bu-ist-demo", "--ref", "oac-apps=pull/246/head", "--scope", "workload"], tool_version="test").run(Environment("bu-ist-demo", 666)).to_dict()
        text = render_text(report, details=True)
        self.assertIn("in pull/246/head under", text)
        self.assertNotIn("All expected files for", text)
        self.assertNotIn("Details:", text)
        self.assertIn("--ref oac-apps=pull/246/head --scope workload --format markdown", text)

    def test_offline_status_and_diff_forbid_all_http_and_credentials(self):
        fixture = FullyConfiguredFakeGitHubClient()

        def response(request, **kwargs):
            url = urlsplit(request.full_url)
            parts = url.path.strip("/").split("/")
            if url.netloc == "raw.githubusercontent.com":
                body = fixture.get_file("/".join(parts[:2]), "/".join(parts[3:]))
            elif url.path == "/rate_limit":
                body = json.dumps({"resources": {"core": {"remaining": 5000}}})
            else:
                repository = "/".join(parts[1:3])
                if parts[3] == "commits":
                    data = {"sha": fixture.SOURCE_SHAS[repository]}
                elif parts[3] == "git":
                    data = {"tree": [{**value, "type": "blob"} for value in fixture.get_tree(repository).values()]}
                else:
                    data = fixture.get_json(url.path)
                body = json.dumps(data)
            stream = io.BytesIO(body.encode())
            stream.headers = {"ETag": '"test"'} if url.path != "/rate_limit" else {}
            stream.status = 200
            return stream

        def run(arguments):
            # This fixture exercises the original per-file response cache.
            arguments = [*arguments, "--backend", "api"]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(arguments)
            self.assertEqual(code, 0, stderr.getvalue())
            return stdout.getvalue(), stderr.getvalue()

        with patch.object(cli, "_resolve_github_token", return_value=None), patch("moc_env.github.urlopen", side_effect=response):
            online, _ = run(["status", "bu-ist-demo", "--no-auth"])
            run(["diff", "bu-ist-demo", "bu-ist-demo", "--no-auth"])
        with (patch.object(cli_support, "load_credential_environment_file", side_effect=AssertionError("offline must not read .env")),
              patch.object(cli_support, "CredentialResolver", side_effect=AssertionError("offline credentials forbidden")),
              patch("moc_env.credentials.subprocess.run", side_effect=AssertionError("offline must not invoke gh or Keychain")),
              patch("moc_env.github.urlopen", side_effect=AssertionError("offline HTTP forbidden")) as http):
            offline, accounting = run(["status", "bu-ist-demo", "--no-auth", "--offline"])
            self.assertEqual(
                next(line for line in online.splitlines() if line.startswith("RESULT:")),
                next(line for line in offline.splitlines() if line.startswith("RESULT:")),
            )
            self.assertIn("GitHub API: 0 requests, 0 counted against quota", accounting)
            diff, _ = run(["diff", "bu-ist-demo", "bu-ist-demo", "--no-auth", "--offline"])
            for repository in fixture.SOURCE_SHAS:
                short = repository.removeprefix("CCI-MOC/")
                self.assertIn(f"{short}: from cache, fetched ", offline)
                self.assertIn(f"{short}: from cache, fetched ", diff)
            http.assert_not_called()

    def test_empty_cache_offline_diff_fails_cleanly_without_transport(self):
        """An offline cache miss is a user error, not an uncaught traceback."""

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(
                cli_support,
                "load_credential_environment_file",
                side_effect=AssertionError("offline must not read .env"),
            ),
            patch.object(
                cli_support,
                "CredentialResolver",
                side_effect=AssertionError("offline credentials forbidden"),
            ),
            patch(
                "moc_env.credentials.subprocess.run",
                side_effect=AssertionError("offline must not invoke gh or Keychain"),
            ),
            patch(
                "moc_env.github.urlopen",
                side_effect=AssertionError("offline HTTP forbidden"),
            ) as http,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(
                ["diff", "bu-ist-demo", "bu-ist-demo", "--no-auth", "--offline"]
            )

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertIn("No cached GitHub response is available", stderr.getvalue())
        self.assertIn("GitHub API: 0 requests, 0 counted against quota", stderr.getvalue())
        http.assert_not_called()

    def test_source_tree_version_does_not_consult_package_metadata(self):
        with (
            patch("importlib.metadata.version", side_effect=AssertionError("installed package metadata forbidden")),
            patch("importlib.metadata.distribution", side_effect=AssertionError("installed package metadata forbidden")),
        ):
            checker = StatusChecker(FullyConfiguredFakeGitHubClient(), include_prs=False)
            self.assertEqual(checker.run(Environment("bu-ist-demo", 666)).metadata.tool_version, "0.1.0")

    def test_warm_conditional_requests_are_free_and_accounted(self):
        url = "https://api.github.com/example"
        body = io.BytesIO(b'{"value":1}')
        body.headers = {"ETag": '"fixture"'}
        body.status = 200
        cold = GitHubClient()
        with patch("moc_env.github.urlopen", return_value=body):
            self.assertEqual(cold.get_json(url), {"value": 1})
        self.assertEqual((cold.requests_made, cold.api_calls_used, cold.cache_hits), (1, 1, 0))
        warm = GitHubClient()
        with patch("moc_env.github.urlopen", side_effect=HTTPError(url, 304, "Not modified", {}, io.BytesIO())):
            self.assertEqual(warm.get_json(url), {"value": 1})
        self.assertEqual((warm.requests_made, warm.api_calls_used, warm.cache_hits), (1, 0, 1))

    def test_feature_chart_values_next_action_lists_only_unmet_values(self) -> None:
        evidence = {
            "chart_count": 27,
            "unmet_required_values": {"object-storage-proxy": ["backend.address"]},
            "missing_overlays": [],
            "orphan_values_files": [],
        }
        check = {"id": "workload.feature_chart_values", "evidence": evidence}

        self.assertEqual(
            failing_field_rows(check),
            [["unmet required values", "none", {"object-storage-proxy": ["backend.address"]}]],
        )
        self.assertEqual(
            _feature_chart_values_next_action(
                evidence, "bu-ist-demo-infra", "bu-ist-demo-workload0"
            ),
            "Set the missing required chart values in "
            "values/bu-ist-demo-infra/bu-ist-demo-workload0/object-storage-proxy.yaml.",
        )

    def test_feature_chart_values_next_action_joins_all_three_clauses(self) -> None:
        evidence = {
            "chart_count": 27,
            "unmet_required_values": {"chart-a": ["value"]},
            "missing_overlays": ["kustomize/pure-cosi/overlays/workload0"],
            "orphan_values_files": ["orphan"],
        }
        check = {"id": "workload.feature_chart_values", "evidence": evidence}

        rows = failing_field_rows(check)
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row[0] for row in rows],
            [
                "unmet required values",
                "missing kustomize overlays",
                "orphan values files",
            ],
        )
        self.assertEqual(
            _feature_chart_values_next_action(evidence, "hub", "workload0"),
            "Set the missing required chart values in values/hub/workload0/chart-a.yaml, "
            "add the kustomize overlay and remove the values files for charts the "
            "cluster does not receive.",
        )

    def test_feature_chart_values_next_action_with_only_orphans(self) -> None:
        evidence = {
            "chart_count": 27,
            "unmet_required_values": {},
            "missing_overlays": [],
            "orphan_values_files": ["orphan"],
        }
        check = {"id": "workload.feature_chart_values", "evidence": evidence}

        self.assertEqual(
            failing_field_rows(check),
            [["orphan values files", "none", ["orphan"]]],
        )
        self.assertEqual(
            _feature_chart_values_next_action(evidence, "hub", "workload0"),
            "Remove the values files for charts the cluster does not receive.",
        )

    def test_feature_placements_failure_names_the_missing_hub_label(self) -> None:
        evidence = {
            "matched_placements": ["all-managed-clusters"],
            "unused_labels": [],
            "missing_on_hub": {"massopen.cloud/feature-gpu": ["oac-dev-infra:gpu-clusters"]},
        }
        check = {"id": "workload.feature_placements", "evidence": evidence}

        self.assertEqual(
            field_rows(check)[2],
            [
                "labels with no placement on this hub",
                "none",
                "massopen.cloud/feature-gpu (defined on: oac-dev-infra:gpu-clusters)",
            ],
        )
        self.assertEqual(
            failing_field_rows(check),
            [[
                "labels with no placement on this hub",
                "none",
                "massopen.cloud/feature-gpu (defined on: oac-dev-infra:gpu-clusters)",
            ]],
        )

    def test_default_rule_drops_none_against_an_empty_list(self) -> None:
        dropped = {
            "id": "example.check",
            "expected": {"field": "none"},
            "actual": {"field": []},
        }
        kept = {
            "id": "example.check",
            "expected": {"field": "none"},
            "actual": {"field": ["x"]},
        }

        self.assertEqual(failing_field_rows(dropped), [])
        self.assertEqual(
            failing_field_rows(kept), [["field", "none", ["x"]]]
        )

    def test_default_rule_keeps_scalar_type_mismatch(self) -> None:
        mismatch = {
            "id": "example.check",
            "expected": {"port": 443},
            "actual": {"port": "443"},
        }

        self.assertEqual(failing_field_rows(mismatch), [["port", 443, "443"]])


if __name__ == "__main__":
    unittest.main()
