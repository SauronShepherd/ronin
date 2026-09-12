# Ronin Platform Portability v1

**Status:** normative migration contract for Ronin Public v1

## 1. Purpose

Ronin Public v1 must provide a credible exit path from major Data + AI platforms. This contract defines how projects are imported, translated, reported and exported without pretending proprietary systems are identical.

Certified source profiles:

- Microsoft Fabric;
- Databricks;
- Palantir Foundry/AIP;
- Dataiku DSS.

The portability target is the **portable semantic intersection plus explicit adapters**, not undocumented emulation of proprietary internals.

## 2. Canonical Ronin Bundle

Every migration converges on a versioned `Ronin Bundle`.

Conceptual structure:

```text
ronin-bundle/
  manifest.json
  project/
  sources/
  notebooks/
  sql/
  pipelines/
  schedules/
  catalog/
  ontology/
  quality/
  semantic-models/
  dashboards/
  ml/
    experiments/
    models/
    features/
    evaluations/
  genai/
    prompts/
    retrieval/
    agents/
    evaluations/
  alerts/
  budgets/
  deployments/
  connections/
  policies/
  migration/
    source.json
    report.json
    losses.json
```

Secrets are never embedded. Connection definitions carry portable metadata and secret references only.

Identity-bearing JSON uses Ronin's canonical JSON contract.

## 3. Migration result classification

Every source object must be assigned exactly one status:

- `exact` — semantics represented without translation loss;
- `translated` — semantics preserved through a documented Ronin equivalent;
- `partial` — useful subset imported, with explicit missing semantics;
- `passthrough` — retained as source-provider artifact/reference and requires that provider to execute;
- `unsupported` — no safe representation;
- `manual_decision` — requires operator mapping or policy choice.

An importer MUST NOT silently drop an object or silently weaken its semantics.

Every migration emits a machine-readable report containing object identity, source type, target type, status, warnings, required remappings and unresolved dependencies.

## 4. Cross-platform canonical mappings

Ronin canonical assets include:

- workspace/project;
- repository/source artifact;
- connection;
- dataset/table/view/file/stream;
- notebook;
- SQL asset;
- transform/recipe;
- pipeline/DAG;
- schedule/trigger;
- quality rule;
- catalog asset;
- lineage edge;
- ontology object type/property/link/interface/action;
- semantic model/metric;
- dashboard/report definition;
- experiment/run;
- feature asset;
- model/model version;
- evaluation;
- deployment/endpoint;
- prompt/retrieval/agent asset;
- alert rule;
- budget/cost allocation rule;
- policy/grant;
- evidence artifact.

## 5. Microsoft Fabric profile

### 5.1 Import sources

The Fabric importer should use documented public definitions/APIs and Git-backed workspace representations where available.

Priority asset mapping:

| Fabric concept | Ronin target |
|---|---|
| Workspace | Workspace/Project boundary |
| Lakehouse / Warehouse table | Lakehouse table / SQL asset |
| Notebook | Notebook |
| Data Pipeline | Pipeline/DAG |
| Dataflow Gen2 transformation | Transform graph; partial when semantics lack Ronin equivalent |
| Semantic model | Semantic model |
| Report | Dashboard definition where portable; otherwise partial/passthrough |
| Environment | Execution profile/environment |
| Eventstream / real-time item | Stream source/processing graph when representable |
| Git-integrated item definition | Source-controlled portable asset |

### 5.2 Required migration behavior

- preserve item identifiers in source metadata;
- import retrievable item definitions rather than screenshots or UI state;
- remap workspace connections and secret references explicitly;
- preserve notebook/source code and pipeline dependencies;
- import semantic model metadata where definition APIs expose it;
- report unsupported Power BI/Fabric-specific visual or engine semantics individually;
- never claim OneLake data was copied if Ronin is instead configured against an external compatible location.

### 5.3 Fabric certification fixture

A certified fixture must include at least a notebook, SQL/lakehouse data asset, scheduled pipeline, semantic model, report/dashboard definition and one alert/monitoring-relevant workload.

## 6. Databricks profile

### 6.1 Import sources

Priority inputs:

- workspace/repository files and notebooks;
- Declarative Automation Bundles / source-controlled project definitions;
- Lakeflow Jobs definitions;
- Unity Catalog metadata and lineage available through documented interfaces;
- MLflow experiments/models;
- SQL queries/dashboards where definitions are retrievable;
- external locations and table metadata without embedded credentials.

### 6.2 Mapping

| Databricks concept | Ronin target |
|---|---|
| Workspace / Bundle | Workspace/Project + Ronin Bundle |
| Notebook | Notebook |
| Lakeflow Job / task DAG | Pipeline/DAG + schedule/trigger |
| Unity Catalog catalog/schema/table/view | Catalog + lakehouse asset |
| Unity Catalog lineage | Lineage graph |
| MLflow experiment/run | Experiment/run |
| Registered model/model version | Model registry |
| Feature engineering asset | Feature asset |
| SQL query/dashboard | SQL asset / dashboard |
| Cluster/serverless policy | Execution profile/policy, translated or partial |

### 6.3 Databricks-specific rules

- preserve open table formats and external locations where possible;
- do not encode DBR-specific runtime behavior as generic Ronin semantics;
- map jobs, dependencies, retries, schedules and parameters explicitly;
- import MLflow-compatible models through MLflow rather than inventing a private Ronin model package;
- retain Unity Catalog source identifiers for traceability;
- provider-specific compute/security features may remain `partial` or `passthrough` when no portable equivalent exists.

## 7. Palantir Foundry/AIP profile

### 7.1 Priority assets

