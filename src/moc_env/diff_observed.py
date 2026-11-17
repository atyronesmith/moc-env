"""Read repository declarations used only by structural environment diffs."""

from __future__ import annotations

import re
from typing import Any

from .github import GitHubClient, GitHubError


def hosted_dns_facts(client: GitHubClient, report: dict[str, Any]) -> dict[str, str]:
    """Locate hosted-zone delegations and wildcards, never infer from a name."""

    defaults = next(
        (
            (check.get("evidence") or {}).get("values") or {}
            for check in report.get("checks", [])
            if check.get("id") == "hub.hosted_cluster_defaults"
        ),
        {},
    )
    domains = {
        value.rstrip(".").lower()
        for key in ("hcpInternalDomain", "hcpExternalDomain", "baseDomain")
        if isinstance(value := defaults.get(key), str) and value
    }
    if not domains:
        return {}
    declarations: dict[str, list[tuple[str, str]]] = {domain: [] for domain in domains}
    wildcards: dict[str, list[tuple[str, str]]] = {domain: [] for domain in domains}
    errors: list[str] = []
    try:
        repository = "CCI-MOC/moc-dns"
        for path in sorted(client.get_tree(repository)):
            if not path.startswith("zonefiles/") or not path.endswith(".zone"):
                continue
            zone = path.removeprefix("zonefiles/").removesuffix(".zone")
            if not any(domain == zone or domain.endswith("." + zone) for domain in domains):
                continue
            for line in client.get_file(repository, path).splitlines():
                match = re.match(r"^([^;\s]+)\s+(?:\d+\s+)?IN\s+(NS|A|AAAA|CNAME)\s+", line, re.IGNORECASE)
                if not match:
                    continue
                name, kind = match.group(1).rstrip(".").lower(), match.group(2).upper()
                for domain in domains:
                    if kind == "NS" and name == domain and domain != zone:
                        declarations[domain].append(("moc-dns zonefile", path))
                    elif kind != "NS" and name == "*." + domain:
                        wildcards[domain].append(("moc-dns zonefile", path))
    except GitHubError as exc:
        errors.append(str(exc))
    try:
        repository = "CCI-MOC/moc-aws"
        tree = client.get_tree(repository)
        for path in sorted(tree):
            if not path.endswith(".tf"):
                continue
            text = client.get_file(repository, path)
            # Current declarations are flat aws_route53_record resources. Match
            # records, not comments or the hosted_zones map (zone creation alone
            # does not prove delegation).
            for match in re.finditer(r'^resource\s+"aws_route53_record"\s+"[^"\n]+"\s*\{(.*?)^\}', text, re.MULTILINE | re.DOTALL):
                body = match.group(1)
                kind = re.search(r'^\s*type\s*=\s*"([A-Z]+)"', body, re.MULTILINE)
                name = re.search(r'^\s*name\s*=\s*"([^"\n]+)"', body, re.MULTILINE)
                each = re.search(r'^\s*for_each\s*=\s*toset\(\[(.*?)\]\)', body, re.MULTILINE | re.DOTALL)
                names = [name.group(1)] if name else []
                if each and re.search(r'^\s*name\s*=\s*each\.value\s*$', body, re.MULTILINE):
                    names.extend(re.findall(r'"([^"\n]+)"', each.group(1)))
                names = [name.rstrip(".").lower() for name in names]
                for domain in domains:
                    location = (f"moc-aws {path}", path)
                    if kind and kind.group(1) == "NS" and domain in names:
                        declarations[domain].append(location)
                    elif kind and kind.group(1) != "NS" and "*." + domain in names:
                        wildcards[domain].append(location)
    except GitHubError as exc:
        errors.append(str(exc))

    def summarize(records: dict[str, list[tuple[str, str]]]) -> str:
        locations = sorted({location for found in records.values() for location, _path in found})
        if not locations:
            return "unavailable (" + "; ".join(errors) + ")" if errors else "not found in any repository"
        missing = sorted(domain for domain, found in records.items() if not found)
        result = ", ".join(locations)
        if missing:
            result += "; " + ", ".join(missing) + (": unavailable" if errors else ": not found in any repository")
        return result

    return {
        "hosted_cluster_zone_delegation": summarize(declarations),
        "hosted_cluster_wildcard_records": summarize(wildcards),
    }
