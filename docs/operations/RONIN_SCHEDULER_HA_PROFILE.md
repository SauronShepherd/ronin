# Scheduler HA profile

Ronin scheduler leadership is durable and generation-fenced in the shared
store. Each daemon must acquire a lease before evaluating schedules, renew it
between bounded phases, and assert the same generation before dispatch or
reconciliation. Losing the lease stops authoritative work; a replacement
leader may continue after the store accepts its newer generation.

For Kubernetes, run scheduler replicas against the same PostgreSQL metadata
store and use a lease interval shorter than the deployment termination grace
period. A rolling update is qualified only when the old generation can no
longer dispatch after lease loss and the new generation produces no duplicate
schedule fire. SQLite single-replica deployments remain the reference local
profile and are not an HA claim.
