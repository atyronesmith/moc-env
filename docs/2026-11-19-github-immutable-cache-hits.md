# Immutable SHA-pinned cache hits (2026-11-19)

Before this change, a warm GitHub response cache still made one conditional
HTTP request per cached URL. Raw files pinned to a commit SHA and Git trees
pinned to a commit SHA can never change, so those requests could not return
new content.

`GitHubClient` now recognizes exactly two immutable URL shapes, each with an
exact 40-hex commit SHA in the SHA position:

- `https://raw.githubusercontent.com/<owner>/<repo>/<sha>/<path>`
- `https://api.github.com/repos/<owner>/<repo>/git/trees/<sha>?recursive=1`

In default mode, a cache entry for one of these URLs is served from disk with
no request and counted as a cache hit. Cache misses, `--refresh`, `--offline`,
and every mutable URL such as `/repos/<repo>/commits/<ref>` behave as before.

## Observed request accounting

An isolated, empty cache directory was used for each cold run, followed by a
warm run against the same directory. The environment was unauthenticated, so
the absolute counts reflect the repository snapshots and the configured file
set at the time; the 2026-11-17 note recorded a smaller `oac-prod` snapshot.
Wall-clock seconds include `uv run` startup and network variability.

| Run | HTTP requests | Counted against quota | From cache | Wall seconds |
|---|---:|---:|---:|---:|
| `status oac-prod --no-prs`, cold, before | 178 | 10 | 0 | 23.9 |
| `status oac-prod --no-prs`, warm, before | 178 | 0 | 177 | 11.5 |
| `status oac-prod --no-prs`, cold, after | 178 | 10 | 0 | 14.6 |
| `status oac-prod --no-prs`, warm, after | 8 | 0 | 177 | 3.6 |
| `charts`, cold, before | 196 | 2 | 0 | 12.8 |
| `charts`, warm, before | 196 | 0 | 196 | 9.6 |
| `charts`, cold, after | 196 | 2 | 0 | 9.5 |
| `charts`, warm, after | 1 | 0 | 196 | 1.3 |

The warm `status oac-prod --no-prs` run after the change made one free
`/rate_limit` preflight and seven mutable `/commits/main` lookups, with zero
requests to `raw.githubusercontent.com` and zero to `/git/trees/<sha>`. Its 177
cache hits were 167 raw files, 3 trees, and 7 revalidated commit responses.
The warm `charts` run made only the `oac-apps` `/commits/main` lookup; its 196
cache hits were 194 raw files, 1 tree, and 1 revalidated commit response.

Cold and warm stdout were byte-identical for both commands when run within the
same UTC minute (the status header embeds the current minute). An `--offline`
`status oac-prod --no-prs` after the warm run made zero HTTP requests and
differed only by the `from cache, fetched <time>` lines that offline mode
already adds.

With `--ref oac-apps=pull/246/head`, the second `status bu-ist-demo` run made
one request for `/repos/CCI-MOC/oac-apps/commits/pull/246/head` and none for
the raw files or trees pinned to the resolved commit SHA.
