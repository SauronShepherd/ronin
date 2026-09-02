# Projects, Git repositories, and execution profiles

Ronin is a multi-project Data + AI platform. A project is the primary unit a user switches between in the product UI and the unit to which repository, execution, policy, lineage, cost, observability, and collaboration context attach.

## Project model

Every usable project has a stable project ID, a human-readable name, exactly one **primary Git repository**, optional supporting repositories, and one selected execution profile. A workspace/application boundary can expose many projects and switch active context without restarting the platform.

The primary repository is where the project code and portable Ronin configuration live. Supporting repositories allow shared libraries, documentation, infrastructure, models, or other project-owned assets to participate without making a hosting provider part of the core model.

Repository bindings are hosting-neutral. GitHub, GitLab, Bitbucket, self-hosted Git, SSH remotes, local repositories, and future Git-compatible systems belong behind adapters. Credentials are never embedded in repository URLs or persisted as literal tokens. Workspace bindings may hold `secret://` or `connection://` references, but committed project intent never contains those auth references.

Each repository declares an opaque `adapter_id`, a default ref, optional repository-relative subdirectory, and a bounded sync policy. `manual` performs no automatic remote synchronization, `fetch` may refresh remote refs without moving the checkout, and `fast-forward` may advance the selected checkout only when Git can do so without merge or rebase. Provider-specific authentication and transport behavior belongs to adapters.

## Portable `.ronin/` project configuration

The canonical repository-local project manifest is `.ronin/project.json` with schema identifier `ronin.project/v1`. `studio_core.ProjectManifest` serializes it as deterministic UTF-8 JSON with recursively stable domain ordering and JSON keys sorted by the serializer. The pure core reads/writes data and strings only; filesystem discovery, atomic writes, checkout registration, and migrations that touch files belong to CLI/storage/application boundaries.

The manifest commits only portable project intent:

- project ID and name;
- primary/supporting repository alias, URI, opaque Git adapter ID, default ref, optional subdirectory, and sync policy;
- opaque execution runtime profile reference when pinned;
- provider-neutral required/preferred capability requirements and resolution policy.

Machine/user-specific state is deliberately excluded: resolved credentials, `auth_ref` bindings, tokens, local checkout paths, runtime discovery snapshots, and resolved execution state. `ProjectManifest.from_project()` strips repository auth references when projecting a workspace project into committed intent. A workspace may reattach credential references after loading the manifest without changing the portable project identity.

Schema parsing is strict for `ronin.project/v1`: missing or unknown keys are rejected rather than silently discarded. Future schema evolution must use an explicit version/migration boundary rather than making older cores reinterpret newer intent.

This design adapts the useful versioned project-metadata idea from `sdp-studio` while intentionally not importing its Pydantic, YAML/filesystem persistence, provider-specific environment settings, clock/random defaults, or resolved runtime state into Ronin's canonical domain.

## Execution profile model

Ronin separates two concepts that commercial platforms often collapse:

1. **Runtime profile reference** — an opaque `adapter_id + profile_id` identifying a concrete profile exposed by an adapter. This permits UX presets such as a Microsoft Fabric Runtime, a Databricks Runtime/LTS profile, a local Spark environment, Spark Connect, Kubernetes, or other engines without hard-coding those vendors into the canonical domain.
2. **Capability requirements** — provider-neutral requirements such as `spark.version`, `python.version`, `engine.spark`, GPU availability, streaming, ML libraries, table-format support, isolation, or other typed capabilities. Requirements can be mandatory or preferred.

A project may pin a concrete runtime profile, express only capability requirements, or combine both. `strict` resolution means a requested concrete profile must exist, be available, and satisfy every required capability. `compatible` resolution may select an alternative advertised profile, but it never relaxes required capabilities; preferred capabilities only influence ranking.

Ronin core never branches on vendor names. Adapters discover currently available runtime profiles and normalize their capabilities into immutable `RuntimeProfile` snapshots. The pure resolver consumes only those snapshots and project intent, so discovery/provisioning I/O remains outside `studio_core`.

## Deterministic compatibility evidence

Every evaluated profile produces explicit evidence for each requirement: the advertised value, whether it satisfied the requirement, and a stable reason. A profile is compatible only when it is available and all required requirements pass. Missing or failed preferred requirements do not make a profile incompatible.

For the portable core grammar, a capability constraint is either an exact string (`delta`, `true`, `cuda`) or a comma-separated conjunction using `==`, `!=`, `>=`, `<=`, `>` and `<`. Ordered comparisons use numeric dotted versions such as `>=3.11,<4`; arbitrary provider version syntax must be normalized by the adapter before advertisement rather than interpreted by vendor-specific code in the core.

Resolution is deterministic. A compatible explicitly requested profile wins first. Otherwise, compatible-mode or capability-only resolution ranks candidates by the number of satisfied preferred requirements, then by stable `adapter_id`/`profile_id` ordering. An unavailable profile is never selected. The resolver never silently converts a required failure into a downgrade.

This evidence is designed for API/UI explanations and later resolved-runtime run snapshots. It is intentionally separate from adapter probing, provisioning, billing metadata, credentials, and runtime execution.

## Examples

The following names are illustrative adapter-owned identifiers, not hard-coded Ronin runtime versions:

- A project may select adapter `fabric-runtime` plus a profile discovered from the connected Fabric environment.
- Another project may select adapter `databricks-runtime` plus an LTS profile discovered from the connected Databricks environment.
- A local project may select `spark-local/default` and require a particular Python/Spark compatibility range.
- A portable project may omit a concrete runtime reference and require capabilities only, allowing Ronin to resolve an eligible local, container, Kubernetes, or remote runtime.

The adapters, not `studio_core`, know how Microsoft Fabric, Databricks, Spark distributions, Kubernetes, cloud services, or future systems name and provision their runtimes.

## Run reproducibility

Project intent is not enough for audit/replay. Every actual execution should later persist a **resolved runtime snapshot** alongside the run evidence: project ID, repository commit, dirty-patch hash when relevant, adapter ID, resolved profile ID, engine/runtime versions, environment/package lock or digest, container image digest where applicable, required/preferred capability evaluation, and effective non-secret runtime configuration.

This makes runs comparable even when a provider later changes the meaning or availability of a friendly profile such as an "LTS" channel.

## UX target

The product shell should provide a persistent project switcher. Project creation/editing should expose two independent steps:

- **Code** — select/create/link the primary Git repository and optional supporting repositories; choose adapter, default ref, sync policy, and workspace credential connection.
- **Compute / Runtime** — browse adapter-discovered runtime profiles and inspect their capabilities, or specify capability requirements and let Ronin resolve compatible targets.

Before execution, the UI should explain incompatibilities rather than silently changing runtime semantics. It should show which requested capabilities are satisfied, missing, downgraded, or supplied by an adapter-specific extension.

Future environments such as development/test/production may override the selected runtime profile or connections while preserving the same project identity and portable code. That environment layer must not duplicate project semantics or introduce vendor-specific branches into the core.
