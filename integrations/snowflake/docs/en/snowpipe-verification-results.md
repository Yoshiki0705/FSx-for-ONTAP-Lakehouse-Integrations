🌐 **English** | [日本語](../ja/snowpipe-verification-results.md)

# Snowpipe + FSx for ONTAP S3 Access Point — Verification Results

**Measured**: 2026-08-05 (AWS side, ListObjectsV2) and 2026-08-06 (Snowflake side) | **Region**: ap-northeast-1

This document records what has actually been measured about ingesting data into
Snowflake from an FSx for ONTAP S3 Access Point, and — equally important — what
has not. It exists because several figures previously quoted in this repository
carried no evidence record, and one of them turned out not to be reproducible.

Raw evidence:

- [ListObjectsV2 latency, 2026-08-05](../../../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml)
- [Pattern A, AWS side, 2026-08-05](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-05/aws-side-verification.yaml)
- [Pattern A, Snowflake side, 2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml)

---

## Executive Summary

**Snowpipe cannot be scheduled.** Snowpipe is event-driven by design; there is no
"run Snowpipe every 5 minutes" option. Scheduled ingestion from an FSx for ONTAP
S3 Access Point is done with a **Snowflake Task running COPY INTO**, which is a
different feature.

Event-driven ingestion *is* now verified working end to end, using a synthesized
notification. It requires four conditions to hold simultaneously, and it has a
failure mode that produces no error anywhere.

| Ingestion path | Status | Evidence |
|---|:---:|---|
| Snowpipe auto-ingest driven by **real** S3 events | ❌ Not possible | FSx for ONTAP S3 AP does not emit S3 Event Notifications ([BLK-003](../../../../docs/en/blocker-tracker.md)) |
| Snowpipe auto-ingest driven by a **synthesized** notification | ✅ **Verified** | [2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml), test_08 — COPY_HISTORY attributes the load to the pipe |
| **Task + COPY INTO (scheduled)** | ✅ **Verified** | [2026-08-06](../../../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml), test_04 |
| Task + `ALTER EXTERNAL TABLE ... REFRESH` | ✅ Verified | External Table read verified 2026-05-24 |
| Pattern A: Lambda polling → SNS → Snowpipe | ✅ Verified, with conditions | Both halves now have evidence; see the two Pattern A sections below |
| Pattern B: FPolicy → Lambda → SNS → Snowpipe | ⚠️ Design only | The Snowflake leg is identical to Pattern A and is verified; the FPolicy event source itself has no live verification |
| Snowpipe REST API (`insertFiles`) | ⚠️ Not verified | Documented as an option only |

**Which to choose.** For scheduled ingestion, Task + COPY INTO remains the
simpler choice: no synthesized notification, no SNS topic policy to maintain, and
Snowflake's own load history gives exactly-once behaviour that a polling window
cannot. Choose the Snowpipe path when detection latency matters more than
operational simplicity — a synthesized notification reached a loaded row in about
half a second, versus (schedule interval) for a Task.

> **Silent failure warning**: if `s3.bucket.name` in the synthesized notification
> does not match the bucket string in the stage URL, Snowpipe accepts the message
> and then discards it. No error appears in `SYSTEM$PIPE_STATUS`, none in
> `COPY_HISTORY`. A pipe in this state looks perfectly healthy while loading
> nothing. Any monitoring for this path must compare object counts on the Access
> Point against rows loaded in Snowflake, not merely watch for pipe errors.

---

## Correction: the "30-80x slower ListObjectsV2" figure

This repository previously stated in about a dozen places that ListObjectsV2
against an FSx for ONTAP S3 Access Point is **30-80x slower** than native S3.
That figure was re-measured and **could not be reproduced**.

Measured medians, five recorded trials per data point, one discarded warm-up
call, timing scoped to the paginated ListObjectsV2 loop only:

| Objects | FSx for ONTAP S3 AP | Native S3 | Ratio |
|--------:|--------------------:|----------:|------:|
| 10 | 38 ms | 27 ms | 1.4x |
| 100 | 52 ms | 39 ms | 1.3x |
| 1,000 | 162 ms | 128 ms | 1.3x |
| 5,000 | 665 ms | 704 ms | 0.9x |

A nested layout (two directory levels, 10 objects per leaf, emulating
date-partitioned data) produced 1.4x at 1,000 objects and 1.0x at 5,000 — no
material difference from the flat layout.

