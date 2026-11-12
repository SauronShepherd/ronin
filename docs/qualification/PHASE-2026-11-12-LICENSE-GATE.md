# Phase receipt — license gate diagnostic — 2026-11-12

## Candidate and environment

- Candidate under development: `8cf38ef4b9000ae685d853bb6983415701b6514c`.
- Canonical lock: `requirements-dev.lock`, SHA-256 `f1b904db278b805118f91044e667166282ac824cbb7346a32d939324655b80d0`.
- Inventory/policy surface: `third_party/licenses-v1.json` and `third_party/license-policy-v1.json`.
- Qualification was rerun in a fresh Python 3.14 virtual environment with the exact lock installed.

## Executed evidence

1. Against the committed inventory, the validator first detected graph drift: `pyyaml==6.0.3` was absent from `third_party/licenses-v1.json`.
2. Regenerating an inventory in the clean environment succeeded and produced a 57-package inventory bound to the exact lock SHA.
3. Comparing the regenerated inventory with the lock showed no missing or extra package/version pairs.
4. Policy projection retained 35 existing reviews but could not create decisions automatically.
5. Final qualification failed closed with missing review decisions for 22 exact package/version keys, including `pyyaml==6.0.3`, `cachecontrol==0.14.4`, `certifi==2026.10.23`, `requests==2.34.2`, `urllib3==2.8.0`, and other locked dependencies.

## Result

NO-GO / not release-qualified. This gate cannot be closed by inference or automated approval: the runbook requires a maintainer to inspect each exact installed license/source/legal-file evidence and commit explicit allow/deny, notice, attribution, and rationale decisions. Public V1 progress remains `0/13 (0%)`.

The corrected inventory and policy decisions must be committed only after that review; no legal approval was fabricated in this phase.

## Reproduction

```text
python -m tools.license_qualification --root . --lock requirements-dev.lock --policy third_party/license-policy-v1.json --inventory third_party/licenses-v1.json
python -m tools.license_qualification --root . --lock requirements-dev.lock --policy third_party/license-policy-v1.json --write-inventory <fresh-inventory.json>
python -m tools.license_policy_profile --inventory <fresh-inventory.json> --source-policy third_party/license-policy-v1.json --output <projected-policy.json> --omit-stale-reviews
python -m tools.license_qualification --root . --lock requirements-dev.lock --policy <reviewed-policy.json> --inventory <fresh-inventory.json>
```
