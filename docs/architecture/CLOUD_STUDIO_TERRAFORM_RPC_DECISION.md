# Cloud Studio Terraform RPC decision

## Decision

No se implementa un `terraform-provider-cloud-studio` RPC separado en la fase actual.

## Rationale

Cloud Studio already has two explicit contracts: the provider-neutral topology is exported as controlled Terraform HCL, and external emulators are reached through the HTTP backend contract or the Terraform CLI backend. These paths preserve the existing Terraform provider ecosystem, workspace isolation, plan/apply/refresh/destroy lifecycle, and bounded import/export parser without introducing a second stateful protocol.

## Re-evaluation triggers

Reconsider a dedicated RPC provider only if a required use case cannot be represented by the controlled HCL export or the HTTP backend, such as a provider-neutral resource lifecycle that cannot be expressed through Terraform, a required bidirectional state operation unavailable through the current endpoints, or a certified backend that mandates Terraform provider RPC rather than endpoint configuration.

This is an architecture decision, not a provider qualification claim. Floci/LocalStack and Public v1 family gates remain independent.