**What this does and does not mean.** At the object counts tested the Access
Point performed within roughly 1.4x of native S3, comfortably inside the
performance targets previously recorded for this blocker (<1 s for <100 files,
<3 s for <1,000 files). It does **not** mean listing scales indefinitely: this
measurement stopped at 5,000 objects, and behaviour at hundreds of thousands or
millions of objects in a single directory remains untested. Design guidance to
consolidate small files and partition the key space still stands on those
grounds.

The origin of the 30-80x figure is not determined. No evidence record survives
to compare against, so it is recorded as unexplained rather than attributed to a
specific cause. Possible contributors include measurement through a CLI wrapper
(process startup dominates short calls), a file system in a degraded state at
the time, or platform changes between then and now.

> **Request-cost note**: with `MaxKeys=1000`, native S3 returned 1,000 keys in a
> single API call while the Access Point needed two, and six versus five at
> 5,000 objects. Wall-clock time stayed comparable, so this is not a bottleneck,
> but do not assume identical request counts when estimating API cost or when a
> client caps pagination depth.

Reproduce:

```bash
python3 shared/scripts/benchmark_list_objects.py \
  --ap-arn arn:aws:s3:<region>:<account>:accesspoint/<ap-name> \
  --native-bucket <comparison-bucket> \
  --counts 10,100,1000,5000 --trials 5 --layout flat --teardown
```

---

## Pattern A, AWS side: Lambda polling → SNS

Pattern A works around the missing S3 Event Notifications by having a scheduled
Lambda list the Access Point, synthesize an S3-event-shaped notification, and
publish it to SNS. Snowflake then subscribes its own managed SQS queue to that
topic, and the pipe consumes from the queue.

### What passed

| Step | Result |
|---|---|
| PutObject to the Access Point (74-byte object) | 716-805 ms |
| Poller Lambda ListObjectsV2 detection | 981 ms wall time |
| SNS publish and delivery | Confirmed by capturing the message on a subscribed SQS queue |
| File write → notification delivered | **2.1 s** |
| Access Point addressing | Both ARN and alias work as the `Bucket` parameter; IAM granted on the AP ARN also authorizes alias-addressed requests |

The 2.1 s figure excludes the EventBridge schedule wait. Real-world detection
lag is (schedule interval) + ~2 s, so a `rate(5 minutes)` schedule means up to
about five minutes.

### Defects found on the AWS side

| ID | Severity | Issue |
|---|---|---|
| DEFECT-1 | High | `snowpipe-lambda/template.yaml` deploys a placeholder function, not the real handler |
| DEFECT-2 | High | Objects older than the polling window are silently never notified (data loss) |
| DEFECT-3 | Medium | Synthesized notification omits fields present in real S3 events |
| DEFECT-4 | **High** (raised from Medium) | `s3.bucket.name` carries an ARN when the AP ARN is configured. Confirmed on 2026-08-06 to cause a silent drop at Snowpipe — see DEFECT-B below |
| DEFECT-5 | Low | Overlapping windows re-notify already-notified objects |
| DEFECT-6 | Low | No dead-letter queue and no error alarm on the poller |

**DEFECT-1** — the template's inline `Code.ZipFile` body is
`return {"statusCode": 200, "body": "Deploy handler.py"}`. Deploying the
template as published yields a poller that never lists anything. `handler.py`
exceeds the inline size limit, so it cannot simply be pasted in; a real
packaging step is required. The template declares
`Transform: AWS::Serverless-2016-10-31` but defines no SAM resources, so the
transform is currently inert.

**DEFECT-2** — when `STATE_TABLE` is unset the cutoff is
`now - POLLING_INTERVAL_MINUTES`, and because that cutoff tracks wall clock, any
object older than the window is never revisited. Reproduced: an object written
at 05:07:52Z was invisible to an invocation at 05:09:33Z whose cutoff was
05:08:33Z — `new_files_found=0`, while ListObjectsV2 on the same prefix
confirmed the object was present. Aggravating factor: `template.yaml` exposes no
`STATE_TABLE` parameter at all, so every CloudFormation-deployed poller runs in
exactly this lossy mode and the DynamoDB checkpoint path in `handler.py` is
unreachable through the published template.

