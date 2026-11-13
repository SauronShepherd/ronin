# License gate diagnostic — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `36f4d398c494db061600fb1b53c295a294e21fb6`

## Automated validator regression

```text
python -m pytest -q tests/test_license_qualification.py tests/test_license_qualification_coverage.py
```

Result: **104 passed, 0 failed**.

## Real gate

```text
python tools/license_qualification.py --inventory third_party/licenses-v1.json --policy third_party/license-policy-v1.json
```

Result: **FAIL / qualification pending**. The exact locked graph has 22 package
versions without explicit human review decisions, including `pip==26.2.2`,
`requests==2.34.2`, `urllib3==2.8.0`, `certifi==2026.10.23` and other
transitive packages. This is fail-closed; no legal approval, NOTICE decision
or policy allow was inferred or invented.

## Decision

The validator implementation phase passes, but the license/legal release gate
remains **OPEN** pending maintainer/legal review. Public v1 remains **0/13
(0%) — NO-GO**.
