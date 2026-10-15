"""Run the local fail-closed GenAI provider/model qualification matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_core.genai import GenAIModel, ModelProvider, ProviderId
from studio_genai.qualification import qualify_provider_model


def qualify_manifest(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("GenAI qualification manifest must be an object")
    raw_provider = payload.get("provider")
    raw_models = payload.get("models")
    if not isinstance(raw_provider, dict) or not isinstance(raw_models, list) or not raw_models:
        raise ValueError("manifest requires one provider and a non-empty models array")
    provider_id = raw_provider.get("id")
    adapter = raw_provider.get("adapter")
    endpoint = raw_provider.get("endpoint")
    properties = raw_provider.get("properties", {})
    if (
        not isinstance(provider_id, str)
        or not isinstance(adapter, str)
        or endpoint is not None
        and not isinstance(endpoint, str)
        or not isinstance(properties, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in properties.items()
        )
    ):
        raise ValueError("provider fields have invalid types")
    provider = ModelProvider(
        ProviderId(provider_id),
        adapter,
        endpoint,
        properties=tuple(sorted(properties.items())),
    )
    records: list[dict[str, object]] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            raise ValueError("model entries must be objects")
        model = GenAIModel(
            ProviderId(raw_model.get("provider_id", provider_id)),
            raw_model["model_id"],
            frozenset(raw_model["capabilities"]),
            raw_model.get("context_limit"),
        )
        records.append(qualify_provider_model(provider, model).to_payload())
    status = "qualified" if all(item["status"] == "qualified" for item in records) else "rejected"
    return {"schema": "ronin.genai-qualification/v1", "status": status, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = qualify_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
