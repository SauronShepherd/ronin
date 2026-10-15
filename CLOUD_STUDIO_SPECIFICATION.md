# Cloud Studio

## Complete Functional, Architectural, and Technical Specification

**Project:** Ronin community plugin  
**Plugin name:** Cloud Studio  
**Plugin ID:** `com.sauronshepherd.ronin.cloud-studio`  
**Current version:** `0.1.0`  
**Plugin API:** `1.0`  
**Edition:** Community / open source  
**Runtime:** Python 3.11+  
**License context:** Distributed as part of Ronin under the repository license

## 1. Executive summary

Cloud Studio is a Ronin vertical plugin for designing, validating, emulating, and exporting
local cloud topologies. It provides a visual drag-and-drop editor, a provider-neutral topology
model, a deterministic in-memory emulator, external AWS-wire-compatible emulator adapters, and
Terraform/OpenTofu integration.

The module is designed for local-first development and CI. It allows a developer to model a
small cloud architecture, validate it without cloud credentials, run it against an in-memory
state engine or an external emulator such as Floci or LocalStack, and export provider-compatible
HCL for Terraform or OpenTofu.

Cloud Studio is not intended to claim production-cloud parity. Its contract is deliberately
provider-neutral and its external adapters depend on the compatibility and behavior of the
selected emulator.

## 2. Goals and non-goals

### 2.1 Goals

- Provide a first-class Ronin plugin rather than a core-runtime modification.
- Offer a stable topology contract shared by API, UI, emulators, and IaC exporters.
- Support local development without cloud credentials by default.
- Support Floci and LocalStack through an intermediate backend abstraction.
- Execute Terraform/OpenTofu workflows against local AWS-compatible endpoints.
- Provide a usable visual editor for common cloud resources.
- Persist topology snapshots safely by workspace.
- Make backend selection explicit and configurable.
- Keep external dependencies optional.
- Make behavior testable in unit, contract, browser, and Docker-based integration tests.

### 2.2 Non-goals

- Full cloud-provider API parity.
- Reimplementing AWS, Azure, or GCP services in the Ronin core.
- Storing or managing real cloud credentials.
- Executing arbitrary Terraform or HCL code during parsing.
- Replacing Terraform/OpenTofu's provider RPC protocol.
- Treating LocalStack or Floci as a production cloud substitute.

## 3. Functional specification

### 3.1 Resource catalog

The initial catalog contains:

| Resource type | Terraform type | Category | In-memory | Floci | LocalStack |
|---|---|---|---:|---:|---:|
| `aws.s3.bucket` | `aws_s3_bucket` | Storage | Yes | Yes | Yes |
| `aws.lambda.function` | `aws_lambda_function` | Compute | Yes | Yes | Yes |
| `aws.sqs.queue` | `aws_sqs_queue` | Messaging | Yes | Yes | Yes |
| `aws.dynamodb.table` | `aws_dynamodb_table` | Database | Yes | Yes | Yes |

The catalog is exposed to the UI and API. Each entry includes a display label, category,
Terraform mapping, supported backend list, and known property schema.

### 3.2 Topology modeling

A topology contains:

- A list of resources.
- A list of directed edges between resource IDs.
- Resource IDs, provider-neutral resource types, display names, and scalar properties.
- Optional visual coordinates used by the browser editor.

Edges represent logical relationships and are preserved in JSON snapshots and exports. The
current Terraform exporter emits resource blocks; edge-to-attribute interpolation is an
extension point for future resource-specific translators.

### 3.3 Validation

Validation checks:

- Resource IDs are present and unique.
- Resource names are present.
- Resource types exist in the catalog.
- Edge endpoints reference existing resources.
- Resource property values are scalar JSON-compatible values.
- Known property names receive type validation.
- Workspace names cannot contain traversal or unsafe characters.

Validation is deterministic and does not make network calls.

### 3.4 Local lifecycle

The lifecycle is:

```text
validate → plan → apply → refresh → destroy
```

#### In-memory backend

- `plan` compares desired resource IDs with current state.
- `apply` replaces the in-memory desired state.
- `refresh` returns the current snapshot.
- `destroy` clears the state and reports destroyed IDs.

#### External Terraform backend

- Writes provider configuration and generated HCL to an isolated Terraform workspace.
- Runs `init` once per backend instance.
- Runs `plan`, `apply`, `refresh`, and `destroy` through the configured IaC binary.
- Captures stdout and stderr.
- Enforces a command timeout.
- Returns non-zero commands as structured runtime errors.

### 3.5 Snapshots

Snapshots are JSON documents stored atomically under a configurable root directory.

Default root:

```text
.ronin/cloud-studio
```

