"""The live-cluster boundary: targeted oc get JSON with unchanged user environment."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import yaml

from .charts import ChartInventoryError, collect_chart_inventory
from .cross_repo import _nested
from .github import GitHubClient, GitHubError
from .model import Environment
from .verify_live import APPS, TRACKING, _template_kinds, _templates

LOGIN_MESSAGE = "moc-env: install oc if needed and log in with oc login, then retry capture-live"
EXCLUDED = frozenset({"Secret", "Event", "Endpoints", "ReplicaSet", "ReplicationController"})

# Infrastructure supplies the API URL for cluster identity without reading
# kubeconfig or credentials. The current user is a separate named User GET.
REQUIRED = {
    "nodes": False, "pods": True, "namespaces": False, "resourcequotas": True,
    "clusterversions.config.openshift.io": False,
    "clusteroperators.config.openshift.io": False,
    "datascienceclusters.datasciencecluster.opendatahub.io": False,
    "hardwareprofiles.infrastructure.opendatahub.io": True,
    "applications.argoproj.io": True, "certificates.cert-manager.io": True,
    "dnses.operator.openshift.io": False,
    "baselineadminnetworkpolicies.policy.networking.k8s.io": False,
    "clusterrolebindings.rbac.authorization.k8s.io": False,
    "subscriptions.operators.coreos.com": True,
    "customresourcedefinitions.apiextensions.k8s.io": False,
    "infrastructures.config.openshift.io": False,
}
RESOURCE_TYPES = {
    "nodes": ("Node", False), "pods": ("Pod", True), "namespaces": ("Namespace", False),
    "resourcequotas": ("ResourceQuota", True),
    "clusterversions.config.openshift.io": ("ClusterVersion", False),
    "clusteroperators.config.openshift.io": ("ClusterOperator", False),
    "infrastructures.config.openshift.io": ("Infrastructure", False),
    "datascienceclusters.datasciencecluster.opendatahub.io": ("DataScienceCluster", False),
    "hardwareprofiles.infrastructure.opendatahub.io": ("HardwareProfile", True),
    "applications.argoproj.io": ("Application", True),
    "certificates.cert-manager.io": ("Certificate", True),
    "dnses.operator.openshift.io": ("DNS", False),
    "baselineadminnetworkpolicies.policy.networking.k8s.io": ("BaselineAdminNetworkPolicy", False),
    "clusterrolebindings.rbac.authorization.k8s.io": ("ClusterRoleBinding", False),
    "subscriptions.operators.coreos.com": ("Subscription", True),
    "customresourcedefinitions.apiextensions.k8s.io": ("CustomResourceDefinition", False),
    "jobsetoperators.operator.openshift.io": ("JobSetOperator", False),
    "kueues.kueue.openshift.io": ("Kueue", False),
    "operatorgroups.operators.coreos.com": ("OperatorGroup", True),
    "configmaps": ("ConfigMap", True), "services": ("Service", True),
    "serviceaccounts": ("ServiceAccount", True), "limitranges": ("LimitRange", True),
    "persistentvolumeclaims": ("PersistentVolumeClaim", True),
    "persistentvolumes": ("PersistentVolume", False),
    "deployments.apps": ("Deployment", True), "daemonsets.apps": ("DaemonSet", True),
    "statefulsets.apps": ("StatefulSet", True), "jobs.batch": ("Job", True),
    "cronjobs.batch": ("CronJob", True),
    "roles.rbac.authorization.k8s.io": ("Role", True),
    "rolebindings.rbac.authorization.k8s.io": ("RoleBinding", True),
    "clusterroles.rbac.authorization.k8s.io": ("ClusterRole", False),
    "networkpolicies.networking.k8s.io": ("NetworkPolicy", True),
    "ingresses.networking.k8s.io": ("Ingress", True),
    "storageclasses.storage.k8s.io": ("StorageClass", False),
    "groups.user.openshift.io": ("Group", False), "routes.route.openshift.io": ("Route", True),
    "securitycontextconstraints.security.openshift.io": ("SecurityContextConstraints", False),
    "apiservers.config.openshift.io": ("APIServer", False),
    "oauths.config.openshift.io": ("OAuth", False),
    "images.config.openshift.io": ("Image", False),
    "networks.config.openshift.io": ("Network", False),
    "networks.operator.openshift.io": ("Network", False),
    "ingresscontrollers.operator.openshift.io": ("IngressController", True),
    "validatingadmissionpolicies.admissionregistration.k8s.io": ("ValidatingAdmissionPolicy", False),
    "validatingadmissionpolicybindings.admissionregistration.k8s.io": ("ValidatingAdmissionPolicyBinding", False),
}


class CaptureError(ValueError):
    """A capture cannot be completed safely."""


def native_resources() -> dict[str, dict[str, Any]]:
    """A resolver table, not a sweep list. Only selected entries are requested."""
    return {key: {"kind": kind, "namespaced": namespaced, "group": key.partition(".")[2]}
            for key, (kind, namespaced) in RESOURCE_TYPES.items()}


def declared_resources(client: GitHubClient, environment: str, workload: str,
                    crds: dict[str, Any], *,
                    progress: Callable[..., None] | None = None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Resolve only the target's declared kinds, including local dependencies."""
    inventory = collect_chart_inventory(client, environment, workload, progress=progress)
    cluster = inventory.clusters[0]
    if cluster.error:
        raise ChartInventoryError(cluster.error)
    tree = client.get_tree(APPS)
    known = native_resources()
    for crd in crds.get("items", []):
        spec = crd.get("spec", {})
        group = spec.get("group", "")
        names = spec.get("names", {})
        plural, kind = names.get("plural", ""), names.get("kind", "")
        if group and plural and kind and re.fullmatch(r"[a-z0-9.-]+", f"{plural}.{group}"):
            known[f"{plural}.{group}"] = {"kind": kind, "group": group,
                                        "namespaced": spec.get("scope") == "Namespaced"}
    selected = {key: known[key] for key in REQUIRED}
    unresolved: list[str] = []
    for row in cluster.rows:
        kinds, dynamic = _template_kinds(_templates(client, tree, row["chart"]))
        if dynamic:
            unresolved.append(f"{row['chart']}: dynamic or unresolved template kind")
        for group, kind in sorted(kinds, key=str):
            if kind in EXCLUDED:
                unresolved.append(f"{row['chart']}: {kind} excluded from capture")
                continue
            matches = {key: entry for key, entry in known.items()
                    if entry["kind"] == kind and (group is None or entry["group"] == group)}
            if not matches or (group is None and len(matches) != 1):
                unresolved.append(f"{row['chart']}: {group or '?'}/{kind} unresolvable")
                continue
            selected.update(matches)
    return selected, sorted(set(unresolved))


