# Ronin plugin authoring

Ronin loads plugins through the `ronin.plugins.v1` Python entry-point group.
Community plugins run locally and must depend only on public contracts and
the plugin SDK. Ronin Pro may add private plugins in its own repository, but
must not import Ronin internals or add commercial branches to this repository.

## Minimal plugin

```python
from studio_plugin_sdk import PluginContext, PluginManifest


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
    )

    def register(self, context: PluginContext) -> None:
        context.contributions.add_route(
            "GET", "/v1/example", context.plugin_id, self.get,
            permission="example:read",
        )

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

## Ronin Pro boundary

Ronin Pro may implement public ports and add private capabilities, routes,
workers, migrations and UI. It must depend on published Ronin contracts/SDK,
keep its own lockfile and license policy, and never import private modules,
touch another plugin's tables, bypass audit/telemetry or add `if PRO` branches
to community code.
