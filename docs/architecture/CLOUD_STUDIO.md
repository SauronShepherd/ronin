# Cloud Studio

Cloud Studio is the community plugin for designing and emulating cloud topologies locally.

## Architecture

The topology (`CloudTopology`) is the stable contract shared by the visual editor, the
in-memory emulator, external emulators, and Terraform export. `EmulatorBackend` is the
intermediate abstraction. It currently supports `in-memory`, `floci`, and `localstack`.
Provider-specific emulators are adapters behind this contract; the core plugin does not import cloud SDKs. The first vertical slice supports
S3, Lambda, SQS, and DynamoDB resource types.

The UI should use the catalog endpoint to render a palette and serialize canvas nodes/edges
to the topology endpoint. React Flow is a suitable optional frontend implementation.

## Running an external backend

For the default no-license path, start `examples/cloud-studio/compose.floci.yaml` and set
`RONIN_CLOUD_STUDIO_BACKEND=floci`. For a LocalStack installation, use the corresponding
compose file and set `RONIN_CLOUD_STUDIO_BACKEND=localstack`; provide any required
`LOCALSTACK_AUTH_TOKEN` through the environment, never through a committed file.

The plugin reads `RONIN_CLOUD_STUDIO_ENDPOINT` when present. Terraform output contains the
AWS provider endpoint overrides, so the same generated configuration can be used with
Terraform or OpenTofu against localhost.

Snapshots are stored as atomic JSON files under `RONIN_CLOUD_STUDIO_SNAPSHOTS` (default
`.ronin/cloud-studio`) and are addressed by workspace name through the snapshot API routes.
The browser editor can also import and download standalone topology JSON files.
`tools/cloud_studio_web_audit.mjs` provides a browserless CI audit for required controls,
accessibility attributes, interaction handlers, and JavaScript syntax.
`tools/cloud_studio_e2e.py` runs a real Chromium headless smoke test covering drag/drop,
zoom, inspector editing, auto-layout, and JSON download.
Edges are rendered in an SVG overlay and auto-layout places resources in dependency columns;
positions are serialized in imported/exported topology JSON.

## API surface

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/cloud-studio/catalog` | Resource catalog for the palette |
| GET | `/v1/cloud-studio/backend` | Backend health/readiness |
| POST | `/v1/cloud-studio/validate` | Validate a topology |
| POST | `/v1/cloud-studio/plan` | Compute local plan |
| POST | `/v1/cloud-studio/apply` | Apply to the selected backend |
| GET | `/v1/cloud-studio/refresh` | Read current emulator state |
| POST | `/v1/cloud-studio/destroy` | Destroy local state |
| POST | `/v1/cloud-studio/terraform` | Generate provider configuration and HCL |
| POST/GET | `/v1/cloud-studio/snapshots` | Save/load workspace snapshots |
| POST | `/v1/cloud-studio/import` | Import the safe scalar HCL subset |

## Compatibility matrix

| Resource | In-memory | Floci | LocalStack |
|---|---:|---:|---:|
| S3 bucket | yes | yes | yes |
| Lambda function | yes | yes | yes |
| SQS queue | yes | yes | yes |
| DynamoDB table | yes | yes | yes |

The catalog exposes the same matrix and property schemas to the visual inspector. Unknown
properties remain forward-compatible, while known properties are type-checked before HCL
generation.

The checked-in smoke fixture under `examples/cloud-studio/terraform` can be run against the
Floci compose service with `terraform init`, `terraform validate`, and `terraform apply`.
The smoke run has been verified end-to-end with Floci 2.1.0 and `hashicorp/aws` 6.65.0,
including `terraform destroy`; the final state was empty.

External Terraform workspaces accept `TF_PLUGIN_CACHE_DIR` to reuse a CI-local provider
cache. Commands have bounded timeouts and return captured stdout/stderr on non-zero exit;
timeouts raise an explicit error instead of leaving the API request hanging indefinitely.

The external backend is selected with `RONIN_CLOUD_STUDIO_BACKEND=floci` or `localstack`.
`RONIN_CLOUD_STUDIO_TERRAFORM_ROOT` isolates Terraform files and state from snapshot files.
Set `RONIN_CLOUD_STUDIO_IAC=tofu` to use OpenTofu instead of Terraform; both binaries use
the same provider-compatible HCL contract. Workspace names reject traversal characters and
are stored in separate snapshot/state paths.
Against a healthy Floci container, the plugin API has been verified with return code 0 for
`plan`, `apply`, and `destroy`.

Terraform integration is intentionally export-first in v0.1. A later `terraform-provider-cloud-studio`
binary should speak Terraform's provider RPC protocol and delegate CRUD to the same emulator
port. This keeps Terraform's separate-process isolation and avoids embedding Go/RPC concerns
in Ronin's Python host.

## Safety and scope

In-memory emulation is deterministic and local-only by default. Floci is the preferred
zero-license external backend. LocalStack is opt-in and must be treated as a licensed
dependency; its endpoint/token configuration must never be committed. It is not a claim of cloud API parity:
acceptance tests against the real provider remain necessary before production deployment.
