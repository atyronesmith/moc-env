"""Deterministic desired-state export renderers."""

from __future__ import annotations

from typing import Any

import yaml

from .model import Environment
from .observed import (
    AppsObservation,
    InfraObservation,
    IssueObservation,
    SourceValue,
)

EXPORT_API_VERSION = "moc-env/v1alpha1"
INFRA_EXPORT_KIND = "InfraCluster"
INFRA_EXPORT_SCHEMA_VERSION = "1"
WORKLOAD_EXPORT_KIND = "WorkloadCluster"
WORKLOAD_EXPORT_SCHEMA_VERSION = "1"
ENVIRONMENT_EXPORT_KIND = "Environment"
ENVIRONMENT_EXPORT_SCHEMA_VERSION = "1"


def _source(source_value: SourceValue) -> dict[str, Any]:
    return source_value.to_dict()


def _field(
    value: Any,
    observation: InfraObservation,
    path: str,
    confidence: str = "exact",
) -> dict[str, Any]:
    return SourceValue(
        value,
        observation.repository,
        path,
        confidence=confidence,
    ).to_dict()


def _hub_variable_field(
    observation: InfraObservation,
    name: str,
) -> dict[str, Any]:
    values = observation.hub_variables.values
    value = values.value.get(name) if isinstance(values.value, dict) else None
    confidence = values.confidence
    if confidence == "exact" and value is None:
        confidence = "exact"
    return SourceValue(
        value,
        values.repository,
        values.path,
        confidence=confidence,
    ).to_dict()


def _boot_image(
    environment: Environment,
    observation: InfraObservation,
) -> dict[str, Any]:
    cluster = observation.clusters[environment.infra_cluster]
    urls = cluster.boot_image_urls
    if len(urls) == 1:
        selected = SourceValue(
            urls[0],
            cluster.hosts.repository,
            cluster.hosts.path,
        ).to_dict()
        ambiguous = False
    else:
        selected = SourceValue(
            None,
            cluster.hosts.repository,
            cluster.hosts.path,
            confidence="unsupported",
        ).to_dict()
        ambiguous = len(urls) > 1
    return {
        "urls": [
            SourceValue(
                url,
                cluster.hosts.repository,
                cluster.hosts.path,
            ).to_dict()
            for url in urls
        ],
        "selected": selected,
        "ambiguous": ambiguous,
    }


def _apps_source(
    apps: AppsObservation,
    value: Any,
    confidence: str = "exact",
) -> dict[str, Any]:
    return SourceValue(
        value,
        apps.source_repository,
        "git/trees/main?recursive=1",
        apps.source_ref,
        confidence=confidence,
    ).to_dict()


def workload_cluster_name(environment: Environment, workload: str) -> str:
    """Resolve a full or shortened workload name for the current model."""

    if workload == environment.workload_cluster:
        return workload
    if workload == environment.workload_cluster.removeprefix(
        f"{environment.base_name}-"
    ):
        return environment.workload_cluster
    raise ValueError(
        f"workload must be {environment.workload_cluster} or "
        f"{environment.workload_cluster.removeprefix(f'{environment.base_name}-')}"
    )


def _workload_boot_image(
    cluster: InfraObservation,
    workload_cluster: str,
) -> dict[str, Any]:
    observation = cluster.clusters[workload_cluster]
    urls = observation.boot_image_urls
    if len(urls) == 1:
        selected = SourceValue(
            urls[0],
            observation.hosts.repository,
            observation.hosts.path,
        ).to_dict()
        ambiguous = False
    else:
        selected = SourceValue(
            None,
            observation.hosts.repository,
            observation.hosts.path,
            confidence="unsupported",
        ).to_dict()
        ambiguous = len(urls) > 1
    return {
        "urls": [
            SourceValue(
                url,
                observation.hosts.repository,
                observation.hosts.path,
            ).to_dict()
            for url in urls
        ],
        "selected": selected,
        "ambiguous": ambiguous,
    }


