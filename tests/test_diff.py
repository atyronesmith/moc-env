from __future__ import annotations

import unittest

from moc_env.diff_observed import hosted_dns_facts
from moc_env.github import GitHubError
from moc_env.report import build_environment_diff, render_diff_markdown, render_diff_text


def report(name: str, files: tuple[str, ...] = ("hcp-config.yaml",)) -> dict:
    hub = name + "-infra"
    workload = name + "-workload0"
    return {
        "environment": {"name": name, "infra_cluster": hub, "workload_clusters": [workload]},
        "checks": [
            {
                "id": "hub.component_values", "scope": "hub", "state": "declared_in_main",
                "evidence": {"paths": [f"values/{hub}/{file}" for file in files]},
            },
            {
                "id": "hub.hosted_cluster_defaults", "scope": "hub", "state": "declared_in_main",
                "evidence": {"values": {
                    "baseDomain": f"hcp.{name}.example.org",
                    "hcpExternalDomain": f"hcp.{name}.example.org",
                    "hcpInternalDomain": f"hcp-int.{name}.example.org",
                }},
            },
            {
                "id": "workload.component_values", "scope": "workload", "state": "declared_in_main",
                "path": f"values/{hub}/{workload}",
                "evidence": {"paths": [f"values/{hub}/{workload}/hcp-config.yaml"]},
            },
        ],
    }


class DnsClient:
    def __init__(self, files: dict[tuple[str, str], str]):
        self.files = files

    def get_tree(self, repository):
        return {path: {} for repo, path in self.files if repo == repository}

    def get_file(self, repository, path):
        return self.files[repository, path]


class EnvironmentDiffTest(unittest.TestCase):
    def test_markdown_explains_comparison_and_identifies_each_source_ref(self):
        a, b = report("oac-prod"), report("bu-ist-demo")
        for item, ref, sha in ((a, "main", "a" * 40), (b, "pull/246/head", "b" * 40)):
            item["metadata"] = {"generated_at": "2026-11-17T19:00:00Z", "sources": [
                {"repository": "CCI-MOC/oac-apps", "ref": ref, "sha": sha},
            ]}
        a["checks"].append({"id": "hub.extra", "check": "Hub reference-only prerequisite",
                            "scope": "hub", "state": "declared_in_main"})
        diff = build_environment_diff(a, b)
        rendered = render_diff_markdown(diff)
        self.assertIn("not a live cluster health check", rendered)
        self.assertIn("Differences are not automatically defects", rendered)
        self.assertIn("Hub reference-only prerequisite", rendered)
        self.assertIn("Compared source snapshots", rendered)
        self.assertIn("`oac-prod` | `CCI-MOC/oac-apps` | `main`", rendered)
        self.assertIn("`bu-ist-demo` | `CCI-MOC/oac-apps` | `pull/246/head`", rendered)
        self.assertIn("Generated 2026-11-17 19:00 UTC", rendered)
        self.assertEqual(diff["comparison_sources"]["a"][0]["ref"], "main")
        self.assertEqual(diff["comparison_sources"]["b"][0]["ref"], "pull/246/head")

    def test_environment_names_do_not_create_file_differences(self):
        diff = build_environment_diff(report("bu-ist-demo"), report("oac-prod"))
        for scope in diff["scopes"]:
            self.assertEqual(scope["files_only_in_a"], [])
            self.assertEqual(scope["files_only_in_b"], [])

    def test_only_genuinely_different_paths_remain_one_per_line(self):
        diff = build_environment_diff(
            report("bu-ist-demo", ("hcp-config.yaml", "one.yaml", "two.yaml")),
            report("oac-prod"),
        )
        self.assertEqual(diff["scopes"][0]["files_only_in_a"], ["values/<hub>/one.yaml", "values/<hub>/two.yaml"])
        text = render_diff_text(diff)
        self.assertIn("    values/<hub>/one.yaml\n    values/<hub>/two.yaml\n", text)
        markdown = render_diff_markdown(diff)
        self.assertIn("- `values/<hub>/one.yaml`\n- `values/<hub>/two.yaml`\n", markdown)

    def test_similar_name_substrings_are_not_rewritten(self):
        diff = build_environment_diff(
            report("bu-ist-demo", ("bu-ist-demo-infra-extra.yaml",)),
            report("oac-prod", ("oac-prod-infra-extra.yaml",)),
        )
        self.assertEqual(diff["scopes"][0]["files_only_in_a"], ["values/<hub>/bu-ist-demo-infra-extra.yaml"])

    def test_values_never_use_python_container_reprs(self):
        a, b = report("bu-ist-demo"), report("oac-prod")
        for target, count in ((a, 3), (b, 4)):
            target["checks"].append({
                "id": "workload.agent_labels_inputs", "scope": "workload", "state": "declared_in_main",
                "path": f"values/{target['environment']['infra_cluster']}/{target['environment']['workload_clusters'][0]}",
                "evidence": {"agent_label_hosts": [{"bm_management": "bmc"}] * count + [{"bm_management": "openstack"}] * 7},
            })
        diff = build_environment_diff(a, b)
        for rendered in (render_diff_text(diff), render_diff_markdown(diff)):
            self.assertIn("bmc 3, openstack 7", rendered)
            self.assertNotIn("{'bmc'", rendered)

    def test_dns_facts_are_attached_to_hub_only(self):
        a, b = report("bu-ist-demo"), report("oac-prod")
        a["diff_facts"] = {"hosted_cluster_zone_delegation": "moc-aws hosted-zones.tf", "hosted_cluster_wildcard_records": "not found in any repository"}
        b["diff_facts"] = {"hosted_cluster_zone_delegation": "moc-dns zonefile", "hosted_cluster_wildcard_records": "moc-aws hosted-zones.tf"}
        diff = build_environment_diff(a, b)
        self.assertEqual(diff["scopes"][0]["structural_facts"]["a"], a["diff_facts"])
        self.assertEqual(diff["scopes"][1]["structural_facts"]["a"], {})


