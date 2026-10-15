# Ronin Execution Architecture Proposal

**Status:** Proposed
**Scope:** Ronin OSS, local-first
**Date:** 2026-09-20
**Audience:** Ronin maintainers and contributors

## Executive decision

Ronin should be **runtime-neutral, local-first, and self-hostable**.

Docker is the default local packaging and execution substrate. Kubernetes is a
first-class execution backend, initially provided by a local `kind` cluster on
Docker Desktop. A virtual machine is a deployment boundary, not a different
product edition. Cloud providers are outside the Ronin OSS runtime boundary;
Cloud Studio uses the provider-neutral emulator contract with Floci as its local
qualification backend.

The control plane must never contain Docker- or Kubernetes-specific execution
logic. It submits a normalized workload to an execution backend, observes the
same lifecycle, and stores the same evidence regardless of where the workload
runs.

```text
                         +----------------------+
                         |     Ronin Control     |
                         | API, auth, durable DB |
                         +----------+-----------+
                                    |
                         ExecutionBackend protocol
                                    |
             +----------------------+----------------------+
             |                      |                      |
   +---------v---------+  +---------v---------+  +---------v---------+
   | Docker backend    |  | Kubernetes backend|  | VM backend        |
   | Compose/local     |  | kind/in-cluster  |  | future adapter    |
   +---------+---------+  +---------+---------+  +---------+---------+
             |                      |                      |
       containers             Jobs/Pods              VM agent/runtime
```

## Goals

- Run entirely on the user's machine without cloud credentials or provider APIs.
- Allow Ronin itself to create, observe, cancel, and clean up its own Pods or
  Jobs when Kubernetes is selected.
- Preserve one worker protocol and one evidence model across Docker, Kubernetes,
  and future VM execution.
- Run Ronin inside a VM or inside Kubernetes without changing domain behavior.
- Keep the local installation simple: Docker Compose remains a supported profile.
- Make isolation, resource limits, cancellation, logs, provenance, and cleanup
  explicit and testable.
- Keep external cloud emulation behind an adapter; Floci is local infrastructure,
  not a cloud dependency.

## Non-goals

- Connecting Ronin OSS to AWS, Azure, GCP, Databricks, Snowflake, or Fabric.
- Building a hosted control plane or multi-tenant SaaS layer.
- Treating Docker Compose as a Kubernetes implementation.
- Giving the Ronin API unrestricted access to the host Docker socket or cluster.
- Supporting every Kubernetes distribution in the first implementation.
- Adding Ronin Pro capabilities to the OSS runtime.

## Terminology and boundaries

### Control plane

The control plane owns API requests, authorization, durable job state, retries,
execution identity, evidence references, and the desired state of a workload.
It does not start processes, create containers, or call Kubernetes APIs directly.

### Execution plane

The execution plane runs bounded worker workloads. It owns runtime-specific
submission, observation, log collection, cancellation, timeout enforcement, and
cleanup.

### Runtime backend

An adapter implementing the execution contract. It translates a normalized
`WorkloadSpec` into a Docker container, Kubernetes Job/Pod, or VM workload.

### Emulator backend

An adapter for Cloud Studio resources. It is separate from the execution backend:
Floci emulates cloud APIs; it does not schedule Ronin workers.

## Canonical execution model

Every execution is represented by a durable `Run` and an immutable workload
specification. The backend receives a backend-independent request:

```python
class ExecutionBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...
    def submit(self, spec: WorkloadSpec) -> WorkloadHandle: ...
    def get_status(self, handle: WorkloadHandle) -> WorkloadStatus: ...
    def stream_logs(self, handle: WorkloadHandle, cursor: str | None = None) -> LogBatch: ...
    def cancel(self, handle: WorkloadHandle, reason: str) -> None: ...
    def delete(self, handle: WorkloadHandle) -> None: ...
    def collect_evidence(self, handle: WorkloadHandle) -> ExecutionEvidence: ...


@dataclass(frozen=True)
class WorkloadSpec:
    run_id: str
    worker_protocol: str                 # currently worker/v1
    image: ImageReference                # digest preferred, tag rejected in release mode
    command: tuple[str, ...]
    environment_refs: tuple[str, ...]    # references, never secret values
    input_artifacts: tuple[str, ...]
    resource_limits: ResourceLimits
    timeout_seconds: int
    network_policy: NetworkPolicy
    labels: Mapping[str, str]
```

