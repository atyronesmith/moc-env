# Chart-values documentation plan

## Purpose

`moc-env document-values` should produce an educational, environment-independent
reference for `oac-apps` chart values. The guide should explain how each
configuration value is used, how values relate to one another, and how they fit
into the broader hub-cluster and hosted-workload-cluster deployment.

The first implementation established the variable hierarchy and generated a
useful inventory, but it relied too heavily on tables and per-row source URLs.
The next version should be topic-first and narrative-first, with compact
evidence references and locally cached background documentation.

## Design principles

- **Manual knowledge is authoritative.** Human-written explanations,
  relationships, defaults, warnings, and topic overviews are never overwritten
  by discovery.
- **Discovery is refreshable.** Repository-derived facts can be regenerated at
  any time without losing manual information.
- **The final guide is assembled from both layers.** Discovery supplies where a
  value appears and what repository state shows; manual entries supply what the
  value means and how it is used.
- **Evidence is compact.** Variable tables use short source IDs such as `DNS-1`;
  the guide lists each unique source once in an appendix.
- **Documentation remains local and read-only.** Catalog refresh and document
  generation do not push, create pull requests, comment, or otherwise mutate
  upstream repositories.

## Information layers

### 1. Manual layer

The manual layer contains human-authored content that is version-controlled and
reviewed:

```text
docs/
  sources.yaml
  variables/
    dns.yaml
    networking.yaml
    hosted-cluster.yaml
    identity.yaml
    storage.yaml
    observability.yaml
```

`docs/sources.yaml` registers documentation sources and assigns stable source
IDs. Variable files contain human-written explanations and relationships.

Example manual entry:

```yaml
key: hcpExternalDomain
title: External hosted-control-plane DNS domain
topic: dns
scope: hosted-cluster-defaults
required: false
fallback: hcpInternalDomain
definition: >
  DNS domain used for externally reachable hosted-control-plane endpoints.
  When unset, it inherits hcpInternalDomain.
related:
  - hcpInternalDomain
  - baseDomain
evidence:
  - source: dns-design
    note: Explains internal and external record layouts and the fallback rule.
```

Manual entries may also include:

- `default`;
- `constraints`;
- `when_to_change`;
- `warnings`;
- `examples` that are explicitly non-normative;
- links to related variables and topics;
- notes explaining disagreement between design docs and implementation.

### 2. Discovered layer

The discovered layer is generated from local repository clones and is cached
locally:

```text
.cache/doc-catalog/
  manifest.json
  documents/
  extracts/
  values/
```

The cache is not committed. It records repository commit SHAs, document hashes,
extracted passages, variable occurrences, scopes, charts, types, paths, and
evidence matches.

Discovery should read:

- chart values files;
- chart defaults and comments;
- Helm templates;
- chart unit tests;
- repository documentation and design specs;
- local clones under `../MOC`.

The initial local repository set is:

- `CCI-MOC/oac-apps`;
- `CCI-MOC/oac-infra`;
- `CCI-MOC/moc-infra-config`;
- `CCI-MOC/moc-dns`.

Additional useful repositories include `CCI-MOC/MOC-issues` for request intent
and `CCI-MOC/moc-keycloak` for identity and OIDC behavior.

### 3. Merged layer

The merged layer is the generated Markdown guide. It is not the source of
truth and does not need to be committed.

For each variable, the merged entry combines:

- manual narrative and relationships;
- discovered scopes, charts, types, occurrence counts, and paths;
- compact evidence IDs;
- a clear marker when a newly discovered variable has no manual entry.

The merge is deterministic by default. An optional LLM-assisted mode may draft
prose from the manual and discovered layers, but it must not silently replace
human-authored text. LLM output should be previewed and explicitly accepted
before becoming part of the manual layer.

## Developer workflow

A developer adding a new parameter would:

1. Add or change the parameter in a chart.
2. Run discovery:

   ```sh
   uv run moc-env refresh-doc-catalog
   ```

3. Review the discovery report for new or changed variables.
4. Create a manual entry, either by copying a generated stub or by adding a
   YAML entry directly.
5. Write the human explanation, topic, relationships, defaults, and warnings.
6. Regenerate the guide:

   ```sh
   uv run moc-env document-values
   ```

A future convenience command may create manual stubs:

```sh
uv run moc-env document-values --prepare-stubs
```

Stub creation must never overwrite an existing manual entry. It should only add
missing entries with fields such as `status: needs-definition`.

## Refresh and merge policy

Discovery can be replaced wholesale on every refresh. Manual data is preserved.

When evidence changes:

- unchanged documents keep their source ID and update only their hash if needed;
- changed documents are marked as updated;
- removed documents are marked as missing;
- newly found variables are reported as needing manual definitions;
- variables with no current repository occurrence are reported as possibly
  obsolete;
  manual entries are retained and marked for review rather than deleted.

The refresh report should distinguish:

- new discovered variables;
- changed evidence;
- missing evidence;
- manual entries without current occurrences;
- manual entries that conflict with discovered defaults or constraints.

## Topic-first output

The generated guide should group variables by operational topic before path
scope. For example, the DNS topic would include:

1. a narrative overview of internal and external DNS;
2. the record layout and wildcard behavior;
3. hub-level and cluster-level variable groups;
4. relationships such as `hcpExternalDomain` falling back to
   `hcpInternalDomain`;
5. a compact evidence table.

The path hierarchy remains visible as supporting information, but it should not
be the primary organizing principle.

## Source and URL policy

- Use stable source IDs in variable tables.
- List each unique source once in an appendix.
- Prefer commit-pinned links for design documents.
- Do not emit one URL per variable row.
- Store source repository, path, commit SHA, content hash, and topic tags in
  the catalog.
- Keep cached document content local so generation does not depend on live
  network access after refresh.

## Initial implementation slice

**Status:** All six steps are complete.

1. Add `docs/sources.yaml` with the hosted-cluster address and DNS design
   document as `dns-design`.
2. Move DNS-related definitions into `docs/variables/dns.yaml`.
3. Update the renderer to read manual definitions and produce topic-first
   sections.
4. Add a local catalog refresh command that records commit SHAs and hashes.
5. Add a discovery report that identifies variables without manual entries.
6. Add tests for:
   - manual entries surviving discovery refresh;
   - `hcpExternalDomain` using the DNS design evidence;
   - compact source IDs rather than per-row URLs;
   - newly discovered variables being reported without overwriting manual data.

## Non-goals

- This work does not modify upstream repositories.
- It does not prove that a chart is deployed or healthy.
- It does not replace upstream Helm chart documentation.
- It does not automatically publish generated guides.
- It does not let machine discovery silently overwrite human explanations.
