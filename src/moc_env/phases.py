"""Deployment-phase metadata derived from the oac-apps deployment guide."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import CheckResult


DEPLOYMENT_GUIDE_PATH = "docs/infra-cluster-deployment.md"


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
HUB_PHASES: tuple[DeploymentPhase, ...] = (
    DeploymentPhase(
        1,
        "Host inventory entry in oac-infra",
        _INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        2,
        "Hub-image inventory entry and group variables",
        _CLUSTER_DEPLOYMENT,
    ),
    DeploymentPhase(
        3,
        "Cluster discovery image published and referenced by the inventory",
        _CLUSTER_DEPLOYMENT,
    ),
    DeploymentPhase(
        4,
        "Keycloak OIDC client",
        _CLUSTER_CONFIGURATION,
    ),
    DeploymentPhase(
        5,
        "GitOps values and applications in oac-apps",
        _CLUSTER_CONFIGURATION,
    ),
)

WORKLOAD_PHASES: tuple[DeploymentPhase, ...] = (
    DeploymentPhase(
        1,
        "Host inventory entry in oac-infra",
        _INFRASTRUCTURE_CONFIGURATION,
    ),
    DeploymentPhase(
        2,
        "Discovery image and agent inputs",
        _CLUSTER_DEPLOYMENT,
    ),
    DeploymentPhase(
        3,
        "Hosted-cluster values",
        _CLUSTER_CONFIGURATION,
    ),
    DeploymentPhase(
        4,
        "Workload component values",
        _CLUSTER_CONFIGURATION,
    ),
    DeploymentPhase(
        5,
        "Merged GitOps changes",
        _CLUSTER_CONFIGURATION,
    ),
)

NOT_CHECKED: tuple[NotChecked, ...] = (
    NotChecked(
        "hub",
        1,
        "Configure cluster and storage networks and firewalls for <cluster>",
        "The four repositories read by this tool do not describe the switch, "
        "network, or firewall state required for <cluster>.",
        _INFRASTRUCTURE_CONFIGURATION,
    ),
    NotChecked(
        "hub",
        2,
        "Create internal DNS records for <cluster> api, api-int, and *.apps",
        "The tool does not query the DNS service or read moc-dns, so it cannot "
        "prove that the records for <cluster> exist.",
        _CLUSTER_DEPLOYMENT,
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
        "trace that this tool can verify in the four repositories it reads.",
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
        "hub",
        5,
        "Complete Pure storage configuration for <cluster>",
        "Pure storage configuration is documented separately and is not among "
        "the repositories read by this tool.",
        _CLUSTER_CONFIGURATION,
    ),
    NotChecked(
        "hub",
        5,
        "Complete cluster certificates and external DNS for <cluster>",
        "The relevant IAM roles and policies are documented separately and are "
        "not among the repositories read by this tool.",
        _CLUSTER_CONFIGURATION,
    ),
)

CHECK_PHASES: dict[str, CheckPhase] = {
    "request.issue": CheckPhase(0, "Environment request"),
    "pull_requests": CheckPhase(
        5, "GitOps values and applications in oac-apps"
    ),
    "hub.inventory": CheckPhase(
        1, "Host inventory entry in oac-infra"
    ),
    "workload.inventory": CheckPhase(
        1, "Host inventory entry in oac-infra"
    ),
    "hub.image_inventory": CheckPhase(
        2,
        "Hub-image inventory entry and group variables",
        ("hub.inventory",),
    ),
    "hub.image_vars": CheckPhase(
        2,
        "Hub-image inventory entry and group variables",
        ("hub.image_inventory",),
    ),
    "hub.boot_image": CheckPhase(
        3,
        "Cluster discovery image published and referenced by the inventory",
        ("hub.image_inventory", "hub.image_vars"),
    ),
    "workload.boot_image": CheckPhase(
        2,
        "Discovery image and agent inputs",
        ("workload.inventory", "hub.boot_image"),
    ),
    "workload.agent_labels_inputs": CheckPhase(
        2,
        "Discovery image and agent inputs",
        ("workload.inventory",),
    ),
    "hub.oidc_client": CheckPhase(
        4, "Keycloak OIDC client", ("hub.boot_image",)
    ),
    "hub.hosted_cluster_defaults": CheckPhase(
        5,
        "GitOps values and applications in oac-apps",
        ("hub.boot_image",),
    ),
    "hub.component_values": CheckPhase(
        5,
        "GitOps values and applications in oac-apps",
        ("hub.hosted_cluster_defaults",),
    ),
    "hub.local_cluster_values": CheckPhase(
        5,
        "GitOps values and applications in oac-apps",
        ("hub.hosted_cluster_defaults",),
    ),
    "hub.argocd_apps": CheckPhase(
        5,
        "GitOps values and applications in oac-apps",
        (
            "hub.hosted_cluster_defaults",
            "hub.component_values",
            "hub.local_cluster_values",
            "hub.oidc_client",
        ),
    ),
    "workload.hosted_cluster_values": CheckPhase(
        3,
        "Hosted-cluster values",
        ("hub.hosted_cluster_defaults",),
    ),
    "workload.component_values": CheckPhase(
        4,
        "Workload component values",
        ("workload.hosted_cluster_values",),
    ),
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
