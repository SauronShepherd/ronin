# RONIN Studio: screen and API map

This map describes the active Ronin Public v1 browser routes. The web client
uses the published `api/openapi-v1.json` contract for control-plane operations.
User, group, membership and role administration are Ronin Pro capabilities and
are not exposed in the Public Studio or its API.

| Screen | Route | Main API surface | Status |
| --- | --- | --- | --- |
| Overview | `#home` | Local aggregates and tutorial catalog | Available |
| Runs | `#runs` | `/v1/jobs*` | Available |
| Workspaces | `#workspaces` | `/v1/workspaces*` | Available |
| Projects | `#projects` | `/v1/workspaces/{id}/projects*` | Available |
| Quality Studio | `#quality` | `/v1/workspaces/{id}/quality/*` | Available |
| Monitoring & Alerts | `#alerts` | `/v1/workspaces/{id}/alerts/*` | Available |
| FinOps Studio | `#finops` | `/v1/workspaces/{id}/finops/*` | Available |
| Migration Studio | `#migration` | `/v1/workspaces/{id}/projects/{id}/migration/*` | Available |
| Synthetic Data | `#synthetic` | `/v1/synthetic-data-studio/*` | Available |
| Machine Learning Studio | `#mlstudio` | `/v1/ml-studio/*` | Available |
| Workflows | `#workflows` | `/v1/workspaces/{id}/schedules*`, `/event-triggers*`, `/backfills*`, `/workflow-runs*` | Available |
| SQL | `#sql` | `POST /v1/sql` (bounded read-only SQL); `/v1/workspaces/{id}/projects/{id}/sql/query` | Available |
| Semantic Studio | `#semantic` | `/v1/workspaces/{id}/projects/{id}/semantic/*` | Available |
| Catalog | `#catalog` | `/v1/workspaces/{id}/catalog/assets` | Available |
| Data Engineering | `#data` | `/v1/data-engineering/*`, `/v1/workspaces/{id}/connections*` | Available |
| Ingestion Studio | `#ingestion` | `/v1/platform/connectors/*` including durable sync submit, scoped status/events/evidence and cancellation | Available |
| Notebook Studio | `#notebooks` | Project notebook APIs and `/v1/jobs*` | Available |
| Streaming | `#streaming` | `/v1/workspaces/{id}/streams/{id}/health` | Available |
| Graphs | `#graphs` | `/v1/workspaces/{id}/graphs/{id}/*` | Available |
| Performance | `#performance` | `/api/v1/performance/analyze` | Available |
| Debugger | `#debugger` | `/v1/data-engineering/debugger/*` | Available |
| Cloud Studio | `#cloud` | `/v1/cloud-studio/*` | Available |
| Deployments | `#deployments` | Project environment bindings | Available |
| Environments | `#environments` | `/v1/workspaces/{id}/environments*` | Available |
| Settings | `#settings` | Browser-local preferences | Available |

Ronin Public v1 has no in-product GenAI/model-provider invocation, RAG or agent
runtime. Coding-agent skills are installed and consumed externally by coding
agents.
