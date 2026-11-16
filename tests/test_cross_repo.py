from __future__ import annotations

import unittest

from moc_env.checks import StatusChecker
from moc_env.github import GitHubError
from moc_env.model import Environment

from fakes import CrossRepoFakeGitHubClient


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
                values.replace('feature-gpu: "false"', 'feature-gpu: "true"'),
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
