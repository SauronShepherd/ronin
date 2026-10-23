---
name: ronin-data-engineering
description: Use when a coding agent is building or debugging Ronin data-engineering workflows involving project validation, notebook or pipeline planning, connector discovery, ingestion planning, job submission, status, logs, and evidence. Trigger for connector capability inspection, source discovery, previews, checkpoint health, Data Engineering Studio workflows, or execution of a validated Ronin target. Use only commands verified to exist, plan before mutating, keep connector reads bounded, and require durable evidence for execution claims.
---

# Ronin Data Engineering

Compose the real Ronin CLI; do not implement a parallel scheduler or connector runtime.

## Workflow
1. Run `scripts/preflight.py` and stop on missing required surfaces.
2. Run `ronin doctor --require core` and `ronin validate PROJECT`.
3. Inspect connectors before execution:
   - `ronin connectors capabilities`
   - `ronin connectors discover ...`
   - `ronin connectors preview ...`
   - `ronin connectors plan ...`
   - `ronin connectors checkpoint-health ...`
4. Prefer bounded preview/planning before any ingestion or pipeline execution.
5. Use `ronin plan PROJECT --target TARGET` before `ronin submit`.
6. Submit with an idempotency key and machine-readable output when the user requested execution.
7. Follow status/logs/evidence to a terminal state. Report incomplete evidence as incomplete.

## Guardrails
- Never treat connector discovery as authorization to read all data.
- Keep page, byte, row, timeout, and retry limits explicit when the command exposes them.
- Never fabricate connection credentials or secret mappings.
- Do not claim exactly-once behavior unless the selected connector/checkpoint contract proves it.
- Separate source discovery, plan, execution, checkpoint commit, and evidence in reports.
- Do not claim Data Engineering Studio completeness from CLI execution alone.

## References
Read `references/workflows.md` for the supported sequence and failure handling.
