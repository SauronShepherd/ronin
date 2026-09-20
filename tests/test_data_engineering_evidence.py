import json
from pathlib import Path

from studio_data_engineering import persist_pipeline_evidence
from studio_storage import LocalArtifactStore


def test_pipeline_evidence_is_content_addressed_and_recoverable(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = persist_pipeline_evidence(
        store,
        project_id="p",
        run_id="run-1",
        output={"rows": [{"id": 1}]},
        evidence={"runtime": "local-preview", "row_count": 1},
    )
    payload = json.loads(store.get_bytes(ref))
    assert payload["version"] == "data-engineering.evidence.v1"
    assert payload["run_id"] == "run-1"
    assert payload["evidence"]["runtime"] == "local-preview"
