# Contributing to moc-env

Thank you for your interest in improving `moc-env`. This project reads public
repository configuration and reports deployment gaps; it does not mutate
GitHub or connect to a live cluster.

## Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Git
- Optional: [pre-commit](https://pre-commit.com/) for local hooks

## Local pre-commit checks

We use Ruff for linting and the standard-library `unittest` suite for tests.
The coverage gate is measured against the `src/moc_env` package and currently
requires at least 84% branch coverage.

Install the locked development environment and run the checks:

```sh
uv sync --locked
uv run --locked ruff check src tests tools
uv run --locked mypy
make test
make coverage
```

Before submitting a pull request, run the full gate:

```sh
make check
```

That target runs Ruff, mypy, the tests under coverage, byte-compilation, the
whitespace and personal-identifier checks, and the package build.

To install the optional pre-commit hook:

```sh
uvx pre-commit install
```

Golden reports and sample reports are generated files. Regenerate them with
the repository tools instead of editing them by hand:

```sh
uv run --locked python tools/generate_report_fixtures.py
make sample-reports
```

## Pull requests

- Create a focused branch and keep one logical change per pull request.
- Add or update tests for behavior changes. The test suite runs offline.
- Update the user guide or samples when the CLI output, checks, or options
  change.
- Do not commit credentials, tokens, personal identifiers, or local report
  output.
- Describe the change, the verification you ran, and any intentionally changed
  expected output in the pull request.

## Commit message standards

Please follow [the seven rules of a great Git commit message][the-7-rules]:

1. Separate the subject from the body with a blank line.
2. Limit the subject line to 50 characters.
3. Capitalize the subject line.
4. Do not end the subject line with a period.
5. Use the imperative mood in the subject line.
6. Wrap the body at 72 characters.
7. Use the body to explain what and why, not how.

[the-7-rules]: https://cbea.ms/git-commit/

While we support the use of AI assistance when working with this repository,
please write commit messages and pull request descriptions yourself.

## Security issues

Do not report suspected vulnerabilities in a public issue. Follow
[SECURITY.md](SECURITY.md) instead.
