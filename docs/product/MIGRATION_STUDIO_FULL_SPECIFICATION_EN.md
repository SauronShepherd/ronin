# Ronin Migration Studio — Functional, Architectural and Technical Specification

**Document status:** Implementation-aligned specification  
**Product:** Ronin Migration Studio  
**Primary use case:** Controlled migration of legacy ETL assets to portable PySpark projects  
**Language:** English  
**Last reviewed:** 2026-09-19

## 1. Purpose and scope

Migration Studio is the Ronin module for discovering, qualifying, converting, validating and exporting migration assets. The module is designed for migration work where source assets must be inspected, transformed into an explicit target blueprint, generated as executable PySpark code, and checked against expected results.

The implementation supports an evidence-driven workflow rather than a blind code translator. Every material decision must be traceable to an uploaded artifact, an inventory item, a blueprint rule, a generated file, a validation result or an execution record.

This document describes the current product contract, architecture, APIs, command-line interface, user interface, security model, validation semantics, testing expectations and operational behavior.

## 2. Product principles

1. **Inventory before conversion.** Source files are classified and indexed before a migration unit is generated.
2. **Explicit contracts.** The blueprint is the canonical intermediate representation between source analysis and code generation.
3. **Safe degradation.** Unsupported or ambiguous constructs become review-required findings; they are never silently discarded.
4. **Portable output.** Generated projects and exported migration scripts must be usable outside Ronin.
5. **Validation is a first-class result.** A conversion is incomplete until structural, metric and semantic checks are represented.
6. **Evidence over assertion.** Runtime claims must be backed by captured execution evidence or clearly marked as planned or unavailable.
7. **Deterministic provenance.** Digests, manifests, rule identifiers and source references make results reproducible.

## 3. Goals

- Accept legacy migration assets, including IICS-style export bundles.
- Build a secure inventory of source assets and their relationships.
- Select one or more migration units with explicit scope and policy.
- Produce a reviewable target blueprint.
- Generate a PySpark project with standard, inspectable files.
- Generate a standalone migration script for execution outside Ronin.
- Run static qualification before runtime execution.
- Define simple and complete validation reports per result.
- Support Spark smoke qualification and runtime evidence capture.
- Compare baseline and candidate outcomes with safe promotion gates.
- Persist session state and expose it through API, CLI and web UI.

## 4. Non-goals

- Automatic semantic equivalence for every proprietary transformation.
- Silent conversion of unsupported expressions, custom Java code or opaque binaries.
- Treating a generated script as production-ready without environment-specific review.
- Using UI state as the source of truth for migration decisions.
- Claiming successful runtime execution when only static generation has occurred.

## 5. End-to-end user journey

1. Create a migration session.
2. Upload source artifacts using the session artifact endpoint.
3. Discover and classify the inventory.
4. Inspect assets, dependencies, warnings and confidence.
5. Select a migration scope.
6. Build or review the target blueprint.
7. Generate the PySpark project.
8. Run static qualification and inspect findings.
9. Export the portable migration script when required.
10. Run validation in simple or full mode.
11. Optionally run Spark preflight or smoke qualification.
12. Generate reports and attach evidence.
13. Review promotion gates and either complete, revise or cancel the session.

## 6. Repository architecture

The implementation is organized into a domain package and thin integration surfaces.

```text
python/studio_migration/
  model.py             Domain models and serializable contracts
  session.py           Migration session lifecycle and orchestration
  session_store.py     Session persistence abstraction
  inventory.py         Source inventory and artifact classification
  adapters/iics.py     IICS export discovery and metadata extraction
  scope.py             Scope selection and dependency closure
  blueprint.py         Blueprint construction and rule precedence
  analysis.py          Static analysis and qualification findings
  pyspark_codegen.py   PySpark project and portable script generation
  validation.py        Result comparison and validation reports
  reports.py           Markdown, JSON and HTML report rendering
  benchmark.py         Benchmark protocol and promotion gates
  spark_validation.py  Spark compiler/runtime validation
  evidence.py          Provenance and evidence bundle integration
  runtime.py           Runtime integration and execution metadata
  api.py               HTTP route registration and handlers

python/studio_cli/
  __init__.py          CLI command tree and migration export command

web/js/app.js          Migration Studio web behavior
api/openapi-v1.json    Public API contract
tests/                 Unit, contract, CLI, static and integration tests
```

