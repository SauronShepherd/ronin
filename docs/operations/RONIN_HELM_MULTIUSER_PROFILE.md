# Ronin Helm multi-user profile

The reference chart defaults to `server.profile: single-node`, SQLite and one
replica. This is the safe local baseline.

For a multi-user deployment, set `server.multiUser.enabled: true`, provide an
existing Kubernetes Secret through `server.multiUser.postgresDsnSecret`, and
choose a PostgreSQL-backed deployment with more than one replica. The chart
then injects `RONIN_STORAGE_BACKEND=postgres` and the DSN by reference; the DSN
never enters `values.yaml`, rendered ConfigMaps, or portable artifacts.

This profile supplies wiring and security defaults, not a production SRE
guarantee. PostgreSQL HA, scheduler fencing under failover, backup/restore and
rolling-upgrade qualification remain deployment-specific gates and must be
verified against the target cluster before production use.