def build_workload_export(
    environment: Environment,
    workload_cluster: str,
    infra_observation: InfraObservation,
    apps_observation: AppsObservation,
) -> dict[str, Any]:
    """Build a deterministic draft WorkloadCluster snapshot."""

    if workload_cluster not in infra_observation.clusters:
        raise ValueError(f"unknown workload cluster: {workload_cluster}")
    inventory = infra_observation.clusters[workload_cluster]
    paths = set(apps_observation.paths.value)
    hosted_values_path = (
        f"hosted-clusters/{environment.infra_cluster}/"
        f"{workload_cluster}/values.yaml"
    )
    component_prefix = f"values/{environment.infra_cluster}/{workload_cluster}/"
    application_prefix = f"apps/{environment.infra_cluster}/{workload_cluster}/"
    component_paths = list(
        sorted(path for path in paths if path.startswith(component_prefix))
    )
    application_paths = list(
        sorted(path for path in paths if path.startswith(application_prefix))
    )

    return {
        "apiVersion": EXPORT_API_VERSION,
        "kind": WORKLOAD_EXPORT_KIND,
        "schemaVersion": WORKLOAD_EXPORT_SCHEMA_VERSION,
        "metadata": {
            "name": SourceValue(
                workload_cluster,
                infra_observation.repository,
                infra_observation.inventory_path,
                confidence="inferred",
            ).to_dict(),
            "environment": SourceValue(
                environment.name,
                infra_observation.repository,
                infra_observation.inventory_path,
                confidence="inferred",
            ).to_dict(),
            "parentInfraCluster": SourceValue(
                environment.infra_cluster,
                infra_observation.repository,
                infra_observation.inventory_path,
                confidence="inferred",
            ).to_dict(),
        },
        "spec": {
            "parent": {
                "domain": SourceValue(
                    (
                        f"{infra_observation.hub_variables.values.value.get('cluster_domain_name')}"
                        f".{infra_observation.hub_variables.values.value.get('base_domain')}"
                        if isinstance(infra_observation.hub_variables.values.value, dict)
                        and isinstance(
                            infra_observation.hub_variables.values.value.get(
                                "cluster_domain_name"
                            ),
                            str,
                        )
                        and isinstance(
                            infra_observation.hub_variables.values.value.get(
                                "base_domain"
                            ),
                            str,
                        )
                        else None
                    ),
                    infra_observation.repository,
                    infra_observation.variables_path,
                    confidence=(
                        "inferred"
                        if isinstance(infra_observation.hub_variables.values.value, dict)
                        and isinstance(
                            infra_observation.hub_variables.values.value.get(
                                "cluster_domain_name"
                            ),
                            str,
                        )
                        and isinstance(
                            infra_observation.hub_variables.values.value.get(
                                "base_domain"
                            ),
                            str,
                        )
                        else "unsupported"
                    ),
                ).to_dict(),
                "network": {
                    "machineNetwork": _hub_variable_field(
                        infra_observation,
                        "machine_network",
                    ),
                },
            },
            "inventory": {
                "path": SourceValue(
                    infra_observation.inventory_path,
                    infra_observation.repository,
                    infra_observation.inventory_path,
                    confidence="inferred",
                ).to_dict(),
                "present": infra_observation.inventory_present.to_dict(),
                "groupPresent": inventory.group_found.to_dict(),
                "hostCount": SourceValue(
                    len(inventory.hosts.value),
                    inventory.hosts.repository,
                    inventory.hosts.path,
                ).to_dict(),
                "hosts": inventory.hosts.to_dict(),
                "bootImage": _workload_boot_image(
                    infra_observation,
                    workload_cluster,
                ),
            },
            "gitOps": {
                "sourceRepository": _apps_source(
                    apps_observation,
                    apps_observation.source_repository,
                    confidence="inferred",
                ),
                "hostedClusterValues": {
                    "path": _apps_source(
                        apps_observation,
                        hosted_values_path,
                        confidence="inferred",
                    ),
                    "present": _apps_source(
                        apps_observation,
                        hosted_values_path in paths,
                    ),
                },
                "componentValues": {
                    "prefix": _apps_source(
                        apps_observation,
                        component_prefix,
                        confidence="inferred",
                    ),
                    "present": _apps_source(
                        apps_observation,
                        bool(component_paths),
                    ),
                    "paths": _apps_source(apps_observation, component_paths),
                },
                "applications": {
                    "prefix": _apps_source(
                        apps_observation,
                        application_prefix,
                        confidence="inferred",
                    ),
                    "present": _apps_source(
                        apps_observation,
                        bool(application_paths),
                    ),
                    "paths": _apps_source(apps_observation, application_paths),
                },
            },
        },
    }


def _observed_domain(infra_observation: InfraObservation) -> tuple[str | None, str]:
    values = infra_observation.hub_variables.values.value
    if not isinstance(values, dict):
        return None, "unsupported"
    cluster_domain = values.get("cluster_domain_name")
    base_domain = values.get("base_domain")
    if isinstance(cluster_domain, str) and isinstance(base_domain, str):
        return f"{cluster_domain}.{base_domain}", "inferred"
    return None, "unsupported"


