# RONIN Studio · screen/API map

The UI consumes only the published `api/openapi-v1.json` contract.

| Screen | Route | Published operations | Status |
|---|---|---|---|
| Overview | `#home` | Local aggregates | available |
| Runs | `#runs` | `GET /v1/jobs` | available |
| Run detail | `#run/{id}` | `GET /v1/jobs/{id}`, `/events`, `/evidence`, `POST /cancel` | available |
| Workspaces | `#workspaces` | `/v1/workspaces*` | available (list) |
| Governance · Access | `#access` | `/v1/admin/security/*` | available (contract entry point) |
| Workflows | `#workflows` | `/v1/workspaces/{id}/workflows*` | available (contract entry point) |
| SQL | `#sql` | `POST /v1/sql` | available |
| Catalog | `#catalog` | `/v1/catalog` | requires API |
| Data | `#data` | `/v1/connections` | requires API |
| Graphs | `#graphs` | `/v1/ontologies` | requires API |
| AI | `#ai` | `/v1/experiments`, `/v1/models` | requires API |
| Deployments | `#deployments` | No published runtime | requires capability |
| Environments | `#environments` | No published runtime | requires capability |
| Settings | `#settings` | No published settings contract | requires API |

The client never constructs or decodes cursors, exposes physical evidence
locators, or persists bearer tokens in `localStorage`.
