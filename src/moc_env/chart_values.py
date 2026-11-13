"""Render an environment-independent chart-values reference."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .observed import ChartValuesReferenceObservation

_SCOPE_ORDER = (
    "hub-wide",
    "hub-local-cluster",
    "hosted-cluster-defaults",
    "hosted-cluster",
    "workload-components",
)

_SCOPE_METADATA = {
    "hub-wide": {
        "description": (
            "Values shared by charts scoped to a hub cluster. They are not "
            "specific to the hub's local cluster or to one hosted workload."
        ),
        "pattern": "values/{hub-cluster}/*.yaml",
        "layer": "Hub cluster",
    },
    "hub-local-cluster": {
        "description": (
            "Values for components installed in the hub cluster's local "
            "cluster. Shared management services such as ACM are configured here."
        ),
        "pattern": "values/{hub-cluster}/local-cluster/*.yaml",
        "layer": "Hub local cluster",
    },
    "hosted-cluster-defaults": {
        "description": (
            "Values shared by hosted clusters under one hub. These files sit "
            "directly beneath a hub directory in hosted-clusters/."
        ),
        "pattern": "hosted-clusters/{hub-cluster}/*.yaml",
        "layer": "Hosted clusters under a hub",
    },
    "hosted-cluster": {
        "description": (
            "The primary definition of one hosted workload cluster. Its hosted "
            "control plane runs on the hub; these values describe the cluster "
            "and its node pools."
        ),
        "pattern": "hosted-clusters/{hub-cluster}/{workload-cluster}/values.yaml",
        "layer": "Hosted control plane and data plane",
    },
    "workload-components": {
        "description": (
            "Values for charts installed into one hosted workload cluster. "
            "Each file normally configures one component."
        ),
        "pattern": "values/{hub-cluster}/{workload-cluster}/*.yaml",
        "layer": "Hosted workload cluster",
    },
}

_CHART_DESCRIPTIONS = {
    "acm": "Advanced Cluster Management installed on the hub.",
    "acm-placements": "ACM placement rules that select clusters by labels.",
    "cert-manager": "Certificate issuance and renewal.",
    "cluster-certificates": "Cluster-facing TLS certificates.",
    "cluster-observability-operator": "Cluster observability instrumentation.",
    "cluster-version": "OpenShift cluster version and update policy.",
    "compliance": "Compliance settings shared by hosted clusters.",
    "external-dns-operator": "External DNS record management.",
    "external-secrets": "Retrieval of secrets from external secret stores.",
    "github-group-sync": "GitHub group synchronization into cluster RBAC.",
    "github-oauth": "GitHub OAuth identity configuration.",
    "hcp-config": "Hosted Control Plane infrastructure configuration.",
    "hosted-cluster": "The hosted workload cluster and its node pools.",
    "hosted-cluster-defaults": "Defaults shared by hosted clusters under one hub.",
    "hypervisor-cluster": "Hypervisor or virtualization host configuration.",
    "jobset-operator": "Kubernetes JobSet operator configuration.",
    "keycloak-oauth": "Keycloak OAuth identity integration.",
    "kueue-operator": "Kueue workload queueing and batch scheduling.",
    "lvmcluster": "Local storage and LVM cluster configuration.",
    "metallb": "MetalLB load-balancer address pools.",
    "moc-metrics-collector": "MOC operational metrics collection.",
    "oac-simple-rbac": "OAC role-based access controls.",
    "object-storage-certificate": "TLS certificate for object storage endpoints.",
    "object-storage-proxy": "Object-storage proxy networking and access.",
    "openshift-gitops": "OpenShift GitOps and Argo CD configuration.",
    "portworx": "Portworx storage configuration.",
    "rhoai": "Red Hat OpenShift AI components.",
    "servicemesh-operator": "OpenShift Service Mesh operator configuration.",
    "spoke-cluster-jetty": "A spoke cluster managed from the hub.",
    "user-projects": "User-facing namespaces, groups, and quotas.",
    "user-workload-monitoring": "Monitoring for user workload metrics.",
}

_KEY_DESCRIPTIONS = {
    "apiVIP": "Virtual IP reserved for the hosted cluster API server.",
    "apiServer.audit.profile": "OpenShift audit policy profile used by the API server.",
    "baseDomain": "Parent DNS domain shared by the deployment.",
    "clusterDomain": "DNS subdomain used for the cluster's services.",
    "clusterName": "Name assigned to the hosted cluster.",
    "hcpExternalDomain": "External DNS name used to reach the hosted control plane.",
    "hcpInternalDomain": "Internal DNS name used by the hosted control plane.",
    "ingressVIP": "Virtual IP reserved for the cluster's default ingress router.",
    "fips": "Enables or disables FIPS-mode settings for the cluster.",
    "managementCluster": "Name of the management cluster that owns hosted control planes.",
    "controllerAvailabilityPolicy": "Availability policy for a controller or operator.",
    "enabledHardwareProfiles": "Hardware profiles eligible for use by the cluster.",
    "provisionRequirements.controlPlaneAgents": (
        "Minimum number of agents required before the control plane can be provisioned."
    ),
    "provisionRequirements.workerAgents": (
        "Minimum number of agents required before workers can be provisioned."
    ),
    "release.channel": "OpenShift release channel used to select cluster updates.",
    "release.image": "Pinned OpenShift release image used by the cluster.",
    "release.name": "Name of the release or image stream being consumed.",
    "release.version": "Pinned OpenShift release version.",
    "etcd.storageClassName": "Storage class used for control-plane etcd data.",
    "imageConfig.allowedRegistriesForImport.domainName": (
        "Registry domain allowed when importing images."
    ),
    "imageConfig.allowedRegistriesForImport.insecure": (
        "Whether the allowed import registry is treated as insecure."
    ),
    "imageConfig.registrySources.allowedRegistries": (
        "Registries allowed as image sources for the cluster."
    ),
    "multiClusterHub.availabilityConfig": "ACM MultiClusterHub availability level.",
    "sshKey.aws_secret_name": "External-secret reference for the cluster SSH key.",
    "aws.region": "AWS region used by the component.",
    "aws.roleArn": "AWS IAM role assumed by the component.",
    "aws.hostedZoneID": "AWS Route 53 hosted zone used for DNS records.",
    "keycloak.clientID": "Keycloak OIDC client identifier.",
    "clientID": "OIDC client identifier.",
    "mappingMethod": "Method used to map identities from the identity provider.",
    "oauth.mocsso.enabled": "Enables the MOC single sign-on OAuth provider.",
    "oauth.tokenConfig.accessTokenInactivityTimeout": (
        "OAuth access-token inactivity timeout."
    ),
    "oauth.tokenConfig.accessTokenMaxAgeSeconds": (
        "Maximum OAuth access-token age in seconds."
    ),
    "tokenConfig.accessTokenInactivityTimeout": (
        "OAuth access-token inactivity timeout."
    ),
    "tokenConfig.accessTokenMaxAgeSeconds": (
        "Maximum OAuth access-token age in seconds."
    ),
    "letsencrypt.email": "Email address used for ACME registration and notices.",
    "letsencrypt.server": "ACME server endpoint used to issue certificates.",
    "letsencrypt.cluster_issuers.enabled": "Enables Let's Encrypt cluster issuers.",
    "certificates.issuer_name": "Cluster issuer used to issue a certificate.",
    "certificates.api.enabled": "Enables API-server certificate configuration.",
    "certificate.dnsName": "DNS name requested on a certificate.",
    "certificate.duration": "Requested certificate duration.",
    "certificate.renewBefore": "How long before expiry a certificate is renewed.",
    "certificate.secretName": "Secret that stores the issued certificate.",
    "clustersecretstores.aws.enabled": "Enables the AWS external-secrets store.",
    "clustersecretstores.aws.region": "AWS region for the external-secrets store.",
    "clustersecretstores.aws.roleArn": "AWS role used by the external-secrets store.",
    "externalSecret.remoteKey": "Remote key containing the external secret.",
    "externalSecret.secretStore": "External-secrets store used to fetch a value.",
    "externalSecret.secretStoreType": "Type of external-secrets store.",
    "dns.enabled": "Enables managed DNS records.",
    "dns.autoGenerate": "Allows the chart to generate DNS records automatically.",
    "dns.records.hostname": "Hostname for a managed DNS record.",
    "dns.records.name": "DNS record name.",
    "dns.records.target": "Target for a managed DNS record.",
    "externaldns.name": "Name of the ExternalDNS deployment.",
    "externaldns.zones": "DNS zones managed by ExternalDNS.",
    "externaldns.hostnameAnnotation": (
        "Hostname annotation used by ExternalDNS to discover records."
    ),
    "externaldns.labelFilter.matchLabels": "Labels used to select ExternalDNS sources.",
    "externaldns.domains.name": "Domain managed by ExternalDNS.",
    "addressPools.name": "MetalLB address-pool name.",
    "addressPools.addresses": "IP addresses assigned to a MetalLB pool.",
    "ingress.ipAddress": "IP address used by cluster ingress.",
    "ingress.externalIpAddress": "External IP address used by cluster ingress.",
    "ingress.poolAddress": "Address pool used for ingress.",
    "ingress.type": "Ingress implementation selected by the chart.",
    "ingressController.enabled": "Enables the managed ingress controller.",
    "ingressController.domain": "DNS domain served by the ingress controller.",
    "ingressController.addresses": "Addresses served by the ingress controller.",
    "ingressController.wildcardPolicy": "Wildcard-host policy for the ingress controller.",
    "monitoring.metricsForwarding": "Mode used to forward cluster metrics.",
    "monitoring.metricsSet": "Metrics collection level for cluster monitoring.",
    "capacityDashboard.console.enabled": "Enables the capacity dashboard in the console.",
    "capacityDashboard.perses.enabled": "Enables the Perses capacity dashboard.",
    "projects.name": "Namespace or project name created by the chart.",
    "projects.description": "Description applied to a project.",
    "projects.requester": "Identity recorded as the project requester.",
    "projects.groups.name": "Group granted access to a project.",
    "projects.groups.role": "Role granted to a project group.",
    "prometheusUrl": "Prometheus endpoint used by a monitoring component.",
    "rhoaiVersion": "Red Hat OpenShift AI version to install or manage.",
    "meshVersion": "Service Mesh version to install or manage.",
    "organization": "Organization name used by a component.",
    "organizations": "Organization configuration consumed by a component.",
    "namespace": "Namespace in which a component is installed.",
    "platform.type": "Infrastructure platform type for the hosted cluster.",
    "platform.retentionSize": "Retention size for control-plane or agent data.",
    "platform.volume.size": "Volume size requested by the platform component.",
    "platform.kubevirt.infraKubeConfigSecretName": (
        "Secret containing the kubeconfig for KubeVirt infrastructure."
    ),
    "nodes.name": "Name of a node or agent declaration.",
    "nodes.interface": "Network interface used by a node.",
    "nodes.ip": "IP address assigned to a node.",
    "nodes.macAddress": "MAC address assigned to a node.",
    "nodes.prefixLength": "Prefix length for a node's IP address.",
    "nodes.gateway": "Gateway used by a node.",
    "nodes.dns": "DNS server used by a node.",
    "volumegroup.devices": "Devices included in a volume group.",
    "portworx.snapshot_directory": "Portworx snapshot directory configuration.",
    "cim.enabled": "Enables the Cluster Infrastructure Operator input.",
    "cim.location": "Location or provider input for cluster infrastructure.",
    "cim.sshAuthorizedKey": "SSH public key used for cluster infrastructure.",
    "cim.kernelArguments.operation": "Kernel-argument operation.",
    "cim.kernelArguments.value": "Kernel argument value.",
    "reports.clusterName": "Cluster name attached to operational reports.",
    "reports.invoiceBucket": "Bucket used for invoice reports.",
    "reports.metricsBucket": "Bucket used for metric reports.",
    "collectors.clusterId": "Cluster identifier used by metric collectors.",
    "collectors.clusterName": "Cluster name used by metric collectors.",
    "collectors.clusterType": "Cluster type used by metric collectors.",
    "collectors.bucket": "Bucket receiving collected metrics.",
}

_KEY_PREFIX_DESCRIPTIONS = {
    "networking.clusterNetwork.": "Pod network CIDR and host-prefix settings.",
    "networking.serviceNetwork.": "Service network CIDR settings.",
    "networking.machineNetwork.": "Machine network CIDR settings.",
    "network.cidr": "CIDR used by the component's network.",
    "network.range.": "Start and end of an address range.",
    "network.routes.": "Static routes used by the component.",
    "nodePools.": (
        "Hosted-cluster node-pool settings: node selection, sizing, storage, "
        "and update behavior."
    ),
    "nodePools.machineConfigs.": "Machine configuration applied to a node pool.",
    "nodePools.hostDevices.": "Host devices attached to nodes in a pool.",
    "nodePools.disk.": "Disk size and storage class for a node pool.",
    "nodePools.agentLabelSelector.": "Labels used to select agents for a node pool.",
    "nodePools.rollingUpdate.": "Rolling-update limits for a node pool.",
    "clusterLabels.": "Feature labels used to select or place clusters.",
    "placements.matchLabels.": "Labels used by ACM placement rules.",
    "placements.": "ACM placement configuration.",
    "controller.resources.": "Resource requests and limits for a controller.",
    "repo.resources.": "Resource requests and limits for a repository component.",
    "server.resources.": "Resource requests and limits for a server component.",
    "projects.quota.hard.": "Hard resource-quota limit for a project.",
    "externaldns.externalSecret.": "External-secret reference used by ExternalDNS.",
    "externaldns.credentials.": "Credential reference used by ExternalDNS.",
    "externaldns.domains.": "Domain-filter settings for ExternalDNS.",
    "externaldns.labelFilter.": "Label filters used by ExternalDNS.",
}

_LEAF_DESCRIPTIONS = {
    "enabled": "Turns the component or behavior on or off.",
    "name": "Name assigned to the resource.",
    "replicas": "Number of replicas or nodes requested.",
    "region": "Cloud region in which resources are created.",
    "roleArn": "Cloud IAM role assumed by the component.",
    "cidr": "Classless inter-domain routing block.",
    "email": "Email address supplied to the component.",
    "cpu": "CPU request or limit.",
    "memory": "Memory request or limit.",
    "count": "Number of items requested.",
    "size": "Size requested for a resource.",
    "timeout": "Timeout applied to an operation.",
    "mode": "Operating mode selected by the component.",
    "type": "Implementation type selected by the component.",
    "value": "Value supplied to the containing setting.",
    "path": "Path consumed by the component.",
    "contents": "Contents supplied to the containing file setting.",
}


@dataclass(frozen=True)
class ManualEvidence:
    """One evidence reference in a manual variable definition."""

    source: str
    note: str | None = None


@dataclass(frozen=True)
class ManualVariable:
    """One human-authored variable definition."""

    key: str
    title: str
    group: str
    required: bool
    definition: str
    related: tuple[str, ...] = ()
    evidence: tuple[ManualEvidence, ...] = ()
    default: Any = None
    fallback: str | None = None


@dataclass(frozen=True)
class ManualTopic:
    """One human-authored documentation topic."""

    topic: str
    title: str
    overview: str
    variables: tuple[ManualVariable, ...]


@dataclass(frozen=True)
class ManualSource:
    """One registered documentation source."""

    source_id: str
    short_id: str
    title: str
    repository: str
    path: str
    ref: str
    kind: str
    topics: tuple[str, ...]
    summary: str
    url: str | None = None


@dataclass(frozen=True)
class ManualDocumentation:
    """The complete manual documentation layer."""

    sources: dict[str, ManualSource]
    topics: tuple[ManualTopic, ...]


def documentation_directory() -> Path:
    """Return the documentation directory bundled with or surrounding the package."""

    candidates = (
        Path(__file__).parent / "docs",
        Path.cwd() / "docs",
        Path(__file__).parents[2] / "docs",
    )
    for candidate in candidates:
        if (candidate / "sources.yaml").is_file():
            return candidate
    raise FileNotFoundError("chart-values documentation sources could not be found")


def _manual_evidence(data: Any) -> tuple[ManualEvidence, ...]:
    if not isinstance(data, list):
        return ()
    evidence: list[ManualEvidence] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        evidence.append(
            ManualEvidence(
                source=str(item.get("source", "")),
                note=item.get("note"),
            )
        )
    return tuple(evidence)


def _manual_variable(data: Any) -> ManualVariable:
    if not isinstance(data, dict):
        raise ValueError("manual variable entry must be a mapping")
    key = data.get("key")
    title = data.get("title")
    group = data.get("group")
    definition = data.get("definition")
    if not isinstance(key, str) or not isinstance(title, str):
        raise ValueError("manual variable entry requires key and title")
    if not isinstance(group, str) or not isinstance(definition, str):
        raise ValueError(f"manual variable {key!r} requires group and definition")
    related = data.get("related", [])
    if not isinstance(related, list):
        raise ValueError(f"manual variable {key!r} related must be a list")
    default = data.get("default")
    fallback = data.get("fallback")
    if default is not None and not isinstance(default, (str, bool, int, float)):
        raise ValueError(f"manual variable {key!r} default must be scalar")
    if fallback is not None and not isinstance(fallback, str):
        raise ValueError(f"manual variable {key!r} fallback must be a string")
    return ManualVariable(
        key=key,
        title=title,
        group=group,
        required=bool(data.get("required", False)),
        definition=definition,
        related=tuple(str(item) for item in related),
        evidence=_manual_evidence(data.get("evidence", [])),
        default=default,
        fallback=fallback,
    )


def load_chart_values_manual() -> ManualDocumentation:
    """Load manual sources and variable definitions from tracked YAML."""

    documentation = documentation_directory()
    source_document = yaml.safe_load(
        (documentation / "sources.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(source_document, dict):
        raise ValueError("docs/sources.yaml must be a mapping")
    sources: dict[str, ManualSource] = {}
    for source_id, source_data in source_document.get("sources", {}).items():
        if not isinstance(source_data, dict):
            raise ValueError(f"source {source_id!r} must be a mapping")
        topics = source_data.get("topics", [])
        if not isinstance(topics, list):
            raise ValueError(f"source {source_id!r} topics must be a list")
        sources[source_id] = ManualSource(
            source_id=source_id,
            short_id=str(source_data.get("shortId", source_id)),
            title=str(source_data.get("title", source_id)),
            repository=str(source_data.get("repository", "")),
            path=str(source_data.get("path", "")),
            ref=str(source_data.get("ref", "")),
            kind=str(source_data.get("kind", "")),
            topics=tuple(str(topic) for topic in topics),
            summary=str(source_data.get("summary", "")),
            url=source_data.get("url"),
        )

    topics: list[ManualTopic] = []
    variables_directory = documentation / "variables"
    for path in sorted(variables_directory.glob("*.yaml")):
        topic_document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(topic_document, dict):
            raise ValueError(f"{path} must be a mapping")
        variables = topic_document.get("variables", [])
        if not isinstance(variables, list):
            raise ValueError(f"{path} variables must be a list")
        topics.append(
            ManualTopic(
                topic=str(topic_document.get("topic", path.stem)),
                title=str(topic_document.get("title", path.stem)),
                overview=str(topic_document.get("overview", "")),
                variables=tuple(_manual_variable(item) for item in variables),
            )
        )

    for topic in topics:
        for variable in topic.variables:
            for evidence in variable.evidence:
                if evidence.source not in sources:
                    raise ValueError(
                        f"manual variable {variable.key!r} references unknown "
                        f"source {evidence.source!r}"
                    )
    return ManualDocumentation(sources=sources, topics=tuple(topics))


def _inline(value: Any) -> str:
    if isinstance(value, Iterable) and not isinstance(value, str):
        rendered = ", ".join(str(item) for item in value)
    else:
        rendered = str(value) if value is not None else "—"
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def _secret_like(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in ("secret", "token", "password", "credential")
    )


def _description(key: str, charts: Iterable[str]) -> str:
    lookup_key = key.replace("[]", "")
    description = _KEY_DESCRIPTIONS.get(lookup_key)
    if description is None:
        for prefix, prefix_description in _KEY_PREFIX_DESCRIPTIONS.items():
            if lookup_key.startswith(prefix):
                description = prefix_description
                break
    if description is None:
        leaf = lookup_key.rsplit(".", 1)[-1]
        description = _LEAF_DESCRIPTIONS.get(leaf)
    if description is None:
        chart_context = next(
            (
                _CHART_DESCRIPTIONS[chart]
                for chart in charts
                if chart in _CHART_DESCRIPTIONS
            ),
            None,
        )
        if chart_context is None:
            description = (
                "Not yet curated; inspect the linked chart source for the exact meaning."
            )
        else:
            description = (
                f"{chart_context} This key controls `{lookup_key.rsplit('.', 1)[-1]}`."
            )
    if _secret_like(key):
        description += " ⚠️ Secret-like name; do not place secret material in values files."
    return description


def render_chart_values_markdown(
    observation: ChartValuesReferenceObservation,
) -> str:
    """Render a topic-first, environment-independent values reference."""

    manual = load_chart_values_manual()
    observed_by_key = {
        key_observation.key.value: key_observation
        for key_observation in observation.keys
    }
    manual_keys = {
        variable.key
        for topic in manual.topics
        for variable in topic.variables
    }
    scope_files = {
        scope: [file_observation for file_observation in observation.files
                if file_observation.scope.value == scope]
        for scope in _SCOPE_ORDER
    }
    scope_keys = {
        scope: [
            key_observation
            for key_observation in observation.keys
            if scope in key_observation.scopes.value
        ]
        for scope in _SCOPE_ORDER
    }

    lines = [
        "# 📘 Chart Configuration Reference",
        "",
        "This guide explains how `CCI-MOC/oac-apps` organizes Helm chart "
        "values across the deployment. It is intentionally independent of a "
        "particular environment: it documents the purpose and placement of "
        "configuration keys, not the current value assigned to any environment.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Source repository | `{observation.source_repository}` |",
        f"| Source ref | `{observation.source_ref}` |",
        f"| Values files | {len(observation.files)} |",
        f"| Unique keys | {len(observation.keys)} |",
        "",
        "## Deployment model",
        "",
        "The hub cluster is the management cluster. It runs shared services "
        "and hosts control planes for workload clusters. A hosted workload "
        "cluster therefore has two important halves: its control plane runs "
        "on the hub, while its worker nodes provide the workload data plane.",
        "",
        "## Scope summary",
        "",
        "| Scope | Layer | Path pattern | Files | Keys |",
        "|---|---|---|---:|---:|",
    ]
    for scope in _SCOPE_ORDER:
        metadata = _SCOPE_METADATA[scope]
        lines.append(
            f"| `{scope}` | {metadata['layer']} | `{metadata['pattern']}` | "
            f"{len(scope_files[scope])} | {len(scope_keys[scope])} |"
        )

    lines.extend(
        [
            "",
            "## Manual topics",
            "",
            "Manual topics carry the reviewed explanation for each variable. "
            "Discovery adds the charts, types, file counts, and scopes where "
            "that key currently appears. Evidence uses compact source IDs; the "
            "appendix lists each referenced document once.",
            "",
        ]
    )

    for topic in manual.topics:
        lines.extend(
            [
                f"## {topic.title}",
                "",
                topic.overview,
                "",
            ]
        )

        groups: dict[str, list[ManualVariable]] = {}
        for variable in topic.variables:
            groups.setdefault(variable.group, []).append(variable)

        for group_name, variables in groups.items():
            lines.extend(
                [
                    f"### {group_name}",
                    "",
                    "| Key | Required | Default or fallback | Evidence |",
                    "|---|---|---|---|",
            ]
        )
            for variable in variables:
                default_or_fallback = variable.default or variable.fallback or "—"
                evidence_ids = ", ".join(
                    manual.sources[evidence.source].short_id
                    for evidence in variable.evidence
                )
                lines.append(
                    f"| `{_inline(variable.key)}` | "
                    f"{'Required' if variable.required else 'Optional'} | "
                    f"`{_inline(default_or_fallback)}` | "
                    f"{evidence_ids or '—'} |"
                )
            lines.append("")

            for variable in variables:
                lines.extend(
                    [
                        f"#### `{variable.key}`",
                        "",
                        variable.definition,
                        "",
                    ]
                )
                key_observation = observed_by_key.get(variable.key)
                if key_observation is None:
                    lines.extend(
                        [
                            "**Discovered:** Not currently observed in merged "
                            "`main`; this entry documents supported chart input.",
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "**Discovered:** "
                            f"charts `{_inline(key_observation.charts.value)}`; "
                            f"types `{_inline(key_observation.types.value)}`; "
                            f"{key_observation.file_count.value} values file(s); "
                            f"scopes `{_inline(key_observation.scopes.value)}`.",
                            "",
                        ]
                    )
                if variable.related:
                    lines.extend(
                        [
                            "**Related:** "
                            + ", ".join(f"`{item}`" for item in variable.related),
                            "",
                        ]
                    )
                if variable.evidence:
                    evidence_ids = ", ".join(
                        manual.sources[evidence.source].short_id
                        for evidence in variable.evidence
                    )
                    lines.extend([f"**Evidence:** {evidence_ids}", ""])

    lines.extend(
        [
            "## Uncurated variables",
            "",
            "These variables do not yet have a manual definition. They are "
            "shown with repository-derived facts and a provisional chart-based "
            "description until a reviewed manual entry is added.",
            "",
        ]
    )

    uncurated_found = False
    for scope in _SCOPE_ORDER:
        uncurated = [
            key_observation
            for key_observation in scope_keys[scope]
            if key_observation.key.value not in manual_keys
        ]
        if not uncurated:
            continue
        uncurated_found = True
        metadata = _SCOPE_METADATA[scope]
        lines.extend(
            [
                f"### {scope}",
                "",
                metadata["description"],
                "",
                f"**Path pattern:** `{metadata['pattern']}`",
                "",
                "| Key | Charts | Type | Files | What it controls |",
                "|---|---|---|---:|---|",
            ]
        )
        for key_observation in uncurated:
            key = key_observation.key.value
            lines.append(
                f"| `{_inline(key)}` | `{_inline(key_observation.charts.value)}` | "
                f"`{_inline(key_observation.types.value)}` | "
                f"{key_observation.file_count.value} | "
                f"{_description(key, key_observation.charts.value)} |"
            )
        lines.append("")

    if not uncurated_found:
        lines.extend(["All discovered variables have manual definitions.", ""])

    lines.extend(
        [
            "## How to use this guide",
            "",
            "- Choose the scope that matches the deployment layer you are changing.",
            "- Use the path pattern to locate the relevant values file.",
            "- Read the cited source and the upstream chart documentation together.",
            "- Keep secret material in an external-secret store; only reference its key here.",
            "- Do not copy an environment's values blindly. Values are examples of usage, not portable defaults.",
            "",
            "This reference is generated read-only from merged `main`. It does "
            "not prove that a chart is installed, healthy, or current in any cluster.",
            "",
            "## Sources",
            "",
            "| ID | Source | Repository | Path | Ref |",
            "|---|---|---|---|---|",
        ]
    )
    for source in sorted(manual.sources.values(), key=lambda item: item.short_id):
        title = f"[{source.title}]({source.url})" if source.url else source.title
        lines.append(
            f"| `{source.short_id}` | {title} | `{source.repository}` | "
            f"`{source.path}` | `{source.ref}` |"
        )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"