def build_environment_export(
    environment: Environment,
    issue: IssueObservation,
    infra_observation: InfraObservation,
    apps_observation: AppsObservation,
) -> dict[str, Any]:
    """Build a deterministic draft Environment bundle snapshot."""

    domain, domain_confidence = _observed_domain(infra_observation)
    return {
        "apiVersion": EXPORT_API_VERSION,
        "kind": ENVIRONMENT_EXPORT_KIND,
        "schemaVersion": ENVIRONMENT_EXPORT_SCHEMA_VERSION,
        "metadata": {
            "name": SourceValue(
                environment.name,
                infra_observation.repository,
                infra_observation.inventory_path,
                confidence="inferred",
            ).to_dict(),
        },
        "spec": {
            "issue": issue.url.to_dict(),
            "hubCluster": SourceValue(
                environment.infra_cluster,
                infra_observation.repository,
                infra_observation.inventory_path,
                confidence="inferred",
            ).to_dict(),
            "workloadClusters": [
                {
                    "name": SourceValue(
                        environment.workload_cluster,
                        infra_observation.repository,
                        infra_observation.inventory_path,
                        confidence="inferred",
                    ).to_dict(),
                    "parentHubCluster": SourceValue(
                        environment.infra_cluster,
                        infra_observation.repository,
                        infra_observation.inventory_path,
                        confidence="inferred",
                    ).to_dict(),
                }
            ],
            "domain": SourceValue(
                domain,
                infra_observation.repository,
                infra_observation.variables_path,
                confidence=domain_confidence,
            ).to_dict(),
            "network": {
                "machineNetwork": _hub_variable_field(
                    infra_observation,
                    "machine_network",
                ),
            },
            "gitOps": {
                "sourceRepository": _apps_source(
                    apps_observation,
                    apps_observation.source_repository,
                    confidence="inferred",
                ),
            },
        },
    }


def render_environment_export(
    environment: Environment,
    issue: IssueObservation,
    infra_observation: InfraObservation,
    apps_observation: AppsObservation,
) -> str:
    """Render a deterministic Environment bundle YAML document."""

    document = build_environment_export(
        environment,
        issue,
        infra_observation,
        apps_observation,
    )
    return yaml.safe_dump(
        document,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def build_infra_export(
    environment: Environment,
    observation: InfraObservation,
) -> dict[str, Any]:
    """Build a deterministic draft InfraCluster snapshot."""

    infra_cluster = observation.clusters[environment.infra_cluster]
    workload_cluster = observation.clusters[environment.workload_cluster]
    variables = observation.hub_variables.values
    domain = None
    domain_confidence = "unsupported"
    if isinstance(variables.value, dict):
        cluster_domain = variables.value.get("cluster_domain_name")
        base_domain = variables.value.get("base_domain")
        if isinstance(cluster_domain, str) and isinstance(base_domain, str):
            domain = f"{cluster_domain}.{base_domain}"
            domain_confidence = "inferred"

    return {
        "apiVersion": EXPORT_API_VERSION,
        "kind": INFRA_EXPORT_KIND,
        "schemaVersion": INFRA_EXPORT_SCHEMA_VERSION,
        "metadata": {
            "name": _field(
                environment.infra_cluster,
                observation,
                observation.inventory_path,
                confidence="inferred",
            ),
            "environment": _field(
                environment.name,
                observation,
                observation.inventory_path,
                confidence="inferred",
            ),
        },
        "spec": {
            "inventory": {
                "path": _field(
                    observation.inventory_path,
                    observation,
                    observation.inventory_path,
                    confidence="inferred",
                ),
                "present": _source(observation.inventory_present),
                "clusters": {
                    environment.infra_cluster: {
                        "name": _source(infra_cluster.cluster),
                        "groupPresent": _source(infra_cluster.group_found),
                        "hosts": _source(infra_cluster.hosts),
                        "bootImage": _boot_image(environment, observation),
                    },
                    environment.workload_cluster: {
                        "name": _source(workload_cluster.cluster),
                        "groupPresent": _source(workload_cluster.group_found),
                        "hosts": _source(workload_cluster.hosts),
                    },
                },
            },
            "hubInventory": {
                "path": _field(
                    observation.hub_inventory_path,
                    observation,
                    observation.hub_inventory_path,
                    confidence="inferred",
                ),
                "present": _source(observation.hub_inventory.path_present),
                "inventoryPresent": _source(
                    observation.hub_inventory.inventory_present,
                ),
                "clusterKeyPresent": _source(
                    observation.hub_inventory.cluster_key_present,
                ),
            },
            "variables": {
                "path": _field(
                    observation.variables_path,
                    observation,
                    observation.variables_path,
                    confidence="inferred",
                ),
                "present": _source(observation.hub_variables.path_present),
                "fields": {
                    name: _hub_variable_field(observation, name)
                    for name in (
                        "cluster_domain_name",
                        "base_domain",
                        "machine_network",
                        "api_ip",
                        "ingress_ip",
                        "dns_ip",
                    )
                },
            },
            "domain": _field(
                domain,
                observation,
                observation.variables_path,
                confidence=domain_confidence,
            ),
        },
    }


def render_infra_export(
    environment: Environment,
    observation: InfraObservation,
) -> str:
    """Render a deterministic InfraCluster YAML document."""

    document = build_infra_export(environment, observation)
    return yaml.safe_dump(
        document,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def render_workload_export(
    environment: Environment,
    workload_cluster: str,
    infra_observation: InfraObservation,
    apps_observation: AppsObservation,
) -> str:
    """Render a deterministic WorkloadCluster YAML document."""

    document = build_workload_export(
        environment,
        workload_cluster,
        infra_observation,
        apps_observation,
    )
    return yaml.safe_dump(
        document,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )
