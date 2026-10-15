"""Qualify Cloud Studio against the local Floci emulator.

This is deliberately provider-neutral: Ronin talks to the EmulatorBackend
contract and Floci is the only runtime selected by this qualification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_cloud.backends import create_backend
from studio_cloud.engine import CloudResource, CloudTopology, export_terraform


def fixture() -> CloudTopology:
    return CloudTopology(
        resources=(
            CloudResource(
                "bucket", "aws.s3.bucket", "qualification-bucket", {"force_destroy": True}
            ),
            CloudResource("queue", "aws.sqs.queue", "qualification-queue", {}),
        ),
        edges=(("bucket", "queue"),),
    )


def qualify(endpoint: str, workspace: str, terraform: bool = False) -> dict[str, object]:
    backend = create_backend("floci", endpoint, workspace_dir=workspace)
    health = backend.health()
    if not health.get("available"):
        raise RuntimeError(f"Floci is not healthy: {health}")
    topology = fixture()
    result: dict[str, object] = {
        "schema": "ronin.cloud-studio.floci-qualification/v1",
        "backend": "floci",
        "endpoint": endpoint,
        "health": health,
        "topology_valid": not topology.validate(),
        "terraform_config_generated": bool(export_terraform(topology)),
        "status": "passed",
    }
    if terraform:
        result.update(
            plan=backend.plan(topology),
            apply=backend.apply(topology),
            refresh=backend.refresh(),
            destroy=backend.destroy(),
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:4566")
    parser.add_argument("--workspace", default=".ronin/cloud-studio/qualification/floci")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--terraform", action="store_true", help="also run the optional Terraform adapter"
    )
    args = parser.parse_args()
    result = qualify(args.endpoint, args.workspace, args.terraform)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
