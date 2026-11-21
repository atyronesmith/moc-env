"""Read-only Terraform guidance copied from observed, commit-pinned files.

No Terraform is executed and no filesystem or GitHub writes are performed here.
Every candidate is applied to a string and checked by the ordinary status checks.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import copy
from dataclasses import dataclass
import re

from .cross_repo import _hcl_string
from .github import GitHubClient, GitHubError
from .model import CheckResult, Environment


SUPPORTED = {
    "hub.moc_aws_hosted_secret_prefix",
    "workload.moc_aws_oidc_cluster",
    "workload.moc_aws_cert_manager_policy",
    "workload.keycloak_oidc_client",
}


class CannotSuggest(ValueError):
    """A reference contains an input that cannot safely be inferred."""


@dataclass(frozen=True)
class Entry:
    key: str
    code: str
    start: int  # zero-based source line, including attached comments
    end: int  # one-based last line (also the insertion index)


def _closing_brace(text: str, start: int) -> int:
    # This is a source-span scanner, not an HCL parser. Skip quoted strings and
    # comments so braces in descriptions/comments cannot change the map bounds.
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\#[^\n]*|//[^\n]*|/\*.*?\*/|[{}]', text[start:], re.S)
    depth = 0
    for token in tokens:
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return start + token.end()
    raise CannotSuggest("map bounds cannot be derived")


def entries(text: str, map_name: str) -> list[Entry]:
    """Locate direct entries only, retaining their literal formatting/comments."""
    match = re.search(rf'^(?P<indent> *){map_name}\s*=\s*\{{', text, re.M)
    if not match:
        raise CannotSuggest(f"{map_name} cannot be derived")
    limit = _closing_brace(text, match.end() - 1)
    indent = match['indent'] + "  "
    pattern = re.compile(rf'^{indent}"?(?P<key>[\w-]+)"?\s*=\s*(?:merge\([^\n]*,\s*)?\{{', re.M)
    lines = text.splitlines()
    result = []
    cursor = match.end()
    while found := pattern.search(text, cursor, limit):
        close = _closing_brace(text, found.end() - 1)
        end = text.count("\n", 0, close) + 1
        start = text.count("\n", 0, found.start())
        while start and lines[start - 1].startswith(indent + "#"):
            start -= 1
        result.append(Entry(found['key'], "\n".join(lines[start:end]), start, end))
        cursor = close
    if not result:
        raise CannotSuggest("reference entry cannot be derived")
    return result


def apply_suggestion(text: str, suggestion: dict) -> str:
    """Apply only to in-memory text at the exact reported, original line."""
    lines = text.splitlines(keepends=True)
    index = suggestion["after_line"]
    lines[index:index] = [suggestion["code"] + "\n"]
    return "".join(lines)


def _required(expected: dict, field: str) -> str:
    value = expected.get(field)
    if not isinstance(value, str) or not value:
        raise CannotSuggest(f"{field} cannot be derived")
    return value


def _copy_entry(reference: Entry, check: CheckResult) -> str:
    """Replace only known inputs; preserve expressions, comments and layout."""
    expected = check.expected
    cert = check.id.endswith("cert_manager_policy")
    cluster = _required(expected, "cluster" if cert else "cluster_name")
    key = cluster.replace("-", "_")
    if cert:
        key = "cert_manager_policy_" + key
        wanted = {field: _required(expected, field) for field in (
            "zone_name", "cluster_subdomain", "policy_name"
        )}
    elif check.id.endswith("keycloak_oidc_client"):
        wanted = {field: _required(expected, field) for field in (
            "cluster_name", "openshift_redirect_uri", "client_secret_name"
        )}
        wanted["keycloak_client_uuid"] = cluster
    else:
        wanted = {"cluster_name": cluster}

    replacements = {reference.key: key}
    for field, value in wanted.items():
        old = _hcl_string(reference.code, field)
        if old is None:
            raise CannotSuggest(f"{field} cannot be derived")
        replacements[old] = value
    if not cert and check.id.endswith("moc_aws_oidc_cluster"):
        old_cluster = _hcl_string(reference.code, "cluster_name")
        if old_cluster is None:
            raise CannotSuggest("cluster_name cannot be derived")
        replacements[old_cluster.replace("-", "_")] = cluster.replace("-", "_")

    # Reject new/unknown attributes instead of guessing their values. The two
    # expressions below are shared references, copied unchanged from this file.
    shared = {
        "oidc_bucket_domain_name": "aws_s3_bucket.oac_oidc.bucket_regional_domain_name",
        "cert_manager_policy_arn": r'module.cert_manager_policy\["cert_manager_policy_[\w-]+"\].policy_arn',
    } if check.id.endswith("moc_aws_oidc_cluster") else {}
    for line in reference.code.splitlines():
        attr = re.match(r'^\s*([\w-]+)\s*=\s*(.*)', line)
        if not attr or attr[1] == reference.key:
            continue
        field, rhs = attr.groups()
        if field in wanted:
            if not re.fullmatch(r'"(?:\\.|[^"\\])*",?\s*(?:#.*|//.*)?', rhs):
                raise CannotSuggest(f"{field} cannot be derived")
        elif cert and field == "policy_description":
            # Preserve the reference wording, substituting its known names.
            old_domain = _hcl_string(reference.code, "zone_name")
            description = _hcl_string(reference.code, field)
            old_cluster = reference.key.removeprefix("cert_manager_policy_").replace("_", "-")
            replacements[old_cluster] = cluster
            if (
                description is None
                or old_domain is None
                or not any(name in description for name in (old_domain, old_cluster))
            ):
                raise CannotSuggest(f"{field} cannot be derived")
        elif field in shared and re.fullmatch(shared[field] + r'\s*(?:#.*|//.*)?', rhs):
            pass
        else:
            raise CannotSuggest(f"{field} cannot be derived")

    # One simultaneous replacement avoids cascading substitutions.
    pattern = "|".join(re.escape(old) for old in sorted(replacements, key=len, reverse=True))
    return re.sub(pattern, lambda match: replacements[match.group()], reference.code)


def _candidate(text: str, check: CheckResult, environment: Environment) -> dict:
    cert = check.id.endswith("cert_manager_policy")
    blocks = entries(text, "cert_manager_policies" if cert else "openshift_oidc_clusters")
    hub_key = environment.infra_cluster.replace("-", "_")
    if cert:
        hub_key = "cert_manager_policy_" + hub_key
    hub = next((entry for entry in blocks if entry.key == hub_key), None)
    if check.id == "hub.moc_aws_hosted_secret_prefix":
        if hub is None:
            raise CannotSuggest("hub entry cannot be derived")
        if re.search(r'^\s*eso_writable_secret_prefixes\s*=', hub.code, re.M):
            raise CannotSuggest("existing eso_writable_secret_prefixes requires a manual edit")
        reference = next((entry for entry in blocks if entry.key == "nist_dev_infra"), None)
        if reference is None:
            reference = next((entry for entry in blocks if "eso_writable_secret_prefixes" in entry.code and entry.key != hub.key), None)
        if reference is None:
            raise CannotSuggest("eso_writable_secret_prefixes cannot be derived")
        match = re.search(r'(?m)(?:^ +#[^\n]*\n)*^ +eso_writable_secret_prefixes\s*=\s*\[[^\]]*\]', reference.code)
        if not match:
            raise CannotSuggest("eso_writable_secret_prefixes cannot be derived")
        prefixes = re.findall(r'"([^"]*)"', match.group())
        expected = check.expected
        prefix = expected.get("eso_writable_secret_prefix") if isinstance(expected, dict) else expected[0]
        if len(prefixes) != 1 or not isinstance(prefix, str):
            raise CannotSuggest("eso_writable_secret_prefix cannot be derived")
        code = match.group().replace(prefixes[0], prefix)
        after = hub.end - 1
        source_lines = text.splitlines()
        while after and (not source_lines[after - 1].strip() or source_lines[after - 1].lstrip().startswith(("#", "//"))):
            after -= 1
        location = f"inside the {hub.key} block, after line {after}"
    else:
        preferred = "cert_manager_policy_oac_prod_workload0" if cert else "oac_prod_workload0"
        workloads = [entry for entry in blocks if "workload" in entry.key]
        reference = next((entry for entry in workloads if entry.key == preferred), None)
        reference = reference or next(iter(workloads), None)
        if reference is None:
            raise CannotSuggest("workload reference cannot be derived")
        code = _copy_entry(reference, check)
        target_key = _identity(check).replace("-", "_")
        if cert:
            target_key = "cert_manager_policy_" + target_key
        if any(entry.key == target_key for entry in blocks):
            raise CannotSuggest("existing entry requires a manual edit")
        anchor = hub or blocks[-1]
        after = anchor.end
        location = f"after the {anchor.key} block, line {after}"
    return {"after_line": after, "location": location, "reference": reference.key, "code": code}


class _Overlay:
    """Delegate reads, overriding exactly one file without touching the client."""

    def __init__(self, client, repository, path, text):
        self.client, self.repository, self.path, self.text = client, repository, path, text

    def get_file(self, repository, path, ref="main"):
        if (repository, path) == (self.repository, self.path):
            return self.text
        return self.client.get_file(repository, path, ref)

    def get_tree(self, repository, ref="main"):
        return self.client.get_tree(repository, ref)

    def resolve_commit(self, repository, ref="main"):
        return self.client.resolve_commit(repository, ref)


def _identity(check: CheckResult):
    """Distinguish workloads when several checks share an ID."""
    if check.id == "hub.moc_aws_hosted_secret_prefix":
        return (check.expected.get("eso_writable_secret_prefix")
                if isinstance(check.expected, dict) else check.expected[0])
    return check.expected.get("cluster", check.expected.get("cluster_name"))


def _pr_correction(client, check, candidate):
    """Correct an existing candidate block, retaining its comments and layout.

    A shallow read-only client view selects the PR without changing baseline
    refs or the Sources table. Other repositories remain at baseline commits.
    """
    if check.id == "hub.moc_aws_hosted_secret_prefix":
        return None
    for evaluation in check.evidence.get("pr_evaluations", []):
        match = re.search(r'open PR (\S+)#(\d+) touches this but the check still fails', evaluation)
        if not match or match[1] != check.repository.split("/")[-1]:
            continue
        view = copy(client)
        view.refs = {**client.refs, check.repository: f"pull/{match[2]}/head"}
        view.source_snapshots = client.source_snapshots.copy()
        # PR evaluation restores baseline Sources, but retains its cached tree.
        # A cached get_tree alone does not re-record the resolved commit.
        view.get_tree(check.repository)
        if (check.repository, view.ref_for(check.repository)) not in view.source_snapshots:
            view.resolve_commit(check.repository)
        text = view.get_file(check.repository, check.path)
        cert = check.id.endswith("cert_manager_policy")
        key = _identity(check).replace("-", "_")
        if cert:
            key = "cert_manager_policy_" + key
        block = next((entry for entry in entries(text, "cert_manager_policies" if cert else "openshift_oidc_clusters") if entry.key == key), None)
        if block is None:
            continue
        candidate["code"] = _copy_entry(block, check)
        label = f"{match[1]}#{match[2]}"
        candidate["reference"] = f"{block.key} in open PR {label}"
        candidate["location"] += f"; corrects open PR {label}"
        lines = text.splitlines(keepends=True)
        lines[block.start:block.end] = [candidate["code"] + "\n"]
        return "".join(lines)
    return None


def attach_suggestions(
    client: GitHubClient,
    environment: Environment,
    checks: list[CheckResult],
    rerun: Callable,
) -> None:
    """Attach guidance only to the four scoped gaps, after successful replay."""
    for check in checks:
        if check.id not in SUPPORTED or not check.next_action or check.deferred:
            continue
        try:
            if check.state in {"unknown", "blocked"}:
                raise CannotSuggest("source inputs cannot be derived")
            text = client.get_file(check.repository, check.path)
            commit = client.source_snapshots.get((check.repository, client.ref_for(check.repository)))
            if not commit:
                raise CannotSuggest("source commit cannot be derived")
            candidate = {
                "repository": check.repository, "path": check.path, "commit": commit,
                **_candidate(text, check, environment),
            }
            corrected_pr = _pr_correction(client, check, candidate)
            variants = [apply_suggestion(text, candidate)]
            if corrected_pr is not None:
                variants.append(corrected_pr)
            for updated in variants:
                results = rerun(_Overlay(client, check.repository, check.path, updated))
                passed = any(item.id == check.id and _identity(item) == _identity(check)
                             and item.state == "declared_in_main" for item in results)
                if not passed:
                    raise CannotSuggest("generated code did not satisfy the check")
            check.suggestion = candidate
        except (CannotSuggest, GitHubError) as exc:
            check.suggestion_skipped_reason = f"no suggestion: {exc}"
