# Ronin Public v1 implementation status

**Status authority:** `docs/product/PUBLIC_V1_SCOPE.md` defines the product/release target.  
**Machine-readable ledger:** `docs/product/public-v1-status.json`.  
**Capability matrix:** [`PUBLIC_V1_CAPABILITY_MATRIX.md`](PUBLIC_V1_CAPABILITY_MATRIX.md).
**Architecture decisions:** [`docs/architecture/PUBLIC_V1_ADRS.md`](../architecture/PUBLIC_V1_ADRS.md).

## Current exact-SHA qualification — 18 November 2026

D135 adds full Docker qualification on candidate
`e204e483ce24f6f5edbec7b1e1a4604832ac712d`: `27/27` integration tests pass,
with `0` skips/failures, and strict v0.1 acceptance passes `15/15`, using real
PostgreSQL, Docker worker, Floci/S3 and Azurite/Azure fixtures. Cleanup passes.
This does not prove indefinite operation, production HA, all 13 families,
human release decisions or every external provider. The production boundary is
`a9413421c27a11ea0e65bfba70777aa2127f37a9`; P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D134 is a complete local Python/PostgreSQL suite on candidate
`a9413421c27a11ea0e65bfba70777aa2127f37a9`: `4757/4788` passed, `31` explicit
skips and `0` failures, with isolated PostgreSQL cleanup. The candidate also
passes the focused architecture/streaming/capability regression selection
`44/44` after decoupling the streaming event bridge through injection. This is
the complete local Python/PostgreSQL scope, not Docker strict v0.1, external
provider certification, indefinite operation, HA, complete P11 qualification
or a release gate. The production implementation boundary is now
`a9413421c27a11ea0e65bfba70777aa2127f37a9`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D132 adds a filtered Docker clean-worker diagnostic on clean candidate
`2edc6a28ef02ade780c75492dc730e461c1c76c7`: the worker demo passes `1/1`, with
`0` skips/failures and Docker cleanup PASS. The strict v0.1 acceptance was not
evaluated, so this is bounded worker-runtime evidence only; it is not the
complete P11 qualification or a release gate. There was no production code
change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D131 adds a filtered direct PostgreSQL decision-integrity cell on clean
candidate `cc8e47b9ebfbe0607cbb8e5f0e90f3a7e14d6046`: rejection of a late
branch decision without terminal-task mutation passes `1/1`, with `0` skips
and `0` failures and isolated cleanup. This is bounded PostgreSQL scheduler
consistency evidence only; it is not the complete PostgreSQL suite, indefinite
operation, HA, external-provider recovery, complete P11 qualification or a
release gate. There was no production code change, and the implementation
boundary remains `e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains
`in_progress`, P13 remains `blocked`, and release remains **NO-GO** at `1/13`
families and `0/10` gates.

D130 adds a filtered direct PostgreSQL scheduler-consistency cell on clean
candidate `2132475f3ee966891f427543f61e3bbc4d2f3978`: atomic and idempotent
run/task snapshots pass `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL consistency evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. There was no
production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D129 adds a filtered direct PostgreSQL workspace-isolation cell on clean
candidate `7b51bf299339e5e2e34f9dd4300ab2652672e593`: workflow mutations
requiring an active workspace pass `1/1`, with `0` skips and `0` failures and
isolated cleanup. This is bounded PostgreSQL mutation-isolation evidence only;
it is not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D128 adds a filtered direct PostgreSQL cancellation-authority cell on clean
candidate `a052aaec40b231be261d89da252028a1bfdb5c42`: authority persistence
before waiting on tasks passes `1/1`, with `0` skips and `0` failures and
isolated cleanup. This is bounded PostgreSQL cancellation evidence only; it is
not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D127 adds a filtered direct PostgreSQL cancellation-authority cell on clean
candidate `51a8a6d91dc08fd1a13b5b701797fd13cb2e7092`: claim fencing before
cancellation intent passes `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL cancellation evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. There was no
production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D126 adds a filtered direct PostgreSQL scheduler-compatibility cell on clean
candidate `8507d689ff60edb7dcc67beb66eff57578cd3deb`: migration five to six
passes `1/1`, with `0` skips and `0` failures and isolated cleanup. This is
bounded historical schema evidence only; it is not the complete PostgreSQL
suite, indefinite operation, HA, external-provider recovery, complete P11
qualification or a release gate. There was no production code change, and
the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D125 adds a filtered direct PostgreSQL workflow/schedule bundle cell on clean
candidate `1ba97c8e76ac674a34e8e3caa46f315c69a30e75`: atomic and idempotent
import passes `1/1`, with `0` skips and `0` failures and isolated cleanup.
This is bounded PostgreSQL persistence/portability evidence only; it is not
the complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. There was no
production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D124 adds a filtered direct PostgreSQL scheduler execution cell on clean
candidate `925c103a9c3f3513842d348ecb63cfbc2bc753a7`: schedule cursor, firing
and HTTP adapter pass `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL scheduler evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. There was no
production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D123 adds a filtered direct PostgreSQL scheduler-authority cell on clean
candidate `d275ea3445b487edd0543432d00fd8a95ac8f7b1`: durable timeout requests
and dispatch authority pass `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL authority evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. There was no
production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D122 adds a filtered direct PostgreSQL scheduler deployment-binding cell on
clean candidate `e8887ef4ab81df4a72679cb2eed001ec4937c4c9`: workspace-scoped
runnable binding passes `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL workspace/runtime-isolation evidence only;
it is not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D121 adds a filtered direct PostgreSQL scheduler-schema migration cell on clean
candidate `61977b834819a3d603a551bec567f69b47cc454f`: migration six to ten
passes `1/1`, with `0` skips and `0` failures and isolated cleanup. This is
bounded PostgreSQL compatibility evidence only; it is not the complete
PostgreSQL suite, indefinite operation, HA, external-provider recovery,
complete P11 qualification or a release gate. There was no production code
change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D120 adds a filtered direct PostgreSQL scheduler-backfill cell on clean
candidate `a576fc990d4910855c5ed0fb750333c55a805d9b`: backfill through the
service and survival after reopen pass `1/1`, with `0` skips and `0` failures
and isolated cleanup. This is bounded PostgreSQL scheduler-recovery evidence
only; it is not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D119 adds a filtered direct PostgreSQL execution-outbox cell on clean candidate
`161bc91271bc5374a84cd206ba406382589e6da5`: survival across expiry and
reconciliation pass `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL authority/recovery evidence only; it is
not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D118 adds a filtered direct PostgreSQL scheduler-leadership cell on clean
candidate `00f5ae85442a28a6011eb89ab194baf104b5b80b`: generation fencing and
persistence pass `1/1`, with `0` skips and `0` failures and isolated cleanup.
This is bounded PostgreSQL authority/recovery evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. D115/D116 startup
attempts remain excluded from PASS. There was no production code change, and
the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D117 adds a filtered direct PostgreSQL cancellation cell on clean candidate
`e05cda36bf99ec2abd3961b4514695a54f9999b3`: retiring an unsubmitted outbox
during cancellation passes `1/1`, with `0` skips and `0` failures and isolated
cleanup. This is bounded PostgreSQL runtime evidence only; it is not the
complete PostgreSQL suite, indefinite operation, HA, external-provider
recovery, complete P11 qualification or a release gate. D115/D116 startup
attempts are not counted as PASS. There was no production code change, and the
implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D114 adds a filtered direct PostgreSQL workflow-cancellation cell on clean
candidate `4015bc91bed15be9519c8df4e833bd5c9bfe2ed3`: durable cancellation
reconciliation between the job and outbox passes `1/1`, with `0` skips and
`0` failures and isolated cleanup. This is bounded PostgreSQL runtime evidence
only; it is not the complete PostgreSQL suite, indefinite operation, HA,
external-provider recovery, complete P11 qualification or a release gate.
There was no production code change, and the implementation boundary remains
`e6f635dfe9159351711f44af9199e573e6e8a5bb`. P11 remains `in_progress`, P13
remains `blocked`, and release remains **NO-GO** at `1/13` families and
`0/10` gates.

D100 adds the current-candidate live replay-idempotency and worker route cell
on clean candidate e6f635dfe9159351711f44af9199e573e6e8a5bb. The production
bridge now reuses the first persisted received_at for a deterministic
stream.record replay when stable content matches, while preserving real event
conflict rejection. The local runtime selection passes 14/14 and the combined
Docker-contract, streaming-runtime and scheduler-bridge selection passes
40/40. The full live route with PostgreSQL/Redpanda/API and the worker passes
42/43 with 0 failures and 1 deliberate multi-broker skip; the required
three-broker companion passes 1/1, and the route audit correlates 439/439 API
events. The runner's non-zero status is only its strict skip policy. The
production implementation boundary is now e6f635dfe9159351711f44af9199e573e6e8a5bb.
The full route starts PostgreSQL for the ingestion fixture but the live server
uses SQLite storage, so this is not PostgreSQL scheduler/runtime qualification.

D99 adds a local failure-boundary retry regression on clean candidate
`df4013704ffe41010e765cd0ff030fbe07e77e3d`: after the real SQLite event store
commits a stream event, a simulated failure occurs before checkpoint CAS; the
checkpoint remains unchanged while the sink and one delivery persist, and a
retry advances without duplicates. The focused runtime selection passes
`14/14` and Ruff passes. This is deterministic local recovery evidence, not a
live provider, PostgreSQL/worker, distributed transaction or complete P11
qualification. The production implementation boundary remains
`8afd9df8d3b52bc7830642c2e59e242cffab8f20`.

D98 adds a current-candidate live stream-to-event-triggered-workflow cell on
clean candidate `6bb64f01430d6123cf395d35a182d4840ff602fe`: a real
single-record Redpanda topic commits through the local table sink, creates a
deterministic `stream.record` event, delivers it to `live-main`, creates a
`workflow-run-event-*` run and keeps exactly one delivery on replay. The
journey passes `1/1`, correlates `12/12` real API events as `OK`, reports no
unexpected errors and cleans up the isolated services. This is a bounded
single-broker diagnostic, not indefinite operation, a production-duration SLO,
a distributed transaction or a complete P11 qualification. The production
implementation boundary is `8afd9df8d3b52bc7830642c2e59e242cffab8f20`.

D97 adds a bounded live supervisor-duration cell on clean candidate
`5dd019fdc89c0d7886ea47db794d70e563c8cb03`: a real producer sends records to a
two-partition Redpanda topic for `60` configured seconds while repeated
supervisor cycles run, checkpoints are observed and the final health check
reaches lag zero. The journey passes `1/1`, correlates `35/35` real API events
as `OK`, reports no unexpected errors and cleans up the isolated services.
This is a bounded single-broker diagnostic, not indefinite operation, a
production-duration SLO or a production-topology claim. The production
implementation boundary remains `633980dd3b08affcc604dc918c1a6cbf026cc408`;
D97 changes qualification tooling/specification only.

D96 adds the first filtered live Parquet-sink cell on clean candidate
`b7b938c3d9712b6a74e87b3b10569161c9e8c789`: real single-broker Redpanda and
Ronin API, a bounded 10-record cap leaving lag 54, resume of the remaining 54
to lag zero, idle replay, and two reset/replay cycles of 7 records with stable
`parquet-batch` commits. The journey passes `1/1`, correlates `11/11` real API
events as `OK`, reports zero unexpected errors and cleans up the isolated
services. This is local PyArrow/filesystem sink evidence, not external
object-store or production-topology evidence. The production implementation
boundary remains `633980dd3b08affcc604dc918c1a6cbf026cc408`; D96 changes
qualification tooling/specification, not production runtime behavior.

D95 extends the local supervisor sink matrix on test candidate
`e5ef16525164bfb346def250dd7d4d8053526144`: four bounded segments of 16
single-record micro-batches (64 records total) use the runtime's Parquet sink,
verify all 64 checkpoint-addressed files and numeric offsets `0..63`, reset the
checkpoint, replay offset `0`, and confirm that no duplicate file is created.
The new case passes `1/1`; the focused Docker-contract, streaming-runtime and
workspace-project API selection passes `98/98`. This is local PyArrow/filesystem
sink evidence only. The production implementation boundary remains
`633980dd3b08affcc604dc918c1a6cbf026cc408`; D95 changes tests, not production
runtime behavior.

D94 adds a new local bounded supervisor-soak cell on test candidate
`467f1a39ac5c4557355ff7df57c3e945d5affc5d`: four sequential segments of 256
single-record micro-batches (1,024 records total), with explicit
`max_records` stop, checkpoint digest/offset checks after every segment, exact
SQLite sink offsets `0..1,023`, bounded `limit` reduction `4,3,2,1`, and
source-session cleanup. The new case passes `1/1`; the focused Docker-contract,
streaming-runtime and workspace-project API selection passes `97/97`. This is
local synthetic supervisor evidence only. The production implementation
boundary remains `633980dd3b08affcc604dc918c1a6cbf026cc408`; D94 changes tests,
not production runtime behavior.

D93 remains the latest high-volume real live cell and extends the current candidate's live
bounded backpressure journey to `65,536` records over a real single-broker
Redpanda fixture. The journey uses
an explicit total timeout of `1,800 s` and segments the resume into requests of
at most `8,192` records, preserving the durable checkpoint boundary between
requests. The cap, lag-zero drain, idle replay, reset and two `7`-record replays
pass `1/1`, with `19/19` real API events correlated to structured logs, all
`OK`, and cleanup succeeds. The qualification harness is at
`549ffe30d6df66e92325c90b582c31880536bcb5`; the production implementation
boundary remains `633980dd3b08affcc604dc918c1a6cbf026cc408` because the new
commit only changes qualification timeout/segmentation behavior.

D97, D96 and D93 are filtered streaming-only diagnostics and D94–D95 are local
diagnostics: PostgreSQL, worker, external providers and production topology are
not established, and none of these receipts is an indefinite-operation claim.
P11 remains `in_progress`, P13 remains `blocked`, and release remains
**NO-GO** at `1/13` families and `0/10` gates.

D90 refreshes the route-wide live audit on the exact candidate
`633980dd3b08affcc604dc918c1a6cbf026cc408` with PostgreSQL, Redpanda, the
Ronin API and a real worker image built from the same source: `25` active
routes (`24` API-backed and `1` UI-only), `39/40` browser cases passed and
`379/379` API events correlated. The single skipped case is explicitly the
multi-broker failover, which the runner requires to be selected as a focused
three-broker diagnostic; the route-wide result is therefore kept open rather
than promoted to a full PASS.

D91 runs that focused multi-broker case on the same candidate with three
brokers at RF3 and the worker image available: `1/1` passed, `0` skips, `0`
failures and `5/5` correlated API events, all `OK`, with isolated cleanup.
Together D90 and D91 provide current-SHA route coverage and the separate
multi-broker recovery cell without claiming indefinite operation or a complete
P11 family journey.

D92 extends the exact-candidate bounded single-broker backpressure journey to
`32,768` records. The filtered Playwright case passes `1/1`, produces `12/12`
correlated `OK` API events, reports zero unexpected errors and cleans up the
isolated broker/network. The run uses `RequestTimeoutSeconds=600`, PostgreSQL
and worker are intentionally out of scope, and the result remains bounded
evidence rather than an indefinite-operation claim.

D89 renueva el dossier de artefactos y supply-chain para la misma frontera
exacta: wheel/sdist, TARs runtime/probe, identidad de artefactos, SBOM de
aplicación de `110` componentes, dos inventarios de contenedor distintos
(`59`/`56` paquetes OS), provenance local y validación estricta pasan. Los
scans Trivy `0.76.1` separados con `vuln,secret` reportan `0` vulnerabilidades
y `0` secretos en runtime y probe; las imágenes se retiraron por digest.
La provenance es local y no firmada, por lo que no sustituye la revisión
humana de seguridad, licencias, NOTICE, VEX o release governance.

D88 revalida el despliegue Helm/kind sobre la imagen del candidato exacto
`633980dd3b08affcc604dc918c1a6cbf026cc408`: Helm 4.3.1 pasa lint, render de
`4` recursos con el token confinado al `Secret`, instalación/readiness,
health `200`, Studio/jobs API, persistencia del job tras restart, upgrade a
revisión `2`, rollback a revisión `1` y cleanup. La imagen
`sha256:c8f2d52af735703ace9bcf10a9d928cf086e5b1b907ad7d8f0703c8fcbfbf2d9`
se eliminó por ID inmutable al terminar.

D87 reconstruye la misma imagen y revalida Docker `27/27` con `0` skips y
`0` fallos, además de aceptación v0.1 estricta `15/15`. D86 revalida el
failover bounded live con tres brokers y RF `3` (`1/1`, `5/5` eventos API
correlacionados, todos `OK`); D85 revalida el backpressure single-broker de
`16,384` registros (`1/1`, `12/12` eventos `OK`); D84 revalida Docker/worker
`27/27` y v0.1 `15/15`; y D83 revalida la suite completa Python/PostgreSQL
(`4,753/4,784`, `31` skips explícitos, `0` fallos, cleanup correcto) sobre
el mismo SHA. La nueva frontera exacta contiene `1,599` archivos y
`16,765,557` bytes.

Estas celdas actualizan la evidencia bounded del candidato nuevo, pero no
prueban operación indefinida, topología productiva, amplitud de proveedores,
la familia P11 completa ni la aprobación de release. D76–D82 permanecen como
recibos del candidato anterior `5c17dd7a642ef1e6a16d00967f9aec38ccce91d0` y
no se reatribuyen al SHA nuevo. El release permanece **NO-GO** en `1/13`
familias y `0/10` gates.

D67 remains linked as an earlier scaled live regression on the preceding exact
candidate and binds `018176e0a3693d668bac0d049a6ce4db3c7f2723` to a
green local streaming/worker regression (`87/87`) and a scaled live
single-broker backpressure journey with `16,384` records. The live case passes
`1/1`, verifies cap `73`, durable resume to lag zero, idle replay, reset and
two `7`-record replays, and correlates `12/12` API events, all `OK`, with
cleanup succeeded. The same candidate's full Python/PostgreSQL regression
passes `4,753` with `31` explicit skips and `0` failures out of `4,784`, with
cleanup succeeded and `13` ResourceWarnings retained for follow-up. The live
run is bounded and uses `RequestTimeoutSeconds=300`; it is not indefinite
operation or complete P11 qualification. D66 remains
linked for the real worker-backed Notebook (`1/1`, `16/16`), three-broker
failover (`1/1`, `5/5`) and clean security scans. The ledger remains
**NO-GO** at `1/13` families and `0/10` gates.

D65 extends the live qualification harness with an explicit bounded request
timeout shared by the Ronin server and the browser proxy. The default remains
`15 s`; the counted high-volume diagnostic uses `-RequestTimeoutSeconds 60` so
the `4,096`-record P11 fixture can drain its `4,023` remaining records in
`503` microbatches without the proxy aborting the request at the default
deadline. Exact candidate
`9b3f3670ac19baac95f4dfd35b73805ba0785ae1` passes `1/1`, verifies the cap at
`73`, resume to lag zero, idle replay, reset and two `7`-record replays, with
`12/12` real API events correlated, all `OK`, no unexpected server/network
errors and cleanup in `69.45 s`. PostgreSQL is intentionally not started for
this streaming-only slice, `workerImage=null`, and the non-default timeout is
recorded as a diagnostic parameter. D65 is scaled bounded evidence, not
indefinite operation or a complete P11 family journey; the ledger remains
**NO-GO** at `1/13` families and `0/10` gates.

D64 fixes the live qualification harness so a filtered diagnostic that selects
`performance` or the complete route surface stages the repository's
`ronin-plugin-performance` package. The first broad route attempt exposed the
gap as a `404` on `/api/v1/performance/analyze`; that attempt is not counted.
The corrected exact candidate `728e1b7861790e7b44bd3081dbdaae60159e2ab4`
passes the route-surface diagnostic `26/26` with `25` active routes (`24`
API-backed and `1` UI-only), `220/220` real API events correlated with
structured logs (`212` OK and `8` expected WARN), zero unexpected
authorization/server/network errors and successful cleanup in `135.95 s`.
`routeCoverage.audited=false` because this is an explicit filtered diagnostic;
the worker image remains unavailable. D64 is route-surface evidence, not the
full worker-backed live qualification, a complete family journey or a release
gate. The ledger remains unchanged: release is **NO-GO** at `1/13` families
and `0/10` gates.

D63 adds clean source, locked-dependency and filesystem vulnerability/secret
scan evidence over the already verified exact candidate
`e27cb00fe680c6ff30ee7e26da2d8556970f8ca5`. Gitleaks `8.30.1` scans
approximately `16,544,004` bytes with `0` findings, pip-audit `2.10.1` reports
no known vulnerabilities for the hash-locked `requirements-test.lock`, and
Trivy `0.76.1` pinned to
`aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c`
reports exit `0` and no filesystem vulnerability or secret findings. D63 does
not bind a Ronin runtime/probe image, produce the aggregate SBOM/provenance
dossier, resolve license or provider decisions, or replace human security
acceptance. It does not change the ledger: release remains **NO-GO** at
`1/13` families and `0/10` gates.

D62 validates the active `streaming` Studio route on exact candidate
`e27cb00fe680c6ff30ee7e26da2d8556970f8ca5`. The live browser case passes
`1/1`, reaches PostgreSQL, Kafka/Redpanda and the Ronin API, and produces
`52/52` structured-log-correlated events (`48` OK and `4` expected WARN), with
zero unexpected authorization/server/network errors and successful cleanup in
`49.21 s`. This is route-surface evidence complementary to the bounded
checkpoint, recovery and backpressure receipts below; it is not a 25-route
audit or a complete P11 family journey.

D62 does not change the ledger. The filtered route summary reports `25` active
routes (`24` API-contract and `1` UI-only), but `routeCoverage.audited=false`;
worker/provider qualification, indefinite operation, security scans and human
visual/accessibility review remain open. Release remains **NO-GO** at `1/13`
families and `0/10` gates.

D61 scales the live P11 backpressure fixture without changing production
runtime behavior. The runner and fixture preserve `256` as the default and
accept an explicit bounded record count; the exact candidate
`aaab84e8cbb111e28e9e81dfc7f5f684bde7f94d` passes `1/1` at `1,024` records on
two real Kafka partitions. The journey caps at `73`, resumes the remaining
`951` records through `119` microbatches to lag zero, verifies an idle replay,
resets to lag `1,024`, and repeats a `7`-record replay after a second reset.
All `12/12` API events correlate with Ronin logs and are `OK`; cleanup succeeds
in `66.12 s`. The runner records the fixture size in its qualification
summary. The implementation baseline remains `0a0cd36d47e403808db519f62eefd726f95637a4`.

D61 is bounded load evidence, not indefinite operation or a complete P11 or
Public v1 qualification. The filtered runner reports `25` active routes but
does not run the route-wide audit, and no worker image or external provider
profile was available. Production topology, worker/provider breadth, security
scans, the complete family journey and human review remain open. Release
remains **NO-GO** at `1/13` families and `0/10` gates.

D60 adds bounded live evidence for P11 on the exact documentation-inclusive
candidate `7f0a005db3b853b55e6a4b00f660d8b5753c2ef5`; the implementation code
baseline remains `0a0cd36d47e403808db519f62eefd726f95637a4`. Three filtered live
API/browser slices pass `7/7` cases and correlate `90/90` HTTP events with the
Ronin logs: the core streaming slice passes `5/5` with `74` events (`70` OK,
`4` expected WARN), multi-broker failover passes `1/1` with `5/5` OK events on
three brokers, and broker restart passes `1/1` with `11` events (`8` OK and
`3` expected `503` outage outcomes). All valid slices report zero unexpected
server/network errors and successful cleanup. The initial broad `streaming`
grep is retained as a diagnostic non-pass because it contained one deliberate
multi-broker skip; it is not mixed into the `7/7` result.

D60 is bounded live evidence, not a complete P11 or Public v1 qualification.
The runner route audit was not enabled (`routeCoverage.audited=false`), no
worker image or external provider profile was available, and indefinite
operation, production topology support, broader sink/replay coverage, the
complete family journey, security scans and human review remain open. Release
remains **NO-GO** at `1/13` families and `0/10` gates.

D59 repaired the stale Studio web-budget ratchet exposed by the static gate.
The normalized asset measurement is now `2,171,102` bytes across `71` assets,
with `37` JavaScript modules, `15` stylesheets and `5,838` HTML bytes; the
static web audit reports `72` files, `184` route invocations and `0` failures.
Ruff, mypy, architecture, negative gates, route consistency, Studio surface,
dependency surfaces, OpenAPI, canonical JSON, runner protocol, capability
status and Node syntax also pass. The ratchet accounts for the bounded
supervised-streaming controls; it is not live UI or manual release evidence.

D58 validates the documentation-inclusive exact candidate
`b86a784e997ce03921d26d99aae7c5f6dced1ebe` after correcting the stale observed
source marker in the public capability matrix to the implementation baseline
`0a0cd36d47e403808db519f62eefd726f95637a4`. The full Python/PostgreSQL suite
passes `4753` tests, skips `31` externally or platform-gated tests and reports
`0` failures, with `13` SQLite `ResourceWarning` entries recorded for follow-up.
The focused public/status/progress selection passes `13/13`. This is broad
regression evidence, not a complete P11 or Public v1 qualification: skipped
Docker/worker/provider lanes, security scans, route-wide audit, human review
and the remaining release gates remain open. Release remains **NO-GO** at
`1/13` families and `0/10` gates.

D57 extends the exact candidate `0a0cd36d47e403808db519f62eefd726f95637a4`
with explicit `max_records` cap/resume/replay evidence. The exact sandbox
remains `60/60` focused contracts with no skips and the qualification runner
contract selection is `25/25`. The live journey caps at `10` records with
`stop_reason=max_records` and lag `54`, resumes the remaining `54` to lag
zero, returns an empty replay, and rejects `max_records=0` with HTTP `400`;
its clean run passes `1/1` with `8/8` correlated events (`7` OK and `1`
expected WARN). D56's supervised drain-to-idle and D55's four streaming
journeys remain green on the same SHA. The runner reports zero unexpected
server/network errors and cleanup succeeds. This is bounded same-candidate P11
evidence, not a complete family qualification: indefinite operation,
worker/provider breadth, production topology support, route-wide audit and the
remaining release gates remain open. Release remains **NO-GO** at `1/13`
families and `0/10` gates.

### Historical exact-SHA qualification — D56 — 17 November 2026

D56 added supervised drain-to-idle evidence on the exact candidate
`0a0cd36d47e403808db519f62eefd726f95637a4`. The two-partition fixture consumed
`64` records, returned `stop_reason=idle`, reached durable lag zero and
rejected `max_batches=0` with HTTP `400`; the live run passed `1/1` with `5/5`
correlated events (`4` OK and `1` expected WARN). D56 was bounded continuity
evidence, not a complete P11 qualification.

### Historical exact-SHA qualification — D55 — 17 November 2026

D55 advanced the exact candidate to `0a0cd36d47e403808db519f62eefd726f95637a4`
and repaired the broker-restart audit contract. The exact sandbox verified
`60/60` focused contracts and `25/25` runner contracts. Four clean candidate
journeys passed `1/1`: single-broker restart (`11/11` correlated events with
three expected `503` errors), multi-broker failover (`5/5`), D50 (`12/12`) and
D51 (`13/13`); the audit reported zero unexpected server/network errors.
D55 was bounded same-candidate evidence, not a complete P11 qualification.

### Historical exact-SHA qualification — D54 — 17 November 2026

D54 revalidated the bounded D50 and D51 journeys on candidate
`b69204d02cd3b7649cab49fc42b6bc68443a94b2`: the 256-record
cap/resume/reset/replay case passed `1/1` with `12/12` correlated HTTP events,
and the near-record/near-batch byte-boundary case passed `1/1` with `13/13`
correlated events (`11` OK and `2` expected WARN). Both filtered live runs
reported zero server/network errors and complete cleanup. D54 was bounded
same-candidate evidence, not a complete P11 qualification.

### Historical exact-SHA qualification — D53 — 17 November 2026

D53 advanced the exact candidate to `b69204d02cd3b7649cab49fc42b6bc68443a94b2`.
The exact sandbox verified `60/60` focused contracts with no skips, and the
clean candidate-bound API/browser failover journey used a real three-node,
three-replica Redpanda topic. After one committed record, the journey stopped
broker-0, resumed four records from the durable checkpoint through surviving
brokers, restored the failed container and reached final lag zero. The run
passed `1/1` with `5/5` correlated HTTP events and zero server/network errors.
Final health was checked after broker restoration; the failure window was
asserted while broker-0 was stopped. D53 was bounded recovery evidence, not a
complete family qualification.

### Historical exact-SHA qualification — D52 — 17 November 2026

D52 advanced the exact candidate to `fe5be99c535ca4eb17ee371744e7b7a6acd87ba0`.
The exact sandbox verified `61/61` focused contracts with no skips, including
an opt-in direct-runtime recovery test against a real three-node, three-replica
Redpanda topic. After one committed record, the test stopped the leader, resumed
four records from the durable SQLite checkpoint through surviving brokers,
restored the failed container and observed a healthy cluster. D52 was bounded
direct-runtime recovery evidence; it did not claim the D51 API journey on this
SHA. Indefinite backpressure, worker/provider breadth, production topology
support, route-wide audit and the remaining release gates remained open.
Release remained **NO-GO** at `1/13` families and `0/10` gates.

### Historical exact-SHA qualification — D51 — 17 November 2026

D51 advanced the exact candidate to `5a4557aa158f4046ca19e0dd28e83ee747d31399`.
The exact sandbox verified `60/60` focused contracts with no skips, and the
clean candidate live journey used real PostgreSQL, Redpanda/Kafka and Ronin
API services. Its byte-boundary fixture accepted one `1,047,552`-byte record
and eight `1,000,000`-byte records totaling `8,000,000` bytes, then rejected
nine such records totaling `9,000,000` bytes twice without advancing lag or
checkpoint. This was bounded P11 byte-limit evidence, not a complete family
qualification: indefinite backpressure, worker/provider breadth, multi-broker
recovery, route-wide audit and the remaining release gates remained open.
Release remained **NO-GO** at `1/13` families and `0/10` gates.

### Historical exact-SHA qualification — D50 — 17 November 2026

D50 advanced the exact candidate to `cb78bc4adccd82c1afbba4608c61b6b22ef5e0b5`.
The exact sandbox verified `60/60` focused contracts with no skips, and the
clean candidate live journey used real PostgreSQL, Redpanda/Kafka and Ronin
API services. Its two-partition fixture started at `128/128` lag over `256`
records, stopped at `73` records under a bounded cap, resumed the remaining
`183` records to zero lag, returned an empty replay, and succeeded on repeated
seven-record reads after checkpoint reset. This was larger bounded P11 evidence,
not a complete family qualification: byte-limit saturation, indefinite
backpressure, worker/provider breadth, multi-broker recovery, route-wide audit
and the remaining release gates remained open. Release remained **NO-GO** at
`1/13` families and `0/10` gates.

### Historical exact-SHA qualification — 16 November 2026

The current exact-head candidate is `a224b7983b31a97abbeb0d482fd50d8c2fa653dc`.
D38 adds candidate-bound P11 broker-restart recovery and refreshes the probe
Alpine lock after the preceding image showed 11 MEDIUM findings with available
fixed versions. The exact candidate sandbox passes `95` streaming/API tests
and `24` Docker contract tests with zero failures/skips. A clean candidate
runner starts real Redpanda and Ronin APIs, executes `2/2` streaming cases,
correlates `52/52` API events, observes expected `503` outage responses and
resumes four records from the durable checkpoint to zero lag; cleanup passes.
Artifact qualification passes `92/92`; Gitleaks reports zero findings and
pip-audit reports no known vulnerabilities in the `54` dev and `99` test
locked dependencies. Trivy `0.76.1` reports `0` vulnerabilities and `0`
secrets in both exact runtime/probe TARs; application/container SBOM,
provenance and fail-closed supply-chain validation pass.
The exact candidate browser archive lane is `SKIP` because `@playwright/test`
is not packaged; Node syntax checks pass. License qualification remains closed
on `21` missing human review decisions.
D39 adds an unfiltered real-service journey from the clean exact source:
`34/34` live cases, `25` active routes audited, `296/296` correlated API
events (`279` OK, `17` expected WARN), real PostgreSQL/Redpanda/API/worker
services and cleanup. The D38 parent product-code candidate suite remains
`FAIL`: `4685 passed, 81 skipped, 8 failed`; D39 does not rerun that suite,
image scans or license decisions because its delta is documentation only.

D40 adds candidate-bound backlog evidence from the exact test commit
`ebe798021d2d593515ee1766f7bdc22119b72e80`: a real Redpanda topic starts with
`64` records across two partitions (`32/32` lag), and the API/Chromium case
drains it with one-shot batches capped at `4`, non-increasing lag, exactly `64`
rows consumed and final lag `0`. The filtered live campaign passes `3/3`
cases with `52/52` API events correlated and cleanup. D40 also reruns the
broker-restart recovery case. PostgreSQL and the worker are intentionally out
of this streaming-only campaign; the candidate browser archive remains `SKIP`
without packaged `@playwright/test`, and D40 does not rerun the full Python
suite, image scans or license decisions.

D41 records a fresh Docker qualification from exact candidate
`f331bb6adae6b7428c43ba53647b39b2f3dc0955`: `27/27` tests pass and strict v0.1
acceptance is `15/15` against real PostgreSQL, Docker worker/runtime,
Floci/S3-compatible and Azurite/Azure Blob services. The executed image is
`sha256:b726de75bc8a1867e6ad788a570bb61dd1210ae2e7bc1e5ef899c576958360bd`;
Gitleaks reports zero findings and pip-audit reports no known vulnerabilities
for the exact candidate locks. Resource cancellation/timeout final measurements
were unavailable after harness termination, and Trivy was not installed, so
neither limitation is represented as a PASS. D41 changes documentation and
evidence only; it does not close a family or gate. P13 remains blocked by the
absent authorized external secret provider and release evidence.

D42 records a candidate-bound local Floci/Terraform provider cell from exact
candidate `bc1884c5dfab00c8cab6c0095154bb4b3748ca1c`. The exact sandbox passes
`13/13` positive and negative Floci qualification contracts. Against pinned
local Floci 2.1.0, Terraform 1.13.5 and AWS provider 6.65.0 pass health,
plan, validate, apply, real S3-bucket/SQS-queue observation, refresh, destroy
and empty Terraform/Floci inventories. Gitleaks reports zero findings and
pip-audit reports no known vulnerabilities in 54 dev and 99 test locked
dependencies. An initial host attempt with global Terraform 1.16.2 was
rejected before plan and is recorded as an environment failure, not a PASS.
Trivy and the full Python suite are not rerun; D42 makes no AWS/Azure cloud,
Ozone, external object-store recovery or external-secret claim. P2/P14 remain
in progress, P13 remains blocked, and no family or gate closes.

D43 records a candidate-bound supervised streaming drain from exact candidate
`d6890832a6743cde1bd949bd3529359285559c0d`. The implementation adds bounded
`max_batches`, `max_records` and `idle_polls` controls to the existing run
route, repeats checkpoint-safe micro-batches, and reinitializes the bounded
provider poll on each cycle. The exact candidate selection passes `110/110`
with zero failures or skips; Ruff, mypy, architecture/negative gates, route
consistency, dependency surfaces and OpenAPI snapshot checks pass.

The real filtered campaign starts PostgreSQL, Redpanda/Kafka and Ronin API.
Chromium seeds two partitions with 64 messages, observes lag 64, drains all
`64` records and `64` rows, and confirms lag zero after the supervised stop by
idle. The invalid `max_batches=0` request returns HTTP 400. The live runner
records `1/1` Playwright pass, `5/5` API/log correlations, `4` OK and `1`
expected WARN, and zero server/network errors; cleanup succeeds. The three
earlier D43 attempts remain recorded as failures (32/64 drain or missing
traffic evidence) and are not counted as PASS. This is one bounded diagnostic,
not a route-wide audit, indefinite backpressure soak, broker-restart recovery,
provider matrix or complete P11 qualification. D43 does not rerun the full
Python suite, Gitleaks, pip-audit or Trivy, and license review remains closed
on 21 human decisions.

D44 records a candidate-bound real broker-restart recovery journey from exact
candidate `bd1b7f4c08fc1f9c36976014dc630317b86a8cf1`. The existing Chromium
journey now captures its API calls, and the runner has a narrow, fail-closed
allowance for exactly two expected `503 streaming_unavailable` responses only
when this exact test and its `events/fault-recovery` health/run paths are
selected. Any other 5xx or network error remains disqualifying; the expected
outages remain recorded as `ERROR`, not `WARN`. The exact candidate selection
passes `134/134` with zero failures/skips and Node syntax checks pass.

Against real PostgreSQL, Redpanda/Kafka and Ronin API, the test consumes one
record, stops the real broker container, observes the expected health/run 503s,
starts the broker, observes health recovery with lag four, consumes the four
remaining checkpointed records, and confirms lag zero. The live runner reports
`1/1` Playwright pass, `10/10` API/log correlations, `8` OK and `2` expected
ERROR responses, with zero unexpected authorization or server/network errors;
cleanup succeeds. The earlier attempt is retained as a failed harness
iteration, not PASS. This is one local single-broker diagnostic, not a
multi-broker quorum test, sustained backpressure soak, route-wide audit,
provider matrix or complete P11 qualification. D44 does not rerun the full
Python suite, Gitleaks, pip-audit or Trivy, and license review remains closed
on 21 human decisions.

D45 records a candidate-bound fix and live qualification for bounded Kafka
backlog polling from exact candidate
`bfa94cf0cb19c7058e0b54c1826f746a9f5594eb`. `KafkaJsonSource` now retries
transient empty/partition-EOF results within the bounded poll timeout, so an
assigned later partition can be discovered without relaxing record or byte
limits. The exact candidate selection passes `135/135` with zero
failures/skips; the unit regression covers an empty poll followed by
partition-1 records, and Node syntax checks pass.

The real filtered campaign starts PostgreSQL, Redpanda/Kafka and Ronin API.
Chromium observes `32/32` initial lag across two partitions, executes bounded
`limit=4` runs, confirms non-increasing lag, drains `64` records and `64` rows,
and reaches lag zero. The runner records `1/1` Playwright pass, `64/64`
API/log correlations, all `64` responses as `OK`, zero server/network errors,
and successful cleanup. The first attempt is retained as a failed 40-attempt
diagnostic that stalled after the first partition and is not counted as PASS.
This is one bounded local backlog diagnostic, not indefinite backpressure,
multi-broker recovery, a route-wide audit, provider matrix or complete P11
qualification. D45 does not rerun the full Python suite, Gitleaks, pip-audit
or Trivy, and license review remains closed on 21 human decisions.

D46 binds the existing Streaming Studio route to exact candidate
`8fc871f0ab2be3e6576ff1936446cfd9ae11f3f9` without changing production code.
The real route journey runs against PostgreSQL, Redpanda/Kafka and Ronin API,
and covers the invalid-limit 400, poison and oversized 422 rejections,
checkpoint preservation, valid-source recovery and bounded two-partition
drain. It records `1/1` Playwright pass, `52/52` API/log correlations, `48`
`OK` and `4` expected `WARN` responses, zero unexpected authorization gaps and
zero server/network errors. The exact candidate sandbox passes `135/135` with
no skips, and its archive/manifest remain identical after cleanup/regeneration.

D46 is a filtered route diagnostic: route-wide audit, full Python suite,
Gitleaks, pip-audit and Trivy are not rerun, and license review remains closed
on 21 human decisions. It does not prove sustained indefinite backpressure,
multi-broker recovery, worker supervision, external providers or complete P11
qualification.

D47 reruns the bounded supervised two-partition drain from exact candidate
`a224b7983b31a97abbeb0d482fd50d8c2fa653dc` after D46. The first clean
candidate run is a real failure: the supervised endpoint returns HTTP 200 with
`status=succeeded`, `stop_reason=idle`, but only `32/64` records and rows. An
immediate repeat on the same candidate and real PostgreSQL, Redpanda/Kafka and
Ronin API drains `64/64` and reaches lag zero. The two results are mixed, so
the retry is retained as an observation and not promoted to a deterministic
qualification PASS. D47 leaves P11 `in_progress` and identifies the open
boundary as consumer/partition discovery or supervisor idle timing; the root
cause remains to be reproduced and fixed or explicitly bounded.

D47 exact sandbox contracts pass `84/84` with zero skips; the candidate was
cleaned, regenerated and verified after tests. The first live receipt records
3/3 correlated HTTP events and no server/network errors despite the failed
32/64 assertion; the repeat records 5/5 correlated events, 4 OK and 1
expected WARN for the invalid cap. Full suite, route-wide audit, Gitleaks,
pip-audit and Trivy remain not rerun, and the license review remains closed on
21 human decisions. This evidence must not be summarized as a stable
supervised PASS until repeated clean-candidate runs are deterministic.

This is bounded technical evidence only. Public v1 remains **1/13 families
qualified, 0/10 gates, NO-GO**: P14 is `in_progress` but external object-store
backup/recovery, supported-platform coverage and complete production
qualification remain open. P12 is still `in_progress`; P13 remains blocked by
external evidence. Manual visual/product review, legal/NOTICE/claims, security
acceptance, support matrix and release governance remain open.

### Historical exact-SHA qualification — `4157181`

The historical runtime/test candidate `4157181843d47893e77d62bed62fdafeb31d6f0b`
is pushed and adds a tenth UI pass: Projects becomes an Author/Connect/Operate/
Govern decision workbench with an operational brief that shows source posture,
next gate and a secret-safe Source column, while the connection dialog gets
deterministic bootstrap before the heavy modules. It sits on top of the governed Catalog,
Semantic, Scheduler, Quality, Data Engineering, Ingestion, ML and Workspaces
workbenches. Its exact receipt is static Chromium `132/132`, web audit `68`
files with zero failures, and budget `2,088,109` bytes. Installed PyRonin
artifact qualification is `90/90`; Docker is `27/27` and strict v0.1 `15/15`
on image
`sha256:af76b755b4bf64ef17f1a670d7b35e1e099f8cd8b26b808194446fb30be6755e`;
Helm/kind install/readiness/health/API/persistence/restart/cleanup pass; live
is `33/33` over 25 active routes with 247 correlated events and no server or
network errors; and Docker Scout/OpenVEX is `3 raw / 0 applied` for that image.
The diff from `8a85586` contains no Python or backend runtime changes, so its
`4562 passed, 27 skipped, 0 failed` PostgreSQL receipt and coverage `53/53`,
`62/62` remain the applicable backend evidence. Trivy is unavailable, so the
container SBOM gate and human VEX/security review remain open. These local
receipts do not silently close the release ledger or human-owned gates.

The exact Python/PostgreSQL receipt is green on the clean documentation tree:
`4562 passed, 27 skipped, 0 failed` of `4589`; coverage passes `53/53` and
`62/62`, with both status-ledger contracts passing. The 27 skips remain
explicitly environment/provider/POSIX gates, not silently converted support
claims.

This does not change the release decision: Public v1 remains **0/13 (0%,
NO-GO)**. Manual visual/product signoff, legal/NOTICE/claims, security reviewer
acceptance, Trivy availability, Terraform `1.13.5`, provider qualification,
CI/branch governance and the complete 13-family evidence matrix remain open.
The UI is a stronger control plane, but the product still needs the deeper,
simpler and more powerful authoring/evidence/operations experience targeted at
Databricks, Dataiku, Palantir and Fabric.

**Historical workspace snapshot (2026-10-25):** At that time main was `4686571b403d1499ffbd8f15fce4b01f650b99e8`, merge of PR #547. PR #430–#546 were merged. PR #520
reconciles Public v1 to exclude in-product GenAI/RAG/agent execution, keeps
coding-agent skills external-only, and places multi-user administration in
Ronin Pro. Its exact-head CI, Docker/PostgreSQL, Web, Security, Release, Status
consistency, external-skills boundary and prerelease-artifact workflows passed.
PR #531 reconciles ML qualification wording. PR #532 adds atomic, exact-replay SQLite ontology Bundle import, including rollback on a late missing asset or conflicting definition; its 55 focused tests, Python 3.11/3.12, Docker/PostgreSQL storage coverage and all six exact-head post-merge workflows passed on `main@29dd455d4ba80d546e830571f2139228d29c6594`. PR #539 adds typed ontology semantics and PR #540 closes unsafe RQL joins for mismatched scalar types and null/missing values. On `main@0b32db1c83e681a08e8118e23c0e4b744b3929a5`, PR checks passed 3,921 local tests (66 platform/provider skips), Python 3.11/3.12, Docker runtime and strict acceptance, PostgreSQL storage coverage, Web, Security, Release, Status and evidence workflows; all six post-merge exact-head workflows passed. `mutation` remained skipped by policy and is not reported as pass. The ontology storage coverage ratchet remains at 76.35%. PR #542 makes Graph `=`/`!=` filters type-aware; its full local suite passed 3,922 tests with 66 environment/platform skips, and its required PR gates passed. Los seis workflows post-merge exact-head de `main@4e63e69334a2ae55ce6bc1c2656742193cb919bb` pasaron. PR #544 corrects OpenLineage export: observed edges emit RunEvents with standard column-lineage facets, declared edges emit DatasetEvents with lineage facets, and validation/transport now enforce bounded payloads and no redirects. The full local suite passed 3,954 tests with 66 skips in 489.21s; all six post-merge exact-head workflows passed. `mutation` remains skipped by policy. PR #546 passed the 3,960-test local suite (66 skips in 453.06s) and all six exact-head post-merge workflows; mutation remained skipped by policy. P6 remains partial and Public v1 remains incomplete.
OpenLineage follow-up source `f91dbfbf6e30d54e18ada1c23c5f2a37983db157` (code tree tested as `b8e6d7834692e35688054f50655f8f73733d34cb`) additionally restricts the known lineage facets to dataset entities and rejects them under run/job. Its 132 focused tests and full local suite (3,962 passed, 66 skipped in 447.66s), Ruff, format, mypy (425 files) and architecture checks passed on the pre-merge code tree. After merge as PR #547, the six exact-head `push` workflows on `main@4686571b403d1499ffbd8f15fce4b01f650b99e8` all passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/40109332120), [Docker](https://github.com/SauronShepherd/ronin/actions/runs/40109332165), [Web](https://github.com/SauronShepherd/ronin/actions/runs/40109332135), [Release](https://github.com/SauronShepherd/ronin/actions/runs/40109332179), [Security](https://github.com/SauronShepherd/ronin/actions/runs/40109332128), and [Status](https://github.com/SauronShepherd/ronin/actions/runs/40109332149). Docker jobs passed PostgreSQL-backed `postgres-storage-coverage` (4,014 passed, 14 skipped; the connector-real test skipped in that job) and the separate `non-docker-qualification` suite (4,015 passed, 11 skipped; it configured `RONIN_CONNECTOR_POSTGRES_DSN` and ran `test_postgres_connector_real.py`), real Docker runtime (8 passed), frozen v0.1 strict acceptance (15/15), and one S3-compatible LocalStack artifact lifecycle test. The PostgreSQL suites are separate and overlap; do not sum their counts. These workflow results do not qualify P6 or any of the 13 Public v1 families; P6 remains partial.
Recent
increments add configurable ML algorithms and preprocessing, selective retry,
non-destructive artifact retention preview, fail-closed reference discovery with
bounded enumeration, bounded-memory local artifact pagination, and paged manual
cleanup that validates a complete bounded inventory before deletion, plus bounded
durable job evidence and cell-result reads across SQLite, PostgreSQL and memory,
Bayesian stopping, ordered directional trial tie-breakers with strict bounded
input validation, a manual-retention guard that requires an explicit opt-in
before an empty live set can delete every artifact, and bounded ML candidate grids.
PR #505 supports up to eight algorithm×preprocessor combinations; its PR Docker
qualification passed in 9m50s and all six exact-head workflows passed on
`main@ad53878fac49330d29824dabf1f27e4c4bd2d9d8`. PR #509 adds durable ML
registration after digest revalidation and passed all six exact-head workflows
on `main@156d60784e8e0c5e23f1383c2cf96dc8860560e3`. PR #510 records the ML
build-plan progress and optimization findings on `main@8c7b7e3a8c9cbbbca7b4cdb8ca1d383125b52afa`.
Global cleanup remains disabled because there is no cross-store write barrier. The
PR #482 prevents an empty live digest set from deleting every artifact unless the
caller opts in with an explicit boolean. Its 26 focused tests, CI Python 3.11/3.12,
Web, Security, Release, Status consistency, Docker PR qualification and all six
post-merge exact-head workflows passed. Local Docker qualification passed 21 tests;
two PostgreSQL-dependent tests were skipped without a local DSN, and strict
acceptance passed 15/15. The global sweep remains disabled until writers and
retention share a cross-store consistency barrier.
Untracked qualification output directories are not release evidence.
PR #527 added atomic, exact-replay SQLite ML Registry Bundle imports. PR #528 extends that transaction guarantee to PostgreSQL, including feature definitions, and merged at `main@72a89d06eaf33f604a613376e630a01c5b163dfd`. Its required exact-head CI, Docker/PostgreSQL coverage, Security, Release and Status gates passed; mutation remained skipped. The first coverage run executed 3929 tests (14 skipped) and prompted the documented ratchet update before the successful rerun. PR #529 then fixed a POSIX child-watcher/Popen polling race that caused synthetic exit code 255 in CI 3.12 and the real Docker worker. Local Windows Docker/PostgreSQL focused coverage passed (11 passed, 1 POSIX-only skip); PR CI and all six post-merge exact-head workflows passed on `main@313b8b87670e3f5cad8d641eeeb4f29cf0c31d63`.
**Observed source head:** `c52f1f404489e673be98f1ea9d4a261a10e1b3ca` (2026-11-18).

D136 live product qualification on candidate `abf0dfab5f2a36ee4a66bc30cdfd1047960421dd` executed 43 cases: 42 passed, 1 skipped, 0 failed. The strict runner therefore records FAIL; 448 API events were correlated across 24 API-backed routes and one UI-only route. The Ronin server used SQLite; PostgreSQL was only the ingestion/browser fixture. P11 remains in_progress, P13 blocked, and release remains NO-GO.

D137 adds a bounded audit of that live traffic: 448/448 unique request IDs, 448/448 correlated HTTP events, zero unexpected errors, and all WARN/ERROR outcomes classified as expected. This strengthens observability evidence only; it does not close the live skip, PostgreSQL runtime, external-provider, indefinite-operation, family, or release gaps.

D138 adds a bounded live PostgreSQL-runtime cell: the Ronin server was configured with `RONIN_STORAGE_BACKEND=postgres`, the Runs route passed `1/1`, and `2/2` API events were correlated with zero skips or failures. This does not claim full scheduler/runtime conformance or change P11, P13, or release status.

D141 requalified the Workflows route with Ronin and scheduler on PostgreSQL after correcting the live seeder's backend mismatch: `1/1` passed, `30/30` API events were correlated, and the affected Python regressions passed `49/49`. This is a bounded wiring cell and does not change the NO-GO release decision.

D142 passed the live Notebook Studio worker cell with Ronin configured for PostgreSQL and a real Docker worker: `1/1` passed, `20/20` API events correlated, and cleanup passed. This remains bounded evidence and does not establish indefinite operation, HA, provider breadth, family coverage, or release readiness.

D143 passed the live streaming event-trigger workflow with Ronin configured for PostgreSQL: `1/1` passed, `12/12` API events correlated, and cleanup passed. This is bounded continuity evidence only; release remains NO-GO.

D144 requalified full Docker integration (`27/27`) and strict v0.1 (`15/15`) with zero skips/failures across PostgreSQL, Docker worker, Floci/S3, and Azurite/Azure fixtures. Cleanup passed; this does not establish indefinite operation, HA, complete family coverage, or release readiness.

D145 passed `2/2` bounded PostgreSQL scheduler-daemon recovery tests: reacquisition after an expired leadership lease and replay after process crash without duplicate work. Cleanup passed; this strengthens scheduler recovery evidence but does not establish indefinite operation, HA, complete family coverage, or release readiness.

D146 passed the complete bounded PostgreSQL scheduler integration file (`21/21`) with cleanup. This broadens persistence, fencing, dispatch, cancellation, backfill, outbox, leadership, and recovery evidence, but does not establish indefinite operation, HA, complete family coverage, or release readiness.

D147 passed `20/20` bounded PostgreSQL store/adapter integration tests with all three required DSN aliases configured and zero skips. Cleanup passed; this broadens runtime persistence evidence but does not establish indefinite operation, HA, complete family coverage, or release readiness.

D148 passed `12/12` bounded PostgreSQL ML/artifact integration tests with zero skips. Cleanup passed; this broadens configured-runtime evidence but does not establish indefinite operation, HA, complete family coverage, or release readiness.

D149 passed the bounded PostgreSQL quality-store integration (`1/1`) with zero skips. Cleanup passed; this adds a focused quality-store runtime check without changing release status.

D150 passed the bounded PostgreSQL local-composed catalog HTTP integration (`1/1`) with zero skips. Cleanup passed; this adds a service-layer catalog check without changing release status.

D151 passed the filtered Docker appliance backup/restore case (`1/1`) with PostgreSQL, a Ronin image, and a local data volume. Cleanup passed; strict v0.1 was not evaluated and the release status remains unchanged.

D152 passed `4/4` filtered real Docker worker/runtime cases with PostgreSQL, including two `SIGKILL` recovery cases that reused persisted cells. Cleanup passed; strict v0.1 was not evaluated and release status remains unchanged.

D153 passed `2/2` bounded local worker lease-renewal/reclaim contention tests in `5.93s`. This is SQLite/artifact-store evidence only and does not establish PostgreSQL, indefinite operation, HA, or release readiness.

D154 passed the bounded local orchestrator/runtime contention test (`1/1`) in `3.04s`, preserving unrelated progress. This is local evidence only and does not establish PostgreSQL, indefinite operation, HA, or release readiness.

D155’s full Python/PostgreSQL campaign reached `4756 passed`, `31 skipped`, and one documentation-baseline failure; cleanup passed. D156 corrected that capability-matrix/status-ledger mismatch and passed its regression `3/3`; D155 is not reclassified as PASS.

D157 repeated the full Python/PostgreSQL campaign after the synchronization fix: `4757 passed`, `31` explicit skips, `0` failures, and cleanup passed in `693.32s`. This is bounded campaign evidence and does not establish indefinite operation, HA, complete family coverage, or release readiness.

D158 passed `2/2` filtered real S3/ML artifact round-trip tests against Floci, including retry and retention behavior. Cleanup passed; strict v0.1 was not evaluated and this does not certify a production external provider or release readiness.

D159 passed the filtered real Azure Blob snapshot replay test (`1/1`) against Azurite. Cleanup passed; strict v0.1 was not evaluated and this does not certify an external production Azure account or release readiness.

D160 attempted a Quality live diagnostic with `StorageBackend postgres` but was not PASS: the quality-only runner skipped PostgreSQL/Kafka and the seeder timed out before server start (`0/0` cases). Cleanup passed; no PostgreSQL qualification is claimed.

D162 passed `1/1` filtered Quality Studio live case with Ronin configured against real PostgreSQL. The run produced 7 correlated API events (6 OK and 1 expected WARN), with zero skipped or failed cases and cleanup passing. The PostgreSQL fixture now seeds the governed catalog revision in PostgreSQL, matching the foreign-key boundary used by `PostgresQualityStore`. This is bounded Quality runtime evidence only; P11 remains in progress, P13 blocked and release NO-GO at `1/13` families and `0/10` gates.

D163 ran the full live browser campaign with PostgreSQL, Kafka and a Docker worker from the candidate. It is **NOT_PASS**: `34/43` cases passed, one deliberate multi-broker case was skipped and eight failed. The PostgreSQL profile exposed unconfigured environments, FinOps, synthetic catalog, graphs and deployments services; the sustained backpressure and supervisor-soak scenarios also missed their criteria. All `411/411` API events were correlated, and cleanup passed. This diagnostic does not change P11, P13 or release status.

D166 passed the filtered environments and deployments journeys (`2/2`) with Ronin configured against real PostgreSQL. All `10/10` API events correlated and were OK; no cases were skipped or failed and cleanup passed. The PostgreSQL composition now wires its existing environment/binding persistence through `PostgresSchedulerSnapshotStore`, and the live fixture registers a valid project for the binding FK. This is bounded evidence only; P11 remains in progress, P13 blocked and release NO-GO at `1/13` families and `0/10` gates.

D168 passed the explicit bounded streaming supervisor-soak criterion (`1/1`) for 60 seconds on the single-broker SQLite runtime. It produced `33/33` correlated API events, all OK, with no skips or failures and cleanup passing. This narrows the D163 soak failure to campaign interference or load interaction but does not qualify indefinite operation, PostgreSQL, HA/multi-broker or release readiness.

D170 passed the filtered Synthetic Data Studio journey (`1/1`) on its configured SQLite runtime, with `8/8` correlated API events, all OK, and cleanup passing. The runner is explicitly SQLite-only for this route; D169's PostgreSQL request timed out before startup and provides no PostgreSQL evidence. This remains bounded local evidence and does not change P11, P13 or release status.

D171 passed the filtered Graphs journey (`1/1`) on the configured SQLite runtime, with `5/5` correlated API events, all OK, and cleanup passing. The PostgreSQL profile still reports `graph_unavailable`; D171 therefore qualifies only the existing SQLite graph path and does not close the PostgreSQL adapter gap or any release gate.

D172 passed the filtered Catalog journey (`1/1`) with Ronin on real PostgreSQL. It produced `4/4` correlated API events, all OK, with no skips or failures and cleanup passing. This confirms the environment/binding composition change did not regress PostgreSQL Catalog; it remains bounded evidence only.

D173 passed the filtered FinOps journey (`1/1`) on its configured SQLite runtime, with `3/3` correlated API events, all OK, and cleanup passing. PostgreSQL FinOps remains unconfigured, so this is local bounded evidence only and does not change P11, P13 or release status.

D174 passed the filtered Workflows journey (`1/1`) with Ronin and scheduler on real PostgreSQL. It produced `29/29` correlated API events (`28 OK`, `1` expected WARN), with no skips or failures and cleanup passing. This strengthens bounded scheduler/runtime evidence after the environment/binding change, but does not qualify indefinite operation, HA or release readiness.

D176 passed the filtered Semantic Studio journey (`1/1`) on its configured SQLite runtime, with `9/9` correlated API events, all OK, and cleanup passing. The runner is explicitly SQLite-only for this route; D175's PostgreSQL request timed out before startup and provides no PostgreSQL evidence. This remains bounded local evidence and does not change P11, P13 or release status.

D178 passed the single PostgreSQL Ingestion route case (`1/1`), with `4/4` correlated API events, all OK, and cleanup passing. The broader D177 selection included two explicit skips and is kept separate; D178 is bounded route evidence only and does not change P11, P13 or release status.

D180 passed the filtered Machine Learning Studio journey (`1/1`) on its configured SQLite runtime, with `38/38` correlated API events (`37 OK`, `1` expected WARN), no skips or failures and cleanup passing. The runner is explicitly SQLite-only for this route; D179's PostgreSQL request timed out before startup and provides no PostgreSQL evidence. This remains bounded local evidence.

D181 passed `1/1` bounded live single-operator authorization diagnostic with Ronin configured against real PostgreSQL/Kafka, with `10/10` correlated API events (`7 OK`, `3` expected WARN), zero server error/critical logs and cleanup passing. This is authorization evidence only and does not qualify a complete family, indefinite operation, HA/multi-worker, external-provider recovery or release gate. P11 remains **in_progress**, P13 **blocked** and release **NO-GO** (`1/13`, `0/10`).

D182 queda **NOT_PASS**: el caso live de Notebook Studio fue seleccionado pero explícitamente omitido (`1 skipped`), produjo `0` eventos API y el auditor no encontró `live-api-traffic.json`; el cleanup de PostgreSQL/Kafka pasó. No es evidencia de worker Docker ni de runtime PostgreSQL, y no cambia P11, P13 ni release.

D183 endurece el runner de cualificación: un diagnóstico omitido sin `live-api-traffic.json` conserva la evidencia vacía y expone el fallo contractual de API ausente, sin ocultarlo tras un error de lectura de archivo. La regresión afectada pasa `26/26`; D182 sigue siendo NOT_PASS.

D184 preparó una imagen Docker de worker para el seguimiento de Notebook, pero el filtro seleccionó `0/27` tests y no es cualificación. D185 sí pasó `1/1` journey live de Notebook Studio con worker Docker, PostgreSQL y Kafka reales: `20/20` eventos API correlacionados, todos OK, cero errores y cleanup PASS. Sigue siendo evidencia acotada; P11 permanece **in_progress**, P13 **blocked** y release **NO-GO** (`1/13`, `0/10`).

D186 intentó la campaña live completa con PostgreSQL, Kafka y worker Docker: **NOT_PASS**, `38/43` casos pasaron, `1` se omitió y `4` fallaron. Los `426/426` eventos API quedaron correlacionados (`399 OK`, `21 WARN`, `6 ERROR`). Persisten FinOps PostgreSQL no configurado, error interno del catálogo Synthetic, Graphs no configurado y supervisor soak con `8/15` ciclos. No cambia P11, P13 ni release.

D187 no ejecutó el supervisor soak: el modo streaming-only no inicia PostgreSQL, pero se solicitó `StorageBackend postgres` y el seeder agotó el timeout contra el DSN ausente. Kafka y cleanup pasaron; se registra como limitación del runner, no como evidencia del supervisor.

D188 corrigió esa limitación de modo y ejecutó el supervisor sobre PostgreSQL/Kafka reales: `19/19` eventos API correlacionados, todos OK y cero errores. Aun así queda **NOT_PASS** por `9` ciclos frente a los `15` exigidos; el criterio no se relajó.

D189 pasa el supervisor soak focalizado: `1/1` caso, `93/93` eventos API correlacionados, todos OK, cero errores y cleanup PASS. El caso limita cada ciclo HTTP a un micro-batch (`max_batches=1`) para que el criterio explícito de `15` ciclos mida realmente ciclos de supervisor; no se relajó el umbral. Es evidencia single-broker acotada.

D190 pasa `1/1` integración del conector S3 JSON contra Floci S3-compatible real, cubriendo sink put/read/retry round-trip, sin skips/fallos y con cleanup PASS. Es una celda de proveedor acotada; no cierra la matriz de providers ni cambia P11, P13 o release.

D191 pasa `1/1` integración del conector Azure Blob JSON contra Azurite real, cubriendo discovery, lectura y replay de snapshot, sin skips/fallos y con cleanup PASS. Es una celda de proveedor acotada; la matriz externa y los estados de release permanecen sin cambios.

D192 pasa `8/8` pruebas del conector HTTP JSON contra un servidor loopback real, cubriendo retry 503, rechazo de redirects, límites de bytes y paginación cross-origin, sin skips/fallos. El filtro Docker incorrecto seleccionó `0/27` y no se cuenta. Es evidencia bounded y no cambia P11, P13 o release.

D193 detecta un fallo nuevo: el preview HTTP JSON a través del control plane devuelve `500` contra un servicio paginado real, aunque el conector directo de D192 pasa `8/8`. Se registra como **NOT_PASS** y requiere corregir el wiring/contrato antes de repetir la cualificación.
The production implementation boundary is now
`e6f635dfe9159351711f44af9199e573e6e8a5bb`; D100 changes production replay
behavior and binds the full route, worker and companion evidence to that exact
candidate. Earlier D83–D99 receipts remain bound to their own documented
candidates and are not reattributed. The runner's one deliberate multi-broker
skip is covered by D100's separate RF3 diagnostic; the release ledger does not
close the release.

**D21 scheduler evidence update (2026-11-15):** exact candidate
`f667460650525a5d8a155cad1be5dcff2fc3fd14` passes the bounded local
API/SQLite/daemon journey and scheduler identity/event/backfill input-boundary
negatives (254 Python tests and 180 web tests pass).
This is not PostgreSQL, Docker-worker or external-provider qualification; P5
remains `in_progress`, the release ledger remains 1/13 families and 0/10
gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-f6674606-d21.json`.

