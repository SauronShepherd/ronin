# P13 — Secret resolution boundary diagnostic

**Date:** 2026-11-12  
**Candidate SHA:** `3f0538326c4877de95506f9889105911211f9074`  
**Scope:** Public v1 single-operator secret-resolution boundary

## Result

The repository-local secret contract is qualified for the supported local
backends at this boundary:

- `EnvironmentSecretResolver` resolves only `secret://env/<single-name>` and
  fails closed for missing or nested names.
- `MountedFileSecretResolver` confines reads to the configured root, rejects
  traversal and symlinks, requires regular files and enforces size and
  permissions limits.
- `SecretMaterial` rejects empty/oversized values and redacts `str`/`repr`.
- `CompositeSecretResolver` dispatches only explicitly configured backends;
  unsupported backends fail closed and reserved names cannot be replaced.
- An external backend can be injected through the narrow `SecretResolver`
  protocol, without discovery or listing operations.

## Gate

Command:

```text
python -m pytest -q tests/test_secret_resolvers.py
```

Result: **8 passed, 1 skipped, 0 failed** in 0.90s on Windows. The single
skip is the symlink-rejection case because symlinks are unavailable in this
host configuration; the same test is platform-conditional and is not counted
as an external-provider qualification.

## Boundary and remaining work

This receipt does **not** claim a real external secret-provider certification.
The capability matrix continues to mark P13 `Partial / Partial / No` because
external-provider qualification and release evidence remain incomplete, and
the Public v1 contract reserves external identity/secret-provider integration
to the Ronin Pro boundary. A future provider-specific gate must supply an
authorized test service, immutable candidate evidence, redaction checks and
failure/timeout behavior before that limitation can change.