class HostedDnsFactsTest(unittest.TestCase):
    def test_zonefile_delegation_and_terraform_wildcards(self):
        files = {
            ("CCI-MOC/moc-dns", "zonefiles/example.org.zone"): "hcp.oac-prod.example.org. 300 IN NS ns1.example.net.\nhcp-int.oac-prod.example.org. 300 IN NS ns1.example.net.\n",
            ("CCI-MOC/moc-aws", "hosted-zones.tf"): '''resource "aws_route53_record" "external" {
    name = "*.hcp.oac-prod.example.org"
    type = "A"
}
resource "aws_route53_record" "internal" {
    name = "*.hcp-int.oac-prod.example.org"
    type = "A"
}
''',
        }
        facts = hosted_dns_facts(DnsClient(files), report("oac-prod"))
        self.assertEqual(facts["hosted_cluster_zone_delegation"], "moc-dns zonefile")
        self.assertEqual(facts["hosted_cluster_wildcard_records"], "moc-aws hosted-zones.tf")

    def test_bu_delegation_without_wildcards_is_not_mistaken_for_records(self):
        text = '''locals {
    hosted_zones = { "hcp.bu-ist-demo.example.org" = "zone" }
}
resource "aws_route53_record" "bu_delegation" {
    for_each = toset(["hcp.bu-ist-demo.example.org", "hcp-int.bu-ist-demo.example.org"])
    name = each.value
    type = "NS"
}
# name = "*.hcp.bu-ist-demo.example.org"
'''
        facts = hosted_dns_facts(DnsClient({("CCI-MOC/moc-aws", "hosted-zones.tf"): text}), report("bu-ist-demo"))
        self.assertEqual(facts["hosted_cluster_zone_delegation"], "moc-aws hosted-zones.tf")
        self.assertEqual(facts["hosted_cluster_wildcard_records"], "not found in any repository")

    def test_hosted_zone_creation_alone_is_not_delegation(self):
        text = '''locals {
    hosted_zones = { "hcp.bu-ist-demo.example.org" = "zone" }
}
'''
        facts = hosted_dns_facts(DnsClient({("CCI-MOC/moc-aws", "hosted-zones.tf"): text}), report("bu-ist-demo"))
        self.assertEqual(facts["hosted_cluster_zone_delegation"], "not found in any repository")

    def test_partial_wildcard_records_identify_missing_domain(self):
        text = '''resource "aws_route53_record" "external" {
    name = "*.hcp.bu-ist-demo.example.org"
    type = "A"
}
'''
        facts = hosted_dns_facts(DnsClient({("CCI-MOC/moc-aws", "hosted-zones.tf"): text}), report("bu-ist-demo"))
        self.assertIn("hcp-int.bu-ist-demo.example.org: not found in any repository", facts["hosted_cluster_wildcard_records"])

    def test_unreadable_sources_are_not_reported_as_absent(self):
        class UnavailableClient(DnsClient):
            def get_tree(self, repository):
                raise GitHubError("temporarily unavailable")

        facts = hosted_dns_facts(UnavailableClient({}), report("bu-ist-demo"))
        self.assertIn("unavailable (", facts["hosted_cluster_wildcard_records"])
        self.assertNotIn("not found", facts["hosted_cluster_wildcard_records"])


if __name__ == "__main__":
    unittest.main()