- projects/spaces and source repositories where export/API access permits;
- datasets and virtual tables;
- pipeline/build definitions available through documented interfaces;
- Ontology object types, properties, links, interfaces and actions;
- models/functions where a portable artifact or callable contract is available;
- application definitions only when their semantics can be represented safely;
- AIP/LLM assets through documented APIs when portable definitions are exposed.

### 7.2 Ontology mapping

Palantir Ontology is the strongest semantic migration profile and MUST be mapped explicitly:

| Foundry Ontology | Ronin Ontology/KG |
|---|---|
| Object type | Object type |
| Property | Property |
| Link type | Link type |
| Interface | Interface |
| Action type | Action/command contract |
| Function | Governed function/tool contract where portable |
| Object instance | KG object/reference depending materialization policy |

Action security, writeback, dynamic policy or proprietary application behavior that cannot be preserved MUST be reported as `partial`, `passthrough` or `unsupported`; it must never be silently treated as a read-only object model.

### 7.3 Palantir certification fixture

Must include a dataset-backed ontology with at least two object types, one link type, one action/function-shaped artifact, lineage to source data and one downstream analytical or AI use case.

## 8. Dataiku DSS profile

### 8.1 Import sources

Priority inputs:

- project exports/bundles;
- Flow datasets and recipes;
- connections with credential remapping;
- scenarios, steps and triggers;
- notebooks/code recipes;
- visual recipe definitions;
- Visual ML models/settings where exportable;
- MLflow model exports;
- model evaluations and monitoring configuration where retrievable.

### 8.2 Mapping

| Dataiku concept | Ronin target |
|---|---|
| Project | Project |
| Flow | Pipeline/data lineage graph |
| Dataset | Dataset/table/file asset |
| Visual recipe | Transform node |
| Code recipe | Code/SQL task |
| Scenario | Pipeline/automation workflow |
| Trigger | Schedule/event trigger |
| Visual ML analysis/model | AI/ML Lab experiment/model; partial if algorithm settings lack portable representation |
| Model Evaluation Store | Evaluation store |
| Saved Model | Registered model |
| API endpoint | Model deployment endpoint |
| Metrics/Checks | Quality/monitoring rules |

### 8.3 Dataiku-specific rules

- preserve Flow topology and lineage;
- translate standard visual transforms before falling back to opaque recipes;
- preserve Python/SQL source where available;
- prefer MLflow for model portability when the source model supports it;
- mark plugin-defined behavior `passthrough` unless its plugin contract has a Ronin adapter;
- scenario triggers and reporters require explicit translation reports.

## 9. Connector and runtime remapping

A migrated bundle separates logical assets from environment bindings.

Import MUST produce a remapping manifest for:

- connection identifiers;
- storage locations;
- secret references;
- compute/runtime profiles;
- notification channels;
- model/LLM providers;
- identities/groups;
- external endpoints.

The importer MAY suggest mappings but MUST NOT fabricate credentials or security decisions.

## 10. Data migration modes

Each data asset declares one mode:

- `metadata_only`;
- `reference_external`;
- `copy_snapshot`;
- `continuous_sync`;
- `manual`.

The default should favor external reference/zero-copy when semantics and permissions allow it. Copying data is an explicit operation with provenance and checksum evidence.

## 11. Scheduler migration rules

Source workflows map to Ronin's DAG model.

Importer must preserve where representable:

- task identity;
- dependencies;
- parameters;
- schedules;
- triggers;
- retries;
- timeouts;
- conditional branches;
- concurrency/resource limits;
- notifications;
- environment/compute requirements.

Unsupported task types become `passthrough` only when a source-provider execution adapter exists; otherwise they are `unsupported`.

## 12. AI/ML migration rules

Prefer open artifacts and standard metadata:

- MLflow model packaging/tracking where available;
- ONNX/standard framework artifacts where lossless and licensed;
- explicit environment/requirements capture;
- dataset/snapshot lineage;
- model metrics/evaluations;
- serving signature/schema.

Ronin must not claim a proprietary training recipe was reproduced merely because its final serialized model can be loaded.

## 13. Round-trip and export

Ronin's primary export is always a Ronin Bundle.

Vendor export adapters MAY generate source-platform artifacts for the supported subset. Every export report uses the same exact/translated/partial/passthrough/unsupported classification.

Round-trip tests MUST distinguish:

- Ronin -> Ronin lossless round-trip (mandatory);
- Vendor -> Ronin semantic preservation for certified subset (mandatory);
- Ronin -> Vendor reconstruction of certified subset (profile-specific, mandatory only where public APIs/formats permit creation safely);
- Vendor -> Ronin -> Vendor byte identity (not generally required).

## 14. Certification gates

Each vendor profile is certified only when:

1. a versioned source fixture is available;
2. importer output is deterministic;
3. every source object appears in the migration report;
4. no object is silently omitted;
5. exact/translated assets execute or render through the Ronin acceptance journey;
6. schedules are runnable;
7. catalog/lineage is inspectable;
8. ML assets are evaluable where present;
9. monitoring/cost telemetry exists for the migrated workload;
10. exported Ronin Bundle reimports losslessly;
11. documented unsupported/partial objects match the generated report;
12. secrets are absent from the bundle and reports.

## 15. Non-claims

Ronin Public v1 does not claim:

- pixel-perfect reproduction of proprietary UIs;
- undocumented proprietary APIs;
- identical query optimizer plans;
- identical cloud billing semantics;
- automatic conversion of every marketplace/plugin/custom extension;
- silent replacement of proprietary policy engines when their semantics cannot be exported.

The product claim is stronger and more useful: **portable project semantics with explicit, testable boundaries and no hidden lock-in.**