def _write_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def reduce_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Allowlist every persisted object, including the REQUIRED kinds."""
    kind = obj.get("kind")
    original_metadata = obj.get("metadata") or {}
    annotations = original_metadata.get("annotations") or {}
    annotation_keys = (TRACKING, "opendatahub.io/disabled") if kind == "HardwareProfile" else (TRACKING,)
    result: dict[str, Any] = {"apiVersion": obj.get("apiVersion"), "kind": kind,
            "metadata": {"name": original_metadata.get("name"),
                        "namespace": original_metadata.get("namespace"),
                        "annotations": {key: annotations[key] for key in annotation_keys if key in annotations}}}
    spec, status = obj.get("spec") or {}, obj.get("status") or {}
    if kind in {"Pod", "Node"}:
        result["status"] = {"conditions": [{key: condition[key] for key in ("type", "status") if key in condition}
                                        for condition in status.get("conditions", [])]}
    if kind == "Pod":
        if "creationTimestamp" in original_metadata:
            result["metadata"]["creationTimestamp"] = original_metadata["creationTimestamp"]
        result["spec"] = {"nodeName": spec.get("nodeName")}
        result["status"]["phase"] = status.get("phase")
        for field in ("containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses"):
            if field in status:
                result["status"][field] = []
                for container in status[field]:
                    reduced = {key: container[key] for key in ("name", "ready", "restartCount") if key in container}
                    state = container.get("state") or {}
                    reasons = {key: {"reason": state[key]["reason"]} for key in ("waiting", "terminated")
                            if "reason" in (state.get(key) or {})}
                    if reasons:
                        reduced["state"] = reasons
                    result["status"][field].append(reduced)
    elif kind == "ResourceQuota":
        result["spec"] = {"hard": spec.get("hard", {})}
    elif kind == "DataScienceCluster":
        result["spec"] = {"components": spec.get("components", {})}
    elif kind == "HardwareProfile":
        result["spec"] = {key: spec[key] for key in ("identifiers", "scheduling") if key in spec}
    elif kind == "ClusterVersion":
        result["status"] = {"desired": {"version": (status.get("desired") or {}).get("version")}}
    return result


def _api_host(address: Any) -> str | None:
    if not isinstance(address, str) or not address or any(char.isspace() for char in address):
        return None
    try:
        return str(ip_address(address))
    except ValueError:
        try:
            return (urlsplit(address if "://" in address else f"//{address}").hostname or "").lower().rstrip(".") or None
        except ValueError:
            return None


def _dns_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.removesuffix(".").lower()
    if not name or len(name) > 253:
        return None
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    return name if all(re.fullmatch(label, part) for part in name.split(".")) else None


def _verify_identity(manifest: dict[str, Any], client: GitHubClient,
                    environment: str, workload: str, skip: bool) -> None:
    manifest["identity_verified"] = False
    if skip:
        manifest["identity_reason"] = "skipped with --skip-identity-check"
        return
    live_host = _api_host(manifest["api_url"])
    if live_host is None:
        manifest["identity_reason"] = manifest.get("api_url_error", "Infrastructure status.apiServerURL has no valid host")
        return
    path = f"hosted-clusters/{Environment(environment).infra_cluster}/{workload}/values.yaml"
    try:
        values = yaml.safe_load(client.get_file(APPS, path))
    except (OSError, ValueError, GitHubError, yaml.YAMLError):
        manifest["identity_reason"] = f"declared API address unavailable: {path}"
        return
    try:
        live_ip = ip_address(live_host)
    except ValueError:
        live_ip = None
    candidates: list[str] = []
    if live_ip is not None:
        live_host = str(live_ip)
        for field in ("ipAddress", "externalIpAddress"):
            address = _nested(values, ("services", "APIServer", field))
            if address in (None, ""):
                continue
            try:
                if not isinstance(address, str):
                    raise ValueError("address is not a string")
                candidates.append(str(ip_address(address)))
            except ValueError:
                manifest["identity_reason"] = f"declared services.APIServer.{field} is not an IP address: {path}"
                return
        if not candidates:
            manifest["identity_reason"] = f"declared services.APIServer.ipAddress and externalIpAddress missing: {path}"
            return
    else:
        hub_path = f"hosted-clusters/{Environment(environment).infra_cluster}/values.yaml"
        try:
            hub_values = yaml.safe_load(client.get_file(APPS, hub_path))
        except (OSError, ValueError, GitHubError, yaml.YAMLError):
            manifest["identity_reason"] = f"declared API domains unavailable: {hub_path}"
            return
        # Mirror hosted-cluster's hcpInternalDomain, hcpExternalDomain,
        # serviceDefaults/serviceHostname, and kubeAPIServerDNSName helpers.
        internal = _dns_name(_nested(hub_values, ("hcpInternalDomain",)))
        external = _dns_name(_nested(hub_values, ("hcpExternalDomain",)) or internal)
        cluster_name = _dns_name(_nested(values, ("clusterName",)))
        if internal is None or external is None or cluster_name is None:
            manifest["identity_reason"] = f"declared API names cannot be derived: clusterName in {path}; hcpInternalDomain/hcpExternalDomain in {hub_path}"
            return
        candidates = [f"api-internal-{cluster_name}.{internal}",
                        f"api-external-{cluster_name}.{external}"]
    if live_host not in candidates:
        raise CaptureError(f"cluster API host {live_host} does not match declared API hosts {', '.join(candidates)} for {workload}")
    manifest["identity_verified"] = True


def capture_live(environment: str, workload: str, output: Path, as_user: str | None = None,
                *, client: GitHubClient | None = None,
                skip_identity_check: bool = False,
                progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Capture with optional structured progress, never persisted in the snapshot.

    Discovery events have total=None until CRDs resolve the complete query plan.
    Each oc_start has an oc_end with outcome/count/elapsed; chart events forward
    the inventory reader's progress. Identity completion is reported last.
    """
    if shutil.which("oc") is None:
        raise CaptureError(LOGIN_MESSAGE)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CaptureError("capture output must be a new or empty directory")
    manifest: dict[str, Any] = {
        "schema_version": 1, "environment": environment, "workload": workload,
        "timestamp": datetime.now(timezone.utc).isoformat(), "api_url": None,
        "user": None, "impersonated_user": as_user, "resources": {}, "forbidden": [],
        "discovery_complete": True, "discovery_errors": [], "commands": [],
    }
    position = 0
    total: int | None = None

    def emit(event: str, **details: Any) -> None:
        if progress is not None:
            progress({"event": event, **details})

    def chart_progress(stage: str, action: str, repository: str, path: str) -> None:
        emit("chart", stage=stage, action=action, repository=repository, path=path)

    emit("declarations", message="Reading chart declarations")

    def get(*arguments: str) -> tuple[Any, str]:
        nonlocal position
        position += 1
        details = {"resource": arguments[0], "position": position, "total": total,
                    "all_namespaces": "--all-namespaces" in arguments}
        command = ["oc", "get", *arguments, "-o", "json", "--request-timeout=30s"]
        if as_user:
            command.extend(["--as", as_user])
        manifest["commands"].append(command)
        started = monotonic()
        emit("oc_start", **details)

        def finish(data: Any, error: str, outcome: str, count: int | None = None) -> tuple[Any, str]:
            emit("oc_end", **details, outcome=outcome, count=count, elapsed=monotonic() - started)
            return data, error

        try:
            # No env override, credential reads, temporary kubeconfig, or shell.
            result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
        except FileNotFoundError as exc:
            finish(None, LOGIN_MESSAGE, "failed")
            raise CaptureError(LOGIN_MESSAGE) from exc
        except subprocess.TimeoutExpired:
            return finish(None, "request timed out", "timed out")
        except OSError:
            finish(None, "oc get failed", "failed")
            raise
        if result.returncode:
            error = result.stderr.lower()
            if any(word in error for word in ("unauthorized", "must be logged in", "provide credentials",
                                            "expired",
                                            "missing or incomplete configuration", "no configuration has been provided",
                                            "current-context is not set", "no context exists")):
                finish(None, LOGIN_MESSAGE, "failed")
                raise CaptureError(LOGIN_MESSAGE)
            if "forbidden" in error:
                return finish(None, "Forbidden", "Forbidden")
            if any(word in error for word in ("notfound", "doesn't have a resource type", "could not find the requested resource")):
                return finish(None, "not-served", "not-served")
            return finish(None, "oc get failed", "failed")
        try:
            data = json.loads(result.stdout)
        except ValueError:
            return finish(None, "invalid JSON from oc get", "failed")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            complete = not (data.get("metadata") or {}).get("continue")
            return finish(data, "", "captured" if complete else "failed", len(data["items"]))
        if arguments[0] == "users.user.openshift.io" and isinstance(data, dict):
            return finish(data, "", "captured", 1)
        return finish(data, "", "failed")

    identity, identity_error = get("users.user.openshift.io", "~")
    if isinstance(identity, dict):
        manifest["user"] = (identity.get("metadata") or {}).get("name")
    if identity_error:
        manifest["user_error"] = identity_error
    infrastructure_key = "infrastructures.config.openshift.io"
    infrastructure_data, infrastructure_error = get(infrastructure_key)
    if infrastructure_data is not None and (
        not isinstance(infrastructure_data, dict)
        or not isinstance(infrastructure_data.get("items"), list)
        or not all(isinstance(item, dict) for item in infrastructure_data["items"])
        or (infrastructure_data.get("metadata") or {}).get("continue")
    ):
        infrastructure_data, infrastructure_error = None, "invalid or incomplete resource list"
    infrastructure: dict[str, Any] = next((item for item in (infrastructure_data or {}).get("items", [])
                            if (item.get("metadata") or {}).get("name") == "cluster"), {})
    manifest["api_url"] = (infrastructure.get("status") or {}).get("apiServerURL")
    if not manifest["api_url"]:
        manifest["api_url_error"] = infrastructure_error or "Infrastructure status.apiServerURL missing"
    client = client if client is not None else GitHubClient(token=None)
    try:
        _verify_identity(manifest, client, environment, workload, skip_identity_check)
    except CaptureError as exc:
        emit("identity", verified=False, reason=str(exc))
        raise
    crd_key = "customresourcedefinitions.apiextensions.k8s.io"
    crds, crd_error = get(crd_key)
    if crds is not None and (not isinstance(crds, dict) or not isinstance(crds.get("items"), list)
                            or (crds.get("metadata") or {}).get("continue")):
        crds, crd_error = None, "invalid or incomplete resource list"
    if crd_error:
        manifest["discovery_errors"].append(f"{crd_key}: {crd_error}")
    try:
        resources, unresolved = declared_resources(client, environment, workload, crds or {},
                                                    progress=chart_progress if progress is not None else None)
    except (OSError, ValueError, GitHubError, ChartInventoryError, yaml.YAMLError):
        if not manifest.get("identity_reason", "").startswith("declared API address unavailable:"):
            raise
        # The same unavailable values can prevent chart selection. Preserve
        # required evidence, but never claim complete discovery in that case.
        known = native_resources()
        resources = {key: known[key] for key in REQUIRED}
        unresolved = ["declared chart resources unavailable: hosted-cluster values unreadable"]
        manifest["discovery_errors"].extend(unresolved)
    manifest["unresolved_kinds"] = unresolved
    # Every kind is queried once; user identity is the one additional GET.
    # CRDs and Infrastructure were already read and are reused below.
    total = len(resources) + 1
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    for key, description in sorted(resources.items()):
        arguments = (key, "--all-namespaces") if description["namespaced"] else (key,)
        if key == crd_key:
            data, error = crds, crd_error
        elif key == infrastructure_key:
            data, error = infrastructure_data, infrastructure_error
        else:
            data, error = get(*arguments)
        if data is not None and (not isinstance(data, dict) or not isinstance(data.get("items"), list)
                                or (data.get("metadata") or {}).get("continue")):
            data, error = None, "invalid or incomplete resource list"
        status = error or "captured"
        if error == "Forbidden":
            manifest["forbidden"].append(key)
        reduced = {"apiVersion": "v1", "kind": "List", "items": [reduce_object(obj) for obj in data["items"]]} if data is not None else {
            "apiVersion": "v1", "kind": "Status", "status": "Failure", "reason": status}
        _write_json(output / f"{key}.json", reduced)
        manifest["resources"][key] = {**description, "status": status, "file": f"{key}.json"}
    manifest["discovery_complete"] = not manifest["discovery_errors"]
    _write_json(output / "manifest.json", manifest)
    emit("identity", verified=manifest["identity_verified"], reason=manifest.get("identity_reason"))
    return manifest