**D22 catalog evidence update (2026-11-15):** exact candidate
`91a2d5efec61bd1776a302027eda2d6e00aeecd3` passes the bounded local
workspace-scoped catalog/revision journey (174 Python P6 tests and 7 web
catalog tests pass). It fixes the advertised GET revision route mismatch and
proves persistence, lineage, workspace isolation, restart recovery and
read-only authorization locally. `CatalogAsset.project_id` is persisted
metadata only; no independent project-level public filter or authorization
claim is demonstrated. P6 remains `in_progress`, the ledger remains 1/13
families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-91a2d5ef-d22.json`.

**D23 ontology/graph evidence update (2026-11-15):** exact candidate
`94911d26dcf90051fdfa7049d7ef4dd67a654272` passes the bounded local
workspace-scoped ontology/Knowledge Graph/RQL and scheduler graph selection
(234 Python tests and 7 web catalog tests pass). It fixes graph-id lookup and
action-replay scope by carrying `workspace_id` through persistence, adapters,
HTTP dispatch and scheduler graph queries; the real local journey proves
typed ontology persistence, same-id graph isolation, RQL, neighbors, unknown-
workspace denial and restart recovery. Graph actions are not mounted in the
local composition, `CatalogAsset.project_id` remains metadata only, and no
project-level catalog claim is made. P6 remains `in_progress`, the ledger
remains 1/13 families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-94911d26-d23.json`.

