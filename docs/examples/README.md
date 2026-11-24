# Live examples

This directory is reserved for real chart and status output from a named
`oac-apps` commit. These examples are refreshed by hand and are not kept
current. They are not the offline fixture samples under `docs/samples/`,
whose synthetic banner and fixture guard must remain intact.

No generated output is included yet. To prepare a manual refresh:

```sh
make sample-live
make update-samples
```

`sample-live` writes `charts-summary.md`, `charts-page.md`,
`status-oac-prod.md`, and `status-compliant-dev.md` into `SAMPLE_DIR`
(default `reports/samples`, ignored by Git). `update-samples` checks that all
four files exist, then copies them into `EXAMPLE_DIR` (default
`docs/examples`). Both directories can be overridden on the command line.
Neither command commits the files or keeps them synchronized automatically.

Before publishing, review the diff and remove sensitive information. Record
the capture date and the full named `oac-apps` commit SHA reported by the
output in this README with each refresh. Check that all four reports use the
intended commit; other source repositories and their SHAs remain recorded in
the status reports. Do not put live examples in `docs/samples/`.
