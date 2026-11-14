# License gate finding — current candidate

Date: 2026-11-14  
Candidate: `aeed51531727f55c8027e4328fcfa29b1ec02219`  
Status: **OPEN — NOT QUALIFIED**

## Reproduction

The release test environment and the host interpreter both reject the current
license evidence with the same deterministic finding:

```text
python tools/license_qualification.py \
  --inventory third_party/licenses-v1.json \
  --policy third_party/license-policy-v1.json
```

The policy review keys do not exactly match the current locked graph. Missing
review decisions include:

```text
boolean-py==5.0, cachecontrol==0.14.4, certifi==2026.10.23,
charset-normalizer==3.5.2, cyclonedx-python-lib==11.12.0,
defusedxml==0.7.1, filelock==4.2.4, idna==3.20, msgpack==1.2.4,
packageurl-python==0.17.6, pip==26.2.2, pip-audit==2.10.1,
pip-requirements-parser==32.0.1, py-serializable==2.1.0,
pyparsing==3.3.3, pyyaml-ft==8.0.0, requests==2.34.2,
tomli-w==1.2.0, urllib3==2.8.0
```

The qualification environment also reports a distinct host-environment issue
when inventory generation is attempted directly: multiple installed
distributions are present for `pytest`. The tool correctly refuses to derive
ambiguous evidence from that environment. Repeating with the repository's
cached qualification interpreter reproduces the policy/lock mismatch above.

## Required closure

1. Resolve the exact dependency lock and installed qualification environment.
2. Regenerate `third_party/licenses-v1.json` from that exact environment.
3. Obtain explicit maintainer/legal review decisions and evidence hashes for
   every changed package; do not copy or infer approvals automatically.
4. Re-run the license gate and record NOTICE/attribution review.

This receipt is evidence of an open release blocker, not a qualification PASS.
The official Public v1 ledger remains **0/13 (0%), NO-GO**. No GitHub Actions,
branch, or worktree was introduced.
