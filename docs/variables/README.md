# Manual chart-variable definitions

Human-authored documentation lives in one YAML file per topic. The current
manual definition set covers DNS:

```text
docs/variables/
  dns.yaml
```

Add another topic file when a new area has reviewed explanations. Register any
new source documents in `docs/sources.yaml` before referencing them.

Each file contains the topic overview and the manual variable entries. A human
can add a new variable by copying an existing entry and filling in:

- `key`;
- `title`;
- `group`;
- `required`;
- `definition`;
- `related`;
- `default` or `fallback`;
- `evidence`.

Discovery never edits these files. It only reports variables that are missing
from them or manual entries that no longer match the repository.
