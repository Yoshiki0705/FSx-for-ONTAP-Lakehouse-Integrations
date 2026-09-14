🌐 **English** | [日本語](../ja/published-article-corrections.md)

# Corrections to Published Articles

Articles in this series are published on external platforms and are edited in place, so they can drift behind the repository. This page is the tracked record of what has been found wrong in a published article, what the correct statement is, and whether the article itself has been updated yet.

**Why this page exists.** A reader who found a claim through a search engine will not know that a later verification overturned it. Recording the correction only in an evidence record fixes the repository and leaves the article wrong. This page also means the correction has a citable URL that can be linked from the article itself.

**How to use it.** Anything marked ⬜ has not been applied to the published article. Do not cite the article for a corrected claim until the row shows ✅.

**Current state.** Every correction on this page has been applied to the live articles, verified by re-fetching each body after the update rather than by trusting the API's success response. Each edited article carries the correction inline, next to the claim it replaces, so a reader who arrives from a search engine sees it without coming here first.

---

## Part 3 — Snowflake and FSx for ONTAP S3 Access Points

Published May 2026. Reviewed against the repository on 2026-09-13.

The article's central claim is sound and unchanged: without `AWS_ACCESS_POINT_ARN` on the stage, `LIST` succeeds and `SELECT` fails with access denied; with it, the read and governance paths work. Nothing below touches that. The corrections are to secondary claims, three of which would mislead someone building on the article.

### C-01 — An unverified ingestion path is presented as recommended

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ✅ 2026-09-14 |

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
| **Applied to the article** | ✅ 2026-09-14 |

The article shows `External Table → Dynamic Table` in the Partner Decision Card, in the "AI-Ready Data Product Journey" diagram, and in "What to Tell Stakeholders".

That path is rejected: `Object ref ... of type EXTERNAL_TABLE not supported in Dynamic Table definition`.

**Correct statement.** The stage must be landed into a standard table first: `stage → COPY INTO standard table → Dynamic Table`. `TARGET_LAG = '60 seconds'` and `REFRESH_MODE = FULL` then behave as specified. The Dynamic Table still depends on a Task to refresh upstream metadata, because `AUTO_REFRESH` is unavailable.

### C-03 — Unload is a partial-write hazard, not an open question

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ✅ 2026-09-14 |

The article lists "PutObject (via COPY INTO unload)" as **⚠️ TBD** with the note "FSx S3 AP supports PutObject ≤5GB", and later says unload "was not validated". <!-- allow:naming: verbatim quotation of the published article, which is the string being corrected -->

**Correct statement.** It was validated and it fails, in the worst way: `COPY INTO @stage` is not refused. The object is written and is intact, and then the statement fails with `Remote upload failed checksum validation` because FSx for ONTAP reports server-side encryption as `aws:fsx`. **A complete object is left behind while the caller is told the write failed.** Setting `ENCRYPTION = (TYPE = 'AWS_SSE_S3')` does not fix it; the statement hangs instead. Anyone who has tried unload against an access-point-backed stage should list the target prefix and remove orphans.

The size note is also wrong in a way that matters: there are **two** ceilings. A single `PutObject`, and each `UploadPart`, tops out around 5 GiB; a whole object tops out around 50 GiB. The whole-object overrun is only detected at `CompleteMultipartUpload`, after every byte has been transferred.

### C-04 — A support case number is published

| | |
|---|---|
| **Severity** | High (hygiene) |
| **Applied to the article** | ✅ 2026-09-14 |

The article's "Support Update (May 2026...)" line includes a vendor support case number. This project's own standard is that support case numbers do not appear in public output; reference the topic, not the ticket.

**Correct statement.** Remove the identifier — and do not replace it with "confirmed by vendor support", which has the same defect in a shorter form. A vendor's reply is not a publishable basis for a claim: cite the public page, state your own observation, or mark it open. Recording that you asked, and when, is fine.

Here the substance is available first-hand and should replace the attribution outright. The Managed Iceberg half of that line is independently measured in this repository, and the Dynamic Table half of the same line is **wrong** (C-02). So the line becomes an observation with an evidence link, not a ticket reference.

### C-05 — Formats and features that have since moved from Expected to Verified

| | |
|---|---|
| **Severity** | Low, and in the reader's favour |
| **Applied to the article** | ✅ 2026-09-14 |

