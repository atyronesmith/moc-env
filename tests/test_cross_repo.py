from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from moc_env.checks import StatusChecker
from moc_env.cross_repo import _dns_records_check, _workload_value_checks
from moc_env.github import GitHubError
from moc_env.model import Environment
from moc_env.observed import parse_hardware_resource_classes

from fakes import CrossRepoFakeGitHubClient


class Pr246Client(CrossRepoFakeGitHubClient):
    """Replay oac-apps PR 246 values.yaml verbatim at commit 625765a.

    Source: https://github.com/CCI-MOC/oac-apps/blob/625765a/
    hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml
    """

    WORKLOAD_PATH = (
        "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml"
    )
    DEFAULTS_PATH = "hosted-clusters/bu-ist-demo-infra/values.yaml"
    VLAN_PATH = "group_vars/all/vlans.yaml"

    def __init__(self) -> None:
        super().__init__()
        self.files = {
            self.WORKLOAD_PATH: (
                Path(__file__).parent / "fixtures/pr246-workload-values.yaml"
            ).read_text(encoding="utf-8"),
            self.DEFAULTS_PATH: (
                "baseDomain: hcp.bu-ist-demo.int.massopen.cloud\n"
                "hcpExternalDomain: hcp.bu-ist-demo.int.massopen.cloud\n"
            ),
            self.VLAN_PATH: yaml.safe_dump({"vlans": [
                {"name": "OAC-PRODUCTION-WORKLOAD0", "subnet4": "10.20.12.0/23"},
                {"name": "OAC-DEV-WORKLOAD0", "subnet4": "10.20.6.0/23"},
                {"name": "BU-IST-DEMO-WORKLOAD", "subnet4": "10.20.28.0/23"},
                {"name": "PureStorage-BU-IST-DEMO-WORKLOAD", "subnet4": "10.9.16.0/24"},
            ]}),
        }

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if (
            repository == "CCI-MOC/oac-apps"
            and path in {self.WORKLOAD_PATH, self.DEFAULTS_PATH}
        ) or (repository == "CCI-MOC/ansible-switches" and path == self.VLAN_PATH):
            return self.files[path]
        return super().get_file(repository, path, ref)


class ModifiedFileClient(CrossRepoFakeGitHubClient):
    def __init__(self, repository: str, path: str, content: str) -> None:
        super().__init__()
        self.repository = repository
        self.path = path
        self.content = content

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == self.repository and path == self.path:
            return self.content
        return super().get_file(repository, path, ref)