The domain layer is intended to remain usable without the web application. API and CLI adapters translate input into domain commands and serialize domain results.

## 7. Core domain objects

### 7.1 SourceArtifact

Represents one uploaded source object. It includes an artifact identifier, original filename, media type, byte size, SHA-256 digest, storage reference and upload metadata. The digest is lowercase SHA-256 and is used for identity, duplicate detection and provenance.

### 7.2 SourceInventory

Represents the discovered contents of an artifact or bundle. Each inventory item contains a normalized path, detected asset kind, source format, metadata, dependencies, confidence and review findings.

### 7.3 MigrationUnit

Represents a source asset selected for conversion. It references the source inventory, selected dependencies, source digest and the conversion profile.

### 7.4 ScopeSelection

Defines the requested roots, inclusion/exclusion rules, dependency closure policy and selected migration units. Scope is explicit and immutable for a generation attempt.

### 7.5 BlueprintContract

The canonical target contract. It describes inputs, outputs, transformations, joins, filters, parameters, expected schema, nullability, ordering assumptions, quality checks and unresolved decisions.

### 7.6 GeneratedProject

Contains generated source files, manifest metadata, blueprint digest, project digest, generation warnings and ownership/provenance information.

### 7.7 MigrationSession

Owns lifecycle state, uploaded artifacts, discovery output, scope, blueprint, generated project, validation results, reports, benchmark observations and evidence references.

## 8. Session lifecycle

The supported state progression is:

```text
draft
  -> artifacts_ready
  -> discovering
  -> scope_ready
  -> converting
  -> qualifying
  -> completed

Any active state may transition to failed or cancelled according to the operation outcome.
```

State invariants:

- A session cannot discover without at least one accepted artifact.
- A session cannot convert without a resolved scope and blueprint.
- A session cannot be marked completed when blocking qualification findings remain.
- Export requires a generated project; it does not require the web UI to remain active.
- Validation results reference the generated project and the selected comparison mode.
- Failed operations retain diagnostic context and do not silently reset earlier evidence.

## 9. Source ingestion and security limits

The ingestion layer accepts binary uploads and validates request metadata before parsing. It supports per-file, per-session and per-validation limits:

| Limit | Current policy |
|---|---:|
| Maximum artifact size | 512 MiB |
| Maximum artifacts per session | 256 |
| Maximum total session bytes | 2 GiB |
| Maximum validation rows | 100,000 |
| Maximum validation columns | 1,000 |
| Maximum validation key fields | 1,000 |

Bundle handling must reject path traversal, absolute paths, symlinks, duplicate normalized paths, unsafe decompression ratios and unsupported special files. Extraction is bounded and does not execute source content.

Upload validation must occur before expensive parsing. Error responses identify the violated limit without exposing local filesystem paths or secrets.

## 10. IICS adapter and source interpretation

The IICS adapter is the first-class source adapter for the current implementation. It discovers common export structures including:

- `DTEMPLATE` mapping templates;
- `MTT` mapping task metadata;
- `mappingTemplate.json` and `mtTask.json` metadata files;
- `bin/@*.bin` opaque or compiled assets;
- parameter files under `ParamFiles`;
- mapping identifiers such as `mappingId` and `assetFrsGuid`.

Discovery is exact-path first and metadata-assisted second. A mapping task is linked to its template through explicit identifiers where available. Ambiguous or missing links are represented as unresolved dependencies and produce review-required findings.

