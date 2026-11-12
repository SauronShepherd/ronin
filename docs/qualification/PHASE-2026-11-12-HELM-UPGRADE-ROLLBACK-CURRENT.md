# Qualification receipt — Helm install/upgrade/rollback current candidate

- Date: 2026-11-12
- Source checkout: `f39a2844cda16b014a682a248eaf897207a580e7`
- Ronin image built from that clean checkout: `sha256:8c7ae4e685aa5c4fb58085a62442dc18a7cbee34814c93d8b639b230cd7e4f52`.
- Docker prerequisite: **27/27 passed, 0 skipped, 0 failed**; strict v0.1 **15/15**, `strict_success=true`. Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-f39a284-2`.
- Helm/kind runner: `tools/run_helm_qualification.ps1`; Helm `v4.3.1`, kind node `v1.37.0`.
- Result: **PASS**. Helm lint and Secret boundary passed; isolated kind install/readiness passed; upgrade created revision 2; rollback restored revision 1; health endpoint and authorized Studio/jobs API passed; queued job ID survived a deployment restart; isolated cluster cleanup passed.
- Helm evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-helm-evidence-f39a284-2`.
- Boundary: this closes the current single-node Helm upgrade/rollback/restart diagnostic. It does not qualify multi-user HA, external object-store recovery, supported-platform breadth, or the complete P14/Public v1 family.
