# Cloud Studio Security Review

## Scope

This review covers topology input, HCL import/export, snapshots, external process execution,
endpoint configuration, credentials, and packaged UI assets.

## Controls

| Area | Control | Status |
|---|---|---|
| HCL import | Scalar-only parser; no evaluation | Implemented |
| Resource input | Known property type validation | Implemented |
| Workspace paths | Unsafe traversal names rejected | Implemented |
| Snapshots | Atomic file replacement | Implemented |
| Terraform state | Separate configurable workspace root | Implemented |
| Process execution | Timeout and captured output | Implemented |
| Endpoint URLs | HTTP/HTTPS scheme allowlist | Implemented |
| Credentials | Mock values only in generated local config | Implemented |
| LocalStack token | Environment-only configuration | Implemented |
| Container isolation | Compose-local scope and explicit volumes | Documented |

## Threats and mitigations

### Arbitrary HCL execution

The importer does not use an HCL evaluator or invoke Terraform. It accepts only known resource
blocks and scalar assignments.

### Path traversal

Workspace names are validated before being converted into snapshot filenames. Terraform roots
are explicit configuration, not derived from user-provided workspace strings.

### Command hanging

Terraform/OpenTofu subprocesses have a bounded timeout. Non-zero commands and timeouts become
explicit errors rather than unbounded API requests.

### Credential leakage

Local provider configuration uses mock credentials. Real tokens are read from process environment
only and are not included in manifests, fixtures, snapshots, or generated logs.

### Emulator parity

Cloud Studio reports backend health and documents compatibility. A local emulator must never be
treated as proof that a topology is safe for production cloud deployment.

## Release checklist

- Run all Cloud Studio tests.
- Run the web audit and Chromium E2E.
- Build the wheel and inspect entry points/assets.
- Scan generated artifacts for tokens and credentials.
- Verify Terraform state directories are ignored.
- Run the Floci smoke lifecycle when Docker is available.
