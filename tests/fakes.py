from __future__ import annotations

from moc_env.github import GitHubClient


class FakeGitHubClient(GitHubClient):
    """Offline GitHub client covering the current milestone fixtures."""

    SOURCE_SHAS = {
        "CCI-MOC/MOC-issues": "1111111111111111111111111111111111111111",
        "CCI-MOC/oac-infra": "2222222222222222222222222222222222222222",
        "CCI-MOC/oac-apps": "3333333333333333333333333333333333333333",
        "CCI-MOC/moc-keycloak": "4444444444444444444444444444444444444444",
    }

    def __init__(self, token: str | None = None, timeout: float = 1) -> None:
        super().__init__(token=token, timeout=timeout)
        self.rate_limit_remaining = 4999

    def get_json(self, path_or_url: str):
        if path_or_url == "/repos/CCI-MOC/MOC-issues/issues/666":
            return {
                "state": "open",
                "title": "RH HW Request - IS&T Tester cluster",
                "html_url": "https://github.com/CCI-MOC/MOC-issues/issues/666",
            }
        raise AssertionError(f"unexpected get_json path: {path_or_url}")

    def get_tree(self, repository: str, ref: str = "main"):
        if repository == "CCI-MOC/MOC-issues":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {}
        if repository == "CCI-MOC/oac-infra":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {
                "infra/inventory/00hosts.yaml": {"path": "infra/inventory/00hosts.yaml"},
                "infra/update-agents.yaml": {
                    "path": "infra/update-agents.yaml"
                },
                "hub-images/inventory.yml": {"path": "hub-images/inventory.yml"},
                "hub-images/group_vars/bu-ist-demo-infra/vars.yml": {
                    "path": "hub-images/group_vars/bu-ist-demo-infra/vars.yml"
                },
            }
        if repository == "CCI-MOC/oac-apps":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {}
        if repository == "CCI-MOC/moc-keycloak":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {"main.tf": {"path": "main.tf"}}
        raise AssertionError(f"unexpected repository: {repository}")

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            return """
all:
  children:
    bu_ist_demo_clusters:
      children:
        bu_ist_demo_infra:
          vars:
            cluster: bu-ist-demo-infra
          children:
            controller:
              vars:
                boot_image_url: http://10.2.0.82/boot/discovery.iso
              hosts:
                control-0:
                  node_name: MOC-R4PAC10U31-S1A
        bu_ist_demo_workload0:
          vars:
            cluster: bu-ist-demo-workload0
          children:
            compute:
              vars:
                boot_image_url: http://10.2.0.82/boot/discovery.iso
              hosts:
                compute-0:
                  node_name: MOC-R4PAC10U31-S1B
                  bm_management: ipmi
                  mac_addr: 00:11:22:33:44:55
                  resource_class: bu-ist-demo-worker
"""
        if repository == "CCI-MOC/oac-infra" and path == "infra/update-agents.yaml":
            return """
- name: Label and approve agents
  hosts: all
  tasks: []
"""
        if repository == "CCI-MOC/oac-infra" and path == "hub-images/inventory.yml":
            return """
all:
  children:
    bu-ist-demo-infra:
      hosts:
        bu-ist-demo-infra:
          ansible_connection: local
"""
        if (
            repository == "CCI-MOC/oac-infra"
            and path == "hub-images/group_vars/bu-ist-demo-infra/vars.yml"
        ):
            return """
cluster_domain_name: bu-ist-demo
base_domain: int.massopen.cloud
machine_network: 10.20.26.0/23
api_ip: 10.20.27.11
ingress_ip: 10.20.27.12
dns_ip: 8.8.8.8
"""
        if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
            return """
bu_ist_demo_infra = {
  cluster_name = "bu-ist-demo-infra"
  openshift_redirect_uri = "https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso"
  client_secret_name = "cluster/bu-ist-demo-infra/keycloak-oidc"
}
"""
        raise AssertionError(f"unexpected file: {repository}:{path}")

    def pulls(self, repository: str, state: str = "all"):
        if repository != "CCI-MOC/oac-apps":
            return
        yield {
            "number": 237,
            "title": "Added initial values for bu-ist-demo infra cluster",
            "body": None,
            "state": "open",
            "merged_at": None,
            "head": {
                "ref": "bu-ist-demo-buildout",
                "sha": "7b528394600996dae5c1e5d497236050d8810edc",
            },
            "html_url": "https://github.com/CCI-MOC/oac-apps/pull/237",
        }

    def pr_files(self, repository: str, number: int):
        yield {"filename": "values/bu-ist-demo-infra/hcp-config.yaml"}


class MultiWorkloadFakeGitHubClient(FakeGitHubClient):
    """Offline fixture with two workloads for one hub and one workload-less hub."""

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-infra":
            tree = {
                **tree,
                "hub-images/group_vars/oac-dev-infra/vars.yml": {
                    "path": "hub-images/group_vars/oac-dev-infra/vars.yml"
                },
            }
            tree.pop("hub-images/group_vars/bu-ist-demo-infra/vars.yml", None)
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-infra" and path == "infra/inventory/00hosts.yaml":
            return """
all:
  children:
    oac_dev_clusters:
      children:
        oac_dev_infra:
          vars:
            cluster: oac-dev-infra
          children:
            controller:
              hosts:
                control-0:
                  node_name: MOC-R4PAC10U31-S1A
        oac_dev_workload0:
          vars:
            cluster: oac-dev-workload0
          children:
            compute:
              hosts:
                compute-0:
                  node_name: MOC-R4PAC10U31-S1B
        oac_dev_workload1:
          vars:
            cluster: oac-dev-workload1
          children:
            compute:
              hosts:
                compute-1:
                  node_name: MOC-R4PAC10U31-S1C
        dizzy_infra:
          vars:
            cluster: dizzy-infra
          children:
            controller:
              hosts:
                control-0:
                  node_name: MOC-R4PAC10U31-S1D
"""
        if repository == "CCI-MOC/oac-infra" and path == "hub-images/inventory.yml":
            return """
all:
  children:
    oac-dev-infra:
      hosts:
        oac-dev-infra:
          ansible_connection: local
    dizzy-infra:
      hosts:
        dizzy-infra:
          ansible_connection: local
"""
        if (
            repository == "CCI-MOC/oac-infra"
            and path == "hub-images/group_vars/oac-dev-infra/vars.yml"
        ):
            return """
cluster_domain_name: oac-dev
base_domain: int.massopen.cloud
machine_network: 10.20.26.0/23
api_ip: 10.20.27.21
ingress_ip: 10.20.27.22
dns_ip: 8.8.8.8
"""
        return super().get_file(repository, path, ref)
