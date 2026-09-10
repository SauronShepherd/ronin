# ADR-V01-011 — Typed scoped grants are a pure core contract

**Status:** accepted — 2026-09-10

## Decision

Ronin v0.1 places the versioned authorization grant/requirement model in `studio_core`, not in the HTTP server, worker, storage adapter, or a provider-specific IAM integration.

The canonical contract consists of typed resource scopes, a closed action vocabulary, bounded constraints, immutable grants, requested requirements, deterministic policy decisions, and observed enforcement evidence. Matching is pure and deny-by-default. Unknown actions/resources/versions fail construction, unsupported constraints deny, and equally specific competing matches deny as ambiguous rather than depending on iteration or lexical order.

Static bearer authentication remains the v0.1 credential mechanism. `RONIN_TOKEN_SCOPES` supplies a versioned `GrantSet` associated with that token, and language-neutral bearer scope strings map losslessly to typed requirements. The bearer secret itself never enters the grant model or durable authorization evidence.

`KernelDirective.required_permissions` remains temporarily available for alpha compatibility. New execution adapters use typed `required_grants`; one directive cannot mix the two representations. Existing legacy string permissions retain exact-match semantics until migrated, avoiding accidental privilege widening.

## Consequences

- `studio_kernel` and `studio_server` may depend on the same provider-neutral model without creating a worker-to-server dependency.
- HTTP route enforcement is deliberately deferred to #161; #52 freezes semantics and transports effective grants to the authenticated edge only.
- Provider IAM syntax, OIDC, enterprise RBAC, OPA and external policy engines remain outside v0.1.
- Constraint data is bounded and credential-shaped values are rejected; v1 matching does not silently interpret unknown constraint semantics.
- Successful typed kernel decisions are persisted before executor effects as non-secret durable authorization evidence, while denials retain the normalized `kernel.permission.denied` behavior.

The complete v1 representation and migration format are documented in `docs/product/AUTHORIZATION_GRANTS_V1.md`.
