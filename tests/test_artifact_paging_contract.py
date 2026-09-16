from studio_storage import LocalArtifactStore, PagedArtifactStore, S3ArtifactStore


def test_artifact_paging_capability_is_explicit(tmp_path) -> None:
    assert isinstance(LocalArtifactStore(tmp_path / "local"), PagedArtifactStore)
    assert isinstance(S3ArtifactStore("bucket", client=object()), PagedArtifactStore)


def test_artifact_page_rejects_invalid_digest_or_cursor_shape() -> None:
    import pytest

    from studio_storage import ArtifactPage

    with pytest.raises(ValueError, match="invalid SHA-256"):
        ArtifactPage(("not-a-digest",), None, False)
    with pytest.raises(ValueError, match="exactly one cursor"):
        ArtifactPage(("0" * 64,), None, True)
