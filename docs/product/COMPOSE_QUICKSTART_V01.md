# Ronin v0.1 Docker Compose quickstart

This is the supported local v0.1 container topology. It uses one Ronin image for the HTTP server, durable worker and isolated Python cell containers; one named volume for SQLite and execution evidence; and the host Docker socket only in the worker service.

## Prerequisites

- Docker Engine with the Compose v2 plugin.
- A local checkout of this repository. Ronin v0.1 does not clone or synchronize repositories for you.

Run all commands from the repository root.

## Start

```sh
docker compose up -d
```

On the first invocation Compose builds `docker/Dockerfile` as `ronin:local`. The server publishes only to `127.0.0.1:8080`. The worker waits for the server healthcheck before starting.

Inspect readiness with:

```sh
docker compose ps
```

The server should become `healthy`. The v0.1 budget is under 60 seconds; this code path has not been re-qualified since automated tests/CI were disabled.

## Use the bundled CLI

The optional `cli` Compose service uses the same image but receives neither the Docker socket nor the durable data volume. It can validate the mounted checkout and call the server over the private Compose network.

```sh
docker compose run --rm cli ronin doctor --require core
docker compose run --rm cli ronin validate examples/demo
docker compose run --rm cli ronin plan examples/demo -t notebooks/etl.ronin.json
```

Submit the demo and retain the printed Job ID:

```sh
docker compose run --rm cli ronin submit examples/demo -t notebooks/etl.ronin.json --idempotency-key quickstart-v1
```

Then inspect it using the returned ID:

```sh
docker compose run --rm cli ronin status JOB_ID --wait
docker compose run --rm cli ronin logs JOB_ID
docker compose run --rm cli ronin evidence JOB_ID
```

The bundled static bearer token is development-only. Its server-side grant is deliberately limited to project `examples/demo` and the seven v1 job-control actions. Override `RONIN_TOKEN` in the Compose environment for local use; use a Compose override if you need a different project grant set.

## Topology and security boundary

- `server` has the SQLite volume and no Docker socket.
- `worker` has the same SQLite volume, the checkout read-only at `/workspace`, and `/var/run/docker.sock` because the v0.1 runner launches sibling containers.
- `cli` has the checkout read-only and no Docker authority.
- The image runs product processes as UID/GID `65532:65532`. Server/worker containers start their entrypoint as root only long enough to prepare volume/socket permissions and then drop privileges with `gosu`.
- The worker resolves `RONIN_IMAGE_REF` through the Docker daemon to an immutable local `sha256:` image ID before constructing the execution runtime. Cell containers remain read-only, networkless, capability-dropped and resource-limited by the existing runner contract.
- Git safe-directory handling is scoped to the mounted `/workspace`; the image does not configure `safe.directory=*`.

## Stop and clean up

Stop containers while preserving durable data:

```sh
docker compose down
```

Remove the local durable volume as well:

```sh
docker compose down --volumes
```

Do not use `--volumes` if you need to retain Job, Run, Attempt, artifact or execution-evidence state.

## Current acceptance truth

This Compose implementation supplies the code path required by frozen acceptance step 01. The last automated v0.1 qualification remains 13/15 because tests and GitHub Actions are intentionally disabled. Public evidence retrieval is also implemented in code, but neither step 01 nor step 12 should be described as newly qualified until automated acceptance is explicitly restored and executed.
