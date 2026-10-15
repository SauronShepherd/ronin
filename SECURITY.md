# Security policy

Ronin is alpha software. Security reports are handled privately whenever a
verified private reporting route is configured by a maintainer.

## Supported versions

Only the current development version receives security fixes. Older alpha
builds are unsupported; include the exact version or commit in every report.

## Reporting a vulnerability

The project currently has no verified private reporting endpoint. Do not put
secrets, exploit details, or personal data in public issues or pull requests.
Until a maintainer publishes a private route here, use the project owner’s
approved private communication channel and ask for an acknowledgement before
sending sensitive material. If no such channel is available, report only the
minimum non-sensitive information needed to request one.

Do not open a public issue for an undisclosed vulnerability. Report a
vulnerability privately through the verified route once one is published.

Maintainers must replace this paragraph with the verified channel and its
expected encryption/key procedure before claiming that private reporting is
available. A release must not advertise a channel that has not been tested.

A useful report contains:

- affected version or commit;
- affected component and deployment mode;
- concise impact statement;
- reproducible steps or a minimal proof of concept, with secrets removed;
- required privileges and interaction;
- suggested mitigation, if known; and
- a safe contact method for follow-up.

## Maintainer triage process

For each private report, the maintainer records an internal acknowledgement,
confirms whether the report is reproducible, assigns severity and an owner,
tracks a remediation commit, and coordinates disclosure only after a fix or an
explicit risk decision. Reporter identity and supplied material are limited to
people who need them for triage.

The public repository may contain only sanitized status, affected versions,
and remediation references. Never commit the original report, credentials,
private keys, tokens, exploit payloads containing real data, or internal
contact details.

## In-scope security boundaries

The in-scope surface includes the Ronin server, SDK/CLI, scheduler, workers,
packaged Studio assets, and release artifacts. Reports involving
authentication, tenant isolation, SSRF, or artifact integrity are especially
important. Third-party dependencies and provider services should be reported
to their respective maintainers when the issue is not caused by Ronin.

## Safe-harbor expectations

Good-faith testing that avoids privacy violations, service disruption, data
exfiltration, and persistence is welcome. Do not access another user’s data,
destroy data, or run denial-of-service tests. Stop testing and report
immediately if you encounter real secrets or personal data.

## Scope and response targets

Until a private route is verified, no response-time target is promised. After
verification, maintainers should publish acknowledgement and remediation
targets here and bind them to the project’s release runbook.

## Verification gate

Before this policy is considered release-qualified, a maintainer must:

1. select a private route and document its access and encryption procedure;
2. send a harmless test report through that route;
3. verify receipt, acknowledgement, restricted access, and follow-up; and
4. record the evidence in the release qualification record.

This document intentionally does not claim that those human-owned steps are
complete.
