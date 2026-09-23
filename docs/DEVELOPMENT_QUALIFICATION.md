# Development and qualification commands

Run commands from the repository root. Python checks use the locked development
environment; browser checks additionally require Playwright Chromium and the
web dependencies from `package-lock.json`.

## Local Spark evidence

When PySpark is installed, run the bounded local SQL qualification:

```text
python tools/local_spark_qualification.py --output artifacts/local-spark-qualification.json
```

This records Spark/Python versions and a correctness digest. It is local
PySpark evidence only; it never substitutes for external Spark Connect
qualification, which requires `SPARK_CONNECT_ENDPOINT`.

## Provider-neutral query-engine evidence

Run the bounded local contract qualification with an explicit external-provider
status:

```text
python tools/query_engine_qualification.py --output artifacts/query-engine-qualification.json
```

The local DuckDB result is marked qualified only when its lifecycle, bounded
rows, and correctness digest match. QueryFlux remains `not_configured` until
an operator supplies `RONIN_QUERYFLUX_QUALIFICATION_COMMAND`; local evidence
does not claim QueryFlux production qualification.

## Source and contract checks

```text
make check
make lint-openapi
python -m tools.route_consistency
python -m tools.capability_status docs/product/public-v1-status.json
```

`lint-openapi` compares the canonicalized `api/openapi-v1.json` document with
`api/openapi-v1.sha256`. Any public contract edit must update the snapshot only
after review of the route-compatibility impact.

## Installed Studio checks

Build an artifact and qualify the installed package, not the checkout:

```text
make ui-installed
make ui-a11y
```

The installed browser smoke visits the supported Studio routes and fails on
missing assets, module errors, page errors, console errors, or horizontal
overflow. The accessibility run covers the 320px, 768px, and desktop viewport
matrix with axe-core.

For a developer-visible Chromium run against a locally served Studio:

```text
make ui-e2e-headed
RONIN_UI_SLOW_MO_MS=200 make ui-e2e-headed
```

Set `RONIN_STUDIO_AUDIT_URL` when the local server is not at the default URL.

## Release evidence

The release qualification workflow creates the exact wheel/sdist identity,
SPDX SBOM, installed-artifact evidence bundle, and fail-closed verdict. Local
evidence can be checked with:

```text
python -m tools.release_evidence validate <bundle.json>
python -m tools.release_evidence verdict <bundle.json> --required-gate <gate>
python -m tools.artifact_identity <wheel> <sdist> --output artifact-identity.json
```

Skipped, missing, stale, or wrong-commit evidence is never a passing release
verdict. Mutation evidence is independently gated by:

```text
make mutation
```

The mutation policy remains 90%; a run with `no_tests`, interrupted, timeout,
or suspicious mutants fails closed.
