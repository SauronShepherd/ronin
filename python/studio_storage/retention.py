"""Provider-neutral content-addressed artifact retention policy."""

from __future__ import annotations

from collections.abc import Iterable

from .artifacts import ArtifactRef
from .ports import ArtifactStore


def collect_unreferenced(store: ArtifactStore, live_digests: Iterable[str]) -> tuple[str, ...]:
    """Delete only stored digests absent from the caller-provided live set."""

    live = set(live_digests)
    if any(
        len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
        for digest in live
    ):
        raise ValueError("live artifact digests must be lowercase sha256 hex")
    deleted: list[str] = []
    for digest in store.list_digests():
        if digest in live:
            continue
        ref = ArtifactRef(
            role="retention",
            digest_algorithm="sha256",
            digest=digest,
            media_type=None,
            size_bytes=0,
            storage_ref=store.storage_ref_for_digest(digest),
        )
        if store.delete(ref):
            deleted.append(digest)
    return tuple(sorted(deleted))


__all__ = ("collect_unreferenced",)
