from __future__ import annotations

import pytest
from studio_storage import ArtifactIntegrityError, ArtifactStore, S3ArtifactStore


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **kwargs: object) -> None:
        del kwargs
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> None:
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **kwargs: str) -> dict[str, object]:
        del kwargs
        return {
            "Contents": [
                {"Key": key}
                for bucket, key in self.objects
                if bucket == Bucket and key.startswith(Prefix)
            ],
            "IsTruncated": False,
        }


class _TransientError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("temporary")
        self.response = {"Error": {"Code": "503"}}


class _RetryClient(_Client):
    def __init__(self) -> None:
        super().__init__()
        self.failures = 2

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **kwargs: object) -> None:
        if self.failures:
            self.failures -= 1
            raise _TransientError
        super().put_object(Bucket=Bucket, Key=Key, Body=Body, **kwargs)


def test_s3_store_is_content_addressed_and_verifies_round_trip() -> None:
    client = _Client()
    store = S3ArtifactStore("ronin-test", client=client)
    assert isinstance(store, ArtifactStore)
    ref = store.put_bytes(role="model", data=b"model", media_type="application/octet-stream")

    assert ref.storage_ref.startswith("s3://ronin-test/ronin/artifacts/sha256/")
    assert store.get_bytes(ref) == b"model"
    assert store.verify(ref)
    assert store.list_digests() == (ref.digest,)
    assert store.storage_ref_for_digest(ref.digest) == ref.storage_ref
    assert store.delete(ref)
    assert not store.verify(ref)
    assert not store.delete(ref)


def test_s3_store_rejects_tampered_content() -> None:
    client = _Client()
    store = S3ArtifactStore("ronin-test", client=client)
    ref = store.put_bytes(role="model", data=b"model")
    key = next(iter(client.objects))
    client.objects[key] = b"tampered"

    try:
        store.get_bytes(ref)
    except ArtifactIntegrityError:
        pass
    else:
        raise AssertionError("tampered S3 artifact was accepted")


def test_s3_store_validates_endpoint_and_region_configuration() -> None:
    client = _Client()
    store = S3ArtifactStore(
        "ronin-test",
        endpoint_url="http://minio:9000",
        region_name="us-east-1",
        client=client,
    )
    assert store.storage_ref_for_digest("a" * 64).startswith("s3://ronin-test/")
    with pytest.raises(ValueError, match="endpoint URL"):
        S3ArtifactStore("ronin-test", endpoint_url="\n", client=client)
    with pytest.raises(ValueError, match="region name"):
        S3ArtifactStore("ronin-test", region_name=" ", client=client)


def test_s3_store_retries_transient_provider_failures() -> None:
    client = _RetryClient()
    store = S3ArtifactStore("ronin-test", client=client, retry_delay_seconds=0)
    ref = store.put_bytes(role="model", data=b"model")
    assert ref.digest
    assert client.failures == 0


def test_s3_artifact_page_accepts_numeric_only_sha256_digest() -> None:
    client = _Client()
    store = S3ArtifactStore("ronin-test", client=client)
    digest = "0" * 64
    client.objects[("ronin-test", "ronin/artifacts/sha256/" + digest)] = b""
    page = store.list_digests_page(page_size=1)
    assert page.digests == (digest,)


def test_s3_artifact_page_rejects_unbounded_or_control_cursor() -> None:
    store = S3ArtifactStore("ronin-test", client=_Client())
    with pytest.raises(ValueError, match="bounded opaque"):
        store.list_digests_page(cursor="x\n")
    with pytest.raises(ValueError, match="bounded opaque"):
        store.list_digests_page(cursor="x" * 2049)