The adapter must preserve source references, detected names, original paths, digests and parser diagnostics. It may infer a friendly asset name, but inferred names must not replace the original identity.

Opaque binary content is inventoried but is not interpreted as executable logic unless a trusted parser is explicitly configured. Unsupported constructs are surfaced in the blueprint as manual actions.

## 11. Scope resolution

Scope selection supports root assets, dependency inclusion, explicit exclusions and profile-level filters. The resolver should compute dependency closure so that a generated migration unit does not silently omit required templates, parameter files or referenced datasets.

The scope result contains:

- selected roots;
- included dependencies;
- excluded assets and reasons;
- unresolved dependencies;
- source digests;
- a deterministic scope digest;
- warnings and blocking findings.

Changing scope invalidates downstream generation and qualification results because the blueprint digest and project digest may change.

## 12. Blueprint and rule precedence

Blueprint construction is deterministic. Rules are evaluated in the following precedence order:

1. core platform rules;
2. PySpark target rules;
3. source adapter profile;
4. project or customer blueprint rules;
5. explicit client overrides.

Each resolved rule should expose its identifier, source, priority, input evidence, output decision and confidence. Conflicts must be visible to the reviewer.

Supported classifications include:

- `supported`: safe to generate automatically;
- `supported_with_warning`: generated with a documented caveat;
- `review_required`: a human decision is required before production use;
- `unsupported`: no safe automatic translation is available;
- `not_applicable`: source construct is outside the selected migration unit.

The blueprint must preserve semantic intent such as join type, filter predicates, projection order, null behavior, duplicate handling, parameter substitution and output format. A code-shaped approximation without these semantics is not a valid blueprint.

## 13. Generated PySpark project

The generated project is deliberately conventional and inspectable. A typical project contains:

```text
<project>/
  generated/
    <asset>.py
  manifest.json
  blueprint.json
  README.md
  validation/
  evidence/
```

The manifest records project identity, source artifacts, source digests, blueprint digest, generation timestamp, generator version, rule identifiers, warnings and expected outputs.

Generated code must:

- use explicit Spark DataFrame transformations;
- avoid hidden global state;
- preserve source-to-target column lineage where known;
- make input and output locations configurable;
- use stable application naming;
- use standard Delta read/write conventions when the target profile requests Delta;
- surface unresolved behavior in comments or manifest findings;
- remain parseable by Python tooling.

Ownership is explicit. Files generated by Ronin carry provenance metadata and are safe to regenerate. User-edited files must be detected by digest or marked as external so regeneration does not silently overwrite custom work.

## 14. Portable migration script export

Migration Studio can export a standalone `ronin_migration.py` program from a generated project. The exported script is intended for use outside Ronin and must not import Ronin modules.

The portable program includes:

- standard-library `argparse`;
- `--source` input location;
- `--output` output location;
- `--app-name` Spark application name;
- embedded manifest JSON;
- embedded project and blueprint digests;
- SparkSession construction;
- generated transformation entry point;
- Delta input and output handling;
- `try/finally` Spark shutdown;
- a clear `main()` entry point.

CLI usage:

```text
python -m python.studio_cli migrate export <project-directory> --output <file.py>
```

The CLI refuses to overwrite an existing output file unless the caller removes or changes the destination. The HTTP export route regenerates the program from the persisted session project and returns the content as `text/x-python` with filename and digest metadata. The web UI downloads the same content as a local Python file.

Export is a reproducibility boundary: the standalone file must retain enough provenance to identify the source project without requiring access to a running Ronin instance.

## 15. Static analysis and qualification

Static qualification runs before runtime execution. It combines Python syntax validation, generated-file checks, manifest checks, blueprint consistency checks and source coverage checks.

Rule families include:

- syntax and import safety;
- missing generated files;
- missing source references;
- unresolved dependencies;
- unsupported source constructs;
- missing input or output declarations;
- schema drift between blueprint and generated code;
- unsafe or non-deterministic expressions;
- missing validation expectations;
- provenance and digest mismatches.

Findings have a stable rule identifier, severity, message, source location, evidence references and remediation guidance. Blocking findings prevent completion or promotion; warnings remain visible in reports.

## 16. Validation model

Validation checks whether generated results match declared expectations. It is independent from code generation and can be run against baseline and candidate datasets.

Supported comparison dimensions include:

- schema and column order;
- data types and nullability;
- row counts;
- null counts;
- distinct counts;
- aggregate metrics;
- full-row equality;
- multiset equality where row order is irrelevant;
- keyed comparison where a stable business key exists;
- duplicate-key detection;
- null-safe value comparison;
- configurable numeric tolerances.

The comparison mode must be recorded with every result. A pass means the configured contract was satisfied; it does not mean every possible property of the datasets is equal.

Keyed validation requires an explicit key declaration. Duplicate keys are reported separately because they can make a keyed comparison ambiguous. Null-safe semantics must distinguish null from an empty string, zero or a missing column.

Validation is bounded by the ingestion limits and must fail clearly when a dataset cannot be safely sampled or compared. Sampling must be visible in the report and must never be presented as full equality.

## 17. Reports

Reports are generated per validation result and support two levels:

### Simple report

The simple report is optimized for operational review and contains:

- session, project and result identifiers;
- overall status;
- comparison mode;
- baseline and candidate references;
- key metrics;
- failed checks;
- warning count;
- top remediation actions;
- source and project digests.

### Complete report

The complete report adds:

- complete check catalog;
- schema differences;
- aggregate and row-level mismatch summaries;
- duplicate-key details;
- tolerance configuration;
- sampling information;
- blueprint and rule references;
- generated-file references;
- runtime metadata;
- evidence links;
- machine-readable diagnostics.

The canonical report model is JSON. Markdown and HTML renderings are presentation formats and must preserve the same status and identifiers. Report generation must be deterministic for identical inputs apart from explicitly labeled timestamps.

## 18. Spark compiler and runtime qualification

`SparkValidationPlan` describes how a generated project is checked against a Spark runtime. It separates:

1. preflight checks, such as Python syntax, dependency availability and configuration;
2. compile or parse checks;
3. smoke execution against bounded data;
4. evidence capture, including command, environment, exit status and output references.

The current verification path includes a Spark smoke test under the supported WSL2/Docker environment when available. Local development environments without Spark must report an unavailable runtime rather than fabricating a pass.

Runtime evidence is associated with the generated project digest and the exact command or plan used. A runtime result from a different project digest cannot satisfy the current project’s qualification gate.

## 19. Benchmarking and promotion

Benchmarking compares a baseline and a candidate under a declared protocol. The protocol records warm-up runs, measured runs, selected statistic, environment metadata, dataset identity and result fingerprints.

The default promotion threshold is a 5% regression budget, subject to quality gates. A candidate cannot be promoted merely because it is faster if validation fails, the output fingerprint changes unexpectedly or blocking findings remain.

Benchmark statuses include:

- `pass`: quality gates pass and performance is within policy;
- `fail`: one or more gates fail;
- `inconclusive`: the environment or sample is insufficient;
- `rejected`: a candidate was explicitly declined with a reason.

All benchmark decisions must be reproducible from their protocol and evidence references.

## 20. Evidence and provenance

Evidence is a first-class bridge between product results and operational review. Evidence records may include:

- source artifact digest;
- inventory item and source path;
- scope digest;
- blueprint digest;
- generated project digest;
- validation result identifier;
- benchmark protocol and observations;
- Spark command and environment;
- report artifact digest;
- reviewer decision and timestamp.

Evidence bundles should be fenced and bounded. A bundle must not include secrets, unrestricted local paths or arbitrary source payloads. Large outputs are referenced by digest and controlled storage location.

