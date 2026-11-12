"""Deterministic desired-state export renderers."""

from __future__ import annotations

from typing import Any

import yaml

from .model import Environment
from .observed import InfraObservation, SourceValue

EXPORT_API_VERSION = "moc-env/v1alpha1"
INFRA_EXPORT_KIND = "InfraCluster"
INFRA_EXPORT_SCHEMA_VERSION = "1"


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