Each workspace maps to a separate JSON file. Snapshot writes use a temporary file followed by
an atomic replacement. Unsafe workspace names are rejected.

Snapshot content includes:

```json
{
  "resources": [],
  "edges": []
}
```

### 3.6 Terraform/OpenTofu export and import

The exporter produces:

1. An AWS provider block with local endpoint overrides.
2. Mock credentials intended for local emulators only.
3. Resource blocks derived from the topology.

The generated provider configuration includes:

- Region `us-east-1`.
- Mock access and secret keys.
- Credential and metadata validation skips.
- Account ID request skip.
- S3 path-style addressing.
- Endpoints for S3, Lambda, SQS, and DynamoDB.

The external backend can invoke either Terraform or OpenTofu through configuration.

Cloud Studio also imports a deliberately restricted HCL subset. Import accepts resource blocks
for catalog resource types and scalar string, boolean, and numeric assignments. It rejects
unknown resource types, nested blocks, interpolations, expressions, and arbitrary HCL evaluation.
The importer creates provider-neutral resource IDs and never executes Terraform.

### 3.7 Visual editor

The standalone visual surface provides:

- Component palette.
- HTML drag-and-drop resource creation.
- Canvas resource nodes.
- Shift-click edge creation.
- SVG edge rendering.
- Resource selection.
- Name and property inspector.
- Node deletion through the Delete key.
- Enter-key selection.
- Undo and redo history.
- JSON import.
- JSON download.
- Terraform export.
- HCL import through the API and a browser Import HCL control.
- Topology validation.
- Zoom from 50% to 200%.
- Zoom reset control.
- Dependency-aware auto-layout.
- Visible focus outlines.
- ARIA role and status attributes.

## 4. Plugin architecture

### 4.1 Ronin plugin contract

Cloud Studio implements the Ronin plugin boundary and is discovered through the Python entry
point:

```toml
[project.entry-points."ronin.plugins.v1"]
cloud_studio = "studio_cloud.plugin:factory"
```

The manifest declares:

```text
id:            com.sauronshepherd.ronin.cloud-studio
name:          Cloud Studio
version:       0.1.0
plugin_api:    1.0
host_requires: >=1,<2
edition:       community
isolation:     in_process
ui_entry:      cloud-studio
```

Capabilities:

- `cloud-studio.catalog`
- `cloud-studio.topology`
- `cloud-studio.emulator`
- `cloud-studio.terraform`

Permissions:

- `cloud-studio:read`
- `cloud-studio:write`

### 4.2 Registration

During registration the plugin contributes:

- UI metadata for the Build navigation group.
- Catalog route.
- Validation route.
- Plan route.
- Apply route.
- Refresh route.
- Destroy route.
- Terraform export route.
- Backend health route.
- Snapshot save and load routes.

Registration is declarative. Backend initialization and filesystem preparation occur through
the plugin instance lifecycle, not by importing the module.

### 4.3 Dependency direction

```text
Ronin host
   │
   ├── Plugin contract / ContributionRegistry
   │
   └── Cloud Studio plugin
          ├── API adapter
          ├── Topology domain
          ├── Backend abstraction
          ├── Snapshot storage
          ├── Terraform/OpenTofu adapter
          └── Static visual surface
```

Cloud Studio does not import cloud SDKs. Cloud-specific behavior is behind the backend and IaC
boundaries.

## 5. Domain model

### 5.1 `CloudResource`

```python
@dataclass(frozen=True, slots=True)
class CloudResource:
    id: str
    type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
```

### 5.2 `CloudTopology`

```python
@dataclass(frozen=True, slots=True)
class CloudTopology:
    resources: tuple[CloudResource, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()
```

Public behavior:

- `validate() -> list[str]`
- Immutable resource and edge collections.
- Provider-neutral serialization boundary.

### 5.3 Backend protocol

```python
class EmulatorBackend(Protocol):
    name: str
    endpoint: str | None

    def apply(self, topology: CloudTopology) -> dict[str, object]: ...
    def plan(self, topology: CloudTopology) -> dict[str, object]: ...
    def refresh(self) -> dict[str, object]: ...
    def destroy(self) -> dict[str, object]: ...
    def health(self) -> dict[str, object]: ...
```

Implementations:

- `InMemoryBackend`.
- `HttpEmulatorBackend` for descriptor/delegation behavior.
- `TerraformEmulatorBackend` for real Terraform/OpenTofu execution.

## 6. API specification

All routes are registered under the Ronin plugin contribution system.