The article marks several rows "✅ Expected" or "⚠️ TBD" that have since been measured:

| Article says | Now |
|---|---|
| JSON, Avro, ORC read — "Expected" | Verified, 2026-08-06 |
| Snowpark `SnowflakeFile.open` — "Not validated" | Verified |
| Iceberg Table read — "TBD" | `COPY INTO` a Managed Iceberg Table on an External Volume verified end to end, with a real Iceberg layout on the destination |
| ListObjectsV2 latency, quoted elsewhere in the series as 30-80x native S3 | Re-measured at 1.3-1.4x up to 5,000 objects; the earlier figure did not reproduce and is withdrawn. Untested above 5,000 objects. The figure originated in the series overview — see [S-01](#s-01--the-series-overview-asserted-the-withdrawn-figure-as-a-product-characteristic) |

### C-06 — Internal inconsistency in the Cortex function count

| | |
|---|---|
| **Severity** | Low |
| **Applied to the article** | ✅ 2026-09-14 |

The article says "8 out of 10" in some places and "7 out of 9" in others, and separately "6 Cortex functions direct" in a comparison table. Pick one denominator and state which functions are counted.

**Correct statement.** Nine capabilities are tested in the article's own table. Six run directly against the external table or stage with no copy — SUMMARIZE, TRANSLATE, SENTIMENT, COMPLETE for text, EXTRACT_ANSWER and PARSE_DOCUMENT. Two more work through a staging copy: Vision AI via `COPY FILES`, Cortex Search via `COPY INTO`. One, `TO_FILE`, is blocked. That is the denominator the table supports.

### C-07 — A second vendor-support attribution, found while applying C-04

| | |
|---|---|
| **Severity** | High (hygiene) |
| **Applied to the article** | ✅ 2026-09-14 |

C-04 was written against the one line that carried a case number. Applying it surfaced a second instance of the same defect elsewhere in the article: a "Support Confirmation" paragraph whose warrant for the resolution was that a vendor had confirmed it.

This is worth recording separately rather than folding into C-04, because it shows the search that produced C-04 was too narrow. Looking for a case number finds one shape of the defect. The defect is the wider one: a vendor's reply standing in for evidence.

**Correct statement.** The resolution is first-hand — the article measures it — and the parameter is publicly documented. Both are stronger than the attribution, so the attribution is removed and the observation stated instead. A sweep for this shape across the whole published series is recorded in [Other articles in the series](#other-articles-in-the-series).

### Not a correction: SnapMirror

The article does not discuss SnapMirror, so the 2026-09-13 finding that a live SnapMirror destination can be served through an access point does not require an article change. It is new material rather than a correction, and belongs in a future part or in the [design considerations](./s3ap-flexcache-snapmirror-considerations.md#32-s3-ap-attachment-at-the-destination).

---

## Other articles in the series

C-05 withdrew a listing-latency figure that this article only quoted. The figure originated elsewhere, and C-07 showed that searching for one shape of a defect finds one shape of it. So both were swept across every published article in the series rather than fixed where they happened to be noticed. What that found is below. All of it is applied.

### S-01 — The series overview asserted the withdrawn figure as a product characteristic

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ✅ 2026-09-14 |

The overview's section 8 was titled "ListObjectsV2 Latency Is a Product-Level Characteristic" and reported 30-80x slower listing than standard S3, resting that characterisation on a vendor support reply. This is where the figure C-05 withdraws actually lived; Part 3 only quoted it.

**Correct statement.** Re-measured at 1.3-1.4x native S3 up to 5,000 objects. The earlier figure did not reproduce. Above 5,000 objects is untested, so the supportable claim is that behaviour at scale is unknown, not that it is slow. The heading asserted the withdrawn conclusion and was changed too — a correction that leaves the heading standing is not applied.

### S-02 — Part 2 extrapolated the withdrawn figure, and published real identifiers

| | |
|---|---|
| **Severity** | High |
| **Applied to the article** | ✅ 2026-09-14 |

Three separate problems in the Databricks article:

1. **An extrapolation of the withdrawn figure.** An Auto Loader note advised planning for "minutes-level detection latency, not seconds" for large directories. That was derived from the 30-80x figure, not measured. Replaced with the re-measurement and an explicit statement that scale is untested. The Directory Listing blocker in the same table is a separate finding and is unaffected.
2. **Three vendor-support attributions.** Two asserted that the NFS mount is "blocked by seccomp by design"; one asserted that the `access_point` field was never GA. Replaced with what is observable: `mount` returns `EACCES` and `strace` shows the syscall blocked rather than a server refusal, and the field is absent from current documentation — which any reader can check. "By design" is retained as the platform's characterisation, labelled as such.
3. **Real environment identifiers.** A private NFS server address appeared in 13 command transcripts, along with two VPC IDs, a peering connection ID and a VPC endpoint ID. Replaced with the RFC 5737 documentation range and placeholders. The article now says the substitution happened, because silently rewriting an identifier inside a transcript changes evidence: ports, error strings, syscall results and timings are unchanged, and the note says so.

### S-03 — A linear projection overstated the case for the recommended path

| | |
|---|---|
| **Severity** | Medium |
| **Applied to the article** | ✅ 2026-09-14 |

The metadata catalog article projects ListObjectsV2 latency to 1,000 through 1,000,000 objects by extrapolating linearly from a measured 40-file scan, and derives multipliers up to 12,389x in favour of the catalog path. It labelled that extrapolation "intentionally conservative".

**Correct statement.** Listing paginates rather than scaling linearly with object count, so linear extrapolation overstates the namespace-scan cost — and therefore overstates the advantage of the path the article recommends. "Conservative" was the wrong word: the error runs in the author's favour, which is the direction that needs stating plainly. The 40-file measurement stands. Above 5,000 objects is untested.

### S-04 — Part 5 cited a vendor reply for a result measured in Part 2

| | |
|---|---|
| **Severity** | Low |
| **Applied to the article** | ✅ 2026-09-14 |

The EMR Serverless article attributed the Databricks session-policy restriction to a vendor support reply. That restriction is measured in Part 2 of the same series, with the generated policy shown next to the failures it produces. Replaced with the cross-reference, which is both stronger and checkable.

### S-05 — A real AWS account ID, and two more vendor attributions

| | |
|---|---|
| **Severity** | High (hygiene) |
| **Applied to the article** | ✅ 2026-09-14 |

The governance article published a real 12-digit AWS account ID inside an IAM user ARN, on the line directly below one that correctly used an `<ACCOUNT_ID>` placeholder. Replaced with a placeholder. The same article carried two vendor-support attributions in a dated log entry; both underlying facts are available first-hand or from public API reference, so the observations replace the attributions and the fact that the vendors were asked is retained without it carrying the claim.

### Addition, not a correction: the SnapMirror result

The AWS Backup cross-Region article explains that a SnapMirror destination is a `DP` volume and cannot be backed up. That is correct and unchanged. It is also the natural place for a reader to conclude that a `DP` volume can do nothing else, so the 2026-09-13 result was added there: a replica can be served read-only through an access point while replication runs, gated by the junction path rather than the volume type. Nothing in that article was wrong; this is added material.

## Known, and deliberately not changed

Recorded so the next sweep does not rediscover it as new.

| Finding | Extent | Why it is left |
|---|---|---|
| Private RFC 1918 addresses in log samples | 9 articles in the observability series, one address each | Not part of this investigation, and each is a judgement about transcript fidelity in an article that was not otherwise being edited. Against this project's own standard, so it is a real debt — but a separate, opt-in change rather than something to fold into a correctness pass |
| `123456789012` and `111111111111` as account IDs | 12 articles | Documentation placeholders, not exposures. No action <!-- allow:pii: the literals are the documentation placeholders themselves, catalogued here so a later sweep does not report them as exposures --> |
| Generic CIDR blocks (`10.0.0.0/16`, `10.53.0.0/16`) | Part 2 | Describe topology, not a host. No action <!-- allow:pii: CIDR blocks, not host addresses; quoted so the distinction is recorded --> |
| "until confirmed by Databricks Support" | Part 2 | Forward-looking, and correctly marks the claim as *not* confirmed. This is the shape the standard asks for, not the one it forbids <!-- allow:support-attribution: quoting the permitted shape in order to distinguish it from the forbidden one; no reply content is published --> |

---

## Related

- [Blocker tracker](./blocker-tracker.md) — BLK-003, BLK-006, BLK-009
- [Unverified item inventory](./unverified-inventory.md)
- [Snowflake integration README](../../integrations/snowflake/README.md) — current validation status
