# Security policy

## Supported versions

Security fixes target the current `main` branch and the most recent tagged
release, if one exists. Older snapshots are not supported.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting from the repository's
**Security** tab. Do not open a public issue for a suspected vulnerability.

Include the affected version or commit, the command or code path involved, and
the smallest reproduction you can provide. Avoid including live credentials or
personal data in the report.

## Scope

`moc-env` reads public CCI-MOC repository configuration through the GitHub API.
It does not connect to live clusters or write repository changes. Relevant
security concerns include:

- handling of GitHub and Bitwarden credentials;
- credential or token disclosure in reports, logs, cache, or generated files;
- unsafe parsing of untrusted repository content;
- dependency and build-supply-chain vulnerabilities.

## Credentials and secrets

- Use a read-only token with access only to the public repositories the tool
  needs.
- Never commit `.env`, tokens, secret IDs, or generated reports containing
  credentials.
- Prefer environment variables or a secret manager over command-line
  arguments, which can be visible to other local users.
- If you believe a token was exposed, revoke it first, then report the issue.

## What to expect

Reports are reviewed on a best-effort basis. We will acknowledge a valid
report, investigate its impact, and coordinate disclosure through the private
reporting thread. Please allow time for a fix before public disclosure.
