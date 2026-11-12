"""Render an environment-independent chart-values reference."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .github import github_url
from .observed import (
    ChartValuesReferenceObservation,
    OAC_APPS_REPOSITORY,
)

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
    """Render a human-readable, environment-independent values reference."""

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
            "## Configuration keys by scope",
            "",
            "The tables below describe keys found in merged `main`. File counts "
            "show how many values files use a key; they do not imply that every "
            "environment uses it. Links point to one representative source file.",
            "",
        ]
    )

    for scope in _SCOPE_ORDER:
        metadata = _SCOPE_METADATA[scope]
        files = scope_files[scope]
        lines.extend(
            [
                f"## {scope}",
                "",
                metadata["description"],
                "",
                f"**Path pattern:** `{metadata['pattern']}`",
                "",
            ]
        )
        unsupported = [
            file_observation
            for file_observation in files
            if file_observation.values.confidence == "unsupported"
        ]
        if unsupported:
            lines.append(
                "⚠️ Some files in this scope use a YAML shape that cannot be "
                "safely flattened into key documentation."
            )
            lines.append("")
        if not scope_keys[scope]:
            lines.append("No supported scalar keys were found in this scope.")
            lines.append("")
            continue

        lines.extend(
            [
                "| Key | Charts | Type | Files | What it controls | Source |",
                "|---|---|---|---:|---|---|",
            ]
        )
        for key_observation in scope_keys[scope]:
            key = key_observation.key.value
            path = key_observation.paths.value[0]
            lines.append(
                f"| `{_inline(key)}` | `{_inline(key_observation.charts.value)}` | "
                f"`{_inline(key_observation.types.value)}` | "
                f"{key_observation.file_count.value} | "
                f"{_description(key, key_observation.charts.value)} | "
                f"[Example]({github_url(OAC_APPS_REPOSITORY, path)}) |"
            )
        lines.append("")

    lines.extend(
        [
            "## How to use this guide",
            "",
            "- Choose the scope that matches the deployment layer you are changing.",
            "- Use the path pattern to locate the relevant values file.",
            "- Read the linked example file and the upstream chart documentation together.",
            "- Keep secret material in an external-secret store; only reference its key here.",
            "- Do not copy an environment's values blindly. Values are examples of usage, not portable defaults.",
            "",
            "This reference is generated read-only from merged `main`. It does "
            "not prove that a chart is installed, healthy, or current in any cluster.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