**DEFECT-3 / DEFECT-4** — the synthesized record carries only `eventVersion`,
`eventSource`, `eventName`, `eventTime`, `s3.bucket.name`, `s3.object.key` and
`s3.object.size`. A genuine S3 notification also carries `awsRegion`,
`s3.s3SchemaVersion`, `s3.configurationId`, `s3.bucket.ownerIdentity`,
`s3.bucket.arn`, `s3.object.eTag` and `s3.object.sequencer`. Separately,
`handler.py` copies `S3_ACCESS_POINT_ALIAS` straight into `s3.bucket.name`, so
supplying the AP ARN emits an ARN where a bucket name belongs.

---

## Pattern A, Snowflake side: does a synthesized notification trigger COPY?

This was the deciding question the AWS-side record left open. It has now been
tested against a live Snowflake account. **The answer is yes**, provided four
conditions all hold.

### The four conditions

| # | Condition | What happens without it |
|---|---|---|
| 1 | The external stage sets `AWS_ACCESS_POINT_ARN` | `LIST` succeeds but every read fails: `Failed to access remote file: access denied` |
| 2 | The pipe sets `AWS_SNS_TOPIC = '<topic ARN>'` | No usable subscription exists, so nothing ever reaches the pipe |
| 3 | The SNS topic policy grants `sns:Subscribe` to Snowflake's IAM user | Snowflake's own subscribe call is denied |
| 4 | `s3.bucket.name` in the payload is the AP **alias**, not the AP ARN | Message is received and then silently discarded |

### What passed

| Test | Result |
|---|---|
| Storage integration + two-phase IAM trust via `integrations/snowflake/template.yaml` | PASS — works exactly as documented |
| Stage **with** `AWS_ACCESS_POINT_ARN` → read 5 rows | PASS, 1.7 s |
| `COPY INTO` from an AP-backed stage | PASS — 5 rows from 2 files, `SUM(amount)` matched the source arithmetic |
| `AUTO_INGEST = TRUE` accepted on an AP-backed stage | PASS — Snowflake issued a managed SQS channel; nothing about the FSx for ONTAP backing is rejected at pipe creation |
| Pipe with `AWS_SNS_TOPIC` → Snowflake subscribes its own queue | PASS — a confirmed subscription ARN appeared on the topic |
| **Synthesized notification → COPY fires** | **PASS** — received 01:55:30.721Z, ingested 01:55:31.211Z (~0.5 s). `COPY_HISTORY`: `events_003.json \| Loaded \| rows=1 \| pipe=EVENTS_PIPE_SNS \| errors=0` |

### The two failures, and what they tell us

**You cannot subscribe Snowflake's queue yourself.** Running
`aws sns subscribe --protocol sqs --notification-endpoint <Snowflake SQS ARN>`
returns `pending confirmation` and stays at `PendingConfirmation` indefinitely.
The queue lives in Snowflake's own AWS account and will not confirm a
subscription it did not initiate. This matters because the architecture drawn in
[Event-Driven Architecture](../../../../docs/en/event-driven-architecture.md)
and in `06_snowpipe.sql`'s header comment — `... → SNS → Snowflake SQS → Snowpipe`
— reads as though the pipeline pushes into that queue directly. It does not. The
subscription is created by Snowflake when `CREATE PIPE` runs with
`AWS_SNS_TOPIC`. The SQL in `06_snowpipe.sql` already does this correctly; it is
the prose that is misleading.

> **Ordering gotcha**: SNS deduplicates subscriptions by (protocol, endpoint).
> A leftover `PendingConfirmation` entry for the same Snowflake queue blocks
> Snowflake's own subscribe call, and `CREATE PIPE` then completes while leaving
> no usable subscription. Do not pre-subscribe. If a stuck pending entry already
> exists it cannot be removed with `sns unsubscribe` (it has no real ARN) — delete
> and recreate the topic.

**A bucket-name mismatch fails silently.** Publishing the same payload with
`s3.bucket.name` set to the Access Point ARN instead of the alias produced:
`lastReceivedMessageTimestamp` advanced (the message arrived),
`lastForwardedMessageTimestamp` unchanged (it was never forwarded), row count
unchanged, and no error in `SYSTEM$PIPE_STATUS` or `COPY_HISTORY`. This is the
most operationally dangerous finding in this document.

### Defects found on the Snowflake side

