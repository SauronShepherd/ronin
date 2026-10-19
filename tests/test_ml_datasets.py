from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetRevision, AssetVersion, CatalogAsset
from studio_ml.datasets import DatasetReferenceError, DatasetResolver, resolve_lab_rows
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import LocalExecutionCoordinator
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.services import InMemoryMLLabStore, LabService


class _Catalog:
    def __init__(
        self, asset: CatalogAsset, revision: AssetRevision, visible_workspace: str = "workspace-a"
    ) -> None:
        self.asset = asset
        self.revision = revision
        self.visible_workspace = WorkspaceId(visible_workspace)
        self.requested_workspaces: list[WorkspaceId] = []

    def get_asset(self, workspace_id, asset_id):
        self.requested_workspaces.append(workspace_id)
        return (
            self.asset
            if workspace_id == self.visible_workspace and asset_id == self.asset.id
            else None
        )

    def get_revision(self, workspace_id, ref):
        self.requested_workspaces.append(workspace_id)
        return (
            self.revision
            if self.revision is not None
            and workspace_id == self.visible_workspace
            and ref == self.revision.ref
            else None
        )


class _Artifacts:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.request: tuple[str, str] | None = None

    def get_bytes_by_storage_ref(self, storage_ref: str, *, digest: str) -> bytes:
        self.request = storage_ref, digest
        return self.data


def _resolver(data: bytes, media_type: str = "text/csv"):
    digest = hashlib.sha256(data).hexdigest()
    ref = AssetRef(AssetId("customers"), AssetVersion(f"sha256:{digest}"))
    revision = AssetRevision(
        ref,
        content_digest=f"sha256:{digest}",
        metadata=(
            ("artifact_ref", f"artifact://sha256/{digest}"),
            ("media_type", media_type),
        ),
    )
    asset = CatalogAsset(ref.asset_id, "dataset", "Customers")
    catalog = _Catalog(asset, revision)
    artifacts = _Artifacts(data)
    return DatasetResolver(catalog, artifacts), catalog, artifacts, ref


def test_resolve_csv_snapshot_is_workspace_scoped_and_digest_verified() -> None:
    resolver, catalog, artifacts, ref = _resolver(b"x,target\n1,yes\n2,no\n")

    rows = resolver.resolve(WorkspaceId("workspace-a"), ref)

    assert rows == [{"x": "1", "target": "yes"}, {"x": "2", "target": "no"}]
    assert catalog.requested_workspaces == [WorkspaceId("workspace-a")] * 2
    assert artifacts.request == (
        ref.version.value.replace("sha256:", "artifact://sha256/"),
        ref.version.value.removeprefix("sha256:"),
    )


def test_resolve_jsonl_snapshot_preserves_native_values() -> None:
    data = b'{"x":1,"target":true}\n\n{"x":2,"target":false}\n'
    resolver, _catalog, _artifacts, ref = _resolver(data, "application/x-ndjson")

    assert resolver.resolve(WorkspaceId("workspace-a"), ref) == [
        {"x": 1, "target": True},
        {"x": 2, "target": False},
    ]


