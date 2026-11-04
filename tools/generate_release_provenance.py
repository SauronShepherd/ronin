"""Create a locally recorded in-toto/SLSA provenance statement for release files.

The output is self-reported local evidence. It is not signed and does not claim a
trusted builder, a SLSA Build level, or an independently verified build process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tools.generate_release_sbom import _load_identity

_BUILD_TYPE = (
    "https://github.com/SauronShepherd/ronin/blob/main/"
    "docs/product/LOCAL_RELEASE_BUILD_TYPE_V1.md#ronin-local-release-qualification-v1"
)
_BUILDER_ID = (
    "https://github.com/SauronShepherd/ronin/blob/main/"
    "docs/product/LOCAL_RELEASE_BUILD_TYPE_V1.md#local-manual-untrusted-builder"
)
_TOOLCHAIN_FIELDS = {
    "python",
    "operating_system",
    "node",
    "npm",
    "docker_engine",
    "docker_compose",
    "postgres_image",
    "playwright",
    "chromium",
    "helm",
    "kind",
    "kubectl",
    "terraform",
    "floci",
    "aws_provider",
    "trivy",
}


def _timestamp(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_provenance(
    artifact_identity: Path,
    *,
    build_command: str,
    started_on: str,
    finished_on: str,
    toolchain: dict[str, str],
    source_uri: str = "https://github.com/SauronShepherd/ronin",
) -> dict[str, Any]:
    """Create an in-toto Statement v1 carrying the SLSA provenance v1 predicate."""
    identity = _load_identity(artifact_identity)
    if (
        not isinstance(build_command, str)
        or not build_command
        or build_command != build_command.strip()
    ):
        raise ValueError("build_command must be non-empty trimmed text")
    if not isinstance(source_uri, str) or not source_uri.startswith(("https://", "git+https://")):
        raise ValueError("source_uri must be an HTTPS or git+HTTPS URI")
    if not isinstance(toolchain, dict) or not toolchain:
        raise ValueError("toolchain must be a non-empty object of observed versions")
    if set(toolchain) - _TOOLCHAIN_FIELDS:
        raise ValueError("toolchain contains unsupported or potentially sensitive fields")
    if any(
        not isinstance(key, str) or not isinstance(value, str) or not value.strip()
        for key, value in toolchain.items()
    ):
        raise ValueError("toolchain values must be non-empty strings")
    started = _timestamp(started_on, "started_on")
    finished = _timestamp(finished_on, "finished_on")
    if datetime.fromisoformat(finished.replace("Z", "+00:00")) < datetime.fromisoformat(
        started.replace("Z", "+00:00")
    ):
        raise ValueError("finished_on must not precede started_on")

    subjects = [
        {"name": item["name"], "digest": {"sha256": item["sha256"]}}
        for item in sorted(identity["artifacts"], key=lambda item: item["name"])
    ]
    identity_digest = hashlib.sha256(artifact_identity.read_bytes()).hexdigest()
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": _BUILD_TYPE,
                "externalParameters": {
                    "candidateCommit": identity["commit"],
                    "artifactIdentitySha256": identity_digest,
                    "buildCommand": build_command,
                    "toolchain": dict(sorted(toolchain.items())),
                },
                "resolvedDependencies": [
                    {
                        "uri": source_uri,
                        "digest": {"gitCommit": identity["commit"]},
                    }
                ],
            },
            "runDetails": {
                "builder": {"id": _BUILDER_ID},
                "metadata": {
                    "invocationId": f"urn:uuid:{uuid4()}",
                    "startedOn": started,
                    "finishedOn": finished,
                },
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="generate-release-provenance")
    parser.add_argument("--artifact-identity", type=Path, required=True)
    parser.add_argument("--build-command", required=True)
    parser.add_argument("--started-on", required=True)
    parser.add_argument("--finished-on", required=True)
    parser.add_argument("--toolchain-json", type=Path, required=True)
    parser.add_argument("--source-uri", default="https://github.com/SauronShepherd/ronin")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        toolchain = json.loads(args.toolchain_json.read_text(encoding="utf-8"))
        result = build_provenance(
            args.artifact_identity,
            build_command=args.build_command,
            started_on=args.started_on,
            finished_on=args.finished_on,
            toolchain=toolchain,
            source_uri=args.source_uri,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
