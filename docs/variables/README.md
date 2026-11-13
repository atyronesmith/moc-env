# Manual chart-variable definitions

Human-authored documentation lives in one YAML file per topic:

```text
docs/variables/
  dns.yaml
  hosted-cluster.yaml
  networking.yaml
```

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
