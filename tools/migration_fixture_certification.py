"""Run the executable, credential-free migration certification subset.

This command deliberately certifies only the checked-in golden fixtures.  It
does not claim authenticated provider compatibility; that evidence must come
from the provider qualification environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio_core import Workspace, WorkspaceId
from studio_execution.bundle_workflow import export_workflow_bundle
from studio_execution.bundle_workflow_commit import commit_workflow_bundle_import
from studio_migration import (
    discover_databricks,
    discover_dataiku,
    discover_fabric,
    discover_foundry,
    translate_code_recipes,
    translate_notebook_items,
    translate_notebook_job,
    translate_python_functions,
)
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore

try:
    from tools.migration_certification import STATUSES, validate
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from migration_certification import STATUSES, validate

ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "migration"
NOW = "2026-09-24T00:00:00.000000Z"

Profile = tuple[
    str,
    str,
    Callable[[str | bytes], Any],
    Callable[[str | bytes], Any],
]

PROFILES: tuple[Profile, ...] = (
    ("fabric", "fabric-items.json", discover_fabric, translate_notebook_items),
    ("databricks", "databricks-job.json", discover_databricks, translate_notebook_job),
    ("foundry", "foundry-functions.json", discover_foundry, translate_python_functions),
    ("dataiku", "dataiku-recipes.json", discover_dataiku, translate_code_recipes),
)


def certify_fixture(
    profile: str,
    filename: str,
    discover: Callable[..., Any],
    translate: Callable[..., Any],
    output: Path,
) -> dict[str, Any]:
    source = (ROOT / filename).read_bytes()
    discovered = discover(source, source_version="golden-2026")
    if not discovered.objects:
        raise RuntimeError(f"{profile} discovery returned no source objects")
    converted = translate(source, source_version="golden-2026")
    report = converted.report
    workspace_id = WorkspaceId(f"migration-certification-{profile}")
    source_db = output / f"{profile}-source.sqlite"
    target_db = output / f"{profile}-target.sqlite"
    source_store = SqliteWorkflowBundleImportStore(source_db, migration_now=NOW)
    target_store = SqliteWorkflowBundleImportStore(target_db, migration_now=NOW)
    workspace = Workspace(workspace_id, f"Migration {profile}")
    source_store.create_workspace(workspace, now=NOW)
    target_store.create_workspace(workspace, now=NOW)
    source_store.put_workflow(workspace_id, converted.workflow, now=NOW)
    schedule = getattr(converted, "schedule", None)
    if schedule is not None:
        source_store.put_schedule(workspace_id, schedule, now=NOW)
    bundle_path = output / f"{profile}.roninbundle"
    manifest = export_workflow_bundle(
        source_store, workspace_id, (converted.workflow.id,), bundle_path
    )
    outcome = commit_workflow_bundle_import(bundle_path, target_store, workspace_id, now=NOW)
    reexport_path = output / f"{profile}-reexport.roninbundle"
    reexport = export_workflow_bundle(
        target_store, workspace_id, (converted.workflow.id,), reexport_path
    )
    if manifest.digest != reexport.digest:
        raise RuntimeError(f"{profile} Bundle round-trip changed the canonical manifest")
    counts = dict.fromkeys(STATUSES, 0)
    source_ids: list[str] = []
    classifications: list[dict[str, str]] = []
    for item in report.objects:
        counts[item.status] += 1
        source_ids.append(item.source_id)
        classifications.append({"source_object_id": item.source_id, "status": item.status})
    evidence = {
        "schema": "ronin.migration-certification/v1",
        "profile": profile,
        "source_inventory_digest": hashlib.sha256(source).hexdigest(),
        "report_digest": report.digest,
        "bundle_roundtrip_digest": manifest.digest,
        "execution_status": "passed",
        "classification_counts": counts,
        "source_object_ids": source_ids,
        "classifications": classifications,
        "workflow_imported": outcome.commit.workflows_created == 1,
        "workflow_reexport_digest": reexport.digest,
    }
    validate(evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("qualification-evidence/migration"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for profile, filename, discover, translate in PROFILES:
        evidence = certify_fixture(profile, filename, discover, translate, args.output)
        path = args.output / f"{profile}-certification.json"
        path.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"migration fixture certification: {profile} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
