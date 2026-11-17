# GitHub accounting and PR review verification (2026-11-17)

This note records an authenticated, isolated-cache verification of the
`moc-env` GitHub request accounting and PR replay annotations. Counts are
snapshot-dependent and are not a permanent request budget.

## Request accounting

| Run | HTTP requests | Counted against REST quota | From cache |
|---|---:|---:|---:|
| `status oac-prod --no-prs`, cold | 36 | 14 | 0 |
| `status oac-prod --no-prs`, warm | 36 | 0 | 35 |
| `diff oac-prod bu-ist-demo`, cold | 123 | 17 | 0 |
| `diff oac-prod bu-ist-demo`, warm | 123 | 0 | 123 |
| `diff oac-prod bu-ist-demo --offline` | 0 | 0 | 123 |

The status warm run's extra HTTP request was the free `/rate_limit`
preflight. `diff` does not make that preflight. Raw files fetched by immutable
commit SHA count as HTTP requests but not REST quota calls. Offline mode skips
credential lookup and quota preflight and serves only cached responses.

## PR replay and snapshot drift

PR annotations are based on replaying the relevant check at
`pull/<number>/head`; changed-file overlap only chooses candidates. A `fixed by
open PR ...` annotation means the replay passes, while a `... check still fails
there` annotation includes the replay's failing fields. The selected source is
excluded from annotating itself.

During this verification, `oac-apps` `pull/246/head` resolved to
`071b4677139a893845ffa2ee70e81aad561db32b`, a child of
`625765a730e30a689f3e7e78886b7877f05bc9c8`; the newer head fixed four
address/DNS issues. Authenticated live-head
`status bu-ist-demo --ref oac-apps=pull/246/head --prs --details` showed 5
blocking and 2 advisory gaps. Pinning the earlier snapshot with
`--ref oac-apps=625765a730e30a689f3e7e78886b7877f05bc9c8` showed 9 blocking and
2 advisory gaps. The latter is not a current-live claim.

The raw accounting logs were captured separately as
`/private/tmp/moc-status-{cold,warm}.{txt,err}` and
`/private/tmp/moc-diff-{cold,warm,offline}.{txt,err}`. The final authenticated
reference output and stderr were captured as
`/private/tmp/moc-review-reference-final.txt` and
`/private/tmp/moc-review-reference-final.err`: the current head reported 5
blocking and 2 advisory gaps with 126 requests, 0 counted against quota, and
125 from cache. The pinned review output is
`/private/tmp/moc-review-pinned.txt` with stderr in
`/private/tmp/moc-review-pinned.err` (9 blocking and 2 advisory gaps).

The final `make check` gate passed with 275 tests; a network-none Linux copied
tree run also passed all 275 tests without `.env` or `.venv`. An offline diff
cache miss exits cleanly with code 2 and no HTTP requests. A separate
authenticated `oac-prod` baseline had 29/29 information checks and zero
unknowns. Rerun with an explicit `--ref` and record source SHAs when an
auditable review snapshot is required.
