#!/usr/bin/env bash

set -euo pipefail

input="${1:-reports/chart-values.md}"
output="${2:-reports/chart-values.html}"
title="${3:-Chart Configuration Reference}"
css_cache=".cache/github-markdown.css"
page_css="${BASH_SOURCE[0]%/*}/github-markdown-page.css"
no_table_widths="${BASH_SOURCE[0]%/*}/pandoc-no-table-widths.lua"
css_url="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.8.1/github-markdown.min.css"

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc is required" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to fetch github-markdown-css" >&2
  exit 1
fi

mkdir -p "$(dirname "$output")" "$(dirname "$css_cache")"

if [[ ! -s "$css_cache" ]]; then
  curl -fsSL "$css_url" -o "$css_cache"
fi

before="$(mktemp)"
after="$(mktemp)"
trap 'rm -f "$before" "$after"' EXIT

printf '<article class="markdown-body">\n' >"$before"
printf '</article>\n' >"$after"

pandoc "$input" \
  --standalone \
  --toc \
  --lua-filter "$no_table_widths" \
  --embed-resources \
  --css "$css_cache" \
  --css "$page_css" \
  --include-before-body "$before" \
  --include-after-body "$after" \
  --metadata title="$title" \
  --output "$output"

echo "wrote GitHub-styled HTML to $output"
