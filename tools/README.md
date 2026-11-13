# Helper tools

## `md2html.sh`

Render a Markdown file as a standalone HTML page using GitHub Markdown styling.

```sh
tools/md2html.sh [INPUT] [OUTPUT] [TITLE]
```

Defaults:

- `INPUT`: `reports/chart-values.md`
- `OUTPUT`: `reports/chart-values.html`
- `TITLE`: `Chart Configuration Reference`

The script:

- uses `pandoc`;
- downloads `github-markdown-css` once into `.cache/github-markdown.css`;
- wraps the rendered body in `<article class="markdown-body">`;
- embeds the stylesheet in the standalone HTML output;
- follows the browser’s light or dark theme;
- centers the document in a 978-pixel reading area, similar to GitHub’s
  rendered Gist view;
- lets wide tables scroll horizontally with a visible custom scrollbar,
  matching GitHub’s rendered Gist behavior;
- uses the upstream GitHub Markdown stylesheet for typography, with only a
  small page-level wrapper stylesheet for width and theme.