## 21. HTTP API contract

The current Migration Studio route family includes:

```text
POST   /v1/migration/sessions
GET    /v1/migration/sessions/{session_id}
DELETE /v1/migration/sessions/{session_id}
POST   /v1/migration/sessions/{session_id}/artifacts
PUT    /v1/migration/sessions/{session_id}/artifacts/{artifact_id}/content
GET    /v1/migration/sessions/{session_id}/artifacts/{artifact_id}
POST   /v1/migration/sessions/{session_id}/discover
GET    /v1/migration/sessions/{session_id}/inventory
POST   /v1/migration/sessions/{session_id}/scope
POST   /v1/migration/sessions/{session_id}/blueprint
POST   /v1/migration/sessions/{session_id}/generate
GET    /v1/migration/sessions/{session_id}/export
POST   /v1/migration/sessions/{session_id}/qualify
POST   /v1/migration/sessions/{session_id}/validate
GET    /v1/migration/sessions/{session_id}/reports
POST   /v1/migration/sessions/{session_id}/benchmark
POST   /v1/migration/sessions/{session_id}/complete
POST   /v1/migration/sessions/{session_id}/cancel
```

Exact request and response schemas are defined in `api/openapi-v1.json`. Route handlers must delegate domain decisions to the session service and must not duplicate lifecycle logic.

The export response contains the generated filename, script content, project digest, blueprint digest and media type. Errors use the platform error envelope and must avoid leaking filesystem or credential data.

## 22. CLI contract

The CLI exposes migration operations for automation and offline workflows. The portable export command is:

```text
python -m python.studio_cli migrate export PROJECT --output OUTPUT.py
```

The command reconstructs the generated project from its manifest and generated files, validates the required project structure, generates the portable program and writes a new file. It returns a non-zero exit code for missing projects, invalid manifests, missing generated assets or an existing destination.

CLI output should be suitable for both humans and automation: concise success information on standard output and actionable diagnostics on standard error.

## 23. Web UI requirements

The Migration Studio UI is a Ronin-styled workflow surface. It must make the lifecycle visible and keep source, target, validation and evidence concepts distinct.

Required controls include:

- session creation and status;
- artifact upload and inventory inspection;
- scope selection;
- blueprint review;
- generation and qualification actions;
- validation mode selection;
- simple and complete report actions;
- portable migration script export;
- benchmark and promotion status;
- evidence and diagnostic references.

The UI must not fabricate metrics, runtime status or validation success. Missing data is represented as unavailable, pending or not run. Download actions must use the API result, preserve the returned filename and give visible feedback for failures.

## 24. Security requirements

- Validate all path-like input before storage or extraction.
- Normalize archive paths before duplicate and traversal checks.
- Reject symlinks and special files in uploaded bundles.
- Bound decompression and parsing work.
- Never execute uploaded source code during discovery.
- Keep secrets out of manifests, reports, logs and evidence bundles.
- Redact credentials, tokens and environment secrets from diagnostics.
- Apply session ownership and authorization checks to every route.
- Enforce content-length and body limits before buffering untrusted data.
- Use deterministic digests for integrity, not as a substitute for authorization.
- Do not expose host filesystem paths in API responses.
- Treat generated code as untrusted until reviewed and qualified in the target environment.

## 25. Persistence and operational behavior

Session persistence must survive normal request boundaries and preserve enough state to resume review. The storage implementation should support atomic updates of session state and associated artifacts.

Persisted records should include schema version, session status, timestamps, identifiers, digests and diagnostic summaries. Large binary content and large report payloads should be stored through controlled artifact references rather than copied into every session record.

On restart, a session may resume from its last durable state. In-progress operations must be represented as interrupted or failed if their completion cannot be proven. A restart must never mark a conversion or runtime operation as successful by assumption.

## 26. Versioning and compatibility

The following values must be versioned independently:

