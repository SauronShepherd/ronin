# Ronin local release evidence v1

This document defines the build type and builder identity used by Ronin's
manually generated local release provenance. It exists to make the statement's
inputs and limits reviewable.

## `ronin-local-release-qualification-v1`

The build type records qualification of already-built release files on a
maintainer-controlled workstation. Its external parameters are:

- `candidateCommit`: the exact source commit from `artifact-identity.json`;
- `artifactIdentitySha256`: SHA-256 of the full artifact identity file;
- `buildCommand`: the operator-recorded command that produced the files;
- `toolchain`: an allowlisted map of observed tool names to version strings.

The statement's subjects are the artifact names and SHA-256 digests from that
identity file. The source repository URL and its Git commit are recorded as a
resolved dependency. The tool does not claim to have observed or executed the
build command; the maintainer must verify that record against the qualification
transcript. A missing artifact, malformed identity, or mismatched digest makes
the evidence unusable.

## `local-manual-untrusted-builder`

The builder identifier denotes a local, operator-run, self-reported process. It
has no trusted control plane, signing key, isolated builder guarantee, or
independent verification. The output uses the in-toto Statement v1 and SLSA
Provenance v1 data shapes, but **does not claim any SLSA Build level**. The
statement is not a signature and is not proof that a particular command ran.

The application SBOM is a CycloneDX 1.6 document containing release artifact
subjects with their exact bytes' SHA-256 digests and versions from the explicit
Python dependency lock supplied to the generator. Runtime and probe operating
system packages are represented by separate Trivy CycloneDX 1.7 inventories.
`bind_container_sbom` binds each raw inventory to the exact Docker image TAR,
its config digest, repository tag, Trivy version, source commit, and candidate
artifact identity. The supply-chain validator rebuilds each bound inventory
from the identity-pinned raw scan and TAR, compares the complete package
inventory, and requires distinct runtime and probe images for release mode.
The raw scanner outputs are candidate identity subjects; bound SBOMs are
derived evidence whose hashes are recorded in the final supply-chain receipt.
This local provenance is self-reported and does not claim independent scanner
attestation or proof that a trusted builder ran the scan.
