"""S3-compatible content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .artifacts import ArtifactIntegrityError, ArtifactPage, ArtifactRef


class S3DependencyError(RuntimeError):
    """Raised when boto3 is unavailable for S3-compatible artifact storage."""


class S3ArtifactStore:
    """Store immutable artifacts behind an S3-compatible object API."""

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "ronin/artifacts",
        endpoint_url: str | None = None,
        region_name: str | None = None,
        client: Any = None,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.05,
    ) -> None:
        if not bucket or bucket != bucket.strip() or "/" in bucket:
            raise ValueError("S3 bucket must be non-empty and contain no slash")
        if prefix.startswith("/") or prefix.endswith("/"):
            raise ValueError("S3 artifact prefix must not start or end with slash")
        if endpoint_url is not None and (
            not endpoint_url or endpoint_url != endpoint_url.strip() or "\n" in endpoint_url
        ):
            raise ValueError("S3 endpoint URL must be non-empty, trimmed, and single-line")
        if region_name is not None and (
            not region_name or region_name != region_name.strip() or "\n" in region_name
        ):
            raise ValueError("S3 region name must be non-empty, trimmed, and single-line")
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("S3 max_attempts must be between 1 and 10")
        if retry_delay_seconds < 0 or retry_delay_seconds > 5:
            raise ValueError("S3 retry delay must be between 0 and 5 seconds")
        self._bucket = bucket
        self._prefix = prefix
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._client = (
            client
            if client is not None
            else self._load_client(endpoint_url=endpoint_url, region_name=region_name)
        )

    def _call(self, operation: str, **kwargs: object) -> Any:
        """Call S3 with bounded retries for explicitly transient failures."""

        for attempt in range(self._max_attempts):
            try:
                return getattr(self._client, operation)(**kwargs)
            except Exception as exc:
                response = getattr(exc, "response", None)
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                code = error.get("Code") if isinstance(error, dict) else None
                transient = code in {
                    "408",
                    "425",
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "RequestTimeout",
                    "SlowDown",
                    "Throttling",
                    "InternalError",
                }
                if not transient or attempt + 1 >= self._max_attempts:
                    raise
                delay = self._retry_delay_seconds * (2**attempt)
                if delay:
                    time.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _load_client(*, endpoint_url: str | None, region_name: str | None) -> Any:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise S3DependencyError("S3 artifact storage requires boto3") from exc
        kwargs: dict[str, str] = {}
        if endpoint_url is not None:
            kwargs["endpoint_url"] = endpoint_url
        if region_name is not None:
            kwargs["region_name"] = region_name
        return boto3.client("s3", **kwargs)

    def _key(self, digest: str) -> str:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("artifact digest must be lowercase sha256 hex")
        return f"{self._prefix + '/' if self._prefix else ''}sha256/{digest[:2]}/{digest}"

    def _ref(self, role: str, digest: str, size: int, media_type: str | None) -> ArtifactRef:
        return ArtifactRef(
            role,
            "sha256",
            digest,
            media_type,
            size,
            f"s3://{self._bucket}/{self._key(digest)}",
        )

    def put_bytes(self, *, role: str, data: bytes, media_type: str | None = None) -> ArtifactRef:
        if not role or role != role.strip() or "\n" in role or "\r" in role:
            raise ValueError("artifact role must be non-empty, trimmed, and single-line")
        digest = hashlib.sha256(data).hexdigest()
        key = self._key(digest)
        self._call(
            "put_object",
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=media_type or "application/octet-stream",
            Metadata={"ronin-role": role, "ronin-sha256": digest, "ronin-size": str(len(data))},
        )
        ref = self._ref(role, digest, len(data), media_type)
        if not self.verify(ref):
            raise ArtifactIntegrityError("S3 artifact failed digest verification after write")
        return ref

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        if (
            ref.digest_algorithm != "sha256"
            or ref.storage_ref != f"s3://{self._bucket}/{self._key(ref.digest)}"
        ):
            raise ValueError("artifact storage_ref does not match S3 digest")
        response = self._call("get_object", Bucket=self._bucket, Key=self._key(ref.digest))
        data = response["Body"].read()
        if not isinstance(data, bytes):
            raise ArtifactIntegrityError("S3 artifact body was not bytes")
        if len(data) != ref.size_bytes or hashlib.sha256(data).hexdigest() != ref.digest:
            raise ArtifactIntegrityError("S3 artifact digest or size verification failed")
        return data

    def get_bytes_by_storage_ref(self, storage_ref: str, *, digest: str) -> bytes:
        expected = f"s3://{self._bucket}/{self._key(digest)}"
        if storage_ref != expected:
            raise ValueError("artifact storage_ref does not match S3 digest")
        response = self._call("get_object", Bucket=self._bucket, Key=self._key(digest))
        data = response["Body"].read()
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != digest:
            raise ArtifactIntegrityError("S3 artifact digest verification failed")
        return data

    def verify(self, ref: ArtifactRef) -> bool:
        try:
            self.get_bytes(ref)
        except (ArtifactIntegrityError, ValueError, KeyError, OSError):
            return False
        return True

    def delete(self, ref: ArtifactRef) -> bool:
        """Delete one validated object; return false when it was absent."""

        key = self._key(ref.digest)
        if ref.storage_ref != f"s3://{self._bucket}/{key}":
            raise ValueError("artifact storage_ref does not match S3 digest")
        try:
            self._call("head_object", Bucket=self._bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", None)
            error = response.get("Error", {}) if isinstance(response, dict) else {}
            error_code = error.get("Code") if isinstance(error, dict) else None
            if error_code in {"404", "NoSuchKey", "NotFound"} or isinstance(exc, KeyError):
                return False
            raise
        self._call("delete_object", Bucket=self._bucket, Key=key)
        return True

    def list_digests(self) -> tuple[str, ...]:
        """List content digests using bounded continuation-token pagination."""

        prefix = f"{self._prefix + '/' if self._prefix else ''}sha256/"
        digests: list[str] = []
        request: dict[str, str] = {"Bucket": self._bucket, "Prefix": prefix}
        while True:
            response = self._call("list_objects_v2", **request)
            for item in response.get("Contents", ()):
                key = item.get("Key", "")
                digest = key.rsplit("/", 1)[-1]
                if len(digest) == 64 and all(char in "0123456789abcdef" for char in digest):
                    digests.append(digest)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
            if not isinstance(token, str) or not token:
                raise ArtifactIntegrityError("S3 listing returned an invalid continuation token")
            request["ContinuationToken"] = token
        return tuple(sorted(set(digests)))

    def list_digests_page(
        self, *, cursor: str | None = None, page_size: int = 1000
    ) -> ArtifactPage:
        if page_size < 1 or page_size > 1000:
            raise ValueError("S3 artifact discovery page_size must be between 1 and 1000")
        if cursor is not None and (
            not cursor
            or cursor != cursor.strip()
            or len(cursor) > 2048
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in cursor)
        ):
            raise ValueError("S3 artifact discovery cursor must be a bounded opaque token")
        prefix = f"{self._prefix + '/' if self._prefix else ''}sha256/"
        request: dict[str, object] = {
            "Bucket": self._bucket,
            "Prefix": prefix,
            "MaxKeys": page_size,
        }
        if cursor is not None:
            request["ContinuationToken"] = cursor
        response = self._call("list_objects_v2", **request)
        digests = tuple(
            key.rsplit("/", 1)[-1]
            for item in response.get("Contents", ())
            if (key := str(item.get("Key", ""))).rsplit("/", 1)[-1]
            and len(key.rsplit("/", 1)[-1]) == 64
            and all(char in "0123456789abcdef" for char in key.rsplit("/", 1)[-1])
        )
        truncated = bool(response.get("IsTruncated"))
        next_cursor = response.get("NextContinuationToken")
        if truncated and not isinstance(next_cursor, str):
            raise ArtifactIntegrityError("S3 listing returned an invalid continuation token")
        return ArtifactPage(
            tuple(sorted(set(digests))), next_cursor if truncated else None, truncated
        )

    def storage_ref_for_digest(self, digest: str) -> str:
        return f"s3://{self._bucket}/{self._key(digest)}"


__all__ = ("S3ArtifactStore", "S3DependencyError")
