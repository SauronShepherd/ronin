# Ronin authorization grants v1

Ronin v0.1 uses one provider-neutral authorization vocabulary for execution requirements and static bearer-token scopes. This contract is intentionally smaller than an IAM system: it does not define users, roles, OIDC, provider policies, cloud resource syntax, or an external policy engine.

## Canonical model

The implementation authority is `python/studio_core/grants.py`.

Every object is versioned with `version: 1` and uses deterministic JSON serialization.

### Resource scope

A resource scope contains:

- `kind`: one of `project`, `job`, `run`, `evidence`, `*`;
- `identifier`: an exact resource identifier, `null` as the explicit wildcard for one concrete kind, or `null` with `kind: "*"` for the global resource wildcard.

A grant never infers hierarchy between resource kinds. In particular, `project:X` does not implicitly authorize a `job`, `run`, or `evidence` resource. A boundary that knows a parent/child relation must resolve that relation explicitly before constructing the requirement it checks.

### Actions

The closed v1 action vocabulary is:

- `read`
- `list`
- `events`
- `submit`
- `execute`
- `cancel`
- `evidence:read`

Unknown actions and unknown resource kinds fail closed.

### Grant

A grant contains:

```json
{
  "version": 1,
  "actions": ["read", "list"],
  "resource": {"kind": "project", "identifier": "demo"},
  "constraints": {}
}
```

Actions are normalized as a set. Constraints are bounded string key/value policy data. Credential-shaped keys and obvious credential payloads are rejected. v0.1 matching supports only unconstrained grants; a matching constrained grant produces a denied `unsupported_constraints` decision rather than silently ignoring policy data.

### Requirement

A requirement contains one action and one resource scope:

```json
{
  "version": 1,
  "action": "execute",
  "resource": {"kind": "project", "identifier": "demo"}
}
```

Requirements describe requested authority. They are separate from effective grants, policy decisions, and observed enforcement evidence.

### Decision and enforcement evidence

`GrantSet.permits(requirement)` returns a pure decision with:

- `allowed`;
- a stable reason;
- the unique matched grant only when allowed.

No match denies. Unknown vocabulary cannot be constructed. Constraint semantics that v1 does not understand deny. When multiple equally specific grants match the same requirement, the result is `ambiguous` and denied rather than depending on input order or lexical identifiers.

`AuthorizationEvidence` records the enforcement point, requirement, and resulting decision. It never contains the bearer token. Successful typed kernel decisions are serialized into the durable `cell.started` event message before execution begins; denied requirements produce the existing normalized `kernel.permission.denied` path before executor side effects.

## Static bearer-token mapping

`ronin serve` keeps the existing static bearer credential and binds it to one canonical `GrantSet` supplied in `RONIN_TOKEN_SCOPES`.

Example:

```sh
export RONIN_TOKEN='development-token'
export RONIN_TOKEN_SCOPES='{"version":1,"grants":[{"version":1,"actions":["read","list","events","submit","execute","cancel","evidence:read"],"resource":{"kind":"project","identifier":"demo"},"constraints":{}}]}'
ronin serve
```

Missing, empty, malformed, unknown-version, unknown-action, or unknown-resource scope configuration fails server startup. The token remains compared with `hmac.compare_digest` and is not copied into the grant model.

For language-neutral scope strings, one requirement maps losslessly to:

```text
ronin:v1:<percent-encoded-action>:<percent-encoded-resource-kind>:<percent-encoded-identifier-or-*>
```

For example:

```text
ronin:v1:execute:project:demo
ronin:v1:evidence%3Aread:evidence:*
```

`requirement_to_bearer_scope()` and `parse_bearer_scope()` are the canonical mapping functions. `parse_legacy_permission()` is the alpha migration parser for old string-based permission fields when those strings adopt this explicit format.

## HTTP enforcement

The supported HTTP server requires both a static bearer token and a non-empty `GrantSet`. There is one canonical `RoninHTTPServer` implementation; `studio_server.scoped_http` is only a compatibility import and cannot instantiate a token-only server.

The HTTP boundary knows every Job's `project_id`, so it resolves the Job first and then checks a project-scoped requirement without teaching the canonical grant model any implicit resource hierarchy. Route requirements are:

| Operation | Required project action |
| --- | --- |
| `GET /v1/jobs` | `list` |
| `POST /v1/jobs` | both `submit` and `execute` |
| `GET /v1/jobs/{job_id}` | `read` |
| `GET /v1/jobs/{job_id}/events` | `events` |
| `GET /v1/jobs/{job_id}/evidence` | `evidence:read` |
| `POST /v1/jobs/{job_id}/cancel` | `cancel` |

For an explicit list `project` filter, lack of `list` authority returns the normalized `403 forbidden` response. An unfiltered list returns only Jobs whose project is permitted and preserves the storage cursor without exposing hidden Job payloads. A caller-supplied project filter never widens authority.

Direct Job-ID routes deliberately collapse both "missing Job" and "existing Job outside the bearer grant" into `404 job_not_found`. This prevents a credential from using status, events, evidence, or cancel as a cross-project existence oracle. Authorization is checked before cancellation or other route side effects.

OpenAPI records the route action requirements with the `x-ronin-required-project-actions` extension. CLI and `pyronin` continue to send only the bearer credential; they do not send client-selected scopes or grants, and they treat authorization failures through the existing status-authoritative normalized API error contract.

## Alpha migration

`KernelDirective.required_permissions` remains available for existing adapters. New adapters should use `required_grants` containing typed `Requirement` objects. A single directive cannot mix the legacy and typed representations.

`SessionPolicy` preserves exact legacy string comparison for old directives. Typed requirements are evaluated exclusively against `granted_grants`; authority is never widened by implicitly translating arbitrary historical strings.

## Scope boundary

Provider IAM names, cloud resource identifiers, OIDC, enterprise RBAC, OPA, multi-user policy administration, and remote policy services remain outside the v0.1 canonical model.

HTTP authorization is intentionally bound only to the existing v0.1 project/job-control routes. It does not introduce roles, token introspection, per-request grant headers, or a new authorization service.