class AddedFileClient(CrossRepoFakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            path = "hosted-clusters/other-infra/other-workload/values.yaml"
            tree[path] = {"path": path}
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if (
            repository == "CCI-MOC/oac-apps"
            and path == "hosted-clusters/other-infra/other-workload/values.yaml"
        ):
            return """
services:
  APIServer:
    ipAddress: 10.20.26.10
"""
        return super().get_file(repository, path, ref)


class UnavailableEverpureClient(CrossRepoFakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        if repository == "CCI-MOC/everpure-moc":
            raise GitHubError("repository unavailable")
        return super().get_tree(repository, ref)


class ZoneSuffixClient(CrossRepoFakeGitHubClient):
    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/moc-dns":
            tree.update(
                {
                    "zonefiles/ocp.massopen.cloud.zone": {
                        "path": "zonefiles/ocp.massopen.cloud.zone"
                    },
                    "zonefiles/massopen.cloud.zone": {
                        "path": "zonefiles/massopen.cloud.zone"
                    },
                    "zonefiles/cloud.zone": {"path": "zonefiles/cloud.zone"},
                }
            )
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/moc-dns" and path == "zonefiles/ocp.massopen.cloud.zone":
            return """
api.infra.oac.ocp.massopen.cloud. 300 IN A 10.20.9.11
api-int.infra.oac.ocp.massopen.cloud. 300 IN A 10.20.9.11
*.apps.infra.oac.ocp.massopen.cloud. 300 IN A 10.20.9.12
"""
        return super().get_file(repository, path, ref)


class CrossRepositoryChecksTest(unittest.TestCase):
    def report(self, client):
        return StatusChecker(client, include_prs=False).run(
            Environment(name="bu-ist-demo", issue_number=666)
        ).to_dict()

    def check(self, report, check_id):
        return next(item for item in report["checks"] if item["id"] == check_id)

    def test_passing_fixture(self) -> None:
        report = self.report(CrossRepoFakeGitHubClient())
        ids = {
            item["id"]
            for item in report["checks"]
            if item["stage"] == "Cross-repository prerequisites"
        }

        expected = {
            "hub.pure_storage_realm",
            "workload.pure_storage_realm",
            "hub.moc_aws_oidc_cluster",
            "workload.moc_aws_oidc_cluster",
            "hub.moc_aws_cert_manager_policy",
            "workload.moc_aws_cert_manager_policy",
            "hub.moc_aws_hosted_secret_prefix",
            "workload.keycloak_oidc_client",
            "hub.moc_dns_records",
            "workload.api_address_network",
            "workload.ingress_address_network",
            "workload.address_uniqueness",
            "workload.dns_base_domain",
            "workload.node_pool_hosts",
            "workload.gpu_without_hosts",
        }
        self.assertEqual(ids, expected)
        for check_id in expected:
            with self.subTest(check_id=check_id):
                self.assertEqual(self.check(report, check_id)["state"], "declared_in_main")

    def test_dns_zonefile_uses_longest_domain_suffix(self) -> None:
        check = _dns_records_check(
            ZoneSuffixClient(),
            Environment(name="oac-prod"),
            {
                "cluster_domain_name": "infra",
                "base_domain": "oac.ocp.massopen.cloud",
                "api_ip": "10.20.9.11",
                "ingress_ip": "10.20.9.12",
            },
            None,
        )

        self.assertEqual(check.state, "declared_in_main")
        self.assertEqual(check.path, "zonefiles/ocp.massopen.cloud.zone")
        self.assertEqual(check.evidence["zone"], "ocp.massopen.cloud")

    def test_each_check_has_a_failing_fixture(self) -> None:
        realms = CrossRepoFakeGitHubClient().get_file(
            "CCI-MOC/everpure-moc", "ansible/group_vars/all/realms.yaml"
        )
        main = CrossRepoFakeGitHubClient().get_file("CCI-MOC/moc-aws", "main.tf")
        policies = CrossRepoFakeGitHubClient().get_file(
            "CCI-MOC/moc-aws", "cert-manager-policies.tf"
        )
        dns = CrossRepoFakeGitHubClient().get_file(
            "CCI-MOC/moc-dns", "zonefiles/int.massopen.cloud.zone"
        )
        keycloak = CrossRepoFakeGitHubClient().get_file(
            "CCI-MOC/moc-keycloak", "main.tf"
        )
        values = CrossRepoFakeGitHubClient().get_file(
            "CCI-MOC/oac-apps",
            "hosted-clusters/bu-ist-demo-infra/"
            "bu-ist-demo-workload0/values.yaml",
        )
        cases = {
            "hub.pure_storage_realm": (
                "CCI-MOC/everpure-moc",
                "ansible/group_vars/all/realms.yaml",
                realms.replace("name: bu-ist-demo-infra", "name: other-infra"),
                "missing",
            ),
            "workload.pure_storage_realm": (
                "CCI-MOC/everpure-moc",
                "ansible/group_vars/all/realms.yaml",
                realms.replace("name: bu-ist-demo-workload0", "name: other-workload"),
                "missing",
            ),
            "hub.moc_aws_oidc_cluster": (
                "CCI-MOC/moc-aws",
                "main.tf",
                main.replace('cluster_name = "bu-ist-demo-infra"', 'cluster_name = "other-infra"'),
                "missing",
            ),
            "workload.moc_aws_oidc_cluster": (
                "CCI-MOC/moc-aws",
                "main.tf",
                main.replace('cluster_name = "bu-ist-demo-workload0"', 'cluster_name = "other-workload"'),
                "missing",
            ),
            "hub.moc_aws_cert_manager_policy": (
                "CCI-MOC/moc-aws",
                "cert-manager-policies.tf",
                policies.replace("bu-ist-demo", "other"),
                "missing",
            ),
            "workload.moc_aws_cert_manager_policy": (
                "CCI-MOC/moc-aws",
                "cert-manager-policies.tf",
                policies.replace("bu-ist-demo-workload0", "other-workload"),
                "missing",
            ),
            "hub.moc_aws_hosted_secret_prefix": (
                "CCI-MOC/moc-aws",
                "main.tf",
                main.replace('["cluster/bu-ist-demo-infra/hostedcluster/"]', "[]"),
                "missing",
            ),
            "workload.keycloak_oidc_client": (
                "CCI-MOC/moc-keycloak",
                "main.tf",
                keycloak.replace(":443/oauth2callback", ":8443/oauth2callback"),
                "value_mismatch",
            ),
            "hub.moc_dns_records": (
                "CCI-MOC/moc-dns",
                "zonefiles/int.massopen.cloud.zone",
                dns.replace("10.20.27.11", "10.20.99.11"),
                "value_mismatch",
            ),
            "workload.api_address_network": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
                values.replace("ipAddress: 10.20.26.10", "ipAddress: 10.20.30.10"),
                "value_mismatch",
            ),
            "workload.ingress_address_network": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
                values.replace("poolAddress: 10.20.28.10", "poolAddress: 10.20.26.10"),
                "value_mismatch",
            ),
            "workload.address_uniqueness": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/other-infra/other-workload/values.yaml",
                "",
                "value_mismatch",
            ),
            "workload.dns_base_domain": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
                values.replace("int.massopen.cloud", "example.invalid"),
                "value_mismatch",
            ),
            "workload.node_pool_hosts": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
                values.replace("replicas: 1", "replicas: 2"),
                "value_mismatch",
            ),
            "workload.gpu_without_hosts": (
                "CCI-MOC/oac-apps",
                "hosted-clusters/bu-ist-demo-infra/bu-ist-demo-workload0/values.yaml",
                values + '\nclusterLabels:\n  massopen.cloud/feature-gpu: "true"\n',
                "value_mismatch",
            ),
        }
        for check_id, (repository, path, content, state) in cases.items():
            with self.subTest(check_id=check_id):
                client = (
                    AddedFileClient()
                    if check_id == "workload.address_uniqueness"
                    else ModifiedFileClient(repository, path, content)
                )
                check = self.check(self.report(client), check_id)
                self.assertEqual(check["state"], state)
                self.assertIn(check["severity"], {"blocking", "advisory"})

    def test_pr246_copied_dns_domain_is_a_blocking_gap(self) -> None:
        check = self.check(self.report(Pr246Client()), "workload.dns_base_domain")
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "blocking")
        self.assertEqual(check["expected"]["baseDomain"], "hcp.bu-ist-demo.int.massopen.cloud")
        self.assertIn(
            "s3.bu-ist-demo-workload0.hcp.oac.int.massopen.cloud",
            check["missing"]["hostnames"],
        )

    def test_pr246_gpu_label_without_hosts_is_advisory(self) -> None:
        check = self.check(self.report(Pr246Client()), "workload.gpu_without_hosts")
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "advisory")
        self.assertEqual(check["actual"]["gpu_host_count"], 0)
        self.assertEqual(check["actual"]["clusterLabels.massopen.cloud/feature-gpu"], "true")

    def test_pr246_ingress_uses_its_environment_vlan(self) -> None:
        check = self.check(self.report(Pr246Client()), "workload.ingress_address_network")
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "blocking")
        self.assertEqual(check["expected"]["vlan_subnet"], "10.20.28.0/23")
        self.assertIn("BU-IST-DEMO-WORKLOAD", check["reason"])
        client = Pr246Client()
        client.files[client.WORKLOAD_PATH] = client.files[client.WORKLOAD_PATH].replace(
            "10.20.7.10/32", "10.20.29.10/32"
        )
        self.assertEqual(
            self.check(self.report(client), "workload.ingress_address_network")["state"],
            "declared_in_main",
        )

    def test_unmatched_vlan_checks_only_outside_hub_network(self) -> None:
        client = Pr246Client()
        client.files[client.VLAN_PATH] = "vlans:\n  - name: OAC-PRODUCTION-WORKLOAD0\n    subnet4: 10.20.12.0/23\n"
        check = self.check(self.report(client), "workload.ingress_address_network")
        self.assertEqual(check["state"], "declared_in_main")
        self.assertIsNone(check["expected"]["vlan_subnet"])
        self.assertIn("No VLAN matches", check["reason"])
        client.files[client.WORKLOAD_PATH] = client.files[client.WORKLOAD_PATH].replace(
            "10.20.7.10/32", "10.20.26.10/32"
        )
        self.assertEqual(
            self.check(self.report(client), "workload.ingress_address_network")["state"],
            "value_mismatch",
        )

    def test_dns_uses_hosted_defaults_and_hostname_boundary(self) -> None:
        client = Pr246Client()
        client.files[client.DEFAULTS_PATH] = "baseDomain: cluster.example\nhcpExternalDomain: public.example\n"
        for hostname, expected_state in (
            ("s3.cluster.example", "declared_in_main"),
            ("s3.public.example.", "declared_in_main"),
            ("s3.notcluster.example", "value_mismatch"),
            ("s3.int.massopen.cloud", "value_mismatch"),
        ):
            with self.subTest(hostname=hostname):
                client.files[client.WORKLOAD_PATH] = yaml.safe_dump({
                    "dns": {"records": [{"hostname": hostname}]},
                })
                self.assertEqual(
                    self.check(self.report(client), "workload.dns_base_domain")["state"],
                    expected_state,
                )

    def test_corrected_checks_replay_live_oac_prod_evidence(self) -> None:
        """Re-run the changed checks, not just assertions on saved verdicts."""

        fixture = json.loads((
            Path(__file__).parent / "fixtures/oac-prod-full-status.json"
        ).read_text(encoding="utf-8"))
        checks = {check["id"]: check for check in fixture["checks"]}
        resource_classes = parse_hardware_resource_classes((
            Path(__file__).parent / "fixtures/oac-prod-gpu-hardware.md"
        ).read_text(encoding="utf-8"))
        environment = Environment(name="oac-prod", workload_clusters=("oac-prod-workload0",))
        path = "hosted-clusters/oac-prod-infra/oac-prod-workload0/values.yaml"
        values = {
            "services": {"APIServer": {"ipAddress": "10.20.9.13"}},
            "ingress": {"poolAddress": checks["workload.ingress_address_network"]["actual"]},
            "dns": {"records": [
                {"hostname": name} for name in checks["workload.dns_base_domain"]["actual"]
            ]},
            "clusterLabels": {"massopen.cloud/feature-gpu": "true"},
        }
        client = ModifiedFileClient(
            "CCI-MOC/ansible-switches", "group_vars/all/vlans.yaml",
            "vlans:\n  - name: BU-IST-DEMO-WORKLOAD\n    subnet4: 10.20.28.0/23\n"
            "  - name: OAC-PRODUCTION-WORKLOAD0\n    subnet4: 10.20.12.0/23\n",
        )
        results = _workload_value_checks(
            client, environment,
            SimpleNamespace(
                clusters={"oac-prod-workload0": SimpleNamespace(hosts=SimpleNamespace(
                    value=checks["workload.inventory"]["evidence"]["hosts"]
                ))},
                hardware_resource_classes=SimpleNamespace(value=resource_classes),
            ),
            SimpleNamespace(paths=SimpleNamespace(value=[path]), files={path: yaml.safe_dump(values)}),
            checks["hub.image_vars"]["evidence"]["values"],
            checks["hub.hosted_cluster_defaults"]["evidence"]["values"],
            None,
        )
        by_id = {check.id: check for check in results}
        for check_id in (
            "workload.dns_base_domain", "workload.gpu_without_hosts",
            "workload.ingress_address_network",
        ):
            with self.subTest(check_id=check_id):
                self.assertEqual(by_id[check_id].state, "declared_in_main")
                self.assertEqual(by_id[check_id].severity, "info")
        self.assertEqual(by_id["workload.gpu_without_hosts"].actual["gpu_host_count"], 7)
        self.assertIn(
            "oac-prod-workload0-gpu-sxm-1",
            by_id["workload.gpu_without_hosts"].evidence["gpu_hosts"],
        )

    def test_duplicate_ip_names_the_other_cluster(self) -> None:
        check = self.check(self.report(AddedFileClient()), "workload.address_uniqueness")
        self.assertEqual(check["state"], "value_mismatch")
        self.assertEqual(check["severity"], "blocking")
        self.assertIn("other-workload", check["reason"])

    def test_unreadable_repository_is_unknown(self) -> None:
        check = self.check(
            self.report(UnavailableEverpureClient()), "hub.pure_storage_realm"
        )
        self.assertEqual(check["state"], "unknown")
        self.assertNotEqual(check["state"], "missing")
        self.assertIn("could not be read", check["reason"])


if __name__ == "__main__":
    unittest.main()