| ID | Severity | File | Issue |
|---|---|---|---|
| DEFECT-A | High | `sql/02_external_stage.sql` | Every stage is created without `AWS_ACCESS_POINT_ARN`, so all reads fail |
| DEFECT-B | High | `snowpipe-lambda/handler.py` | `s3.bucket.name` is taken from an env var with no validation; an ARN there causes the silent drop |
| DEFECT-C | Medium | `shared/cloudformation/fpolicy-routing.yaml` | The `sns:Subscribe` grant is gated on `aws:SourceArn`, a key absent from Snowflake's direct call, so the statement grants nothing |
| DEFECT-D | Low | `fpolicy-routing.yaml`, `snowflake/template.yaml` | Both list `sns:Receive`, not a valid SNS action (cfn-lint W3037) |
| DEFECT-E | Medium | `integrations/snowflake/template.yaml` | The SNS topic policy falls back to the deployer's own account root, producing a topic Snowflake cannot subscribe to |

**DEFECT-A is the most consequential.** `LIST` passing makes the script look
successful, and the failure only appears when bytes are actually read — which is
what External Tables, `COPY INTO` and Snowpipe all do. Every numbered SQL file
downstream of `02_external_stage.sql` inherits the broken stages.

**DEFECT-C detail** — `aws:SourceArn` is populated only when an AWS service makes
a call on a resource's behalf. Snowflake calls `sns:Subscribe` directly as an IAM
user, so the key is absent and the condition never matches. The file already
contains a correct `AllowSnowflakeIAMUserSubscribe` statement that names the IAM
user as principal; that is the one that works.

### What remains unverified

- Which individual payload fields Snowpipe requires versus ignores. Only
  `s3.bucket.name` was varied deliberately; the rest of the field set was sent
  complete throughout.
- Behaviour when the same synthesized notification is delivered more than once.
- Behaviour at notification volumes high enough to exercise the channel backlog.
- Whether the EventBridge-based Snowpipe path accepts synthesized events equally.
- Pattern B's FPolicy event source. Its Snowflake leg is identical to Pattern A
  and is now verified, but FPolicy → Lambda has never been run live.

---

## Constraints that apply to every path

| Constraint | Effect |
|---|---|
| No S3 Event Notifications | Real-event auto-ingest and `AUTO_REFRESH` are unavailable; a synthesized notification is required ([BLK-003](../../../../docs/en/blocker-tracker.md)) |
| No `AUTO_REFRESH` | External Table and Directory Table metadata need an explicit `REFRESH`, typically driven by a Task |
| No conditional writes | Iceberg / Delta write-back is blocked ([BLK-002](../../../../docs/en/blocker-tracker.md)) |
| Two different size ceilings | A single `PutObject` (and each `UploadPart`) tops out around 5 GiB; a whole object tops out around 50 GiB. Larger files need multipart upload, and the whole-object overrun is only detected at `CompleteMultipartUpload` — after every byte is transferred. [Details](../../../../docs/en/compatibility-matrix.md#part-sizes-are-not-near-the-ceiling) |
| `AWS_ACCESS_POINT_ARN` required on stages | Without it reads fail while `LIST` still succeeds — a misleading partial success |
| `TO_FILE()` unsupported on AP stages | Vision AI needs a `COPY FILES` staging step |
| Not officially supported by Snowflake | Snowflake does not document FSx for ONTAP S3 Access Points as a supported External Stage backend. Read, ingest and governance paths are verified here, but consult Snowflake Support before production use |

> **Dynamic Table note**: a Dynamic Table sourced from an External Table needs
> `REFRESH_MODE = FULL` (incremental refresh requires change tracking, which
> External Tables do not provide) and a minimum `TARGET_LAG` of 60 seconds. It
> also still depends on a Task to refresh the External Table metadata first,
> because `AUTO_REFRESH` is unavailable.

---

## Related Documents

- [Snowflake Integration README](../../README.md) — validation status and decision guidance
- [Snowpipe Integration Guide](./snowpipe-integration.md) — the three candidate patterns
- [Internal Table Ingestion Guide](./internal-table-ingestion-guide.md) — Task + COPY INTO and Dynamic Table patterns
- [Blocker Tracker](../../../../docs/en/blocker-tracker.md) — BLK-003 and BLK-006
- [Event-Driven Architecture](../../../../docs/en/event-driven-architecture.md) — design targets for the FPolicy path
- [Compatibility Matrix](../../../../docs/en/compatibility-matrix.md) — full constraint list
