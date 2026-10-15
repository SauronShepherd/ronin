from __future__ import annotations

import pytest
from studio_data_engineering.pipeline_contracts import PipelineParameter, PipelineParameterSchema


def test_pipeline_parameter_schema_validates_and_applies_defaults() -> None:
    schema = PipelineParameterSchema(
        (
            PipelineParameter("region", "string"),
            PipelineParameter("retries", "integer", required=False, default=2),
        )
    )
    assert schema.validate({"region": "EU"}) == {"region": "EU", "retries": 2}


def test_pipeline_parameter_schema_rejects_missing_unknown_and_wrong_types() -> None:
    schema = PipelineParameterSchema((PipelineParameter("count", "integer"),))
    with pytest.raises(ValueError, match="missing"):
        schema.validate({})
    with pytest.raises(ValueError, match="unknown"):
        schema.validate({"count": 1, "extra": True})
    with pytest.raises(ValueError, match="integer"):
        schema.validate({"count": True})


def test_pipeline_parameter_schema_has_canonical_versioned_round_trip() -> None:
    schema = PipelineParameterSchema((PipelineParameter("count", "integer", default=1),))
    assert PipelineParameterSchema.from_json(schema.canonical_json()) == schema
    data = schema.to_data()
    data["version"] = 2
    with pytest.raises(ValueError, match="version"):
        PipelineParameterSchema.from_data(data)
