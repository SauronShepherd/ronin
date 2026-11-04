# Local SQL and semantic Parquet sources

The local-composed profile shares one project-isolated DuckDB engine between
the SQL endpoint and Semantic Studio. It loads `*.parquet` relations from a
project directory when that project's SQL or semantic query runs, and refreshes
the registered views on subsequent requests so an atomic file replacement or
removal is visible without restarting Ronin.

## Directory layout

Set `RONIN_SQL_PARQUET_ROOT` to a directory. If it is unset, local-composed
uses `sql-parquet` beside the configured `RONIN_DB` file. Under that root,
store each table as `<encoded-project-scope>/<relation>.parquet`. The encoded
scope is the URL-escaped value returned by Ronin's canonical
`semantic_project_scope(workspace_id, project_id)` function. The Parquet
filename stem is the SQL relation name and must be a portable SQL identifier.

For example, for workspace `default` and project `examples/demo`:

```python
from pathlib import Path
from urllib.parse import quote

from studio_semantic import semantic_project_scope

root = Path(".ronin/sql-parquet")
scope = semantic_project_scope("default", "examples/demo")
project_directory = root / quote(scope, safe="")
project_directory.mkdir(parents=True, exist_ok=True)
print(project_directory)
```

Place `orders.parquet` in the printed directory and set the semantic model's
`source` to `orders`. SQL Studio and Semantic Studio then query the same table
inside that workspace/project namespace. Other projects receive separate
directories even when they use the same relation name. The server rejects
symbolic links, paths outside the configured root, and filenames that are not
valid relation identifiers.

Write new datasets to a temporary file in the same directory and atomically
replace the final Parquet file. Removed relation files are dropped from that
project's DuckDB connection the next time it is queried. This is a local
file-backed source contract; it does not claim automatic ingestion, PostgreSQL
table discovery, or a multi-user authorization model.