**D24 integrated catalog/ontology/graph evidence update (2026-11-15):** exact
candidate `870484a5b749b14a443d2bbf062c3ec10183ab31` passes the bounded local
SQLite/HTTP journey through direct HTTP, PyRonin, the public CLI and Graph
Studio. The journey reads a catalog asset and revision, a typed ontology bound
to that revision, bounded RQL, objects and neighbors; it proves same-id graph
workspace isolation, an unknown-workspace 403, invalid CLI key rejection and
restart recovery. The CLI now exposes catalog, ontology and graph read
operations; Graph Studio inherits active workspace context and can load the
catalog-bound ontology schema. Browser route fulfillment is UI contract
evidence only. Project-level catalog authorization/filtering, graph actions,
PostgreSQL/operator, Docker worker/provider and complete family qualification
remain open. P6 remains `in_progress`, the ledger is 1/13 families and 0/10
gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-870484a5-d24.json`.

**D25 quality evidence update (2026-11-15):** exact candidate
`2da767235dd633159e8e13dda73723bdef052cba` passes the bounded local
SQLite/HTTP quality journey through direct server behavior, PyRonin and the
new public CLI operations for contract get/put, run, history and state. The
journey pins a canonical contract digest, proves a passed result, records a
failed threshold without a false PASS, rejects malformed rows with 400,
preserves state/history after restart and denies an unknown workspace with 403.
Quality Studio now inherits the active workspace context. Candidate static
gates and clean-sandbox Gitleaks/pip-audit pass; candidate browser launch is
explicitly `SKIP` after Chromium timed out twice, while the checkout UI
contract passed 2/2. PostgreSQL/custom-rule providers, external alerts,
complete catalog/lineage quality integration and full P7 provider/consumer
qualification remain open. P7 remains `in_progress`, the ledger is 1/13
families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-2da76723-d25.json`.