@pytest.mark.parametrize(
    ("data", "media_type", "message"),
    [
        (b"x,x\n1,2\n", "text/csv", "headers"),
        (b"x,target\n1\n", "text/csv", "width"),
        (b'x,target\n"1,yes\n', "text/csv", "malformed"),
        (b"not json\n", "application/x-ndjson", "invalid JSON"),
        (b'{"x":NaN}\n', "application/x-ndjson", "invalid JSON"),
        (b"[]\n", "application/x-ndjson", "must be an object"),
        (b'{" x ":1}\n', "application/x-ndjson", "must be an object"),
    ],
)
def test_resolve_rejects_malformed_rows(data: bytes, media_type: str, message: str) -> None:
    resolver, _catalog, _artifacts, ref = _resolver(data, media_type)

    with pytest.raises(DatasetReferenceError, match=message):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_rejects_revision_digest_mismatch() -> None:
    resolver, catalog, _artifacts, ref = _resolver(b"x,target\n1,yes\n")
    catalog.revision = AssetRevision(
        ref,
        content_digest="sha256:" + "0" * 64,
        metadata=catalog.revision.metadata,
    )

    with pytest.raises(DatasetReferenceError, match="digest does not match"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_rejects_missing_revision_and_unsupported_artifact() -> None:
    resolver, catalog, _artifacts, ref = _resolver(b"x,target\n1,yes\n")
    catalog.asset = CatalogAsset(ref.asset_id, "file", "Customers")
    with pytest.raises(DatasetReferenceError, match="missing or is not a dataset"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)

    resolver, catalog, _artifacts, ref = _resolver(b"x,target\n1,yes\n")
    catalog.revision = None
    with pytest.raises(DatasetReferenceError, match="revision is missing"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)

    resolver, catalog, _artifacts, ref = _resolver(b"x,target\n1,yes\n")
    catalog.revision = AssetRevision(
        ref,
        content_digest=catalog.revision.content_digest,
        metadata=(("artifact_ref", "https://example.invalid/data.csv"), ("media_type", "text/csv")),
    )
    with pytest.raises(DatasetReferenceError, match="not backed by a supported artifact"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_rejects_unavailable_artifact_reader() -> None:
    resolver, catalog, _artifacts, _ref = _resolver(b"x,target\n1,yes\n")
    resolver = DatasetResolver(catalog, object())
    ref = catalog.revision.ref
    with pytest.raises(DatasetReferenceError, match="cannot resolve dataset storage references"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_wraps_missing_artifact_and_invalid_utf8() -> None:
    resolver, _catalog, artifacts, ref = _resolver(b"x,target\n1,yes\n")
    artifacts.get_bytes_by_storage_ref = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        FileNotFoundError("missing")
    )
    with pytest.raises(DatasetReferenceError, match="unavailable or invalid"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)

    for data, media_type in ((b"\xff", "text/csv"), (b"\xff", "application/x-ndjson")):
        resolver, _catalog, _artifacts, ref = _resolver(data, media_type)
        with pytest.raises(DatasetReferenceError, match="must be UTF-8"):
            resolver.resolve(WorkspaceId("workspace-a"), ref)


@pytest.mark.parametrize(
    ("data", "media_type"),
    [(b"x,target\n", "text/csv"), (b"\n \n", "application/x-ndjson")],
)
def test_resolve_rejects_empty_dataset(data: bytes, media_type: str) -> None:
    resolver, _catalog, _artifacts, ref = _resolver(data, media_type)
    with pytest.raises(DatasetReferenceError, match="at least one row"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_lab_rows_validates_inline_data_and_requires_a_resolver() -> None:
    _resolver_instance, _catalog, _artifacts, ref = _resolver(b"x,target\n1,yes\n")
    lab = Lab(
        "dataset-lab",
        "Dataset Lab",
        "project-1",
        ref,
        "target",
        "classification",
        (FeatureSpec("x", "numeric"),),
    )
    assert resolve_lab_rows(WorkspaceId("workspace-a"), lab, [{"x": 1}], None) == [{"x": 1}]
    with pytest.raises(ValueError, match="array of objects"):
        resolve_lab_rows(WorkspaceId("workspace-a"), lab, ["bad row"], None)
    with pytest.raises(DatasetReferenceError, match="stores are unavailable"):
        resolve_lab_rows(WorkspaceId("workspace-a"), lab, None, None)


def test_resolve_rejects_artifact_content_digest_mismatch() -> None:
    resolver, _catalog, artifacts, ref = _resolver(b"x,target\n1,yes\n")
    artifacts.data = b"x,target\n1,no\n"

    with pytest.raises(DatasetReferenceError, match="content digest is invalid"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_resolve_enforces_row_column_and_byte_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    import studio_ml.datasets as datasets

    resolver, _catalog, _artifacts, ref = _resolver(b"x,target\n1,0\n2,1\n")
    monkeypatch.setattr(datasets, "MAX_DATASET_ROWS", 1)
    with pytest.raises(DatasetReferenceError, match="100000 row limit"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)

    monkeypatch.setattr(datasets, "MAX_DATASET_ROWS", 100_000)
    jsonl_resolver, _catalog, _artifacts, jsonl_ref = _resolver(
        b'{"a":1}\n{"b":2}\n', "application/x-ndjson"
    )
    monkeypatch.setattr(datasets, "MAX_DATASET_COLUMNS", 1)
    with pytest.raises(DatasetReferenceError, match="1024 column limit"):
        jsonl_resolver.resolve(WorkspaceId("workspace-a"), jsonl_ref)

    monkeypatch.setattr(datasets, "MAX_DATASET_COLUMNS", 1024)
    monkeypatch.setattr(datasets, "MAX_DATASET_ROWS", 1)
    with pytest.raises(DatasetReferenceError, match="100000 row limit"):
        jsonl_resolver.resolve(WorkspaceId("workspace-a"), jsonl_ref)

    monkeypatch.setattr(datasets, "MAX_DATASET_COLUMNS", 1024)
    monkeypatch.setattr(datasets, "MAX_DATASET_ROWS", 100_000)
    monkeypatch.setattr(datasets, "MAX_DATASET_BYTES", 2)
    with pytest.raises(DatasetReferenceError, match="64 MiB limit"):
        resolver.resolve(WorkspaceId("workspace-a"), ref)


def test_quality_endpoint_reads_the_lab_dataset_when_rows_are_omitted() -> None:
    rows = "\n".join(f"{number},{number % 2}" for number in range(1, 21))
    resolver, _catalog, _artifacts, ref = _resolver(f"x,target\n{rows}\n".encode())
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    plugin._dataset_resolver = resolver
    lab = Lab(
        "dataset-lab",
        "Dataset Lab",
        "project-1",
        ref,
        "target",
        "classification",
        (FeatureSpec("x", "numeric"),),
    )
    plugin._labs.create(WorkspaceId("workspace-a"), lab)
    try:
        report = plugin.quality_check("workspace-a", "dataset-lab", body={})
        assert report["row_count"] == 20
        assert report["passed"] is True
        plugin._runner = SimpleNamespace(
            run=lambda _lab, resolved_rows: SimpleNamespace(
                to_payload=lambda: {"rows": resolved_rows}
            )
        )
        result = plugin.run_lab("workspace-a", "dataset-lab", body={})
        assert result["rows"][0] == {"x": "1", "target": "1"}
        observed_rows: list[dict[str, object]] = []

        class _CapturingRunner:
            def run(self, _lab, input_rows):
                observed_rows.extend(input_rows)
                return SimpleNamespace(to_payload=lambda: {"accepted": True})

        plugin._coordinator.close()
        plugin._coordinator = LocalExecutionCoordinator(_CapturingRunner())
        submitted = plugin.submit_execution(
            "workspace-a", "dataset-lab", body={"run_id": "assetref-run"}
        )
        assert submitted["run_id"] == "assetref-run"
        deadline = time.monotonic() + 5
        execution = plugin.execution_status("assetref-run", workspace_id="workspace-a")
        while execution["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            execution = plugin.execution_status("assetref-run", workspace_id="workspace-a")
        assert execution["state"] == "succeeded"
        assert observed_rows[0] == {"x": "1", "target": "1"}
        with pytest.raises(DatasetReferenceError, match="missing or is not a dataset"):
            resolver.resolve(WorkspaceId("workspace-b"), ref)
    finally:
        plugin.shutdown()
