# Review-fix acceptance criteria

This follow-up verifies the original eight fixes against explicit properties,
not just the original reproductions. Tests and all repository reads are offline.

## Scope and classification

| Follow-up finding | Classification | Required behavior |
|---|---|---|
| Omitted workloads still match | Incomplete workload-comparison fix, exposed by valid empty bundles | Compare desired and actually discovered workload sets in both directions. |
| Inventory placeholders count as present | Pre-existing comparison weakness left unresolved | A group is present only when inventory evidence says it was found. |
| Neighboring names and query strings identify an image | Pre-existing substring weakness copied into the shared helper | Match a complete supported cluster alias in the filename from the URL path. |
| Changed PR identity reuses URL-only memory entries | Incomplete cache-identity fix | All file-list cache layers and pagination follow the observed head/base identity. |
| Quota exhaustion promotes stale URL-keyed disk pages | Additional cache boundary found by independent review | Safely report unavailable evidence instead of publishing unvalidated pages under a new identity. |
| Malformed pool names crash detailed reports | Additional malformed-input gap found by independent review | Reject malformed names and render the resulting diagnostic safely in text, Markdown, and JSON. |

## Positive and negative acceptance cases

- Workload sets: equal empty/nonempty sets match; ordering is irrelevant;
  missing, additional, and mixed differences are reported. An empty desired
  list must not conceal observed workloads. Hub-only exports remain valid.
- Inventory presence: real groups count as present, even with zero hosts;
  absent groups and synthetic placeholders do not. Check both environment and
  workload comparisons, including their CLI exit status.
- Images: preserve supported workload/parent-hub names and `oac-`-shortened
  aliases. Reject neighboring names, unrelated prefixes, and names found only
  in a query or fragment. Both status and comparison use the same rule.
- PR cache: unchanged identities reuse complete lists; head/base transitions
  within one client cannot reuse old pages or publish them under a new identity.
  Verify pagination, a subsequent fresh client, refresh, and offline misses.
  Exhausting quota before the first or a later page must not promote stale
  URL-keyed pages into a complete identity-specific cache entry.
- Malformed pools: list/dict names must produce an actionable finding, not a
  false pass or an exception in detailed text, Markdown, or JSON rendering.

## Original eight-fix coverage

1. Exact node selectors: positive equality and wrong-prefix negatives.
2. Discovery-based exports: multiple workloads, workload1-only, hub-only,
   deterministic order, full/short names, and unknown selections.
3. Comparisons: per-workload paths, complete workload sets, and real presence.
4. Discovery images: valid aliases plus boundary and URL-component negatives.
5. Malformed node pools: actionable findings without crashes or false passes;
   retain explicit zero and supported omitted-replica behavior.
6. PR cache: identity across disk and memory, pagination, refresh, and offline.
7. Fleet output: JSON/text files, empty stdout, failure status, and list cache.
8. Documentation defaults: preserve false, zero, and empty strings; use fallback
   only when the default is absent.

## Regression test map

| Original fix | Focused test files |
|---|---|
| Exact selectors | `tests/test_node_pool_selector_regressions.py` |
| Discovery exports | `tests/test_desired_state_review_fixes.py` |
| Comparisons and actual presence | `tests/test_comparison_acceptance.py`, `tests/test_compare.py`, `tests/test_desired_state_review_fixes.py` |
| Image identity | `tests/test_boot_image_acceptance.py`, `tests/test_desired_state_review_fixes.py` |
| Malformed pools and safe diagnostics | `tests/test_node_pool_selector_regressions.py`, `tests/test_node_pool_render_acceptance.py` |
| PR cache identity | `tests/test_pr_file_cache.py`, `tests/test_pr_cache_identity_acceptance.py` |
| Fleet output | `tests/test_desired_state_review_fixes.py`, `tests/test_output_format_inference.py` |
| Falsey documentation defaults | `tests/test_chart_values_defaults_regressions.py` |

## Verification and review

New counterexamples must fail before implementation and pass afterward.
An independent reviewer receives these requirements, the source, and the diff,
without an implementation success summary. Confirmed findings become permanent
regression tests and their corrections are reviewed again. Completion requires
no unresolved in-scope findings, a successful `make check`, reviewed generated
samples, and a package containing all required modules. This is bounded
verification, not a proof of correctness for every possible input.

## Recorded verification

- Comparison counterexamples were run before correction and reproduced nine
  failing assertions/subtests, including false-success CLI exit codes.
- Image-boundary and PR-identity counterexamples failed before their respective
  corrections. Subsequent independent review found the quota-boundary cache and
  malformed-name rendering gaps; both received failing regression coverage
  before correction and were independently re-tested afterward.
- The independent reviewer examined all eight original fixes and the follow-up
  requirements, ran 76 focused tests plus separate CLI/cache reproductions, and
  reported no unresolved confirmed in-scope findings.
- The final acceptance suite contains 25 tests. The complete `make check` gate
  passes with 740 tests and 87% coverage, including lint, typing, compilation,
  whitespace, personal-identifier checks, and source/wheel packaging.
- Regenerated samples are deterministic. Their intended changes are restored
  false DNS defaults and the description allowing hub-only workload lists.
- Verification is offline and bounded. It does not assert live-cluster health,
  exhaustive input coverage, or atomic consistency if remote GitHub data changes
  between separate HTTP requests.
