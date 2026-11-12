# Docker integration qualification — exact current candidate

**Date:** 2026-11-12  
**Candidate SHA:** `5535b13b3fd3e20d7171aafd800c1b2cd9b4618b`  
**Evidence:** `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-docker-qualification-5535b13`

The clean-candidate Docker runner completed **27/27 passed, 0 skipped, 0
failed** in 192.19s. Strict v0.1 acceptance was **15/15**, with no skipped,
xfail or failed cases. The image was built from this exact checkout:

`sha256:7c57679e60acf821e7697124cf41605d9f1fef4a2e5fa1fbe32855bab3c6a6d7`

The run covered PostgreSQL/Docker worker execution and recovery, Floci/S3,
Azurite/Azure, strict journeys, persistence, backup/restore and resource
limits. Cleanup succeeded.

