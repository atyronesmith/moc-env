"""Deployment-phase metadata derived from the upstream deployment guides."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import CheckResult


DEPLOYMENT_GUIDE_PATH = "docs/infra-cluster-deployment.md"
WORKLOAD_DEPLOYMENT_GUIDE_PATH = "docs/workload-cluster-deployment.md"


@dataclass(frozen=True)
class PhaseGuide:
    """A section in the documented deployment sequence."""

    document: str
    heading: str

    def to_dict(self) -> dict[str, str]:
        return {"document": self.document, "heading": self.heading}


@dataclass(frozen=True)
class DeploymentPhase:
    """One ordered phase in a hub or workload deployment."""

    phase: int
    title: str
    guide: PhaseGuide

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "title": self.title,
            "guide": self.guide.to_dict(),
        }


@dataclass(frozen=True)
class CheckPhase:
    """Deployment metadata for one check id."""

    phase: int
    phase_title: str
    blocked_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotChecked:
    """A documented deployment step that repository state cannot prove."""

    scope: str
    phase: int
    title: str
    why: str
    where: PhaseGuide

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "why": self.why,
            "where": self.where.to_dict(),
            "phase": self.phase,
        }


_INFRASTRUCTURE_CONFIGURATION = PhaseGuide(
    DEPLOYMENT_GUIDE_PATH, "Infrastructure Configuration"
)
_CLUSTER_DEPLOYMENT = PhaseGuide(DEPLOYMENT_GUIDE_PATH, "Cluster Deployment")
_CLUSTER_CONFIGURATION = PhaseGuide(
    DEPLOYMENT_GUIDE_PATH, "Cluster Configuration"
)
_WORKLOAD_INFRASTRUCTURE_CONFIGURATION = PhaseGuide(
    WORKLOAD_DEPLOYMENT_GUIDE_PATH, "Infrastructure Configuration"
)
_WORKLOAD_CLUSTER_CONFIGURATION = PhaseGuide(
    WORKLOAD_DEPLOYMENT_GUIDE_PATH, "Cluster Deployment and Configuration"
)
HUB_PHASES: tuple[DeploymentPhase, ...] = (
    DeploymentPhase(
        1,
        "Host inventory entry",
        _INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        2,
        "Hub image inventory and vars",
        _CLUSTER_DEPLOYMENT,
    ),
    DeploymentPhase(
        3,
        "Discovery image reference",
        _CLUSTER_DEPLOYMENT,
    ),
    DeploymentPhase(
        4,
        "Keycloak OIDC client",
        _CLUSTER_CONFIGURATION,
    ),
    DeploymentPhase(
        5,
        "GitOps values and apps",
        _CLUSTER_CONFIGURATION,
    ),
)

WORKLOAD_PHASES: tuple[DeploymentPhase, ...] = (
    DeploymentPhase(
        1,
        "Host inventory entry",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        2,
        "Hub agent discovery ISO",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        3,
        "Agent ISO boot",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        4,
        "Agent visibility",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        5,
        "Agent labels and approval",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        6,
        "oac-apps values",
        _WORKLOAD_CLUSTER_CONFIGURATION,
    ),
    DeploymentPhase(
        7,
        "Shared-service prerequisites",
        _WORKLOAD_CLUSTER_CONFIGURATION,
    ),
)

NOT_CHECKED: tuple[NotChecked, ...] = (
    NotChecked(
        "hub",
        1,
        "Configure cluster and storage networks and firewalls for <cluster>",
        "The repositories read by this tool do not describe the switch, "
        "network, or firewall state required for <cluster>.",
        _INFRASTRUCTURE_CONFIGURATION,
    ),
    NotChecked(
        "hub",
        2,
        "Store the <cluster> SSH key and kubeadmin credentials in AWS Secrets Manager",
        "Secrets Manager is outside the public repositories read by this tool, "
        "so it cannot verify cluster/<cluster>/sshkey or "
        "cluster/<cluster>/kubeadmin.",
        _CLUSTER_DEPLOYMENT,
    ),
    NotChecked(
        "hub",
        2,
        "Place the pull secret and SSH key under hub-images/credentials/<cluster>",
        "The documented credential directory is intentionally not committed, "
        "so repository state cannot prove that its files exist for <cluster>.",
        _CLUSTER_DEPLOYMENT,
    ),
    NotChecked(
        "hub",
        3,
        "Run create_agent_install_media and copy the <cluster> ISO to the bastion host",
        "Running the playbook and copying the generated discovery ISO leave no "
        "trace that this tool can verify in the repositories it reads.",
        _CLUSTER_DEPLOYMENT,
    ),
    NotChecked(
        "hub",
        5,
        "Bootstrap Argo CD for <cluster>",
        "Running setup-gitops.sh and applying the bootstrap Helm template "
        "changes live cluster state, which this repository-only report cannot "
        "verify.",
        _CLUSTER_CONFIGURATION,
    ),
    NotChecked(
        "workload",
        4,
        "Agents visible in hardware-inventory",
        "Agent visibility in the hub's hardware-inventory namespace requires "
        "live cluster state that repository configuration cannot prove.",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
    NotChecked(
        "workload",
        5,
        "Agents labelled and approved",
        "Labelling and approving agents with update-agents.yaml changes live "
        "hub cluster state that repository configuration cannot prove.",
        _WORKLOAD_INFRASTRUCTURE_CONFIGURATION,
    ),
)

CHECK_PHASES: dict[str, CheckPhase] = {
    "request.issue": CheckPhase(0, "Environment request"),
    "hub.inventory": CheckPhase(
        1, "Host inventory entry"
    ),
    "workload.inventory": CheckPhase(
        1, "Host inventory entry"
    ),
    "hub.image_inventory": CheckPhase(
        2,
        "Hub image inventory and vars",
        ("hub.inventory",),
    ),
    "hub.image_vars": CheckPhase(
        2,
        "Hub image inventory and vars",
        ("hub.image_inventory",),
    ),
    "hub.boot_image": CheckPhase(
        3,
        "Discovery image reference",
        ("hub.image_inventory", "hub.image_vars"),
    ),
    "workload.boot_image": CheckPhase(
        2,
        "Hub agent discovery ISO",
        ("workload.inventory", "hub.boot_image"),
    ),
    "workload.agent_labels_inputs": CheckPhase(
        5,
        "Agent labels and approval",
        ("workload.inventory",),
    ),
    "hub.oidc_client": CheckPhase(
        4, "Keycloak OIDC client", ("hub.boot_image",)
    ),
    "hub.hosted_cluster_defaults": CheckPhase(
        5,
        "GitOps values and apps",
        ("hub.boot_image",),
    ),
    "hub.component_values": CheckPhase(
        5,
        "GitOps values and apps",
        ("hub.hosted_cluster_defaults",),
    ),
    "hub.local_cluster_values": CheckPhase(
        5,
        "GitOps values and apps",
        ("hub.hosted_cluster_defaults",),
    ),
    "hub.argocd_apps": CheckPhase(
        5,
        "GitOps values and apps",
        (
            "hub.hosted_cluster_defaults",
            "hub.component_values",
            "hub.local_cluster_values",
            "hub.oidc_client",
        ),
    ),
    "workload.hosted_cluster_values": CheckPhase(
        6,
        "oac-apps values",
        ("hub.hosted_cluster_defaults",),
    ),
    "workload.component_values": CheckPhase(
        6,
        "oac-apps values",
        ("workload.hosted_cluster_values",),
    ),
    "hub.pure_storage_realm": CheckPhase(5, "GitOps values and apps", ("hub.hosted_cluster_defaults",)),
    "workload.pure_storage_realm": CheckPhase(7, "Shared-service prerequisites", ("workload.component_values",)),
    "hub.moc_aws_oidc_cluster": CheckPhase(5, "GitOps values and apps", ("hub.hosted_cluster_defaults",)),
    "workload.moc_aws_oidc_cluster": CheckPhase(7, "Shared-service prerequisites", ("workload.component_values",)),
    "hub.moc_aws_cert_manager_policy": CheckPhase(5, "GitOps values and apps", ("hub.hosted_cluster_defaults",)),
    "workload.moc_aws_cert_manager_policy": CheckPhase(7, "Shared-service prerequisites", ("workload.component_values",)),
    "hub.moc_aws_hosted_secret_prefix": CheckPhase(5, "GitOps values and apps", ("hub.moc_aws_oidc_cluster",)),
    "workload.keycloak_oidc_client": CheckPhase(7, "Shared-service prerequisites", ("workload.hosted_cluster_values",)),
    "hub.moc_dns_records": CheckPhase(2, "Hub image inventory and vars", ("hub.image_vars",)),
    "workload.api_address_network": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
    "workload.ingress_address_network": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
    "workload.address_uniqueness": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
    "workload.dns_base_domain": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
    "workload.node_pool_hosts": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
    "workload.gpu_without_hosts": CheckPhase(6, "oac-apps values", ("workload.hosted_cluster_values",)),
}

_SCOPE_ORDER = {"hub": 0, "workload": 1, "shared": 2}


def phase_definitions(scope: str) -> tuple[DeploymentPhase, ...]:
    if scope == "hub":
        return HUB_PHASES
    if scope == "workload":
        return WORKLOAD_PHASES
    if scope == "environment":
        return (*HUB_PHASES, *WORKLOAD_PHASES)
    return ()


def not_checked_entries(scope: str, cluster: str) -> list[NotChecked]:
    """Return manually verifiable steps for one scope and cluster."""

    return [
        replace(
            entry,
            title=entry.title.replace("<cluster>", cluster),
            why=entry.why.replace("<cluster>", cluster),
        )
        for entry in NOT_CHECKED
        if entry.scope == scope
    ]


def annotate_and_sort_checks(checks: list["CheckResult"]) -> list["CheckResult"]:
    """Assign deployment metadata and order checks by scope and phase."""

    annotated = []
    for position, check in enumerate(checks):
        phase = CHECK_PHASES[check.id]
        annotated.append(
            replace(
                check,
                phase=phase.phase,
                phase_title=phase.phase_title,
                blocked_by=list(phase.blocked_by),
            )
        )
    return sorted(
        annotated,
        key=lambda check: (
            _SCOPE_ORDER.get(check.scope, len(_SCOPE_ORDER)),
            check.phase if check.phase is not None else 0,
            position,
        ),
    )