**D26 alert/catalog evidence update (2026-11-15):** exact candidate
`9ca22d7b24e622203484d58707ec550b4c6cf9a4` passes the bounded local
SQLite/HTTP journey for alert rules, open instances, idempotent evaluation,
durable acknowledgement and catalog/lineage quality-state projections. The
public CLI exposes the alert operations, Catalog Studio renders bounded
passed/failed/error/unknown quality state, replay remains deterministic and
restart recovers quality history and alert state. Candidate static checks and
Gitleaks/pip-audit pass; candidate browser evidence is explicitly `SKIP`
because `@playwright/test` is not packaged in the exact archive, while the
checkout Catalog + Quality Studio contract passed 9/9. PostgreSQL/custom-rule
providers, external alert delivery, broader provider/consumer qualification and
complete P7 qualification remain open. P7 remains `in_progress`, the ledger is
1/13 families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-9ca22d7b-d26.json`.

**D27 ML evidence update (2026-11-15):** exact candidate
`f685a54b7b5f39cef3a9998480e2bc4dedd235b3` adds a real local HTTP/SQLite
journey through ML Lab creation, quality, durable `local.sklearn` training,
artifact-digest-verified registration, model-card/artifact retrieval,
prediction, unknown-workspace denial and restart recovery. The candidate
journey passes 1/1, the composed local suite passes 26/26, ML unit tests pass
298/298 and ML HTTP integration passes 3/3. Candidate static gates and clean
candidate Gitleaks/pip-audit pass; candidate browser evidence is explicitly
`SKIP` because `@playwright/test` is not packaged, while the checkout Catalog +
Quality Studio contract passes 9/9. PostgreSQL/S3/MLflow/serving providers,
broader algorithm/search performance and the complete P8 qualification remain
open. P8 remains `in_progress`, the ledger is 1/13 families and 0/10 gates,
and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-f685a54b-d27.json`.

