from __future__ import annotations

from moc_env.github import GitHubClient


class FakeGitHubClient(GitHubClient):
    """Offline GitHub client covering the current milestone fixtures."""

    SOURCE_SHAS = {
        "CCI-MOC/MOC-issues": "1111111111111111111111111111111111111111",
        "CCI-MOC/oac-infra": "2222222222222222222222222222222222222222",
        "CCI-MOC/oac-apps": "3333333333333333333333333333333333333333",
        "CCI-MOC/moc-keycloak": "4444444444444444444444444444444444444444",
        "CCI-MOC/everpure-moc": "5555555555555555555555555555555555555555",
        "CCI-MOC/moc-aws": "6666666666666666666666666666666666666666",
        "CCI-MOC/moc-dns": "7777777777777777777777777777777777777777",
        "CCI-MOC/ansible-switches": "8888888888888888888888888888888888888888",
    }

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 1,
        refs: dict[str, str] | None = None,
    ) -> None:
        super().__init__(token=token, timeout=timeout, refs=refs)
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
        ref = self.ref_for(repository)
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
                "docs/hardware-and-network-configuration.md": {
                    "path": "docs/hardware-and-network-configuration.md"
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
        if repository == "CCI-MOC/everpure-moc":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {
                "ansible/group_vars/all/realms.yaml": {
                    "path": "ansible/group_vars/all/realms.yaml"
                }
            }
        if repository == "CCI-MOC/moc-aws":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {
                "main.tf": {"path": "main.tf"},
                "cert-manager-policies.tf": {"path": "cert-manager-policies.tf"},
            }
        if repository == "CCI-MOC/moc-dns":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {
                "zonefiles/int.massopen.cloud.zone": {
                    "path": "zonefiles/int.massopen.cloud.zone"
                }
            }
        if repository == "CCI-MOC/ansible-switches":
            self.record_source(repository, ref, self.SOURCE_SHAS[repository])
            return {"group_vars/all/vlans.yaml": {"path": "group_vars/all/vlans.yaml"}}
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
        if (
            repository == "CCI-MOC/oac-infra"
            and path == "docs/hardware-and-network-configuration.md"
        ):
            return """
# Hardware and network configuration

| Node Name | Resource Class |
|---|---|
| MOC-R4PAC10U31-S1A | bu-ist-demo-control |
| MOC-R4PAC10U31-S1B | bu-ist-demo-worker |
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
        if (
            repository == "CCI-MOC/oac-apps"
            and path.startswith("hosted-clusters/")
            and path.endswith("/values.yaml")
        ):
            if path.endswith("bu-ist-demo-workload0/values.yaml"):
                return """
clusterName: bu-ist-demo-workload0
feature-gpu: "false"
services:
  APIServer:
    ipAddress: 10.20.26.10
    externalIpAddress: 10.20.29.10
ingress:
  poolAddress: 10.20.28.10
  externalIpAddress: 10.20.29.10
dns:
  records:
    - hostname: api.bu-ist-demo-workload0.int.massopen.cloud
oauth:
  mocsso:
    enabled: true
nodePools:
  - name: compute
    replicas: 1
    agentLabelSelector:
      cluster: bu-ist-demo-workload0
      resource_class: bu-ist-demo-worker
"""
            return """
hcpExternalDomain: hcp.bu-ist-demo.int.massopen.cloud
baseDomain: int.massopen.cloud
"""
        if repository == "CCI-MOC/moc-keycloak" and path == "main.tf":
            return """
bu_ist_demo_infra = {
  cluster_name = "bu-ist-demo-infra"
  openshift_redirect_uri = "https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso"
  client_secret_name = "cluster/bu-ist-demo-infra/keycloak-oidc"
}
bu_ist_demo_workload0 = {
  cluster_name = "bu-ist-demo-workload0"
  openshift_redirect_uri = "https://oauth-bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud:443/oauth2callback/mocsso"
  client_secret_name = "cluster/bu-ist-demo-infra/hostedcluster/bu-ist-demo-workload0/keycloak-oidc"
}
"""
        if (
            repository == "CCI-MOC/everpure-moc"
            and path == "ansible/group_vars/all/realms.yaml"
        ):
            return """
realms:
  - name: bu-ist-demo-infra
    subnet_vlan: 2321
    subnet_prefix: 10.9.15.0/24
    s3_endpoint: s3.bu-ist-demo.int.massopen.cloud
  - name: bu-ist-demo-workload0
    subnet_vlan: 2322
    subnet_prefix: 10.20.28.0/24
    s3_endpoint: s3.bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud
"""
        if repository == "CCI-MOC/moc-aws" and path == "main.tf":
            return """
locals {
  openshift_oidc_clusters = {
    bu_ist_demo_infra = merge(local.defaults, {
      cluster_name = "bu-ist-demo-infra"
      eso_writable_secret_prefixes = ["cluster/bu-ist-demo-infra/hostedcluster/"]
    })
    bu_ist_demo_workload0 = merge(local.defaults, {
      cluster_name = "bu-ist-demo-workload0"
    })
  }
}
"""
        if repository == "CCI-MOC/moc-aws" and path == "cert-manager-policies.tf":
            return """
locals {
  cert_manager_policies = {
    "cert_manager_policy_bu_ist_demo_infra" = {
      cluster_subdomain = "bu-ist-demo.int.massopen.cloud"
      policy_name = "cert-manager-bu-ist-demo-infra"
    }
    "cert_manager_policy_bu_ist_demo_workload0" = {
      cluster_subdomain = "bu-ist-demo-workload0.hcp.bu-ist-demo.int.massopen.cloud"
      policy_name = "cert-manager-bu-ist-demo-workload0"
    }
  }
}
"""
        if (
            repository == "CCI-MOC/moc-dns"
            and path == "zonefiles/int.massopen.cloud.zone"
        ):
            return """
api.bu-ist-demo.int.massopen.cloud. 300 IN A 10.20.27.11
api-int.bu-ist-demo.int.massopen.cloud. 300 IN A 10.20.27.11
*.apps.bu-ist-demo.int.massopen.cloud. 300 IN A 10.20.27.12
"""
        if (
            repository == "CCI-MOC/ansible-switches"
            and path == "group_vars/all/vlans.yaml"
        ):
            return """
vlans:
  - name: BU-IST-DEMO-WORKLOAD0
    subnet4: 10.20.28.0/24
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


class CrossRepoFakeGitHubClient(FakeGitHubClient):
    """Offline fixture with passing cross-repository prerequisite data."""

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "hosted-clusters/bu-ist-demo-infra/values.yaml",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml",
            }
            tree.update({path: {"path": path} for path in paths})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if repository == "CCI-MOC/oac-apps":
            files = {
                "hosted-clusters/bu-ist-demo-infra/values.yaml": """
hcpExternalDomain: hcp.bu-ist-demo.int.massopen.cloud
baseDomain: int.massopen.cloud
""",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml": """
clusterName: bu-ist-demo-workload0
feature-gpu: "false"
services:
  APIServer:
    ipAddress: 10.20.26.10
    externalIpAddress: 10.20.29.10
ingress:
  poolAddress: 10.20.28.10
  externalIpAddress: 10.20.29.10
dns:
  records:
    - hostname: api.bu-ist-demo-workload0.int.massopen.cloud
oauth:
  mocsso:
    enabled: true
nodePools:
  - name: compute
    replicas: 1
    agentLabelSelector:
      cluster: bu-ist-demo-workload0
      resource_class: bu-ist-demo-worker
""",
            }
            if path in files:
                return files[path]
        return super().get_file(repository, path, ref)


class FullyConfiguredFakeGitHubClient(CrossRepoFakeGitHubClient):
    """Offline fixture where every repository check passes."""

    REQUIRED_LOCAL_COMPONENTS = (
        "acm.yaml",
        "acm-placements.yaml",
        "cert-manager.yaml",
        "cluster-certificates.yaml",
        "cluster-version.yaml",
        "external-dns-operator.yaml",
        "external-secrets.yaml",
        "hcp-config.yaml",
        "keycloak-oauth.yaml",
        "metallb.yaml",
        "openshift-gitops.yaml",
        "portworx.yaml",
        "user-workload-monitoring.yaml",
    )

    def get_tree(self, repository: str, ref: str = "main"):
        tree = super().get_tree(repository, ref)
        if repository == "CCI-MOC/oac-apps":
            paths = {
                "hosted-clusters/bu-ist-demo-infra/values.yaml",
                "values/bu-ist-demo-infra/hcp-config.yaml",
                "apps/bu-ist-demo-infra/keycloak-oauth.yaml",
                "hosted-clusters/bu-ist-demo-infra/"
                "bu-ist-demo-workload0/values.yaml",
                "values/bu-ist-demo-infra/bu-ist-demo-workload0/example.yaml",
            }
            paths.update(
                f"values/bu-ist-demo-infra/local-cluster/{name}"
                for name in self.REQUIRED_LOCAL_COMPONENTS
            )
            tree.update({path: {"path": path} for path in paths})
        return tree

    def get_file(self, repository: str, path: str, ref: str = "main") -> str:
        if (
            repository == "CCI-MOC/oac-infra"
            and path == "infra/inventory/00hosts.yaml"
        ):
            return super().get_file(repository, path, ref).replace(
                "http://10.2.0.82/boot/discovery.iso",
                "http://10.2.0.82/boot/bu-ist-demo-infra-agent-discovery.iso",
            )
        if repository == "CCI-MOC/oac-apps" and path not in {
            "hosted-clusters/bu-ist-demo-infra/values.yaml",
            "hosted-clusters/bu-ist-demo-infra/"
            "bu-ist-demo-workload0/values.yaml",
        }:
            return "{}\n"
        return super().get_file(repository, path, ref)


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