The existing kernel and worker contracts remain the domain-level source of
truth. `ExecutionBackend` is an orchestration port around them, not a second
execution protocol. The existing `plugin-worker/v1` request and response
semantics must be carried unchanged across every backend.

## Lifecycle and state machine

The control plane persists intent before submission and treats backend calls as
retriable, idempotent operations.

```text
accepted → admitted → submitted → running → succeeded
                         │            ├── failed
                         │            ├── cancelled
                         │            └── timed_out
                         └── submission_failed
```

Required rules:

1. `run_id` and `workload_id` are stable identities.
2. Submission uses an idempotency key derived from the run identity.
3. A controller restart reconciles durable desired state with backend state.
4. Cancellation is persisted first, then propagated to the backend.
5. A terminal workload is retained long enough to collect logs and evidence.
6. Cleanup is separate from completion and is retryable.
7. An orphan detector removes workloads whose control-plane owner no longer
   exists, subject to a grace period.

## Backend profiles

### Profile A: Docker Compose local

This is the lowest-friction installation profile.

```text
Ronin API → local runner broker → Docker Engine → worker container
```

The runner broker owns the narrow Docker authority. The API and ordinary
workers do not receive a general-purpose Docker socket. SQLite is acceptable for
single-user development; PostgreSQL is the durable local appliance option.

Use this profile for quick setup, plugin development, and deterministic unit and
integration tests.

### Profile B: local Kubernetes with kind

This is the reference Kubernetes profile.

```text
Ronin API Pod → Kubernetes API → Ronin namespace → Job/Pod → worker container
```

Docker Desktop's Kubernetes integration with `kind` is preferred for local
development because it supports multi-node clusters, selectable Kubernetes
versions, and Docker-backed nodes. The cluster is still local; no cloud account
or remote control plane is involved.

Ronin creates a `Job` for finite work and a `Pod` only where an interactive or
long-lived workload requires it. The backend watches status, container state,
events, and logs through the Kubernetes API.

Recommended initial local cluster:

- one control-plane node and one worker for ordinary development;
- one control-plane node and two workers for scheduling and failure tests;
- a Ronin namespace, ResourceQuota, LimitRange, and NetworkPolicy;
- a pinned Kubernetes version recorded in the qualification evidence.

`minikube --driver=docker` remains a supported contributor option, but is not a
core architectural dependency. It provides a useful alternative single-cluster
developer experience; the backend contract must not branch on Minikube.

### Profile C: Ronin inside a VM

A VM is a packaging boundary. Inside it, Ronin uses either the Docker backend or
the Kubernetes backend. The VM adapter is responsible only for bootstrap,
storage paths, networking, and lifecycle of the guest runtime.

The application must not inspect hypervisor-specific APIs. VM identity and
runtime facts are recorded as environment evidence, not leaked into domain
objects.

### Profile D: Ronin inside Kubernetes

When Ronin itself runs in Kubernetes, it uses in-cluster API discovery and a
dedicated ServiceAccount. It creates workloads in a configured namespace, which
may be the same namespace for a single-user installation or a separate managed
namespace.

The first implementation should support same-cluster execution. Cross-cluster
submission is a later adapter and must require an explicit endpoint, trust
configuration, and separate evidence policy.

## Kubernetes backend design

### Submission

The backend renders a deterministic Job manifest from `WorkloadSpec`:

- labels include `ronin.run_id`, `ronin.workload_id`, and `ronin.worker_protocol`;
- the image is resolved to a digest before release qualification;
- command and arguments are allowlisted by the worker contract;
- environment values are references or projected secrets, never arbitrary API
  payload values;
- `activeDeadlineSeconds` mirrors the Ronin timeout;
- `backoffLimit` is explicit and bounded;
- restart policy is selected by workload kind;
- CPU, memory, ephemeral storage, and process limits are explicit;
- security context runs as non-root with a read-only root filesystem where
  compatible;
- service account token automount is disabled unless the worker explicitly needs
  Kubernetes API access.

### Observation

The backend watches the Job and Pod resources, but the durable source of truth is
Ronin's run ledger. Kubernetes status is an observed projection. Events and
container termination reasons are normalized into provider-neutral failure kinds:

```text
submission_error, image_error, timeout, cancellation, crash,
resource_exhausted, policy_denied, protocol_error, unknown
```

### Cancellation and cleanup

Cancellation marks the run first, sends a delete request with a bounded grace
period, and verifies that the workload has terminated. Cleanup deletes owned
Jobs, Pods, temporary ConfigMaps, and ephemeral volumes. Finalizers must not be
used to hide failed cleanup; the ledger records cleanup state separately.

### Logs and evidence

Logs are collected through the Kubernetes API and stored through the existing
evidence store with bounded size and redaction. Evidence must contain:

- cluster and Kubernetes server identity;
- namespace, Job, and Pod names;
- image digest and worker protocol;
- resource requests and limits;
- start/end timestamps;
- terminal state and reason;
- relevant event summaries;
- log/artifact references.

## Security model

The local-first requirement does not justify unrestricted local authority.

### Docker

- Keep Docker authority in the runner broker.
- Do not expose a raw Docker command endpoint.
- Validate image, command, mounts, environment references, and limits.
- Use an allowlisted workspace mount policy.
- Record the Docker image digest and daemon identity.

### Kubernetes

- Use a dedicated ServiceAccount and namespace.
- Grant the minimum verbs on Jobs, Pods, Pods/log, Events, ConfigMaps, and
  Secrets required by the selected profile.
- Do not grant cluster-admin.
- Apply ResourceQuota and LimitRange before accepting workloads.
- Use NetworkPolicy default-deny where the local cluster supports it.
- Make hostPath, privileged mode, host networking, host PID, and host IPC
  unavailable to ordinary workloads.
- Keep user-provided content out of labels, annotations, and shell commands.
- Redact secrets from logs, status, and evidence.

### VM

- Treat the VM boundary as isolation, not authorization.
- Keep the same workload validation and evidence rules inside the guest.
- Do not assume a VM makes privileged containers safe.

## Persistence and recovery

The execution backend must not own business truth. Durable state belongs to the
control plane's Job/Run store.

Minimum records:

- run identity and requested backend;
- immutable WorkloadSpec digest;
- backend handle and ownership labels;
- lifecycle transitions;
- retry and cancellation attempts;
- evidence references;
- cleanup state;
- environment and image fingerprints.

On restart, the controller executes reconciliation:

```text
desired run state + backend observation → deterministic correction
```

If a backend cannot be reached, the run becomes `observation_degraded`, not
silently `failed`. A bounded retry policy eventually produces an explicit
`backend_unavailable` outcome.

## Cloud Studio relationship

Cloud Studio and workload execution are separate ports:

```text
CloudTopology → EmulatorBackend → Floci (local)
WorkloadSpec  → ExecutionBackend → Docker/kind/VM
```

Ronin OSS must not call cloud provider APIs. Floci is started locally through
Compose or Kubernetes and is selected through the emulator adapter. Terraform
or OpenTofu export is optional and must not be required for Ronin's own
execution lifecycle.

## Configuration and deployment contract

The deployment profile should be explicit rather than inferred from incidental
environment variables:

