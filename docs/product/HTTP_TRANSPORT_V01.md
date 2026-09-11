# Ronin v0.1 HTTP transport security

Ronin v0.1 uses static bearer authentication with typed project/action grants. Bearer credentials therefore require a transport policy that prevents accidental plaintext exposure outside explicitly declared local topologies.

## Supported defaults

Authenticated clients use these rules:

- `https://...` is supported for remote and local endpoints.
- `http://127.0.0.1`, `http://[::1]`, and `http://localhost` are supported under the default `loopback` policy.
- Authenticated `http://` to any other host is rejected before the request is sent unless a non-loopback policy is explicitly selected.
- The installed CLI does not follow HTTP redirects. This prevents a validated HTTPS origin from redirecting a bearer-bearing request to another or weaker origin.
- URL user-info, query components on the configured base URL, fragments, non-origin-relative request paths, unbounded response bodies, and raw server error text remain rejected/bounded by the existing client contract.

`RONIN_BIND_POLICY` has exactly three accepted values:

- `loopback` — default when the variable is unset. Plaintext server binding and authenticated plaintext clients are limited to explicit loopback targets.
- `container-internal` — permits non-loopback plaintext only as an operator declaration that traffic is confined to the supported private container topology. This value is used by the bundled Compose server and CLI because `http://server:8080` is not a loopback address inside the Compose bridge.
- `insecure-plaintext-network` — explicit escape hatch for a trusted development network where plaintext bearer transport is knowingly accepted.

Unknown, empty, whitespace-modified, or differently cased values fail closed. Neither non-loopback value adds encryption or verifies network isolation cryptographically.

## Built-in server

`ronin serve` uses Python's built-in plaintext HTTP server. It does **not** provide TLS.

By default, the supported server may bind only to loopback (`127.0.0.1`, `::1`, or `localhost`). A non-loopback bind such as `0.0.0.0` fails before the server starts under `loopback` policy.

The bundled local Compose topology sets `RONIN_BIND_POLICY=container-internal` because the server must bind `0.0.0.0` inside its container so sibling services can reach it. For other trusted development networks, `RONIN_BIND_POLICY=insecure-plaintext-network` is the explicit acknowledgement. Neither mode makes public remote plaintext access supported.

## Remote access

For authenticated access from another host or an untrusted network, terminate TLS in a dedicated reverse proxy or other external TLS terminator and expose Ronin to clients through `https://`.

The recommended boundary is:

```text
remote client -- HTTPS --> TLS terminator -- local/private HTTP --> ronin serve
```

Keep the Ronin backend listener on loopback or a private network inaccessible to untrusted peers. The TLS terminator is responsible for certificate/key handling and HTTPS policy; Ronin does not claim built-in certificate management or TLS termination in v0.1.

## Docker Compose

The supported `compose.yaml` is deliberately local-only at the host boundary:

- startup requires an explicit `RONIN_TOKEN`; there is no repository-known bearer-token default;
- the server binds `0.0.0.0:8080` inside the private Compose network so the bundled CLI can reach it;
- both server and bundled CLI set `RONIN_BIND_POLICY=container-internal` for that topology;
- the host publishes the server only as `127.0.0.1:${RONIN_PORT:-8080}:8080`;
- `container-internal` must not be interpreted as permission to publish the container port on a remote-facing host interface.

For remote deployment, do not copy a private-container plaintext policy into a publicly reachable listener. Put an HTTPS terminator at the client-facing boundary instead.

## Credential handling

Transport-policy failures never include the bearer token. The built-in HTTP server suppresses normal request logging, and public error responses do not echo credentials. Clients expose normalized transport/API failures rather than raw response bodies that might contain sensitive server text.

The supported Compose path requires the operator to provide `RONIN_TOKEN` before interpolation. This prevents a known token committed in the repository from becoming the credential for a normal deployment.

## Current validation mode

GitHub Actions remain disabled. Targeted local validation may be executed from exact connector-reconstructed source where the required dependencies are already available; such local evidence is reported separately and is not CI or full acceptance qualification.
