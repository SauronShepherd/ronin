"""Build provider-neutral ML run records from local execution results."""

from __future__ import annotations

from studio_core.ml import ExperimentId, MetricValue, MLRunId, MLRunRecord

from .domain import Lab
from .runner import ExperimentResult


def run_record(
    lab: Lab,
    result: ExperimentResult,
    *,
    run_id: str,
    execution_ref: str,
    source_revision: str,
    runtime_snapshot_ref: str | None = None,
) -> MLRunRecord:
    """Create immutable provenance without embedding rows or secret configuration."""

    return MLRunRecord(
        id=MLRunId(run_id),
        experiment_id=ExperimentId(lab.id),
        execution_ref=execution_ref,
        source_revision=source_revision,
        datasets=(lab.dataset,),
        parameters=(
            ("algorithm", result.model.algorithm),
            ("backend_id", result.backend_id),
            ("seed", str(lab.seed)),
            ("task", result.model.task),
        ),
        metrics=tuple(MetricValue(name, value) for name, value in result.model.metrics),
        artifact_refs=(result.artifact_digest,),
        runtime_snapshot_ref=runtime_snapshot_ref,
    )


__all__ = ["run_record"]
