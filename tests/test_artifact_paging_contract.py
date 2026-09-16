from studio_storage import LocalArtifactStore, PagedArtifactStore, S3ArtifactStore


def test_artifact_paging_capability_is_explicit(tmp_path) -> None:
    assert isinstance(LocalArtifactStore(tmp_path / "local"), PagedArtifactStore)
    assert isinstance(S3ArtifactStore("bucket", client=object()), PagedArtifactStore)
