# Security Policy

## Supported versions

Security fixes are developed against the default branch and the latest published
release. Older releases may not receive fixes when the required change depends
on a public-v1 contract or storage migration.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Report a
vulnerability** action for the `SauronShepherd/ronin` repository. Do not open a
public issue, pull request, or discussion containing exploit details, credentials,
private keys, tenant data, or a proof of concept that enables unauthorized access.

Include the affected commit or release, deployment mode, impacted component,
reproduction steps, security impact, and any suggested mitigation. Redact secrets
and personal data before sending the report. If GitHub private reporting is not
available for a particular fork or deployment, contact the repository maintainers
through a private channel and reference this policy.

Maintainers will acknowledge receipt when practicable, validate the report,
coordinate a fix and disclosure timeline with the reporter, and credit the
reporter unless anonymity is requested. Please allow time for a fix before making
details public.

## In-scope security boundaries

Reports are especially valuable for authentication or authorization bypasses,
tenant isolation failures, secret exposure, SSRF or unsafe connector behavior,
path traversal and archive handling, deserialization, stale-worker fencing,
artifact integrity, and data loss or unauthorized evidence access.

## Safe-harbor expectations

Act in good faith, avoid accessing or modifying data that does not belong to you,
avoid service degradation, and stop testing after demonstrating the minimum
necessary impact. We will not pursue security research that follows these
expectations.
