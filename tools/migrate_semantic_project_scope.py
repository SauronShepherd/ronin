"""Move legacy unscoped semantic rows into one explicitly selected workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_semantic import SqliteSemanticStore, semantic_project_scope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="Ronin SQLite database path")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--legacy-project-id",
        help="defaults to --project-id; specify only when the legacy key differs",
    )
    args = parser.parse_args()
    if not args.workspace_id.strip() or args.workspace_id != args.workspace_id.strip():
        parser.error("--workspace-id must be non-empty and trimmed")
    if not args.project_id.strip() or args.project_id != args.project_id.strip():
        parser.error("--project-id must be non-empty and trimmed")
    legacy_project_id = args.legacy_project_id or args.project_id
    if not legacy_project_id.strip() or legacy_project_id != legacy_project_id.strip():
        parser.error("--legacy-project-id must be non-empty and trimmed")

    scope = semantic_project_scope(args.workspace_id, args.project_id)
    result = SqliteSemanticStore(args.database).migrate_legacy_project_scope(
        legacy_project_id, scope
    )
    print(json.dumps({"workspace_id": args.workspace_id, "project_id": args.project_id, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
