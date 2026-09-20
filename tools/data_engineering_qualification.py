"""Environment qualification probe for external Data Enginerring runtimes."""

from __future__ import annotations

import os
import shutil
import subprocess


def qualify() -> dict[str, object]:
    spark_endpoint = os.environ.get("SPARK_CONNECT_ENDPOINT")
    sdp_command = os.environ.get("SDP_STUDIO_COMMAND")
    docker = False
    docker_path = shutil.which("docker")
    if docker_path is not None:
        try:
            docker = subprocess.run(  # noqa: S603 - fixed diagnostic command
                [docker_path, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            ).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            docker = False
    return {
        "docker_cli": docker,
        "spark_connect": "configured" if spark_endpoint else "not_configured",
        "sdp_studio": "configured" if sdp_command else "not_configured",
        "ready_for_external_e2e": bool(spark_endpoint and sdp_command and docker),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(qualify(), sort_keys=True))
