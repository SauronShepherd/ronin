# Workspace, project and source-control contracts — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `ab30bafcd68ac82c1da8ccb5af7de1550b3b24b1`

## Gate

The selected P1 suite covered workspace/project lifecycle, context and source
bindings, environments/connections, project manifests, local source control,
real temporary Git repositories and VCS safety boundaries.

Result: **240 passed, 4 skipped, 0 failed** in 61.81 seconds.

The four skips are host capabilities: Windows symlink creation without
Developer Mode/privilege and POSIX executable-mode behavior. They are not
counted as passes.

## Boundary

This qualifies the local P1 contract surface and real Git/VCS lane. Remote Git
provider certification, complete installed Studio workspace journeys and
multi-user authorization remain open. Public v1 remains **0/13 (0%) — NO-GO**.