```yaml
execution:
  backend: docker | kubernetes
  namespace: ronin-system
  worker_image: ghcr.io/example/ronin-worker@sha256:...
  worker_protocol: plugin-worker/v1
  default_timeout_seconds: 900
  limits:
    cpu: "2"
    memory: 4Gi
  network_policy: local-only
```

Environment variables may override development defaults, but release manifests
must be rendered from a validated configuration object and included in evidence.

## Implementation roadmap

### Phase 1 — normalize the port

1. Define `WorkloadSpec`, `WorkloadHandle`, `WorkloadStatus`, capabilities, and
   normalized failure kinds in a runtime-neutral module.
2. Move existing Docker/container execution behind `DockerExecutionBackend`.
3. Preserve `plugin-worker/v1` and existing durable execution/evidence contracts.
4. Add conformance tests that run against an in-memory fake backend.

### Phase 2 — local Kubernetes backend

1. Add a Kubernetes client adapter with injectable transport for unit tests.
2. Render deterministic Job manifests and validate them before submission.
3. Implement submit, watch, logs, cancel, cleanup, and reconciliation.
4. Add a local `kind` profile with namespace, RBAC, quotas, and network policy.
5. Run the worker protocol and isolation qualification against kind.

### Phase 3 — local appliance integration

1. Package Ronin, PostgreSQL, Floci, and the selected backend profile.
2. Add health/readiness checks for the control plane, database, emulator, and
   execution backend.
3. Emit one release evidence bundle containing all local runtime fingerprints.

### Phase 4 — VM and in-cluster packaging

1. Define a VM image/bootstrap contract that selects Docker or Kubernetes.
2. Add Helm/Kustomize manifests for Ronin-in-Kubernetes.
3. Add in-cluster RBAC and same-cluster worker submission.
4. Qualify restart, orphan cleanup, cancellation, and upgrade behavior.

### Phase 5 — optional remote adapters

Remote or provider-specific adapters may be added later without changing the
control-plane contract. They require separate security review, credentials
handling, evidence policy, and release scope. They are not required for Ronin
OSS local-first.

## Qualification matrix

| Gate | Local target | Evidence required |
|---|---|---|
| Docker isolation | Docker Desktop Engine | daemon, image digest, lifecycle, cancellation |
| Kubernetes execution | kind on Docker Desktop | cluster version, RBAC, Job/Pod lifecycle, logs |
| Persistence | local PostgreSQL | server version, migrations, rollback, concurrency |
| Cloud emulation | Floci | emulator version, endpoint health, topology contract |
| Browser shell | local Chromium | routes, console, keyboard, accessibility results |
| Worker protocol | Docker and kind | `plugin-worker/v1` request/response evidence |
| Reconciliation | restart local control plane | desired/observed convergence and orphan cleanup |

No gate is considered passed merely because a mock or in-memory backend passed.
Each qualification record must identify the exact commit, runtime/build
fingerprint, environment, command, result, and artifact references.

## Architectural consequences

- Kubernetes is not an optional conceptual feature; it is a first-class backend.
- Docker Compose remains the best default installation path.
- `kind` is the reference local Kubernetes environment.
- Minikube is supported only as an adapter-compatible contributor environment.
- VM support is achieved through packaging and runtime adapters, not domain
  changes.
- Cloud Studio remains local and emulator-backed through Floci.
- Ronin Pro is not required for any of these contracts or deployment profiles.

## Open decisions

1. Whether the first Kubernetes backend uses the official Kubernetes Python
   client or a narrower HTTP transport wrapper.
2. Whether interactive notebook sessions use Pods, Deployments, or a dedicated
   session controller; finite executions should use Jobs.
3. The supported local Kubernetes version range and kind node image policy.
4. The default PostgreSQL persistence profile for the first self-hosted release.

These decisions must not change the central boundary: Ronin's control plane
submits provider-neutral workloads to a replaceable local execution backend.