**D28 ML lifecycle evidence update (2026-11-15):** exact candidate
`360ce3092afcf485c113ccfb781069914abc3ee0` adds the missing real local
HTTP/SQLite journey from model evaluation through promotion, digest-pinned
deployment, health, prediction telemetry, numeric drift reporting, rollback,
post-rollback rejection, workspace denial and full composition restart. The
D28 journey passes 1/1, the composed local suite passes 27/27, ML unit tests
pass 298/298 and ML HTTP integration passes 3/3. Candidate browser evidence is
explicitly `SKIP` because `@playwright/test` is not packaged; the checkout ML
Studio contract passes 9/9. Candidate static checks and clean Gitleaks/
pip-audit pass, while Trivy remains unavailable. PostgreSQL/S3/MLflow/external
serving providers, broader algorithm/search performance and complete P8
qualification remain open. P8 remains `in_progress`, the ledger is 1/13
families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-360ce309-d28.json`.

**D29 semantic evidence update (2026-11-15):** exact candidate
`567ee82eafd30661c5e6c10ea5fe26f3eaad6dce` adds the missing real local
HTTP/SQLite/DuckDB/Parquet journey from persisted semantic model/query through
dashboard execution, tile-budget rejection, semantic Bundle digest/plan/import,
workspace denial and full composition restart. The D29 journey passes 1/1, the
composed local suite passes 28/28, selected semantic unit/HTTP tests pass
36/36, ML unit tests pass 298/298 and ML HTTP integration passes 3/3. Candidate
browser evidence is explicitly `SKIP` because `@playwright/test` is not
packaged; the checkout Semantic Studio contract passes 6/6. Candidate static
checks and clean Gitleaks/pip-audit pass, while Trivy remains unavailable.
PostgreSQL semantic persistence/import, external warehouse/provider
compatibility, dashboard cancellation/fan-out evidence and complete P10
qualification remain open. P10 remains `in_progress`, the ledger is 1/13
families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-567ee82e-d29.json`.

**D30 semantic dashboard evidence update (2026-11-15):** exact candidate
`0c31232eaec42d2f26f8fbc466bd52d2898d09a5` fixes the public dashboard PUT
replacement bug by separating replacement from create/idempotent conflict
semantics in the SQLite store, HTTP adapter and control-plane protocol. Its
real local HTTP/SQLite/DuckDB/Parquet journey replaces an existing dashboard,
returns the independent filtered `ES=5` result, rejects an empty filter with
HTTP 400 and recovers after restart. The D30 journey passes 1/1, the composed
local suite passes 29/29, selected semantic unit/HTTP tests pass 36/36, ML
unit tests pass 298/298 and ML HTTP integration passes 3/3. Candidate browser
evidence is explicitly `SKIP` because `@playwright/test` is not packaged;
checkout Semantic Studio passes 6/6. Candidate static checks, clean
Gitleaks/pip-audit and final candidate reproducibility pass; Trivy remains
unavailable. PostgreSQL semantic persistence/import, external warehouse/
provider compatibility, dashboard cancellation/fan-out and complete P10
qualification remain open. P10 remains `in_progress`, the ledger is 1/13
families and 0/10 gates, and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-0c31232e-d30.json`.

**D31 streaming evidence update (2026-11-15):** exact candidate
`902ddc9acea2d8806ba7fab3538ec900a8effc37` binds the P11 streaming source,
runtime, health, Bundle, HTTP and Studio path to a clean candidate. A
streaming-only live runner started a real Redpanda broker, a real Ronin API and
Chromium; the case passed `1/1`, with `38/38` correlated API events, `34` `OK`,
`4` expected `WARN`, zero server/network errors and cleanup of the isolated
broker/network. The candidate Python streaming selection passes `44` tests and
the checkout Streaming Studio contract passes `3/3`,
while the browser inside the exact archive is explicitly `SKIP` because
`@playwright/test` is not packaged. PostgreSQL and the worker were not started
in this bounded profile. Continuous operation, broader partition/backpressure/
failure recovery, provider/operator breadth and complete P11 qualification
remain open. P11 is `in_progress`, the ledger is 1/13 families and 0/10 gates,
and release remains **NO-GO**. See
`docs/qualification/candidates/candidate-902ddc9a-d31.json`.

**Current worktree update (2026-10-30; dirty diagnostic candidate):** P3 now includes a project-authorized local DuckDB `POST .../sql/explain` route and a SQL Studio action. The route reuses project-read authorization, validates the shared read-only SELECT contract and registered relation scope, forwards a bounded execution deadline, incrementally caps serialized plan rows, and redacts paths, URLs and inline secret assignments. Providers without the optional capability return an explicit 501. Targeted verification is recorded in `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`; this does not qualify P3 or the release, and the historical notes below remain historical snapshots.

**Suite completa más reciente (30-10-2026):** Windows/Python 3.13/PostgreSQL 16.4: **4.404 passed, 24 skipped, 0 failed**; Linux/Python 3.11.18/PostgreSQL 16.4 en Docker: **4.412 passed, 16 skipped, 0 failed**, 4.428 casos JUnit; `tests/perf`: **3/3**. No hubo warnings de coverage/procesos hijos. El test positivo del sandbox ahora aísla los hooks `pytest-cov` del worker; los 47 tests focalizados de superficie/calidad/sandbox pasan en Linux y Windows. Ruff check/format y mypy del test modificado pasan. Los resultados son del worktree sucio basado en `f9a0456`, no de un candidato limpio; el ledger sigue en **0/13**. Véase §18 del plan fechado para diagnóstico, skips y expediente.

PR #552 merged at 19:41:11 UTC. Required PR checks passed; all six exact-head push workflows on the merge SHA passed (CI 40388942726, Docker 40388942459, Web 40388942544, Release 40388943097, Security 40388942691, Status consistency 40388942624). `mutation` and release publish/verdict jobs were skipped by policy and are not passes. The remote feature branch was deleted; local main is aligned with origin/main.

PR #553 merged at 01:20 UTC on 2026-10-27 as `main@993f519e02e611a951b258bb266979fa747e7bbf`. All required PR checks and all six exact-head post-merge workflows passed; `mutation` was skipped by policy. The branch was deleted after merge.

**SQL execution budgets integrated by PR #553:** the request contract now accepts bounded `timeout_ms` and `max_result_bytes`; DuckDB interrupts overdue queries and enforces result limits during fetch, while the HTTP adapter enforces the exact serialized payload cap. SQL Studio forms and OpenAPI expose/document both bounds and the route maps timeout/result-limit failures to 408/413. Focused SQL/API tests passed 85/85, Playwright passed 96 with 3 external-service skips, local Docker worker qualification passed 8/8 against a fresh PostgreSQL database, frozen v0.1 acceptance passed 16 with 3 Spark-configuration skips, and performance tests passed 3/3. The local whole-suite attempt had 4,111 passes, 22 skips and three documentation-sync failures; after correcting those ledgers, the affected tests passed 6/6. The whole suite was not rerun locally, but exact-head CI passed both Python versions and Docker qualification. These tests do not qualify P3 or the release. Explicit pagination/cancel/explain, governed assets, source-revision evidence, CPU bounds, engine-neutral semantics, and full SQL journeys remain open.

**Historical implementation candidate (now merged by PR #552):** `codex/postgres-catalog-support@5f2a3bbaba8f32446293b9d280f6fe2d1bc7bd74` added governed catalog pagination/search and a durable quality workflow across SQLite/PostgreSQL, API, Studio and observability. Its full local suite passed 4,097 tests with 24 environment/platform skips in 337.92s; Docker runtime/acceptance passed 23 tests and strict v0.1 acceptance passed 15/15 using a fresh PostgreSQL database. Coverage run also passed 4,097/24; it emitted 679 Python 3.13 `ResourceWarning` reports, which remain under investigation. Per-file storage ratchet baselines were raised to measured catalog and PostgreSQL-core coverage. This evidence is local and does not qualify a Public v1 family.

The follow-up `68519402` aligned HTTP adapter and DuckDB statement validation on the shared read-only `SELECT` subset; it is included in PR #552. Its focused SQL/API tests passed 26/26. This did not implement pagination, cancel, explain or source-revision evidence; RPV1-304 remains partial.

Commit `2109cbc9` wires the local-composed SQL Studio API to a project-scoped DuckDB engine, verifies the project exists before namespace creation, serializes typed query results, and closes the engine on server shutdown. SQL/composition/server/Parquet tests passed 46/46; the full Python suite with Docker PostgreSQL passed 4,104 tests with 24 environment/platform skips in 590.19s; `tests/perf` passed 3/3. PR #552 then fixed the no-DSN storage coverage gate to exclude PostgreSQL-only `postgres_quality.py` only in that lane; the full Docker lane still measures it. The final PR rerun passed Python 3.11/3.12, Docker/PostgreSQL, Web, Security, ledger and Release packaging; all six exact-head post-merge workflows also passed. Mutation and release publication/verdict jobs were skipped by policy. These results do not qualify P3 or the Public v1 release.

PR #547 restricts known OpenLineage facets to dataset entities. All six exact-head `push` workflows passed (links above); Docker workflow details and conditional skip are stated above. Five focused test commands on a clean worktree of this SHA passed: connectors/checkpoints/ingestion 54; Streaming Bundle 6; PostgreSQL Bundle 2 using PostgreSQL 16.4 in an ephemeral Docker container; OTLP exporter 5; and OTLP collector integration 1 using an ephemeral Docker collector. These 68 tests are local focused evidence only and do not replace the pre-merge 3,962-test result or qualify any of the 13 family gates.
**Release status:** **INCOMPLETE**.

**Scope amendment (2026-10-24):** No Ronin tier provides in-product GenAI/model invocation, RAG, or agent execution. Ronin coding-agent skills are external instructions consumed outside the product. Multi-user identity, user/group administration and multi-user deployment belong to Ronin Pro. Dated evidence notes below preserve their original scope context; the current release denominator excludes GenAI and Pro capabilities.

**Verified release progress:** **0% (0/13 active Public v1 capability families are
release-qualified).** A family counts only after its mandatory Public v1
journey and applicable provider, security and exact-head evidence are complete.
No active family is release-qualified; this is a release-completion metric, not a measure of
code already implemented. P9 is out of scope.

**Build-plan implementation progress:** **not calculable**. No reproducible weighted rubric currently maps partial implementation across the 13 active capability families to a global percentage. The earlier 14% estimate is retired; it must not be reported as current progress. GenAI and multi-user Pro capabilities do not count.

PR [#557](https://github.com/SauronShepherd/ronin/pull/557) integrated the QueryFlux SQL result-byte limit and OpenAPI route parity. All required PR checks passed; mutation was skipped by policy. Six post-merge exact-SHA workflows passed on the merge commit: CI 40444233807, Docker 40444233763, Web 40444233747, Release 40444233740, Security 40444233748 and Status consistency 40444233746. Local verification of this merge SHA passed **4,090 tests with 74 environment/platform skips** and performance tests **3/3**. This does not qualify P3 or any release family.

PR [#558](https://github.com/SauronShepherd/ronin/pull/558) binds QueryFlux execution to explicit workspace/project path scopes, authorizes the project resource and rejects cross-workspace project IDs before execution. Its HTTP integration case, focused route/API checks, local full suite (**4,091 passed, 74 skipped**) and performance suite (**3/3**) passed on the PR candidate. All required PR checks and all six exact-head post-merge workflows passed on `main@56e42c77f5dfc4bc60a3a0047f0a09fdfc112688`: CI 40446346828, Docker 40446346782, Web 40446346833, Release 40446347050, Security 40446346780 and Status consistency 40446346794. Docker qualification included real Docker runtime acceptance and PostgreSQL storage coverage. `mutation` remained skipped by policy. This closes an authorization gap but does not qualify P3 or any release family.

**QueryFlux pagination and SQL route follow-up integrated by PRs #560/#561:** PR #560 added immutable content-addressed result pages scoped to project/run/attempt, authorized page retrieval, durable SQLite/PostgreSQL references and Studio retrieval/export of loaded pages. It also reconciled `/v1/sql` timeout/result-byte enforcement and OpenAPI response/error shapes. PR #561 fixed the explicit empty-cursor edge case: `cursor=` now returns 400 instead of restarting at page one. Focused local evidence includes 82 SQL/QueryFlux tests, 7 HTTP SQL tests, a separate overlapping group of 48, 3 QueryFlux Playwright journeys and the corrected legacy SQL journey. The local web suite initially had one stale `dialect` expectation (98 passed, 3 skipped, 1 failed); after updating it, the affected journey and QueryFlux journeys passed. Mypy (429 files), Ruff, formatting (896 files), OpenAPI and diff checks passed. These separate local runs are not represented as one clean full-suite run. PR #560 and #561 required checks passed; all six exact-head push workflows passed on `main@cca60214044402867094335a2c999a50c3c7fda7` (CI 40452266063, Docker 40452265954, Web 40452266016, Release 40452265985, Security 40452265996, Status consistency 40452266002). The first PR #561 Docker evidence upload timed out after runtime/acceptance passed; its rerun passed and uploaded evidence. `mutation` was skipped by policy. P3 remains partial: durable cancellation, safe explain, governed assets/source revisions, CPU budgets, broader journeys and provider qualification remain open. Release remains 0/13; global implementation progress is not calculable; integral clean-review streak is 0/10.

This document records implementation state only. It does not claim test execution, legal review, human decisions, release qualification or operational evidence that does not exist.

### SQL typed scalar-binding candidate (2026-10-27)

The current candidate makes typed SQL scalar bindings explicit and consistent
across `DurableHTTPApplication.sql` and `SqlHTTPAdapter`: `null`, `boolean`,
signed 64-bit `integer`, finite `float`, and bounded `string`. Unknown fields,
unsupported types, type mismatches, non-finite floats, out-of-range integers,
more than 1,000 parameters, and strings over 512 KiB fail before engine execution.
Existing untagged JSON scalars remain accepted and are normalized to preserve
Public v1 client compatibility. OpenAPI and API compatibility documentation
describe both forms. Local focused tests cover the live HTTP route and DuckDB
binding behavior; remote engine parameter parity is still unqualified.

The current-code/API/ledger focused suites pass 61 tests. The whole local
Python run reported 4,072 passed, 72 skipped and one failure caused by the
OpenAPI hash becoming stale after the schema edit. The snapshot was updated and
the focused suite, including `test_openapi_snapshot`, passes; the whole suite
was not rerun after the final schema and string-limit refinement. Local Docker
qualification passed 21 tests and strict v0.1 acceptance 15/15; two PostgreSQL
worker tests skipped because no DSN was configured. That image was built before
the final schema/string-limit refinement and does not cover SQL bindings;
exact-head PR CI remains required.

This slice does not close RPV1-304/P3: pagination, durable cancellation,
explain, catalog-backed asset registration, source revisions in query evidence,
CPU budgets, engine-neutral provider semantics, complete journeys and provider
qualification remain open. Release progress remains **0/13 (0%, NO-GO)**;
global implementation progress is **not calculable**. Integral clean review
streak after this code change: **0/10**.

**Shared query-engine binding follow-up:** `QueryRequest` now enforces the
shared read-only `SELECT` grammar and carries normalized typed scalar values in
its canonical digest. The local transport binds parameters through DuckDB; the
Trino transport emits `EXECUTE IMMEDIATE ... USING`, with string values encoded
as UTF-8/base64 expressions. QueryFlux rejects execution unless its discovered
engine advertises `parameter_binding: true`. The durable query evidence retains
the request digest without persisting bound values. The current worktree passes
74 focused tests across DuckDB, Trino request construction, QueryFlux, capability
authorization and evidence, including a live Trino 484 Docker transport test
for string, int64, boolean, float and null bindings. This does not certify the
full QueryFlux/provider deployment; the dynamic QueryFlux route also lacks
static core OpenAPI coverage.
RPV1-304 and Public v1 remain partial; release is still **0/13 (0%, NO-GO)**,
and global implementation progress remains **not calculable**.

## Reading this snapshot

The source tree is the authority for implementation presence. The status ledger
is intentionally conservative: a capability is `partial` until its mandatory
Public v1 path is complete end to end. Historical CI/evidence files retain the
candidate SHA they were generated for and are not promoted to current-head
evidence. Older narrative entries that say `0/14` predate the 2026-10-24 scope
amendment; the current denominator is `0/13`.

## Exact-head qualification snapshot

On `main@1edb11a5123bf9ef3c29b7eb2d6d189cc459b8ea`, PR #451 fixes scheduler
dispatch to pass the exact digest-pinned PipelineIR into `execute_pipeline` and
rejects runners that cannot execute that definition. All six exact-head workflows
passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39390985070),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39390984778),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39390984964),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39390985032),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39390984768) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39390984813).
Docker qualification took 9m36s. P5 remains partial; release progress remains
0% (0/14).

On `main@6dc051ec18d8c54cb61bab37aba59a72f8dc843a`, PR #450 adds S3-compatible
artifact qualification to CI with LocalStack. The exact-head workflow set passed:
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39387588485),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39387588518),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39387588423),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39387588440),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39387588444) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39387588479).
Docker qualification took 9m27s. Product support remains partial; this is not a
production-vendor certification.

On `main@a5d6a246e67d9f7c7e656c2b56101d6c9f3e6866`, PR #443 adds workspace-scoped
registration of successful durable ML executions as candidate model versions after
rechecking artifact size and digest; PR #445 integrates the flow into Studio. PR #446
adds workspace-scoped artifact retrieval in digest-verified chunks capped at 512 KiB
and a chunked UI download. PR #447 fingerprints executable source, Python and ML
dependencies, backend, options and upstream outputs for checkpoint reuse and durable
result provenance; changed outputs invalidate downstream stages. Its CI and Docker
qualification passed. PR #448 adds promotion after successful execution registration;
79/79 local Playwright tests pass. All six post-merge exact-head checks for `a5d6a24`
passed, including [CI](https://github.com/SauronShepherd/ronin/actions/runs/39379910718),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39379910700),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39379910676),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39379910703),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39379910695) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39379910759).
On `main@c2df9035d9bdbd24b7dee4357d884807645e5048`, PR #449 adds selective retries
for failed durable ML executions from a selected pipeline stage. All six post-merge
exact-head workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39384556262),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39384556283),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39384556228),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39384556222),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39384556217) and
[Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39384556223).
PR [#441](https://github.com/SauronShepherd/ronin/pull/441) passed CI
Python 3.11/3.12, quality, security, verification, ledgers and [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39371246065)
(8m54s, including PostgreSQL-backed coverage, a real Docker worker and strict
frozen v0.1 acceptance). Public v1 remains incomplete; P8 is partial and release
progress remains 0% (0/14).

On `main@92165f5dbf23b6153c62b0150d4e74e300ac1dd8`, post-merge [CI](https://github.com/SauronShepherd/ronin/actions/runs/39367136040),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136035),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136031),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136019)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39367136046)
passed. [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39367136062)
also passed at 04:07:53Z. PR [#439](https://github.com/SauronShepherd/ronin/pull/439)
passed its exact-head Docker qualification in 8m40s, including PostgreSQL-backed
coverage, a real Docker worker and strict frozen v0.1 acceptance. Public v1 remains
incomplete and P8 remains partial.

On `main@18b2cdecc1380886edeba2a0ad16305be065fa43`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39309554646),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554163),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554116),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554392),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39309554126)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39309554432).
PR [#436](https://github.com/SauronShepherd/ronin/pull/436) passed exact-head
CI (Python 3.11/3.12), Docker qualification (**8m20s**), Web, Security, Release,
ledgers and verification. Post-merge Docker took **8m43s**, including PostgreSQL
coverage, a real Docker worker and strict frozen v0.1 acceptance. PipelineIR now
governs the supported six local stages, and durable checkpoints let re-execution
reuse successful stage outputs. Explicit per-node retry, downstream invalidation and
materialization remain incomplete. Public v1 remains incomplete and P8 remains
partial.

On `main@2d3f7d3b43d0b3b9268a57860e19e707a57a02e8`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39300808656),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808822),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808898),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808705),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39300808877)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39300808941).
PR [#434](https://github.com/SauronShepherd/ronin/pull/434) passed exact-head CI,
Docker qualification (8m50s), Web, Security and Release; Docker covered
PostgreSQL-backed storage, a real Docker worker and strict frozen v0.1
acceptance. Public v1 remains incomplete and P8 remains partial.

On `main@95d25d0e5fccebac66d5a52a814a6c4ad7036f82`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39295218270),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295221825),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218170),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218134),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39295218175)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39295218271).
Docker included PostgreSQL-backed storage coverage, real Docker workers and strict
frozen v0.1 acceptance. PR [#432](https://github.com/SauronShepherd/ronin/pull/432)
closed the inline row/column/byte-limit bypass and passed exact-head CI and Docker.
These checks qualify the merged changes; P8 and Public v1 remain incomplete.

On `main@43654932b573a8e84339095323ed8a424a21cb23`, all six post-merge
workflows passed: [CI](https://github.com/SauronShepherd/ronin/actions/runs/39287975345),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975304),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975253),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975331),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39287975149)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39287975583).
Docker included PostgreSQL-backed storage coverage, real Docker worker
qualification and strict frozen v0.1 acceptance. PR [#430](https://github.com/SauronShepherd/ronin/pull/430)
was squash-merged as `43654932b573a8e84339095323ed8a424a21cb23` after its exact-head
CI, Docker, Security, Release and Status consistency checks passed. These checks
qualify the merged change; they do not close P8 or any Public v1 release family.

On the prior `main@58876c2a759fdb2d6dd93ba354ca6b5ce75ffbff` snapshot
(2026-10-17), GitHub reported success for [CI](https://github.com/SauronShepherd/ronin/actions/runs/39029783787)
(Python 3.11/3.12), [Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783816),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783792),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783786),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39029783791)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39029783794).
Docker included PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance (15 passed, zero skips/failures/errors). CI's
`mutation` job was skipped; skipped is not pass. This is exact-head automation
evidence only. The Public v1 release remains **INCOMPLETE**, and product
qualification remains **blocked** by incomplete capability journeys and
external/human-owned evidence.

On the prior `main@41a2024fde3de508d29c2fc3f9960b611f075edd` snapshot,
GitHub reported success for CI, Docker, Web, Security, Release and Status
consistency. The prior `main@fa8cc731f4af11120328b25aa207cb39897503d5`
snapshot also passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39034134947),
[Docker qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134890),
[Web qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134789),
[Security qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034135001),
[Release qualification](https://github.com/SauronShepherd/ronin/actions/runs/39034134870)
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39034134902).
Docker passed PostgreSQL storage coverage, real container qualification, and
strict frozen v0.1 acceptance. PR #396's isolated dispatcher termination test
passed the scheduler/API suite (151 tests), Ruff, and local image qualification
(21 passed; strict acceptance 15/15). This candidate additionally implements
the first PostgreSQL run/task snapshot store; its real PostgreSQL Docker
integration passed 3/3 with 95% adapter coverage, plus Ruff, architecture and
mypy. Standard CI excludes this PostgreSQL-only module from its no-service
coverage gate; Docker runs the full per-file coverage gate against PostgreSQL.
The snapshot store
does not implement dispatch, fencing, events, backfills or task evidence, and
does not exercise daemon shutdown/restart or close the broader Public v1 paths.

The prior `main@46f98056b9c501a374fe0f33a1548110f3cbf17f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39035748927),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39035748910),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39035748905),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39035748879),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39035748917),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39035748936).
The merged PR #397 exact commit `b1b4574d336b1d16cd4b2975e0f996563a8042a1`
and PR #398 exact commit `53f4cc8d6c827e0caa6a8624dff3543d1d6dd4ed`
passed CI (Python 3.11/3.12), Docker, Web, Security, Release, Status
consistency, quality, dependencies and negative gates. Docker passed
PostgreSQL storage coverage, real container qualification, and strict frozen
v0.1 acceptance; `mutation` was skipped.

