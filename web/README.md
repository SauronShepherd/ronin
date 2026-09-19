# Ronin Studio

Ronin Studio is the static operator interface for the Public v1 HTTP control
plane. Serve it from the Ronin server at `/studio/`.

## Connecting

Enter the HTTP(S) base URL of the Ronin control plane and a bearer token with
the required project grants. The URL is remembered locally; the bearer token
is kept only in browser `sessionStorage` and is cleared when the session ends.

The UI uses these authenticated v1 routes:

- `GET /v1/jobs` to list visible jobs;
- `GET /v1/jobs/{job_id}` to read status;
- `GET /v1/jobs/{job_id}/events` to inspect durable events;
- `GET /v1/jobs/{job_id}/evidence` to inspect portable evidence;
- `POST /v1/jobs/{job_id}/cancel` to request cancellation.
- `POST /v1/sql` to run bounded read-only SQL.

The shell also includes backend-aware entry points for workspaces, workflows,
and governance access. Surfaces without a published route remain visible as
disabled planned capabilities and never render invented records.

The server remains the authorization boundary. A Studio user must have
`list`, `read`, `events`, `evidence:read`, and, for cancellation, `cancel`
permission on the job's project.

Bearer tokens are kept in `sessionStorage` only. Cursors are opaque and are
passed through without construction or decoding in the browser.

## Delivery

Source checkouts serve assets from `web/`. The Docker image copies them to
`/usr/local/lib/ronin/web`, and wheels install them under
`share/ronin/web`. The server uses an allowlist for all Studio asset paths.
