# Phase 2026-11-12 — Docker Scout candidate scan

## Scope

Run the Docker Scout vulnerability scan against the immutable image used by the Docker/Helm candidate lanes.

## Candidate

- Image reference: `ronin:qualification-5e8a57e`
- Immutable image ID: `sha256:46f6b99641ca7497ab15a4c6f4c987ce9aaa296441a718afe672bdc691f4c920`
- Docker Scout: `v1.28.0`
- Scan output: local Scout indexing of the image; 93 packages indexed

## Execution

```text
docker scout cves ronin:qualification-5e8a57e \
  --only-severity critical,high,medium,low --format only-packages
```

Result: **PASS**. Docker Scout reported `No vulnerable package detected` and **0 critical, 0 high, 0 medium, 0 low** findings.

## Boundary and limitation

This receipt covers Docker Scout only. Trivy was not installed on the qualification host and is therefore not claimed as executed here. Gitleaks and `pip-audit` remain covered by the separate supply-chain receipts. Human security acceptance and the license/legal gate remain open; Public v1 stays **0/13 (0%) — NO-GO**.