- source adapter version;
- blueprint schema version;
- rule-pack version;
- code generator version;
- validation schema version;
- report schema version;
- portable script contract version.

Changes to any of these values should be visible in the manifest and reports. Backward-compatible readers may accept older manifests, but generation should identify the active versions explicitly.

## 27. Test strategy

The module is tested at several levels:

1. domain unit tests for inventory, scope, blueprint, validation and lifecycle rules;
2. adapter tests for IICS discovery and ambiguous relationships;
3. code-generation tests for syntax, manifests, provenance and portable export;
4. API contract tests for routes, limits, error envelopes and export responses;
5. CLI tests for offline export and failure exit codes;
6. static web tests for required controls and route markers;
7. browser smoke checks for navigation, UI overflow and console errors;
8. Spark runtime checks where the supported runtime is available;
9. full-suite regression testing to detect cross-module route or schema changes.

Acceptance evidence for the current implementation includes focused Migration Studio tests covering code generation, API export, OpenAPI consistency, CLI export and static UI behavior; route consistency checks; OpenAPI parsing; Ruff checks; JavaScript syntax checks; browser smoke checks; and a broader repository suite previously recorded at 1,407 passed and 16 skipped tests. Skips correspond to environment-dependent integrations and must remain explicitly reported.

## 28. Definition of done

A migration session is operationally complete only when:

- all source artifacts are accepted, inventoried and digested;
- scope and dependency closure are explicit;
- the blueprint contains no unexplained blocking ambiguity;
- generated files are syntactically valid and provenance-tagged;
- static qualification has passed or has documented review findings;
- a portable script can be exported when requested;
- validation results have a declared comparison mode and report;
- runtime claims have evidence or are marked unavailable;
- promotion decisions include quality and performance gates;
- the session state and reports are persisted;
- the user can inspect, download and reproduce the result outside Ronin.

## 29. Operational runbook

When a migration fails, inspect in this order:

1. session state and last durable operation;
2. artifact size, digest and ingestion diagnostics;
3. inventory classification and unresolved dependencies;
4. scope and blueprint findings;
5. generator manifest and project digest;
6. static qualification findings;
7. validation mode, keys, tolerances and sampling metadata;
8. Spark preflight and runtime evidence;
9. benchmark protocol and promotion gates.

Do not resolve a semantic mismatch by changing a tolerance without recording the decision in the blueprint or validation policy. Do not rerun a failed runtime claim without preserving the original evidence and environment metadata.

## 30. Traceability matrix

| Product capability | Domain implementation | External contract |
|---|---|---|
| Ingestion | `inventory.py`, `session.py` | Artifact API |
| IICS discovery | `adapters/iics.py` | Inventory model |
| Scope | `scope.py` | Scope API |
| Blueprint | `blueprint.py` | Blueprint API |
| Generation | `pyspark_codegen.py` | Generated project manifest |
| Portable export | `pyspark_codegen.py`, `studio_cli`, `api.py` | CLI and export route |
| Static qualification | `analysis.py`, `qualification.py` | Qualification result |
| Validation | `validation.py` | Validation result and reports |
| Reporting | `reports.py` | JSON, Markdown and HTML outputs |
| Spark runtime | `spark_validation.py`, `runtime.py` | Runtime evidence |
| Benchmarking | `benchmark.py` | Promotion decision |
| Provenance | `evidence.py` | Evidence bundle |
| Web workflow | `web/js/app.js` | Ronin UI |

## 31. Implementation notes and boundaries

The current module is intentionally conservative around semantics that cannot be established from source metadata. This means a high-quality result may contain review-required findings even when code generation succeeds. The generated project and portable script are deliverables, not proof of business equivalence.

The strongest contract is the combination of source digest, scope digest, blueprint digest, generated project digest, validation mode and runtime evidence. Any downstream system consuming a Migration Studio result should persist those identifiers together.

