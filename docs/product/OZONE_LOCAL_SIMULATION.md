# Apache Ozone local simulation

Ronin can exercise an Apache Ozone S3 Gateway as a local, provider-compatible
object source. This path is intended for local simulation and contract testing;
it is not a production deployment recipe or a provider certification claim.

## Connection shape

Create a Ronin connection using the `ozone.s3.json` connector and these
deployment-local options:

```text
bucket=data
prefix=fixtures/
endpoint_url=http://127.0.0.1:9878
region_name=us-east-1
```

`endpoint_url` is mandatory and must be an absolute HTTP(S) URL without a query
or fragment. The connector uses path-style S3 addressing and SigV4, which is
the addressing mode expected by the Ozone S3 Gateway. Credentials are resolved
from the configured secret references at execution time and must not be put in
the connection manifest.

## Supported local path

The connector can boundedly discover and read `.json` and `.jsonl` objects. A
read is snapshot-based, capped at 10 MiB per object and at the requested row
limit. Discovery can be consumed page by page with the opaque continuation
cursor. A repeated snapshot checkpoint returns no duplicate rows.

The Ronin Compose profile does not start an Ozone cluster automatically. Run a
local Ozone/S3-Gateway environment separately, then point the connection at its
gateway endpoint. This keeps the default local demo small and makes the
external runtime dependency explicit.

## Explicit boundaries

- Ozone bucket provisioning, IAM administration and cluster operations are
  outside Ronin's connector boundary.
- Real Ozone-version compatibility, performance and failure-mode qualification
  require an environment-specific qualification run.
- The connector does not claim support for arbitrary S3 object formats or
  production operations.