| Method | Route | Permission | Purpose |
|---|---|---|---|
| GET | `/v1/cloud-studio/catalog` | `cloud-studio:read` | Return catalog, schemas, and compatibility metadata |
| GET | `/v1/cloud-studio/backend` | `cloud-studio:read` | Return backend health/readiness |
| POST | `/v1/cloud-studio/validate` | `cloud-studio:read` | Validate topology |
| POST | `/v1/cloud-studio/plan` | `cloud-studio:read` | Compute desired-state plan |
| POST | `/v1/cloud-studio/apply` | `cloud-studio:write` | Apply topology |
| GET | `/v1/cloud-studio/refresh` | `cloud-studio:read` | Refresh current backend state |
| POST | `/v1/cloud-studio/destroy` | `cloud-studio:write` | Destroy managed state |
| POST | `/v1/cloud-studio/terraform` | `cloud-studio:read` | Generate provider HCL and resources |
| POST | `/v1/cloud-studio/import` | `cloud-studio:write` | Import the safe scalar HCL subset |
| POST | `/v1/cloud-studio/snapshots` | `cloud-studio:write` | Save a workspace snapshot |
| GET | `/v1/cloud-studio/snapshots` | `cloud-studio:read` | Load a workspace snapshot |

### 6.1 Topology request example

```json
{
  "resources": [
    {
      "id": "bucket",
      "type": "aws.s3.bucket",
      "name": "assets",
      "properties": {
        "force_destroy": true
      }
    }
  ],
  "edges": []
}
```

### 6.2 Validation response

```json
{
  "valid": true,
  "errors": []
}
```

### 6.3 Backend health response

```json
{
  "backend": "floci",
  "available": true,
  "endpoint": "http://127.0.0.1:4566",
  "license_required": false,
  "status_code": 200
}
```

### 6.4 Snapshot request

```json
{
  "workspace": "orders-dev",
  "resources": [],
  "edges": []
}
```

## 7. Backend configuration

### 7.1 In-memory

```text
RONIN_CLOUD_STUDIO_BACKEND=in-memory
```

This is the default and requires no external process, cloud account, or credential.

### 7.2 Floci

```text
RONIN_CLOUD_STUDIO_BACKEND=floci
RONIN_CLOUD_STUDIO_ENDPOINT=http://127.0.0.1:4566
RONIN_CLOUD_STUDIO_TERRAFORM_ROOT=.ronin/cloud-studio/terraform/floci
```

The repository includes:

```text
examples/cloud-studio/compose.floci.yaml
```

### 7.3 LocalStack

```text
RONIN_CLOUD_STUDIO_BACKEND=localstack
RONIN_CLOUD_STUDIO_ENDPOINT=http://127.0.0.1:4566
RONIN_CLOUD_STUDIO_TERRAFORM_ROOT=.ronin/cloud-studio/terraform/localstack
```

LocalStack is optional. Any required token must be supplied through the environment and must
never be committed to source control.

### 7.4 Terraform/OpenTofu selection

```text
RONIN_CLOUD_STUDIO_IAC=terraform
# or
RONIN_CLOUD_STUDIO_IAC=tofu
```

The executable must be available on `PATH` or supplied through the configured runtime.

### 7.5 Provider cache

```text
TF_PLUGIN_CACHE_DIR=.ronin/terraform-plugin-cache
```

This avoids downloading providers separately for every isolated workspace.

## 8. Terraform/OpenTofu behavior

### 8.1 Workspace layout

```text
<terraform-root>/
├── main.tf
├── .terraform/
├── .terraform.lock.hcl
└── terraform.tfstate
```

Terraform files and state are separate from Cloud Studio JSON snapshots.

### 8.2 Command lifecycle

The backend executes commands equivalent to:

```text
terraform -chdir=<workspace> init -backend=false -input=false
terraform -chdir=<workspace> plan -input=false -no-color
terraform -chdir=<workspace> apply -auto-approve -input=false -no-color
terraform -chdir=<workspace> refresh -input=false -no-color
terraform -chdir=<workspace> destroy -auto-approve -input=false -no-color
```

For OpenTofu, the binary name is replaced with `tofu`.

All commands:

- Run without interactive input.
- Capture stdout and stderr.
- Enforce a timeout.
- Return non-zero exit status as an error.
- Operate in an isolated workspace directory.

## 9. Security model

- Cloud Studio does not require real cloud credentials for local emulators.
- Generated credentials are mock values only.
- LocalStack tokens are environment-only configuration.
- Endpoint schemes are restricted to HTTP and HTTPS.
- Workspace names reject traversal characters.
- Terraform state is isolated per workspace.
- Snapshot writes are atomic.
- External command execution has bounded time.
- The configured Terraform/OpenTofu executable is treated as trusted local software.
- Untrusted HCL parsing is not implemented; arbitrary code must not be executed during import.

## 10. Packaging and distribution

The plugin is included in the Ronin wheel through:

- Python package `studio_cloud`.
- Entry point `ronin.plugins.v1:cloud_studio`.
- Web assets:
  - `cloud-studio.html`
  - `cloud-studio.css`
  - `cloud-studio.js`

The wheel build is verified to contain the plugin package, entry point metadata, and all three
visual assets.

## 11. Testing strategy

### 11.1 Python unit and contract tests

The test suite covers:

- Topology validation.
- Property schema validation.
- HCL export.
- In-memory plan/apply/refresh/destroy.
- Snapshot round trips.
- Unsafe workspace rejection.
- Backend selection.
- OpenTofu selection.
- Backend health behavior.
- Plugin lifecycle.
- Plugin route registration.
- UI contribution registration.

### 11.2 Web surface audit

```text
node tools/cloud_studio_web_audit.mjs
```

The audit checks required controls, accessibility attributes, interaction handlers, SVG edge
rendering hooks, layout hooks, and JavaScript syntax.

### 11.3 Browser E2E

```text
python tools/cloud_studio_e2e.py
```

The Chromium headless test covers:

- Drag and drop.
- Node creation.
- Zoom.
- Inspector editing.
- Auto-layout.
- JSON download.

### 11.4 Docker and Terraform smoke test

```text
docker compose -f examples/cloud-studio/compose.floci.yaml up -d
terraform -chdir=examples/cloud-studio/terraform init -backend=false -input=false
terraform -chdir=examples/cloud-studio/terraform validate
terraform -chdir=examples/cloud-studio/terraform apply -auto-approve -input=false
terraform -chdir=examples/cloud-studio/terraform destroy -auto-approve -input=false
docker compose -f examples/cloud-studio/compose.floci.yaml down
```

The flow has been verified against Floci with the AWS Terraform provider.

## 12. Operational runbook

### Local in-memory development

1. Install Ronin in the development environment.
2. Leave `RONIN_CLOUD_STUDIO_BACKEND` unset.
3. Start Ronin.
4. Open the Cloud Studio UI entry.
5. Create or import a topology.
6. Validate and export HCL.

### Floci development

1. Start `compose.floci.yaml`.
2. Set `RONIN_CLOUD_STUDIO_BACKEND=floci`.
3. Set `RONIN_CLOUD_STUDIO_ENDPOINT` if the endpoint is not localhost.
4. Configure `RONIN_CLOUD_STUDIO_TERRAFORM_ROOT`.
5. Configure provider caching if desired.
6. Check `/v1/cloud-studio/backend`.
7. Run plan/apply/refresh/destroy.

### Diagnosing failures

- Check backend health first.
- Inspect captured Terraform stderr.
- Confirm the configured executable exists.
- Confirm provider cache availability.
- Check for a stale Terraform process holding a state lock.
- Use a new workspace directory for isolated reproduction.
- Never delete a state file to bypass a lock without confirming that no Terraform process is active.

## 13. Extension points

### New resource type

1. Add a catalog entry.
2. Define property schemas.
3. Define Terraform resource mapping.
4. Add backend compatibility metadata.
5. Update the inspector catalog behavior.
6. Add validation tests.
7. Add HCL export tests.
8. Add emulator compatibility tests.
9. Update the compatibility matrix and this document.

### New emulator backend

1. Implement `EmulatorBackend`.
2. Provide health/readiness behavior.
3. Define endpoint and authentication semantics.
4. Add backend selection in `create_backend`.
5. Keep credentials out of source control.
6. Add Compose or deployment documentation.
7. Add unit and integration tests.
8. Update the compatibility matrix.

## 14. Known limitations

- The current external backend uses Terraform/OpenTofu as the execution adapter rather than
  implementing a native cloud API client for every service.
- HCL import is intentionally limited to the safe scalar subset emitted by Cloud Studio.
- The visual editor is intentionally dependency-light and standalone rather than React-based.
- Edges are modeled and visualized, but resource-specific Terraform relationship translation is
  still an extension point.
- Cloud-provider parity depends on Floci or LocalStack behavior.
- Browser E2E covers the standalone surface; full Ronin-hosted browser routing requires the
  host application to be running.

## 15. Current verification baseline

The current repository baseline includes:

- Python contract tests passing.
- Ruff checks passing for Cloud Studio Python code.
- Browserless web audit passing.
- Chromium headless E2E passing.
- Docker Compose configuration passing.
- Floci health check passing.
- Terraform/OpenTofu provider-compatible HCL validation.
- Real Floci `plan`, `apply`, and `destroy` verification through the Cloud Studio backend.
- Wheel build containing plugin code, entry point, and visual assets.

Contribution and security procedures are documented in:

- `docs/architecture/CLOUD_STUDIO_CONTRIBUTING.md`
- `docs/architecture/CLOUD_STUDIO_SECURITY.md`
