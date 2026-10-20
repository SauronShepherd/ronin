"""ML execution round-trip against a real S3-compatible service."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_execution import DurableExecutionService
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import JobStoreExecutionStore, LocalExecutionCoordinator
from studio_ml.runner import ExperimentResult
from studio_ml.runtime import TrainedTabularModel
from studio_orchestrator import Instant
from studio_storage import ArtifactRef, S3ArtifactStore, SqliteJobStore, collect_unreferenced

_MIGRATION_NOW = Instant("2026-10-20T00:00:00.000000Z")


def test_ml_durable_input_output_and_retention_round_trip_through_s3(tmp_path: Path) -> None:
    endpoint = os.environ.get("RONIN_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("RONIN_TEST_S3_ENDPOINT is required for S3-compatible integration")
    boto3 = pytest.importorskip("boto3", reason="boto3 is required for S3 integration")
    from botocore.config import Config  # type: ignore[import-untyped]

    bucket = f"ronin-ml-qualification-{uuid4().hex}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        config=Config(s3={"addressing_style": "path"}),
    )
    client.create_bucket(Bucket=bucket)
    artifacts = S3ArtifactStore(
        bucket,
        endpoint_url=endpoint,
        region_name="us-east-1",
        client=boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
            config=Config(s3={"addressing_style": "path"}),
        ),
    )

    lab = Lab(
        "s3-roundtrip",
        "S3 round trip",
        "integration",
        AssetRef(AssetId("rows"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    artifact_bytes = b'{"schema":"ronin.ml-tabular/v1","provider":"local"}'
    model = TrainedTabularModel(
        "classification",
        "logistic_regression",
        ("x",),
        "target",
        artifact_bytes,
        (("accuracy", 1.0),),
    )
    result = ExperimentResult(
        lab.id,
        "local.sklearn",
        4,
        model,
        f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}",
    )

    class ResultRunner:
        def run(self, _lab: Lab, _rows: Sequence[dict[str, object]]) -> ExperimentResult:
            return result

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    coordinator = LocalExecutionCoordinator(
        runner=ResultRunner(),  # type: ignore[arg-type]
        store=JobStoreExecutionStore(service, artifacts),  # type: ignore[arg-type]
    )
    try:
        rows = [{"x": index, "target": index % 2, "payload": "p" * 55_000} for index in range(22)]
        coordinator.submit("workspace-s3", "s3-roundtrip", lab, rows)
        deadline = time.monotonic() + 30
        snapshot = coordinator.status("workspace-s3", "s3-roundtrip")
        while snapshot.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = coordinator.status("workspace-s3", "s3-roundtrip")

        assert snapshot.state == "succeeded", snapshot.error
        assert snapshot.result_payload is not None
        model_digest = hashlib.sha256(artifact_bytes).hexdigest()
        assert snapshot.result_payload["artifact_digest"] == f"sha256:{model_digest}"
        model_ref = str(snapshot.result_payload["artifact_ref"])
        assert model_ref.startswith(f"s3://{bucket}/")
        assert artifacts.get_bytes_by_storage_ref(model_ref, digest=model_digest) == artifact_bytes

        stale_ref = artifacts.put_bytes(role="test-unreferenced", data=b"stale artifact")
        digests = artifacts.list_digests()
        assert len(digests) == 3  # large request input, materialized model, and stale object
        input_digest = next(
            digest for digest in digests if digest not in {model_digest, stale_ref.digest}
        )
        deleted = collect_unreferenced(artifacts, (model_digest, input_digest))
        assert deleted == (stale_ref.digest,)
        assert artifacts.list_digests() == tuple(sorted((input_digest, model_digest)))
        assert artifacts.get_bytes_by_storage_ref(model_ref, digest=model_digest) == artifact_bytes
    finally:
        coordinator.close()
        asyncio.run(service.aclose())
        for digest in artifacts.list_digests():
            artifacts.delete(
                ArtifactRef(
                    role="test-cleanup",
                    digest_algorithm="sha256",
                    digest=digest,
                    media_type=None,
                    size_bytes=0,
                    storage_ref=artifacts.storage_ref_for_digest(digest),
                )
            )
        client.delete_bucket(Bucket=bucket)
