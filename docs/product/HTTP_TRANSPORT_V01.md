# Ronin v0.1 HTTP transport security

Ronin v0.1 uses static bearer authentication with typed project/action grants. Bearer credentials therefore require a transport policy that prevents accidental plaintext exposure outside explicitly local development.

## Supported defaults

Authenticated clients use these rules:

- `https://...` is supported for remote and local endpoints.
- `http://127.0.0.1`, `http://[::1]`, and `http://localhost` are supported for local development.
- Authenticated `http://` to any other host is rejected before the request is sent unless the process explicitly sets `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1`.
- The installed CLI does not follow HTTP redirects. This prevents a validated HTTPS origin from redirecting a bearer-bearing request to another or weaker origin.
- URL user-info, query components on the configured base URL, fragments, non-origin-relative request paths, unbounded response bodies, and raw server error text remain rejected/bounded by the existing client contract.

`RONIN_INSECURE_ALLOW_REMOTE_HTTP` accepts only `0` or `1` when present. Any other value fails closed. The override is intended only for explicit local-development networks such as the private Docker Compose bridge; it is not a remote-production mode.

## Built-in server

`ronin serve` uses Python's built-in plaintext HTTP server. It does **not** provide TLS.

By default, the supported server may bind only to loopback (`127.0.0.1`, `::1`, or `localhost`). A non-loopback bind such as `0.0.0.0` fails before the server starts unless `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1` is explicitly set.

The override does not add encryption. It only acknowledges that plaintext traffic is intentionally confined to a trusted local-development network.

## Remote access

For authenticated access from another host or an untrusted network, terminate TLS in a dedicated reverse proxy or other external TLS terminator and expose Ronin to clients through `https://`.

The recommended boundary is:

```text
remote client -- HTTPS --> TLS terminator -- local/private HTTP --> ronin serve
```

Keep the Ronin backend listener on loopback or a private network inaccessible to untrusted peers. The TLS terminator is responsible for certificate/key handling and HTTPS policy; Ronin does not claim built-in certificate management or TLS termination in v0.1.

## Docker Compose

The supported `compose.yaml` is deliberately local-only at the host boundary:

- the server binds `0.0.0.0:8080` inside the private Compose network so the bundled CLI can reach it;
- both server and bundled CLI explicitly set `RONIN_INSECURE_ALLOW_REMOTE_HTTP=1` for that private bridge;
- the host publishes the server only as `127.0.0.1:${RONIN_PORT:-8080}:8080`;
- the override must not be interpreted as permission to publish the container port on a remote-facing host interface.

For remote deployment, do not copy the Compose insecure-development override into a publicly reachable listener. Put an HTTPS terminator at the client-facing boundary instead.

## Credential handling

Transport-policy failures never include the bearer token. The built-in HTTP server suppresses normal request logging, and public error responses do not echo credentials. Clients expose normalized transport/API failures rather than raw response bodies that might contain sensitive server text.

## Current validation mode

This transport policy is implemented under the maintainer's current code-only mode. Automated tests and GitHub Actions are intentionally disabled, so this document records the implemented contract rather than new runtime qualification evidence.
