# Ronin plugin authoring

Ronin loads plugins through the `ronin.plugins.v1` Python entry-point group.
Plugins run locally and must depend only on public contracts and the plugin SDK.
This repository defines Ronin OSS; commercial distributions are outside its
scope and must not add branches or conditionals here.

## Minimal plugin

```python
from studio_plugin_sdk import PluginContext, PluginManifest, SurfaceContribution


class ExamplePlugin:
    manifest = PluginManifest(
        id="com.example.ronin.example",
        name="Example",
        version="1.0.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="third-party",
    capabilities=("example.read",),
    permissions=("example:read",),
    surface_ids=("example.get.v1",),
    )

    def register(self, context: PluginContext) -> None:
        context.contributions.add_route(
            "GET", "/v1/example", context.plugin_id, self.get,
            permission="example:read",
        )
        context.contributions.add_surface(SurfaceContribution(
            id="example.get.v1",
            plugin_id=context.plugin_id,
            namespace="example",
            command="get",
            operation_id="example.get.v1",
            capability="example.read",
            permission="example:read",
            path="/v1/example",
            method="GET",
            output_schema={"type": "object"},
        ))

    def startup(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def get(self, **_kwargs: object) -> dict[str, str]:
        return {"status": "ok"}


def factory() -> ExamplePlugin:
    return ExamplePlugin()
```

The package must publish:

```toml
[project.entry-points."ronin.plugins.v1"]
example = "example_plugin:factory"
```

## Registration rules

- `register()` declares contributions only; it must not perform I/O.
- Startup/shutdown must be bounded and repeatable.
- Every route permission must be declared by the same manifest.
- Every surface capability and permission must be owned by the same plugin.
- Every surface ID must be declared in `surface_ids`; surfaces publish the
  stable CLI/SDK operation ID, HTTP/worker binding and input/output schemas.
- Capabilities, job types, event types, migrations and UI contributions must
  be declared in the manifest where applicable.
- Route collisions, duplicate IDs and duplicate owners reject composition.
- A critical plugin blocks readiness when startup fails. An optional plugin is
  reported as `degraded` and does not publish usable runtime surfaces.

## Local observability

Use the community plugins `com.sauronshepherd.ronin.logging` and
`com.sauronshepherd.ronin.monitoring` for local logs, traces and metrics. They
write only to the injected local buffer; they do not export data to external
systems. Attributes are redacted for tokens, passwords, secrets, API keys and
authorization headers.

```python
from studio_plugin_observability import LocalObservability, LocalObservabilityBuffer

buffer = LocalObservabilityBuffer(max_records=10_000)
telemetry = LocalObservability("com.example.ronin.example", buffer)
telemetry.log("info", "operation started")
with telemetry.span("example.read"):
    telemetry.metric("ronin.example.requests", 1)
```

The facade assigns `plugin_id` automatically, creates trace/span identifiers,
and redacts sensitive attributes. It is local-only and intentionally has no
exporter or network connector.

## Performance plugin

`packages/ronin-plugin-performance` is the reference local plugin distributed as
an independent wheel. It demonstrates how a larger plugin can contribute a
versioned manifest, permissions, a job, a REST route and a UI manifest while
remaining outside the core package. Its tests cover adapters, correlation,
policy, rendering and service behavior.

## Events

Events use a versioned type such as `projects.project-created.v1`. Register a
schema before publishing and publish through a runtime dispatcher. Event IDs
are idempotent; an outbox record is not marked published when a consumer fails.
Consumers must tolerate retries and use the inbox key `(consumer_id, event_id)`.

## UI

Declare `ui_entry` and register one declarative UI manifest. The shell receives
ready-plugin contributions through `GET /v1/platform/ui-manifest`. UI metadata
is not an authorization boundary; every operation remains protected server-side.

## Configuration and secrets

Use `PluginSettingsRegistry` with a namespace of the form
`RONIN_PLUGIN_<PLUGIN_ID>_<SETTING>`. Unknown keys and empty values are
rejected. Secret keys are redacted in diagnostics. Never put credentials in a
manifest, event, bundle, route parameter, log or metric attribute.

## Testing and clean-room validation

Use `studio_plugin_testkit.assert_plugin_ready()` for contract checks. Build a
wheel and install it into an isolated target; the host must discover it through
metadata without editing Ronin source. The tutorial at
`examples/ronin-plugin-tutorial` is the reference clean-room fixture.

## Worker plugins

Plugins that require untrusted code or heavy/cloud SDKs must use the worker
boundary. The public protocol defines handshake `1.0`, capability negotiation,
bounded payloads, heartbeats, cancellation and retryable error categories.
Cloud SDKs and credentials belong in the worker/plugin distribution, never in
the Ronin HTTP process.

## ML pipeline stages

A plugin can declare a versioned ML stage through the frozen contribution
registry. Stage identifiers are namespaced as `<plugin-id>/<local-name>` and
must also appear in `PluginManifest.pipeline_stage_ids`. Pin both the installed
plugin distribution digest and an OCI executor image by digest; mutable image
tags are rejected. Declare typed input ports, an output type, the exact config
fields, required artifact permissions, and CPU, memory, process and timeout
ceilings. Every stage permission must also be declared in
`PluginManifest.permissions`. The host includes the complete declaration set in the PipelineIR v3
stage registry digest so a durable Job cannot resume against different plugin
code or a changed port contract.

```python
from studio_plugin_sdk import PipelineStageContribution

stage = PipelineStageContribution(
    plugin_id="com.example.ronin.ml",
    stage_id="com.example.ronin.ml/normalize",
    version=1,
    plugin_version="1.2.0",
    distribution_digest="a" * 64,  # host-verified installed wheel digest
    executor_image="registry.example/ml-plugin@sha256:" + "b" * 64,
    operation_id="normalize.v1",
    input_ports={"model": ("ml.model", 1, 1)},
    output_type="ml.metrics",
    config_fields=("strategy",),
    cpu_limit="1.0",
    memory_limit="512m",
    pids_limit=128,
    timeout_seconds=300,
)
context.contributions.add_pipeline_stage(stage, plugin_id=context.plugin_id)
```

The host compares the declared distribution digest with the installed plugin
distribution before freezing the stage registry, so a durable Job cannot use a
different package than the one that supplied its declaration. The stage contribution contract rejects mutable image tags, undeclared config, unbounded ports and unsupported permissions. Pure stages execute through the
isolated OCI runner with bounded canonical JSON, and their output checkpoints
are pinned to the contribution and image digests. A metrics stage returns an
object such as `{"scores":{"accuracy":0.92}}`; the selector binds those scores
to exactly one directly supplied trained model. `artifact:read` exposes only
referenced upstream artifacts, while `artifact:write` accepts up to eight
outputs with a 512 KiB aggregate limit. The host verifies and persists each
artifact under the shared reference writer lease together with the durable
checkpoint, and the retention inventory discovers those references.

## OSS boundary

Ronin OSS is the only product contract in this repository. Extensions must use
the public plugin SDK, remain independently installable, and never import
private modules, touch another plugin's tables, bypass authorization/audit, or
add product-edition conditionals to host code.
