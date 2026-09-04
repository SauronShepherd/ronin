# pyronin

`pyronin` is the official Python SDK for the Ronin control plane.

> **Alpha:** `0.1.0a2` establishes the public client shape while the Ronin control-plane API is still under active development.

## Install

```bash
pip install pyronin
```

## Submit and observe a job

```python
from pyronin import Ronin

ronin = Ronin("http://localhost:8080")
job = ronin.submit(
    project="demo",
    target="daily-etl",
    parameters={"date": "2026-09-04"},
    idempotency_key="daily-etl-2026-09-04",
)

print(job.id)
print(job.status())
result = job.wait()
print(result.state)
```

The SDK is intentionally a control-plane client. It does not execute Python, Spark, Docker, Kubernetes, Fabric, Databricks, or other provider runtimes itself. Those concerns remain behind Ronin server/orchestrator adapters.

## Initial API

- `Ronin.submit(...)`
- `Ronin.get_job(...)`
- `Ronin.list_jobs(...)`
- `JobHandle.status()`
- `JobHandle.wait()`
- `JobHandle.cancel()`
- `JobHandle.events()`

Transports are replaceable so HTTP is not embedded in the public job model. Authentication is also transport-side; tokens are never persisted by job objects.

## Project

Ronin is Apache-2.0 licensed and developed at https://github.com/SauronShepherd/ronin.
