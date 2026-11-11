from __future__ import annotations

from moc_env.github import GitHubClient


class FakeGitHubClient(GitHubClient):
    """Offline GitHub client covering the current milestone fixtures."""

    def __init__(self, token: str | None = None, timeout: float = 1) -> None:
        super().__init__(token=token, timeout=timeout)

    def get_json(self, path_or_url: str):
        if path_or_url == "/repos/CCI-MOC/MOC-issues/issues/666":
            return {
                "state": "open",
                "title": "RH HW Request - IS&T Tester cluster",
                "html_url": "https://github.com/CCI-MOC/MOC-issues/issues/666",
            }
        raise AssertionError(f"unexpected get_json path: {path_or_url}")

    def get_tree(self, repository: str, ref: str = "main"):
        if repository == "CCI-MOC/oac-infra":
            return {
                "infra/inventory/00hosts.yaml": {"path": "infra/inventory/00hosts.yaml"},
                "hub-images/inventory.yml": {"path": "hub-images/inventory.yml"},
                "hub-images/group_vars/bu-ist-demo-infra/vars.yml": {
                    "path": "hub-images/group_vars/bu-ist-demo-infra/vars.yml"
                },
            }
        if repository == "CCI-MOC/oac-apps":
            return {}
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