The prior `main@2a7d0c9ef697d3de131f04d0973b49bfb2e1c780` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39036976451),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39036976461),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39036976408),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39036976428),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39036976444),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39036976413).
The prior `main@e3ca935055968460ba4a0cc3063617c42383b45f` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39039830705),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39039830679),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39039830690),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39039830694),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39039830715),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39039830750).
The prior `main@586801468a6b1cdc0f28d72d0da585ceb3ca2fd1` passed
[CI](https://github.com/SauronShepherd/ronin/actions/runs/39041024109),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39041024090),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39041024085),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39041024151),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39041024086),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39041024136).
The prior `main@209991ab4b67a1d1cdb85057432e80bda1c2bfdd`, including the
squash merge of PR #401, passed [CI](https://github.com/SauronShepherd/ronin/actions/runs/39047807894),
[Docker](https://github.com/SauronShepherd/ronin/actions/runs/39047807872),
[Web](https://github.com/SauronShepherd/ronin/actions/runs/39047807911),
[Security](https://github.com/SauronShepherd/ronin/actions/runs/39047807769),
[Release](https://github.com/SauronShepherd/ronin/actions/runs/39047807778),
and [Status consistency](https://github.com/SauronShepherd/ronin/actions/runs/39047807882).
PR #402 added PostgreSQL task-attempt claims, lease heartbeat/fencing,
expiry reclaim/retry, terminal completion and resource-pool capacity. Its exact
head passed Python 3.11/3.12, PostgreSQL-backed storage coverage and Docker
qualification; `mutation` was skipped. The squash commit is
`main@0ccb5fdd68b8849f860c7ffe9ef2526e4ec9b3e4`; on `main@ef0d107`, exact-head
Status consistency and Security passed, with CI, Docker, Web and Release
running. PR #404 added the PostgreSQL schema-4 execution
outbox with lease-fenced writes, idempotent intent replay, expired-attempt
protection and terminal reconciliation; its required CI, Docker (7m45s),
`ledgers`, Security, dependencies and remaining checks passed. `mutation` was
skipped. PostgreSQL event delivery, backfills and task-evidence stores remain
incomplete, and the scheduler HTTP routes stay unavailable for that profile.
PostgreSQL snapshots, replay-safe branch decisions and generation-fenced
leadership persist in main. The real PostgreSQL integration passed 4 tests
with 87% leadership-adapter coverage, including repeat execution against the
same database. The local scheduler/workflow suite passed 115 tests. Ruff,
formatting, architecture, focused mypy for the adapter, and status generator
checks passed. The repository-wide mypy command reports three existing
unused-ignore errors in unrelated files. Standard CI
excludes PostgreSQL-only adapters from its no-service coverage gate; Docker
runs the full per-file coverage gate against PostgreSQL. PostgreSQL scheduler
HTTP routes remain unavailable until task execution state and the remaining
scheduler stores are qualified.

The audit for PR #401 found that a branch decision arriving after task completion
could overwrite the terminal task state. The fix rejects late decisions in both
SQLite and PostgreSQL under their transaction locks, increments SQLite
`row_version` for a persisted decision, and tests that a rejected update leaves
state and version unchanged. CI and Docker passed on code candidate
`a5ae71629589b5d722c4ba29c50492661fe94728`; Docker passed PostgreSQL storage
coverage, real container qualification, and strict v0.1 acceptance. The 0% release
progress remains unchanged because P5 and all other mandatory capability families
remain partial.

The PostgreSQL task-attempt implementation passed real PostgreSQL integration
in Docker: 14 focused tests passed and focused line coverage reached 81%.
PR #404 added the PostgreSQL execution intent outbox and terminal reconciliation.
PRs #406–#414 now provide PostgreSQL event delivery, backfills, task evidence,
schedule cursors/fires and the workflow/schedule HTTP adapter. Later PRs qualified
the combined daemon-crash→Docker-worker→terminal-reconciliation journey. P5 remains
partial because complete controller recovery, broad operator conformance and
notification-provider qualification remain incomplete.

The current workspace includes the implementation families listed in the
package inventory (`studio_ai_studio`, `studio_cloud`, `studio_data_engineering`,
`studio_migration`, `studio_ml`, `studio_streaming`, `studio_synthetic_data`,
and the shared runtime/storage/server packages). It also includes the current
ML, migration, Cloud Studio, PostgreSQL and synthetic-data contracts under
`docs/`; those documents describe implemented slices and remaining boundaries,
not Public v1 completion.

## Historical local verification (prior snapshot)

These local results were recorded against the prior source snapshot
`dfdb1045de2e997caa191ba81a8ec640c1dd04bd`, not the observed candidate above.
The full `python -m pytest -q` verification produced **2266 passed, 15 skipped**
with zero failures or errors. The skips are
environment-gated Docker/PostgreSQL/Spark/provider qualification checks, not
test failures.
The latest focused contract verification produced **144 passed**.
Additional evidence recorded for that snapshot includes Docker qualification
(21 historical CI checks plus 5 current real-Docker tests), real PostgreSQL integration (11 passed), the installed-wheel
browser smoke (no console/request/CSP failures), installed-wheel accessibility
(no violations at 320/768/1440 px), and four credential-free migration fixture
certifications. These checks do not constitute current-head or Public v1 release qualification.

That snapshot's local checks additionally passed Ruff format/lint across all 881
Python files, the public import smoke for 32 packages, 11 Data Engineering
async tests, and installed-wheel plus installed-sdist Studio Chromium and
accessibility qualification (zero console/request/CSP, axe, or layout failures).

Mutation evidence is retained as a historical, frozen record in
`docs/quality/MUTATION_CAMPAIGN_FINAL.md`. Recurring mutation qualification is
retired by product decision and is not a release or implementation blocker.
Current product readiness is determined by ordinary unit, integration, contract,
and end-to-end verification plus the capability matrix; temporary mutation
workspaces and generated reports are not release evidence.

## Status vocabulary

- **implemented** — the stated foundation/path exists in source and is not known here to require another feature to perform its narrow claimed role;
- **partial** — meaningful source implementation exists, but the mandatory Public v1 family lacks an end-to-end supported path;
- **missing** — no supported implementation path exists for the mandatory capability;
- **blocked** — work/evidence cannot be truthfully completed under a current external or maintainer-controlled prerequisite;
- **human decision** — a maintainer/product/security/legal decision must be made rather than invented by implementation;
- **qualification pending** — implementation exists but current exact-head execution/release evidence does not.

## Repository-grounded capability snapshot

| Capability | Status | Current source truth |
| --- | --- | --- |
| Durable execution foundation | implemented | Job/Run/Attempt, SQLite durability, leases/heartbeat/fencing/reclaim/resume, cancellation, evidence, local/container worker, HTTP/CLI/SDK foundation |
| Workspace/project/source control | partial | workspace/project persistence, authenticated create/read/update/archive workspace and project lifecycles with idempotency, audit and active-project filtering, project manifest, reproducible secret-free deployment manifest with canonical identity, Git identity, environment/deployment bindings, Studio and SDK journeys covering project creation, environment binding, Bundle export/archive, audited/idempotent governed pipeline execution and project-scoped permission inspection; full Public v1 APIs/UI remain. Multi-user membership belongs to Ronin Pro. |
| Connectors/ingestion | partial | connection/discovery/checkpoint contracts, governed local CSV/JSONL, bounded HTTP/PostgreSQL, S3-compatible including Apache Ozone, Azure Blob and JDBC profiles, public capability/plan/preview/checkpoint-health API, Studio actions and SDK parity; production driver qualification and broader incremental coverage remain |
| Lakehouse/SQL | partial | bounded Arrow/Parquet open-data and streaming publication paths, provider-neutral SQL/table contracts, optional local DuckDB engine with bounded relation lifecycle, shared query lifecycle adapter, provider-neutral query-engine contracts/discovery/local transport/Trino HTTP transport, QueryFlux discovery and QueryFlux-to-Trino lifecycle adapters, bounded project-scoped fail-closed read-only SQL HTTP adapter/route, and optional Iceberg/Delta adapters exist; external QueryFlux and remote/catalog qualification, full format features, and broader SQL service remain |
| Data Engineering Studio | partial | notebook/pipeline execution foundations, durable SQL editor revisions/history/bounded export, parameter schemas, pipeline revision comparison/archive, and an authenticated pipeline-revision-to-workflow-run creation route with deterministic idempotency exist; worker/evidence lineage, complete CRUD and complete Web Studio remain |
| Durable DAG scheduler | partial | durable snapshots/task runs, fenced attempts/retries/dependencies, deterministic task→Job planning, execution outbox/reconciliation, deployment-aware controller, timezone-aware durable cron, durable event inbox/delivery, cancellation, timeout enforcement, snapshot-safe bounded backfill, shared resource pools, generation-fenced leader authority, leader-guarded cron/event/backfill/controller services, bounded and continuous daemon orchestration, graceful SIGINT/SIGTERM daemon entrypoint with fenced lease release, group backfill cancellation, fail-closed conditional branches with idempotent persisted decisions/skipped task state, authenticated schedule/event-trigger APIs and Studio authoring, durable adapters for supported operators, optional notification dispatch and durable retry/error recording exist. PostgreSQL dispatch replay, real Docker notebook execution, worker crash/reclaim, and the combined daemon-crash→worker-Docker→terminal-reconciliation journey have focused qualification. Webhook requests reject non-public DNS answers and pin validated addresses through TLS. Broad scheduler/operator conformance, complete controller recovery and notification-provider qualification remain |
| Catalog/lineage | partial | governed asset CRUD/revisions, versioned sensitivity/ownership, glossary authoring, bounded search, lineage HTTP navigation, OpenLineage export/HTTP transport and selected-subgraph Bundle portability exist; event certification and complete asset integration remain |
| Ontology/KG | partial | object/property/link/action schema and persistence, instance materialization, link resolution, bounded graph queries and authorized actions exist; durable replay and public interfaces remain |
| Graph intelligence/RQL | partial | bounded read-only RQL SELECT filtering, one-hop typed traversal, and typed property joins over materialized KnowledgeGraph views exist; planning, provider execution and public API exposure remain |
| Data quality/contracts | partial | versioned definitions/results, all built-in checks, injected SQL/Python/referential checks, quality gates, scheduler release enforcement, quality-to-common-alert transition evaluation, authenticated contract read/replace and run/history/state APIs, pyronin SDK parity including contract authoring, and Quality Studio contract authoring, validation, dry-run, evidence/history and blocking-policy controls exist; provider qualification remains |
| AI/ML/MLOps | partial | experiment/run/model/evaluation provenance, deterministic tabular training, canonical Lab/pipeline digest pinning for scheduled ML runs, digest-verified inference, champion serving resolution, deterministic trial comparison, bounded numeric drift summaries, explicit feature-level threshold assessments, versioned feature definitions with dataset snapshots, workspace-scoped HTTP routes and pyronin SDK parity exist; broader feature engineering, algorithms, MLflow and network serving remain |
| GenAI/RAG/agent runtime | out of scope | No Ronin tier ships model/provider invocation, RAG, tools, or in-product agent runtime/API/Studio. Coding-agent skills are installed for external agent use only. |
| Semantic models/dashboards | partial | safe semantic contracts, canonical persistence, parameterized metric compiler, calculated metrics, SQL metric runtime, bounded declared-column two-model JOIN execution, dashboard CRUD/execution, workspace+project-scoped storage keys, Studio semantic Bundle export/plan/import API with digest-bound preview, project read/write permissions, audit, 700 KiB limit, SQLite atomic model+dashboard import, exact replay and conflict handling exist; an explicit SQLite migration tool rehomes legacy unscoped definitions into an operator-selected workspace with conflict-safe atomicity; dashboard fan-out/cancellation budget, PostgreSQL import and exact-head public API/Studio qualification remain |
| Streaming/real-time | partial | Kafka polling, durable CAS checkpoints, micro-batch processing, Parquet sinks, event-time windows, stream tables, scheduler integration, bounded health/lag and canonical stream-definition Bundles exist. Local execution caps records at 1 MiB and batches at 8 MiB. D32 adds a real two-partition Redpanda browser/API proof that drains 12 records in six 2-record batches with lag 6/6→0/0, and a checkpoint contract for monotonic partition expansion while retaining removal/regression rejection. Poison/oversized recovery remains covered; broader continuous operation, backpressure/failure recovery, provider and complete Bundle qualification remain |
| Observability/alerts/FinOps | partial | durable metrics/events, threshold alerts, SMTP/webhook notification adapters, durable delivery intents with retry/backoff, Prometheus export, instrumentation, usage pricing, actual-versus-estimated costs, non-ledger forecasts, anomaly hooks and budget gates exist; authenticated alert-rule/evaluation APIs, SDK parity, fail-closed alert operation validation and the Monitoring & Alerts Studio route are covered by static and Playwright smoke evidence; broader service adoption and production qualification remain |
| Security/authentication (single-operator) | partial | bearer auth, transport policy, fail-closed classification-aware policy actions, secret resolver ports, broad mutation audit and append-only audit foundation exist; external provider qualification and release evidence remain. OIDC, user/group administration and multi-user role management are Ronin Pro scope. |
| Local/Compose operations | partial | local/Compose foundation, PostgreSQL metadata healthcheck, PostgreSQL JobStore adapter wired to the server, single-node real-PostgreSQL lifecycle qualification, SQLite backup/restore with path-bound artifact-tree manifests, PostgreSQL dump verification, S3 artifact retry/corruption checks, Kubernetes Job adapter and recovery runbooks exist; Kubernetes/server deployment and multi-user Helm are not Public v1 profiles. Scheduler conformance and backup/restore qualification remain incomplete. |
| Ronin Bundle | partial | deterministic verified archive IO, project/connection/catalog/workflow/schedule/quality/ontology/semantic/stream-definition inventories, shared verified archive reading across importers, atomic SQLite/PostgreSQL workflow commits, atomic SQLite semantic model+dashboard imports, and explicit streaming checkpoint reset/resume bindings exist; durable import receipts/recovery, ML artifacts/data assets, broader PostgreSQL domain adapters, certification and public surfaces remain |
| Fabric migration | qualification pending | deterministic fixture discovery and fail-closed notebook-item translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Databricks migration | qualification pending | deterministic fixture discovery and fail-closed notebook-job translation with dependency/schedule mapping and CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Palantir Foundry data/Ontology migration | qualification pending | deterministic fixture discovery and fail-closed Python-function translation with CLI/report tests; AIP generative models, prompts, agents, tools and model/provider invocation are excluded; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Dataiku DSS migration | qualification pending | deterministic fixture discovery and fail-closed Python/SQL recipe translation with CLI/report tests; authenticated discovery, canonical import/export integration, provider compatibility and certification remain |
| Web Studio | partial | authenticated static Studio shell supports job/evidence/event workflows, project-scoped read-only SQL, project/environment/Bundle/governed-pipeline journeys, resource-scoped project permission inspection and a Monitoring & Alerts route; 77 Playwright route/accessibility/history/domain-journey checks pass; authoring editors, domain workflows and complete Public v1 journeys remain |
| Public v1 release qualification | blocked | CI is intentionally absent; latest dirty-worktree digest-pinned Alpine runtime/probe images use exact-version APK package locks and passed Trivy 0.76.1 across all severities with 0 vulnerabilities and 0 secrets; Docker qualification passed 23/23 and strict acceptance 15/15; live UI/API passed 30/30 with 102 real calls and 0 5xx; server logs recorded 1,348 INFO/OK, 4 expected WARN for invalid cron/credentials, and 0 ERROR. This supersedes Debian/VEX evidence. A clean candidate-bound evidence set, complete capability journeys, legal/product decisions and provider certification remain pending. |

## Public v1 source work merged in the current construction sequence

PRs **#242–#288** moved Public v1 from planning into source implementation. Scheduler foundations include deterministic task→Job identity/linking (#259), execution outbox/reconciliation (#260), deployment-aware controller (#262), cron/events (#263/#264), cancellation/timeouts (#265/#267), snapshot-safe backfill (#268), pools (#270), leader fencing (#271/#273), daemon orchestration (#274/#275), and group backfill cancellation (#276). Native Bundle portability added project semantic inventory/export (#278), project import planning (#279), runtime remapping plus atomic project/environment-binding commit (#280), connection round-trip with explicit secret-reference remapping (#282), deterministic dependency-ordered multi-object staging (#283), atomic project+connection commit (#285), explicit selected catalog subgraph export/planning (#287), and atomic catalog asset/revision/lineage commit (#288). PR #266 made Public v1 the active construction authority while preserving the historical v0.1 planning files verbatim.

These merges do **not** imply that their parent capability families are complete. Scheduler branching/skipped semantics, durable notification dispatch, public APIs/Studio authoring, and process/signal wiring now exist; the combined crash/replay/worker/reconciliation journey has focused evidence, while complete controller recovery and broader operator/provider qualification remain. PostgreSQL now persists workflow/task snapshots, branch decisions, leader fencing, task-attempt leases and execution intents with terminal reconciliation, durable event delivery, snapshot-safe backfills, and workspace-scoped task-evidence lookup. Scheduler HTTP routes remain unavailable on the PostgreSQL backend until full scheduler conformance is qualified. Bundle support now covers project, connection, workflow/schedule, quality contracts, ontology definitions, semantic models/dashboards, and an explicitly selected catalog subgraph. Ronin has no in-product GenAI capability; coding-agent skills are consumed externally. PostgreSQL has atomic commit adapters for project/connection, workflow/schedule, and selected catalog imports, but lacks adapters for several other domains and a cross-domain transaction/recovery coordinator. Semantic SQLite Bundle import now atomically commits models and dashboards with exact replay. Catalog export intentionally does not invent whole-catalog revision discovery because the current catalog port does not expose it.

## Invariants that remain mandatory

1. **Canonical identity:** semantic IDs use versioned canonical contracts; physical locators, credentials and ephemeral worker state do not silently enter logical identity.
2. **Durability:** logical retries do not duplicate Job/Run meaning; state transitions are persisted before dependent completion claims.
3. **Fencing:** stale workers/controllers cannot commit authoritative state after lease loss.
4. **Checkpoint safety:** ingestion/stream checkpoints advance only after governed output commit.
5. **Secrets:** portable state stores references only; resolution happens at an authorized execution/deployment edge.
6. **Storage portability:** SQLite remains a supported local adapter while production backends must preserve the same service semantics.
7. **Security:** authorization is typed and resource-scoped; unsupported constraints fail closed; UI never replaces server-side enforcement.
8. **Migration honesty:** every source object is classified as exact, translated, partial, passthrough, unsupported or manual-decision; nothing is silently dropped or upgraded semantically.
9. **Evidence honesty:** implementation presence is not CI/release qualification, and historical evidence is not current-head evidence.

## Human-decision / blocked work

- **License/NOTICE/attribution and release approval:** tooling may inventory facts; maintainers/legal review own conclusions.
- **Provider certifications:** real vendor qualification still needs authorized environments and credentials; fixture-only migration evidence is not certification.
- **#102:** the `coverage-release-gates` target enforces its explicit 90% floor on release and evidence modules. The previously summarized 11 gate modules passed their recorded thresholds; this branch adds `tools/bind_container_sbom.py` to that enforced list with **100% line and branch coverage**. Future evidence-decision modules must join the same floor.
- **#63:** current GitHub API evidence shows protected `main` with eight required checks, admin enforcement, no force pushes or deletion, and an active `v*` tag ruleset. Reconcile the open issue's checklist with this evidence before claiming the issue is fully satisfied.
- **#199, #57, #96, #202:** automated qualification is active and exact-head runs pass on the recorded candidate. The strict 15-step Docker/release gate for #96 landed in #389; keep the broader journey and product/provider/legal criteria open.
- **Mutation:** the campaign is permanently frozen and the score gate retired by product decision. Do not rerun; reopen only through a new explicit product decision and campaign plan.

## Updated critical path

1. Keep this ledger and the active construction plan synchronized with repository truth.
2. Broaden scheduler/operator conformance and qualify notification delivery in supported local/Compose profiles. The combined daemon→real PostgreSQL/Docker worker→terminal reconciliation journey now has exact-candidate Docker evidence. PostgreSQL event, backfill, task-evidence, dispatch replay, worker success and worker crash recovery also have focused evidence. Do not claim production HA.
3. Extend native Bundle support to the next executable canonical metadata family, preferring workflow/pipeline persistence if its canonical snapshot/store contracts preserve identity without deployment locators; then quality/ontology/ML as their contracts permit.
4. Complete store ports for remaining domains; then implement PostgreSQL adapters and an S3-compatible artifact store without changing logical references.
5. Implement the first open data path: Arrow/Parquet + reference open table profile + reference SQL engine, with catalog/lineage/quality hooks.
6. Complete remote connectors and safe incremental checkpoint execution.
7. Expand the Public v1 API and begin Web Studio against documented/generated clients.
8. Complete quality runtime, ontology/KG actions/query, RQL, ML, semantic/dashboard, streaming and observability/alerts/FinOps.
9. Keep multi-user identity, administration and Kubernetes multi-user deployment on the Ronin Pro roadmap.
10. Build the four vendor migration profiles only against executable canonical target capabilities and certify them with exhaustive migration reports.
11. Continue #102 coverage work: `coverage-release-gates` applies a 90% floor to the strict gate, exact-candidate aggregator, artifact identity, release evidence/emission, installed-artifact evidence, artifact/license qualification, SBOM generation, supply-chain evidence, container SBOM binding, and mutation-policy parser. The container binder currently has 100% line and branch coverage.
12. Maintain exact-candidate qualification; the strict Docker/release acceptance gate must pass on its exact candidate. Public v1 remains incomplete until every mandatory family has its supported end-to-end path and the human-owned evidence is approved.

### Reconciled after PRs #420–#421 (2026-10-18)

PR [#420](https://github.com/SauronShepherd/ronin/pull/420) added PostgreSQL-backed worker crash recovery after three durable checkpoints and the complete 30-second lease expiry. A replacement worker reused the three completed cells and executed the remaining two. The merge is `main@37d00eb3d02ad6f6d9e8dba923261c5536d08838`; all six workflows passed exact-head after merge. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) then qualified the combined daemon crash/replay, actual Docker notebook execution against the same PostgreSQL schema, and terminal workflow reconciliation. CI 3.11/3.12 and all required PR checks passed on `0e8becfe517a18e697ab72afe889c20a68d8f204`, including Docker qualification with PostgreSQL-backed coverage, real worker execution and strict acceptance in 8m46s. The squash is `main@a0faef17d4897377765deac8445a60def604fd49`; its exact-head post-merge workflows are being reconciled. P5 remains partial and verified release progress remains 0% (0/14).
PR [#420](https://github.com/SauronShepherd/ronin/pull/420) added PostgreSQL-backed worker crash recovery after three durable checkpoints and the complete 30-second lease expiry. A replacement worker reused the three completed cells and executed the remaining two. The merge is `main@37d00eb3d02ad6f6d9e8dba923261c5536d08838`; all six workflows passed exact-head after merge. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) then qualified the combined daemon crash/replay, actual Docker notebook execution against the same PostgreSQL schema, and terminal workflow reconciliation. CI 3.11/3.12 and all required PR checks passed on `0e8becfe517a18e697ab72afe889c20a68d8f204`, including Docker qualification with PostgreSQL-backed coverage, real worker execution and strict acceptance in 8m46s. The squash is `main@a0faef17d4897377765deac8445a60def604fd49`; all six exact-head post-merge workflows passed. P5 remains partial and verified release progress remains 0% (0/14).

PR #423 fixed the `quality.gate` contract-pinning gap: `contract_digest` is now bound to the canonical persisted `DataContract` and checked before evaluation or evidence recording. It merged as `35072ef4d1940842076814d34a240869ebf48065` after Docker and all remaining exact-head workflows passed. PR #424 closed the webhook DNS-to-private-network SSRF gap by pinning validated public addresses through TLS; Docker and all six exact-head post-merge workflows passed on `e4ddf182fca00a8861140fd1664590d027092b51`.

PR [#425](https://github.com/SauronShepherd/ronin/pull/425) merged the canonical pipeline/Lab digest pin for scheduled `ml.run` jobs as `main@0180e27ffd8171e27f5731b3397a3439ff90e916`; all six exact-head post-merge workflows passed. PR [#426](https://github.com/SauronShepherd/ronin/pull/426) then preserved terminal cancellation when the runner raises late, with deterministic queued/running tests, CI 3.11/3.12 and full Docker qualification; all six exact-head post-merge workflows passed on `main@0afa7db291eddcf0db0a3acc67372c9f55378ef4`. The current candidate reconciles Lab/v1 serialization, metadata, clustering and split semantics; it passes the broad ML suite locally and in Docker, plus a PostgreSQL 16 Lab round-trip. Durable coordinator/workspace fencing, broader Public v1 ML journeys and external qualification remain open.

PRs #522–#525 then added rollback on late PostgreSQL conflicts, a shared verified Bundle reader, and atomic/replayable SQLite semantic model/dashboard imports. PR [#526](https://github.com/SauronShepherd/ronin/pull/526) added portable streaming-definition Bundles with explicit connection/storage/runtime remaps and reset/resume checkpoint binding. Exact-head CI, Docker/PostgreSQL, Security, Release and status consistency passed; it merged as `main@70632ed148b4e433ae0fbf87220f6cb3370ab968`. The current reconciliation keeps release-qualified progress at 0% (0/13): no Public v1 capability family is closed.

## Reconciliación de PostgreSQL scheduler (2026-10-17)

Los PR #406 y #407 añadieron entrega durable de eventos y backfills PostgreSQL, respectivamente. #407 corrigió además la carrera de cancelación al crear workflows. El candidato `8edb47807fc4ce9db23067fd5a933c95d821a8c9` pasó CI 3.11/3.12 y Docker qualification; la integración local con PostgreSQL 16 pasó 10 pruebas del adaptador de backfills (88% de cobertura de ramas), más 27 pruebas SQLite/scheduler relacionadas. El merge actual es `main@418ab8be9604c12d84e2825ec2b925cf865d39b7`. En la observación de reconciliación, CI, Web, Security, Release y Status consistency exact-head de `main` pasaron; Docker qualification seguía en ejecución. Después, `read_task_evidence(workspace_id, attempt_id)` quedó implementado para resolver evidencia del Job asociado al intent durable con aislamiento por workspace, y la prueba de integración de outbox/evidencia/reconciliación pasó en PostgreSQL 16. Esta evidencia no cierra P5 ni cambia el progreso release-qualified de 0% (0/14): faltan recuperación end-to-end del dispatcher y conformance integral de operador/notificaciones.

### Estado reconciliado tras PR #411 (2026-10-17)

`main@39c83b4490328fc0be44a7f4e7f30c4870615491` integra el vínculo PostgreSQL workspace-scoped de workflow con proyecto y entorno (`WorkflowDeploymentBinding`) por medio de migración 6→7. El PR #410 pasó CI 3.11/3.12, Security, Release, Status consistency, Web y Docker (**7m15s**); su primer job Docker expuso una mejora del adaptador `postgres_core.py` hasta 37,61%, así que el ratchet se elevó de 32,00% a ese valor medido.

El PR #411 integra migraciones PostgreSQL 7→9 para solicitudes persistentes de timeout y estado cancelado de intentos. Las funciones compartidas consultan la autoridad de dispatch y las solicitudes PostgreSQL; la detección es repetible, el timeout se reconcilia a retry/fallo, y si el workflow está cancelándose, la finalización conserva el estado cancelado. CI 3.11/3.12 y Docker qualification pasaron; Docker completó la cobertura PostgreSQL, pruebas Docker reales y aceptación estricta en **7m25s**. La cobertura medida de `scheduler_timeout.py` llegó a 68,78%, por lo que su baseline subió a 66,70% manteniendo el ratchet de 2,1 puntos. El merge squash es `main@dacd3ffbecef029a77fdfa6ef09cc45bea232f2c`; CI, Docker (**6m57s**), Web, Security, Release y Status consistency exact-head también pasaron.

El PR [#412](https://github.com/SauronShepherd/ronin/pull/412) delega a PostgreSQL el cambio durable de workflow a `cancelling`, la cancelación de tareas sin intent, el retiro de intents aún no enviados y la reconciliación de Jobs cancelados. La autoridad de cancelación se persiste antes de esperar bloqueos de tareas. Sus 17 pruebas PostgreSQL pasaron en Docker/PostgreSQL 16 con 82% de cobertura del adaptador; CI 3.11/3.12 y Docker qualification completa (**8m14s**) también pasaron. El squash quedó en `main@897e04a3b6c4219d82ed70d13a126c27a97cff4c`; CI, Docker, Web, Security, Release y Status consistency exact-head de main pasaron.

El PR [#414](https://github.com/SauronShepherd/ronin/pull/414) añadió migración PostgreSQL 9→10 con cursores monotónicos y ledger idempotente de schedule fires, implementación del contrato HTTP completo y montaje condicionado de rutas workflow/schedule en Compose. PostgreSQL 16 en Docker pasó **19 pruebas**, incluida una ruta HTTP real, y el módulo nuevo obtuvo 100% de cobertura de líneas y ramas. El PR pasó CI 3.11/3.12 y Docker qualification (**7m54s**); quedó integrado en `main@98e79db96ef45cfca6c3678c59475d5f74d024b6`. CI, Docker, Web, Security, Release y Status consistency exact-head de esa base pasaron. Las rutas generales workflow/schedule están disponibles cuando el backend expone todas las operaciones del contrato.

El PR [#415](https://github.com/SauronShepherd/ronin/pull/415) añadió takeover del `SchedulerDaemon` sobre stores PostgreSQL aislados: tras expirar el lease anterior, la instancia nueva adquiere generación 2 y vuelve a leer el cursor/fire persistente sin duplicarlo. PostgreSQL 16 en Docker pasó **20 tests** del módulo completo y CI 3.11/3.12 más Docker qualification (**6m37s**) pasaron antes del merge `main@2abc6ac3495ae3aa61a406f6f8c5be3e3478b796`. También pasaron todos los workflows exact-head post-merge: CI, Docker, Web, Security, Release y Status consistency. El test cubre takeover/replay de schedule, no recovery del controller.

El PR [#416](https://github.com/SauronShepherd/ronin/pull/416) mueve la entrega síncrona de notificaciones fuera del event loop y renueva el lease durante proveedores lentos. La regresión confirma que un contender no obtiene liderazgo mientras el dispatcher excede el lease inicial. Daemon + PostgreSQL 16 en Docker pasaron **29 tests**, con Ruff, formato y mypy. El squash `main@3b7e9aca15c94d247af2ac459b606e83c2699581` pasó CI 3.11/3.12, Docker qualification (**7m56s**) y todos los workflows exact-head post-merge. No se han cualificado endpoints SMTP/HTTPS reales.

El PR [#417](https://github.com/SauronShepherd/ronin/pull/417) termina un proceso real del `SchedulerDaemon` después de que su Job quede confirmado en PostgreSQL y antes de responder a la llamada dispatch. La instancia reiniciada recupera generación 2, reproduce la intención idempotente y verifica un Job/intent únicos. El módulo PostgreSQL más los tests del daemon pasó localmente en Docker/PostgreSQL 16 (**30 tests**); el candidato pasó CI 3.11/3.12 y Docker qualification (**8m03s**). El merge es `main@c2329b0e46c9a67636f20a5c70c8ba87f65af0ca`; todos los checks post-merge exact-head (CI, Docker, Web, Security, Release y Status consistency) están verdes.

El PR [#418](https://github.com/SauronShepherd/ronin/pull/418) continúa el caso de crash hasta completar el Job persistido desde un worker y reconciliar task/workflow a `succeeded` en el siguiente ciclo del daemon. El módulo PostgreSQL más los tests del daemon pasó localmente con Docker/PostgreSQL 16 (**30 tests**); CI 3.11/3.12 y Docker qualification (**8m13s**) pasaron en el PR. El merge es `main@90bbeb3ed1dd95ff3091a324408895a8836340c1`; CI, Docker, Web, Security, Release y Status consistency exact-head post-merge están verdes.

El PR [#419](https://github.com/SauronShepherd/ronin/pull/419) añadió ejecución de notebook en contenedores Docker reales con Jobs/checkpoints/eventos persistidos en PostgreSQL. La qualification usa una base PostgreSQL dedicada y verifica cinco celdas, estado terminal, checkpoints, evento único y resultados. El módulo worker real pasó localmente (**3 tests**, 67.83s); CI 3.11/3.12 y Docker qualification (**8m11s**) pasaron. El squash es `main@f067affb09d5db74013e66544d16fc2f1423c90a`; todos los checks exact-head post-merge están verdes.

El PR [#420](https://github.com/SauronShepherd/ronin/pull/420) añadió la terminación forzada de un worker PostgreSQL real tras tres checkpoints, espera del lease de 30 segundos y recuperación en proceso sustituto. Reutilizó las tres celdas y ejecutó las dos restantes; Job y evento terminal quedaron persistidos sin duplicados. Los cuatro tests de `tests/integration/test_worker_runtime_real.py` pasaron localmente en Docker/PostgreSQL 16 (**4/4**, 102.57s); CI 3.11/3.12, Docker qualification y los seis workflows exact-head post-merge también pasaron. PR [#421](https://github.com/SauronShepherd/ronin/pull/421) luego integró el journey completo daemon→worker Docker→reconciliación, cuyos checks PR también pasaron. No se cualifican proveedores externos ni operator general/HA; P5 continúa parcial y release-qualified en **0% (0/14)**.


## Current diagnostic validation — 2026-10-30

On dirty branch 20261029 at base f9a0456ab7df3e2bb77247d54b4336fca64903b0, the Windows/Python 3.13/PostgreSQL 16.4 full suite passed **4,404 passed, 24 skipped, 0 failed** (4,428 JUnit cases). The later Linux/Python 3.11.18/PostgreSQL 16.4 full suite passed **4,412 passed, 16 skipped, 0 failed** (4,428 JUnit cases); details and evidence are in §18 of the build plan. Docker qualification passed (**23/23**) and strict v0.1 acceptance passed (**15/15**).

These are diagnostic worktree results, not clean-candidate evidence. The release ledger remains **0/13 families qualified (0%) — NO-GO**. Version 0.0.0, human license/NOTICE and claim approvals, complete family journeys on one clean SHA, and manual visual review remain open. No CI, integrated GenAI, or Public multi-user support was added.

The license qualification gate exposed 21 packages without a current human review and one stale `pyyaml==6.0.3` entry. Its CLI now prints the exact missing/stale keys without a traceback; 103 focused tests plus Ruff, format, and mypy passed. The gate remains failed pending human license/NOTICE decisions.

The first full Python/PostgreSQL rerun after that harness change passed **4,353 tests, 24 skipped, 1 failed**: a Hypothesis slow-generation health check. A second rerun exposed the same non-deterministic health check in another bounded property. Both properties now keep 100 examples; the first bounds generated text to 32 characters while retaining Unicode, and the second suppresses only `HealthCheck.too_slow`. The timed-out quality sandbox test removes pytest-cov hooks from its intentionally terminated multiprocessing child.

The earlier pre-binder rerun recorded in section 16 passed **4,354 tests, 24 skipped, 0 failed** in 807.37 seconds against PostgreSQL 16.4. Its 4,378 JUnit cases match the pytest summary; no coverage warning or secondary .coverage.* file remained, and the temporary PostgreSQL container was removed. The later rerun after the container SBOM boundary tests is recorded in section 17. Evidence remains diagnostic for a dirty worktree, not a clean release candidate. Public v1 remains **NO-GO, 0/13 families qualified** while version, human license/NOTICE and claims decisions, complete candidate-bound journeys, and manual visual review remain open.

Version review: `PUBLIC_V1_SCOPE.md` explicitly calls the existing `0.1.0a*` line an engineering alpha/foundation milestone and does not select the final package version. Do not treat `0.1.0` or `1.0.0` as approved by inference; `ronin-studio 0.0.0` and `pyronin 0.0.1a0` remain diagnostic metadata until the product version is decided.

Supply-chain follow-up: `tools/bind_container_sbom.py` now binds Trivy CycloneDX 1.7 package inventories to exact runtime/probe image TARs and artifact identity; `tools/supply_chain_evidence.py --require-container-inventory` rechecks each full inventory and requires both images. The 123 focused supply-chain tests pass, and the binder has **100% line and branch coverage**. A diagnostic integration using actual Trivy 0.76.1 runtime/probe TARs passed. The final Windows/Python 3.13/PostgreSQL 16.4 rerun passed **4,404 tests, skipped 24, failed 0** (4,428 JUnit cases) in 659.30 seconds; `tests/perf` passed **3/3**. The later Linux/Python 3.11.18/PostgreSQL 16.4 rerun passed **4,412 tests, skipped 16, failed 0** (4,428 JUnit cases) in 730.15 seconds; its separate `tests/perf` run passed **3/3**. The Linux result is recorded in §18 of PLAN_FINAL_RONIN_RELEASE_2026-11-03.md. The 15-module `coverage-release-gates` report passed its 90% floor (95% total). No `CoverageWarning` or secondary `.coverage.*` file remained, and the ephemeral PostgreSQL container was removed. Both runs are dirty-worktree diagnostics, not a release candidate. Release remains **NO-GO, 0/13**; ten clean iterations, clean-candidate qualification, visual review, and human decisions remain open.

## Latest full Python and web rerun — 2026-10-30

After the Quality gate and ML registration fixes, the full Windows/Python 3.13.15 suite with isolated PostgreSQL 16.4 completed with **4,406 passed, 24 skipped, and 0 failed** (4,430 JUnit cases). The complete static Playwright suite reported **100 passed and 31 skipped**; those cases require API-backed live services. The separate Docker-backed Ronin live matrix passed **31/31**, exercised **130 real API calls** with no 5xx responses, and recorded 1,415 INFO, 8 expected WARNING, and 0 ERROR server events. The ML live journey completed training and durable model registration successfully; the full focused ML suite passed 67/67.

Evidence is diagnostic on dirty branch `20261029` at `f9a0456ab7df3e2bb77247d54b4336fca64903b0`, not a clean release candidate. Cold synchronous ML search took 73 seconds and remains an open P8 performance issue. Skips are not counted as passes. Release remains **NO-GO, 0/13**; clean-candidate gates, the full family journeys, manual visual review, and human version/license/NOTICE/claims decisions remain outstanding. No CI, integrated GenAI, or Public multi-user capability was added.

## Latest diagnostic rerun after ML operator evaluation — 2026-10-30

The live ML lifecycle now records an explicit operator evaluation (`passed`,
`failed`, or `unknown`) against the immutable source-run dataset and metrics.
Promotion is blocked until an evaluation is `passed`; cards expose the bounded
review history, and SQLite/PostgreSQL enforce idempotent writes and a 100-review
limit. OpenAPI and its digest were updated.

Windows/Python 3.13.15 with PostgreSQL 16.4: **4,408 passed, 24 skipped, 0
failed**; `tests/perf`: **3/3**. Static Playwright: **101 passed, 31 skipped**.
Docker worker/acceptance: **23/23**, strict acceptance **15/15**. The final real
API/Chromium matrix: **31/31**, all **25 active routes**, **143 API calls**, 0
5xx/network errors, 0 unexpected authorization gaps; expected WARN responses
were 1×400, 5×401, 1×403 and 2×409. Detailed transcripts and artifact paths are
in §24 of `PLAN_FINAL_RONIN_RELEASE_2026-11-03.md`.

The latest ML search still takes about **78 seconds** cold; P8 remains open. All
results are dirty-worktree diagnostics at `f9a0456ab7df3e2bb77247d54b4336fca64903b0`.
Release remains **NO-GO, 0/13 families release-qualified** pending a clean
candidate and complete journeys, human version/license/NOTICE/claims decisions,
manual visual approval, and supported-platform runs. No CI, integrated GenAI,
or Public multi-user support was added.

## Qualification follow-up — 2026-11-18 (D202)

D202 pasa `2/2` pruebas del Bundle PostgreSQL real: commit multiobjeto atómico, replay idempotente y rollback ante conflicto de binding tardío. PostgreSQL 16.4 y cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D202.json`; handoff: `docs/qualification/handoffs/2026-11-18-D202.md`.

## Qualification follow-up — 2026-11-18 (D201)

D201 pasa `2/2` pruebas del JobStore PostgreSQL real: ciclo completo de job/run, claim y actualizaciones, listados durables con filtros y paginación keyset. PostgreSQL 16.4 y cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D201.json`; handoff: `docs/qualification/handoffs/2026-11-18-D201.md`.

## Qualification follow-up — 2026-11-18 (D200)

D200 pasa `12/12` pruebas ML PostgreSQL sobre un contenedor 16.4 real: registry y conflictos, bundles atómicos/concurrent/replayable, rollbacks, checkpoints tras reopen, Lab v1 y fencing de jobs/cancelación. Cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D200.json`; handoff: `docs/qualification/handoffs/2026-11-18-D200.md`.

## Qualification follow-up — 2026-11-18 (D199)

D199 pasa `3/3` pruebas PostgreSQL de la barrera de retención de artefactos: lease bounded del collector, ordenación writer/collector, espera hasta commit de referencia y fencing de nuevos writers. PostgreSQL 16.4 real y cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D199.json`; handoff: `docs/qualification/handoffs/2026-11-18-D199.md`.

## Qualification follow-up — 2026-11-18 (D198)

D198 pasa `3/3` pruebas PostgreSQL de checkpoints de ingestión sobre un contenedor 16.4 real: avance scoped, fencing/inventory/restart y montaje del conector compartido en la composición local. Cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D198.json`; handoff: `docs/qualification/handoffs/2026-11-18-D198.md`.

## Qualification follow-up — 2026-11-18 (D197)

D197 pasa `1/1` del round-trip durable de input/output ML y retención sobre Floci 2.1.0 real: lectura posterior ligada a digest, recolección del artefacto no referenciado y conservación de los artefactos vivos. El runner limpió imagen, compose, volumen y contenedor. Floci es evidencia S3-compatible local, no certificación AWS/proveedor externo. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Receipt: `docs/qualification/daily/2026-11-18-D197.json`; handoff: `docs/qualification/handoffs/2026-11-18-D197.md`.

## Qualification follow-up — 2026-11-18 (D196)

D196 pasa `1/1` del journey real de control plane PostgreSQL: creación autenticada de conexión, discovery, rechazo de `page_size` booleano, preview de tres filas y preview tras reabrir la composición. PostgreSQL 16.4 y `RONIN_POSTGRES_TEST_DSN` fueron realmente configurados; cleanup PASS. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia bounded y no cambia P11, P13 ni release. Receipt: `docs/qualification/daily/2026-11-18-D196.json`; handoff: `docs/qualification/handoffs/2026-11-18-D196.md`.

## Qualification follow-up — 2026-11-18 (D195)

D195 pasa `21/21` de `tests/integration/test_postgres_workflow_store_real.py` con PostgreSQL 16.4 real y `RONIN_POSTGRES_TEST_DSN` inyectado por el runner. La selección cubre recovery del daemon tras lease expirado sin duplicate fire y replay tras process crash sin duplicate job, además de fencing, outbox, liderazgo por generación, backfill/reopen, migraciones, snapshots e integración HTTP. El cleanup del contenedor pasó. No hubo cambios de producción; la frontera sigue siendo `e6f635dfe9159351711f44af9199e573e6e8a5bb`. Es evidencia PostgreSQL bounded, no cierre de P11 ni de release. Receipt: `docs/qualification/daily/2026-11-18-D195.json`; handoff: `docs/qualification/handoffs/2026-11-18-D195.md`.

## Qualification follow-up — 2026-11-18 (D194)

D194 pasa la integración real del preview HTTP JSON del control plane: `1/1`, repetida `5/5`, contra un servicio loopback paginado. La evidencia cubre creación autenticada de la conexión, páginas 1/2/3, filas Ada/Grace, checkpoint vacío y cleanup. Está ligada al candidato `6079a1c9cfcaac55e0ddfa7e004c813664fc3d8e`; no es cualificación PostgreSQL ni de proveedor externo. D193 permanece registrado como `NOT_PASS` y no se reatribuye. P11 continúa `in_progress`, P13 `blocked` y release `NO-GO` (`1/13`, `0/10`). Receipt: `docs/qualification/daily/2026-11-18-D194.json`; handoff: `docs/qualification/handoffs/2026-11-18-D194.md`.

## Full diagnostic rerun — 2026-10-30

The dirty-worktree Python/PostgreSQL suite passed **4,408**, skipped **24**,
failed **0** (4,432 JUnit cases); `tests/perf` passed **3/3**. Docker worker
qualification passed **23/23**, with strict v0.1 acceptance **15/15**. Static
Playwright passed **101** and skipped **31** live-only cases. A separate live
Chromium/API run passed **31/31**, covered **25/25** routes and made **146 real
API calls** with no 5xx, network errors, or unexpected authorization gaps.
Server logs contained **1,430 INFO/OK**, **9 expected WARN**, **0 ERROR**. All
temporary Docker services were removed. Evidence is under the three
`%TEMP%\ronin-*-full-continuation-20261030` directories referenced in section
26 of the build plan.

ML search remains a P8 performance blocker: the live run completed, but its
38.33-second cold search spent 38.23 seconds in the first trial. Release remains
**NO-GO, 0/13 qualified**; human version/license/NOTICE/claims and visual
approvals, clean-candidate journeys, platform qualification, and ten clean
iterations remain open.

## Follow-up — 2026-10-30

The isolated live ML search completed **1/1** with 36 real API calls. Safe phase
timing shows a **37.38 s** cold search, almost entirely in its first trial; P8
remains open. The live runner now compiles third-party bytecode during setup,
but this did not establish an acceptable search time. The Studio budget was
reviewed for the added SQL explain and ML evaluation-review interactions and
ratcheted to the measured **1,943,645 bytes**; asset/module counts are unchanged.
The size gate and 60-file Studio web audit pass. Focused ML and qualification
contract modules pass **45/45** sequentially; an earlier concurrent run had one
30-second test timeout, which passed in isolation and on the sequential rerun.

These results remain dirty-worktree diagnostics. Public v1 remains **NO-GO,
0/13 release-qualified** pending P8, clean-candidate family journeys, human
release decisions, and manual visual review. Ten clean iterations are not
complete.

## Empaquetado reproducible — 2026-10-31

Dos compilaciones del mismo árbol diagnóstico, con `SOURCE_DATE_EPOCH` fijado,
produjeron wheel y sdist byte a byte idénticos. SHA-256: wheel
`0230ed664aa32e89902d2a581993be840b96e9eeb775f94664b7cda6bb10ef4e` y sdist
`8dec5b0785c53429f95f4acb8b942e32d329a44d932fa883bb88f4d5653b2b04`. Evidencia
en `%TEMP%\ronin-artifacts-repro-20261031`; los artefactos son `0.0.0` y no
califican como release. El plan §27 registra el alcance de este resultado.

El estado sigue **NO-GO, 0/13 (0%)**: P8, decisiones humanas de versión,
licencias/NOTICE y claims, revisión visual manual, candidate SHA limpio,
qualification completa por familia y matriz de plataformas están pendientes.

