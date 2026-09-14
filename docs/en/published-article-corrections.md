🌐 **English** | [日本語](../ja/published-article-corrections.md)

# Corrections to Published Articles

Articles in this series are published on external platforms and are edited in place, so they can drift behind the repository. This page is the tracked record of what has been found wrong in a published article, what the correct statement is, and whether the article itself has been updated yet.

**Why this page exists.** A reader who found a claim through a search engine will not know that a later verification overturned it. Recording the correction only in an evidence record fixes the repository and leaves the article wrong. This page also means the correction has a citable URL that can be linked from the article itself.

**How to use it.** Anything marked ⬜ has not been applied to the published article. Do not cite the article for a corrected claim until the row shows ✅.

---

## Part 3 — Snowflake and FSx for ONTAP S3 Access Points

Published May 2026. Reviewed against the repository on 2026-09-13.

The article's central claim is sound and unchanged: without `AWS_ACCESS_POINT_ARN` on the stage, `LIST` succeeds and `SELECT` fails with access denied; with it, the read and governance paths work. Nothing below touches that. The corrections are to secondary claims, three of which would mislead someone building on the article.

### C-01 — An unverified ingestion path is presented as recommended

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ⬜ Not yet |

The article's "Snowpipe Alternatives" section labels **"Option 1: FPolicy → Lambda → SNS → Snowpipe REST API"** as **(Recommended)** and gives it a latency of "Seconds (<30s from file write to Snowflake availability)".

Three problems:

1. **FPolicy has never been run live as an event source.** What was actually verified is a polling Lambda: write to notification in 2.1 s, excluding the scheduler wait, so real detection lag is the schedule interval plus about two seconds. The `<30s` figure has no evidence record behind it.
2. **The drawn topology cannot deliver a message.** You cannot subscribe Snowflake's managed SQS queue yourself; the subscription stays `PendingConfirmation` indefinitely because the queue lives in Snowflake's account. The working shape is `AWS_SNS_TOPIC` on the pipe, which makes Snowflake subscribe its own queue.
3. **Six defects were later found in the published artifacts** for this path, two of which cause silent data loss.

**Correct statement.** For scheduled ingestion, use a **Snowflake Task running `COPY INTO`** — the article's Option 2, which should be Option 1. It is verified, it needs no synthesized notification and no SNS topic policy, and Snowflake's load history gives exactly-once behaviour that a polling window cannot. Event-driven ingestion via a synthesized notification is verified end to end (notification to loaded row in about 0.5 s) but requires four conditions to hold simultaneously and has a failure mode that produces no error anywhere: if `s3.bucket.name` carries the access point ARN instead of the alias, Snowpipe accepts the message and discards it, and the pipe reports healthy. Monitoring for that path must compare object counts against rows loaded.

Reference: [Snowpipe verification results](../../integrations/snowflake/docs/en/snowpipe-verification-results.md).

### C-02 — Dynamic Table cannot read an External Table

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ⬜ Not yet |

The article shows `External Table → Dynamic Table` in the Partner Decision Card, in the "AI-Ready Data Product Journey" diagram, and in "What to Tell Stakeholders".

That path is rejected: `Object ref ... of type EXTERNAL_TABLE not supported in Dynamic Table definition`.

**Correct statement.** The stage must be landed into a standard table first: `stage → COPY INTO standard table → Dynamic Table`. `TARGET_LAG = '60 seconds'` and `REFRESH_MODE = FULL` then behave as specified. The Dynamic Table still depends on a Task to refresh upstream metadata, because `AUTO_REFRESH` is unavailable.

### C-03 — Unload is a partial-write hazard, not an open question

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ⬜ Not yet |

The article lists "PutObject (via COPY INTO unload)" as **⚠️ TBD** with the note "FSx S3 AP supports PutObject ≤5GB", and later says unload "was not validated". <!-- allow:naming: verbatim quotation of the published article, which is the string being corrected -->

**Correct statement.** It was validated and it fails, in the worst way: `COPY INTO @stage` is not refused. The object is written and is intact, and then the statement fails with `Remote upload failed checksum validation` because FSx for ONTAP reports server-side encryption as `aws:fsx`. **A complete object is left behind while the caller is told the write failed.** Setting `ENCRYPTION = (TYPE = 'AWS_SSE_S3')` does not fix it; the statement hangs instead. Anyone who has tried unload against an access-point-backed stage should list the target prefix and remove orphans.

The size note is also wrong in a way that matters: there are **two** ceilings. A single `PutObject`, and each `UploadPart`, tops out around 5 GiB; a whole object tops out around 50 GiB. The whole-object overrun is only detected at `CompleteMultipartUpload`, after every byte has been transferred.

### C-04 — A support case number is published

| | |
|---|---|
| **Severity** | High (hygiene) |
| **Applied to the article** | ⬜ Not yet |

The article's "Support Update (May 2026...)" line includes a vendor support case number. This project's own standard is that support case numbers do not appear in public output; reference the topic, not the ticket.

**Correct statement.** Remove the identifier and keep the substance: "Confirmed with Snowflake Support, May 2026."

### C-05 — Formats and features that have since moved from Expected to Verified

| | |
|---|---|
| **Severity** | Low, and in the reader's favour |
| **Applied to the article** | ⬜ Not yet |

The article marks several rows "✅ Expected" or "⚠️ TBD" that have since been measured:

| Article says | Now |
|---|---|
| JSON, Avro, ORC read — "Expected" | Verified, 2026-08-06 |
| Snowpark `SnowflakeFile.open` — "Not validated" | Verified |
| Iceberg Table read — "TBD" | `COPY INTO` a Managed Iceberg Table on an External Volume verified end to end, with a real Iceberg layout on the destination |
| ListObjectsV2 latency, quoted elsewhere in the series as 30-80x native S3 | Re-measured at 1.3-1.4x up to 5,000 objects; the earlier figure did not reproduce and is withdrawn. Untested above 5,000 objects |

### C-06 — Internal inconsistency in the Cortex function count

| | |
|---|---|
| **Severity** | Low |
| **Applied to the article** | ⬜ Not yet |

The article says "8 out of 10" in some places and "7 out of 9" in others, and separately "6 Cortex functions direct" in a comparison table. Pick one denominator and state which functions are counted.

### Not a correction: SnapMirror

The article does not discuss SnapMirror, so the 2026-09-13 finding that a live SnapMirror destination can be served through an access point does not require an article change. It is new material rather than a correction, and belongs in a future part or in the [design considerations](./s3ap-flexcache-snapmirror-considerations.md#32-s3-ap-attachment-at-the-destination).

---

## Related

- [Blocker tracker](./blocker-tracker.md) — BLK-003, BLK-006, BLK-009
- [Unverified item inventory](./unverified-inventory.md)
- [Snowflake integration README](../../integrations/snowflake/README.md) — current validation status
