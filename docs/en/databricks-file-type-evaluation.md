🌐 **English** | [日本語](../ja/databricks-file-type-evaluation.md)

# Databricks FILE type (Beta) Evaluation: Multimodal Data, Metadata Tables, and FSx for ONTAP

> **Status**: Initial evaluation (2026-08-12). Databricks-side claims are from official documentation; the FSx for ONTAP object-metadata behaviour is **Verified** in this environment. Databricks runtime behaviour is **not yet verified here** — see [Verification Status](#verification-status).
> **Evidence tier** per claim: **Public** (verifiable from public sources) / **Verified** (measured in this environment) / **Project-context** (internal assumption) / **Hypothesis**.
> **Test environment**: AWS ap-northeast-1, FSx for ONTAP S3 Access Point (INTERNET origin, UNIX user), boto3 1.43.36.
> **Framing**: right-tool-for-the-job, not vendor-versus. Trade-offs stated symmetrically, including for the approach this repository recommends.

---

## Executive Summary

- **What FILE type is**: a Delta column type that stores a *governed reference* to an unstructured file (`uri`, `offset`, `size`, `content_type`, `checksum`) rather than its bytes, so documents, images, audio and video sit in a table next to structured columns and can be passed to AI functions and UDFs. Announced in Beta, 2026-08.
- **Design-level verdict**: FILE type is essentially the productised form of the pattern this repository already implements in the [Iceberg metadata catalog](../../integrations/iceberg-metadata-catalog/README.md) — a metadata table that carries file references plus AI-derived columns. The convergence is a useful signal that the pattern is the right one.
- **But it still does not unblock FSx for ONTAP** — for a narrower reason than previously recorded. `FILE EXTERNAL` references are only supported for files inside a Unity Catalog volume. A UC external volume on an S3 Access Point **can be created**; what fails is **reading through it**, because the down-scoped session policy Unity Catalog vends is written in bucket-style resource ARNs while AWS authorises access-point requests against the access point ARN ([BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads), scope corrected 2026-08-12). There is no user-side workaround. The only remaining route is `FILE MANAGED`, which **copies** the bytes into UC-managed storage and therefore forfeits zero-copy and the ONTAP efficiencies that depend on the data staying in place.
- **What did move**: a separate feature, the [`_object_metadata` column](https://docs.databricks.com/aws/en/ingestion/object-metadata-column) (DBR 18.2+), exposes S3 **object tags** and **user-defined metadata** as queryable columns. That is the documented bridge between object-storage-side metadata and a metadata table — exactly the linkage this repository had no answer for.
- **Verified this run**: FSx for ONTAP S3 AP **does** support object tagging and `x-amz-meta-*`, tags are **file-scoped** (readable through a different Access Point on the same volume), and tags can be written **in the same PutObject** as the data. Two constraints matter: object tags are **effectively ASCII-only** on this Access Point, and an object overwrite **silently clears** tags and user metadata.
- **The two mechanisms are mutually exclusive**: Databricks documents that user metadata, system metadata and tags are `null` for Databricks-managed storage. So `FILE MANAGED` (copy into UC storage) and `_object_metadata` (read tags from the source) cannot both be used for the same bytes. Read tags once at ingestion, then treat the table as the source of truth.
- **Recommended shape**: a three-layer split — ONTAP/IAM as the only enforcement layer, the metadata table as the source of truth, and object tags as a narrow discovery inlet. Object tags are an *input*, never the basis of an authorization decision.

---

## 1. What FILE type is

**Evidence tier: Public** — from [FILE type reference](https://docs.databricks.com/aws/en/sql/language-manual/data-types/file-type), [FILE type and unstructured data](https://docs.databricks.com/aws/en/unstructured/file), [Ingest files as the FILE type](https://docs.databricks.com/aws/en/ingestion/file), and the [announcement blog](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data).

A `FILE` value holds a reference and metadata, not bytes:

| Field | Type | Note |
|---|---|---|
| `uri` | STRING | Cannot be null |
| `offset` | BIGINT | Byte offset into the file |
| `size` | BIGINT | Size in bytes |
| `content_type` | STRING | MIME type, when known |
| `checksum` | STRING | `<algorithm>:<digest>` — `ETAG`, `MD5`, `CRC32`, `CRC32C`, `SHA-256` |

Because the column stores a pointer, the engine reads bytes only at the step that needs them. The stated contrast is with `BINARY`, which materialises the whole object on every read even when only the size or path is wanted, and with a `STRING` path column, which carries no governed link so the table goes stale when another workload deletes the file.

> **Note on the metadata surface**: the five fields above are the entire metadata surface of a `FILE` value. There is **no field for object tags or user-defined metadata**. Any attribute you intend to search, filter or govern on must become its own column in the table. This is the single most important thing to understand before designing around FILE type.

### FILE MANAGED vs FILE EXTERNAL

| | `FILE MANAGED` | `FILE EXTERNAL` |
|---|---|---|
| Bytes | **Copied** into a *FileSpace* (a UC volume declared via the `databricks.filespace-preview` table property) | Referenced **in place** |
| Where the source may live | Anywhere, including SharePoint / Google Drive / OneDrive / SFTP via Lakeflow connectors | **Only inside a Unity Catalog volume** |
| Lifecycle | Tied to the row. Deleting the row makes the file eligible for garbage collection | Not managed by UC. Deleting the row does not touch the file |
| Access control | Table privileges (`SELECT`) **and** volume privileges (`READ VOLUME`) | Volume privileges (`READ VOLUME`). Table grants expose metadata; reading bytes still needs `READ VOLUME` |
| Databricks recommendation | Preferred, for file-level permissions and built-in compliance | When files must stay where other tools read them |

`FILE MANAGED` is what carries the GDPR "right to be forgotten" claim in the announcement: delete the row and the binary becomes collectable, so table and storage stay in sync instead of leaving an orphaned pointer.

### Beta constraints to plan around

**Evidence tier: Public.**

| Constraint | Consequence |
|---|---|
| **Delta Lake tables only** | Not available for Iceberg. This repository's metadata catalog is Iceberg on S3 Tables, so FILE type is not a drop-in there |
| **DBR 18 LTS and above**; not supported on serverless notebooks (works on notebooks attached to serverless SQL warehouses) | Compute-plane prerequisite |
| Beta — a workspace admin must enable it on the **Previews** page | Cannot be assumed present in a customer workspace |
| Cannot be a **partitioning column, clustering column, MAP key, join key, or grouping expression** | Group and join on `file.uri` instead |
| **Automatic garbage collection of unreferenced managed files is not supported in Beta** | A manual sweep notebook is provided. Storage grows silently until run |
| `FILE EXTERNAL` is unsupported for files stored **outside volumes** | The constraint that governs everything in §2 |
| Open-format support is stated as in progress ("we are working with the community to build support directly into Parquet, Delta Lake, Apache Iceberg, and Apache Spark") | Portability is a direction of travel, **not** a currently available property. Do not present FILE type as an open, portable format today |

---

## 2. Why this does not unblock FSx for ONTAP

**Evidence tier: Verified** (measured 2026-08-12 on a purpose-built non-trial workspace, with a native-S3 control — [evidence](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)). Reproduce it in your own account with the [verification runbook](./databricks-verification-runbook.md).

> **Corrected 2026-08-12.** This section previously said a UC external volume cannot be
> created on an S3 Access Point. That is wrong. The storage credential, the external
> location and the external volume are all created successfully, with UC's own validation
> enabled. What fails is **reading through them**.

The chain terminates one step later than previously recorded — and for a different reason:

```
Goal: reference a file on FSx for ONTAP from a FILE column, without copying
  │
  ├─ FILE EXTERNAL?
  │    └─ supported only for files inside a Unity Catalog volume
  │         └─ UC external volume over the S3 Access Point
  │              ├─ CREATE STORAGE CREDENTIAL      → OK
  │              ├─ CREATE EXTERNAL LOCATION       → OK (validation enabled)
  │              ├─ CREATE EXTERNAL VOLUME         → OK
  │              └─ READ through it                → BLOCKED (403)
  │                   └─ BLK-001: the down-scoped session policy UC vends
  │                      is written in bucket-style ARNs, while AWS
  │                      authorises access-point requests against the
  │                      access point ARN. "no session policy allows
  │                      the s3:ListBucket action"
  │
  └─ FILE MANAGED?
       └─ works, but COPIES the bytes into UC-managed storage
            ├─ zero-copy lost; storage billed twice
            ├─ ONTAP dedup / compression / Snapshot / FlexClone do not
            │  apply to the copy
            └─ object tags on the source become unreadable (see §4)
```

This is the same wall as every other UC governance feature on FSx for ONTAP data, and the recommended interim path is unchanged: stage to a standard S3 bucket, then govern the copy. See [BLK-001 workarounds](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads) and the [DataSync to S3 guide](./datasync-to-s3-guide.md).

> **What did change**: the value of resolving BLK-001 went up. Previously it bought lineage, tags, masks and row filters on tabular data resident on FSx for ONTAP. Now it additionally buys `FILE EXTERNAL` over ONTAP-resident unstructured data, which is the multimodal-AI story on data that stays on the NAS. That is worth restating when the feature gap is raised with Databricks — see the [support and forum question set](#6-open-questions-raised-externally).

---

## 3. Where per-file access control actually lands

**Evidence tier: Public** — from [ABAC core concepts](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/core-concepts) and [Apply tags to Unity Catalog securable objects](https://docs.databricks.com/aws/en/database-objects/tags).

The announcement leans on ABAC, so it is worth being precise about the granularity, because it determines the schema you have to design:

- **Governed tags** are account-level key-value pairs applied to *securables* — catalog, schema, table, column. They are **not** applied to rows.
- Tags applied at one level are inherited downward, **except to the column level**.
- What ABAC provides is **row filter policies and column mask policies** on tables, materialized views and streaming tables.

So a requirement like "this image is visible to Team A only" cannot be expressed as a tag on the file. It has to become **an attribute column on the row, protected by a row filter**. FILE type changes what the row *contains* — a real, lifecycle-managed file reference instead of a bare path string — but it does not change where the control point sits.

That is the same conclusion this repository reached independently for the Iceberg metadata catalog, and it is worth noting that a colleague's intuition on this project arrived at the same design before FILE type was announced: put the rich metadata in a table because a table is where you can impose format and length rules, then use that table for search and, where appropriate, for access control.

---

## 4. The object-metadata bridge

This is the part that genuinely advanced, and it is a different feature from FILE type.

### 4.1 Databricks side: the `_object_metadata` column

**Evidence tier: Public** — [Object metadata column](https://docs.databricks.com/aws/en/ingestion/object-metadata-column), DBR 18.2+.

`_object_metadata` is a hidden STRUCT column exposed by file-based data sources, distinct from the older `_metadata` column (path, size, modification time):

| Field | Type | Content |
|---|---|---|
| `mime_type` | STRING | Content type |
| `etag` | STRING | ETag — usable for change detection |
| `user_metadata` | VARIANT | S3 `x-amz-meta-*` user-defined metadata |
| `system_metadata` | VARIANT | Provider-set system metadata |
| `tags` | VARIANT | **S3 object tags** |

Values are extracted with `_object_metadata.tags:environment::string`, and the column can be selected through `spark.read`, Auto Loader, or `COPY INTO`, so tags can be landed into a Delta column at ingestion.

Documented caveats that shape the design:

- Selecting any field triggers **up to two additional cloud API calls per file**, so wide scans over many small files get slower.
- `tags` requires **`s3:GetObjectTagging`**; without it, `tags` returns `null` rather than failing loudly.
- **`user_metadata`, `system_metadata` and `tags` are `null` for Databricks-managed storage.**
- New fields may be added, so select specific fields rather than the whole struct to avoid schema-evolution errors.

### 4.2 FSx for ONTAP side: what the Access Point actually supports

**Evidence tier: Verified** — measured 2026-08-12. Evidence: [`verification-pack/s3ap-object-tagging/evidence/2026-08-12/`](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml). Reproduce with [`shared/scripts/probe_s3ap_object_tagging.py`](../../shared/scripts/probe_s3ap_object_tagging.py).

AWS documents `PutObjectTagging` / `GetObjectTagging` / `DeleteObjectTagging` as supported for Access Points attached to FSx for ONTAP volumes, and Object Annotations as **not** supported. That settles capability; this run measured the operating envelope.

| Property | Result | Same as native Amazon S3? |
|---|---|:---:|
| `PutObjectTagging` / `GetObjectTagging` / `DeleteObjectTagging` | Supported | ✅ |
| `x-amz-meta-*` user metadata round-trip | Supported (returned by `HeadObject`) | ✅ |
| **Tag at write time** (`x-amz-tagging` on `PutObject`) | Supported — one request, no second round trip | ✅ |
| Max tags per object | 10; 11 → `BadRequest: Object tags cannot be greater than 10` | ✅ |
| Tag key length | 128 accepted, 129 → `InvalidTag` | ✅ |
| Tag value length | 256 accepted, 257 → `InvalidTag` | ✅ |
| **Character set** | **U+0000–U+00FF accepted; U+0100 and above rejected for most strings** | ❌ **Diverges** |
| Tag scope | **File-scoped** — tags written via one Access Point are readable via another Access Point on the same volume | n/a |
| Tags after object overwrite | **Cleared** | ✅ (matches `PutObject` semantics, but easy to miss) |
| User metadata after object overwrite | **Cleared** | ✅ |
| `GetObjectTagging` latency | median 52–59 ms, single caller, warm | n/a |
| Object Annotations | Not supported (per AWS docs) | ❌ |

#### The character-set divergence

Amazon S3 documents tag keys and values as Unicode counted in UTF-16. On this Access Point, that is not the behaviour. Characters in the Latin-1 range are accepted (`café`, `ü`, `ÿ` at U+00FF); characters at U+0100 and above are rejected with `InvalidTag` — Greek, Cyrillic, hiragana, katakana, CJK, fullwidth and non-BMP all fail.

The inconsistency is that **a few multibyte strings are accepted**. As tag keys, `分類`, `品質`, `名古屋`, `画像`, `音声` succeed while `東京`, `機密`, `日本語`, `工場`, `検査` fail. Outcomes are **stable per string** (6/6 identical across repeats), so this is not flakiness, but no rule could be inferred. Three hypotheses were tested and rejected:

| Hypothesis | Result |
|---|---|
| UTF-8 byte-length parity (odd fails) | Contradicted: `名古屋` (9 bytes) accepted, `機機` (6 bytes) rejected |
| Service validates the UTF-8 bytes as UTF-16BE | 15/21 agreement; contradicted by every accepted multibyte case |
| Bytes also decodable as euc-jp / shift_jis / cp932 / iso2022_jp / big5 / gb2312 / euc-kr | Best agreement 11/16; no codec explains the split |

**Practical guidance: restrict FSx for ONTAP S3 AP object tags to ASCII.** A predictable subset of multibyte strings fails validation and the failing subset cannot be predicted from outside, so any pipeline that writes Japanese tag values will fail on some inputs and not others. Raised with AWS as a behaviour/documentation question ([§6](#6-open-questions-raised-externally)).

This makes the length limits less academic than they look. Ten tags, 128-character keys, 256-character values, ASCII only, means object tags cannot carry a Japanese summary, a classification rationale, or an embedding. They can carry a handful of low-cardinality ASCII labels. Everything else belongs in the table — which is what the colleague's intuition about "format and character-count rules" anticipated, for a sharper reason than expected.

#### Presigned URLs work and that is expected

The AWS Access Point compatibility table lists **`Presign` as "Not supported"** for FSx for ONTAP volumes. Measured here, `aws s3 presign` produced a URL and an unauthenticated `curl` against it returned **HTTP 200 with the object body**.

This is not a defect, and it is not really a contradiction. **Evidence tier: Public** (explained by AWS Support on a prior case raised from this account, May 2026): presigning is a purely **client-side SigV4 signature calculation** — no request reaches AWS at presign time. Using the resulting URL is simply a `GetObject`, which the same table lists as Supported. It would be structurally impossible to block presigning without also breaking `GetObject`.

So the table's `Presign` row should be read as **"not officially tested, do not rely on it in production"**, not as "will fail". AWS has a documentation-correction request open for the wording.

> **Guidance**: treat "Supported" as build-on-freely and "Not supported" as do-not-rely-on, even when it demonstrably works. This is why this repository does not recommend a presigned-URL delivery pattern on FSx for ONTAP data despite having measured it working. It also reconciles the Snowflake `GET_PRESIGNED_URL` result recorded elsewhere here: that works for the same reason, and carries the same caveat.
>
> Related detail from the same explanation: ONTAP S3 supports v4 presigned URLs from ONTAP 9.11.1 and v2 from 9.16.1, with v4 recommended.

### 4.3 The mutual exclusion

Putting §4.1 and §4.2 together produces the constraint that decides the pipeline order:

| What you want | Where the bytes must be | What you lose |
|---|---|---|
| Inherit object tags / user metadata into columns | The **original** storage, read directly (`_object_metadata`) | FILE type's row-tied lifecycle |
| FILE type lifecycle sync (delete row → collect file) | **UC-managed** storage (`FILE MANAGED`) | Object tags and user metadata — documented as `null` for Databricks-managed storage |

You cannot have both for the same bytes. The resolution is ordering: **read object-side metadata once, at ingestion, into real columns; from that point the table is the source of truth.** Which is precisely the "write time, or on a periodic cycle, record the metadata into a metadata table" shape that was sketched informally on this project.

---

## 5. Recommended shape: three layers

**Evidence tier: Project-context** (the recommendation) built on **Verified** and **Public** facts above.

```
┌─ Enforcement ────────────────────────────────────────────────┐
│  ONTAP file ACL + S3 AP policy + IAM  (+ UC row filters when │
│  data has been staged into UC)                               │
│  → the ONLY layer that actually denies access                │
└──────────────────────────────────────────────────────────────┘
        ▲ consulted for every authorization decision
        │
┌─ Source of truth ────────────────────────────────────────────┐
│  Metadata table (Iceberg on S3 Tables today; Delta + FILE    │
│  type once BLK-001 is resolved)                              │
│  → classification, summary, embedding, PII flags, ACL hints  │
│  → schema and validation rules are imposed HERE              │
└──────────────────────────────────────────────────────────────┘
        ▲ read once at ingestion, never treated as authoritative afterwards
        │
┌─ Discovery inlet ────────────────────────────────────────────┐
│  S3 object tags (≤10, ASCII, key 128 / value 256)            │
│  → onboarding existing NAS assets, coarse filtering          │
└──────────────────────────────────────────────────────────────┘
```

Three rules follow from the measurements:

1. **Object tags are an input, not an output.** Anyone holding `s3:PutObjectTagging` can rewrite them, and an object overwrite clears them. They are a discovery signal, never the basis of an authorization decision. This is the same discovery-vs-enforcement boundary already documented for [S3 Annotations](./s3-annotations-governance-evaluation.md).
2. **Impose structure in the table.** The table is the layer where you can require a schema, validate values, and store Japanese text and embeddings — none of which object tags can hold.
3. **Access control resolves to a row.** Given ABAC's granularity (§3), per-file control is a row filter over an attribute column. Design the attribute columns first.

### Write-time vs periodic, both already implemented

The two population strategies sketched informally on this project already exist in this repository:

| Strategy | Implementation | Characteristic |
|---|---|---|
| **At write time** (event-driven) | FPolicy → SQS → Lambda ([`shared/cloudformation/fpolicy-ingestion.yaml`](../../shared/cloudformation/fpolicy-ingestion.yaml); metadata catalog Phase 2) | Seconds. Substitutes for S3 Event Notifications, which FSx for ONTAP S3 AP does not emit ([BLK-003](./blocker-tracker.md#blk-003-s3-event-notifications-not-supported)) |
| **Periodic scan** | [`initial-metadata-scan.py`](../../integrations/iceberg-metadata-catalog/scripts/initial-metadata-scan.py) | Catches what events missed. Reconciliation path |
| Write-time tagging on the object itself | `PutObject` with `x-amz-tagging` — **Verified**, single request | Lets the producer stamp ASCII labels with no extra round trip |

The Databricks-native equivalents (`list_files`, `STREAM read_files(..., format => 'file')`, `AUTO CDC`) all assume a UC volume, so they are unavailable for FSx for ONTAP today. The FPolicy route remains the fit for ONTAP-resident data.

> **Cost note**: tags are not returned by `ListObjectsV2`, so building a table from object tags costs one `GetObjectTagging` per file. At a measured median of ~52–59 ms with no concurrency that is roughly 17 files/second per caller — a cold-path operation needing parallelism, not something to put in a request path. Sample run on one Access Point; concurrency, file size and throughput capacity were not varied.

---

## 6. Open questions raised externally

Drafts and tracking are kept outside the public tree. Raised with the respective vendors:

| # | To | Question |
|:---:|---|---|
| ~~Q1~~ | AWS | ~~`Presign` listed as Not supported but a presigned GET returns HTTP 200~~ — **closed, already answered**. Presigning is client-side signature computation, so the request that reaches the service is a supported `GetObject`. A duplicate case raised on 2026-08-12 was withdrawn once the prior history was found; an AWS-side documentation-correction request for the table wording has been open since 2026-07-19. See [§4.2](#presigned-urls-work-and-that-is-expected) |
| Q2 | AWS | **Escalated 2026-08-12.** Object tag keys/values at U+0100 and above are rejected with `InvalidTag` for most strings but accepted for some (`分類` accepted, `東京` rejected — both two-character CJK). **Now published as an ONTAP defect**: [CONTAP-771956](https://kb.netapp.com/on-prem/ontap/da/S3/S3-Issues/CONTAP-771956) (Public) records that U+0000-U+00FF is accepted while most of U+0100 and above is rejected, that `分類` / `品質` / `名古屋` are deterministically accepted while `東京` / `機密` / `日本語` are rejected, and that **validation is not per-character** (`分` and `類` fail alone, `分類` succeeds). Track that article for the fix. Object tags stay ASCII until it ships |
| Q3 | Databricks | **Reframed 2026-08-12.** An external location and external volume on an S3 Access Point alias are created successfully, but every read is denied because the down-scoped session policy is expressed in bucket-style ARNs while AWS authorises access-point requests against the access point ARN (`because no session policy allows the s3:ListBucket action`). Can Unity Catalog emit the access point ARN form (`arn:aws:s3:<region>:<account>:accesspoint/<name>` and `.../object/*`) when the location URL is an access point alias? Reproduces outside Databricks with UC-vended credentials |
| Q4 | Databricks | Can a `FILE MANAGED` FileSpace be an **external** volume, or must it be a managed volume? The docs say "a Unity Catalog volume" without qualifying |
| Q5 | Databricks | Can a table containing a `FILE` column be shared via OpenSharing, and is it recognised by a recipient? Volume sharing exists (`ALTER SHARE ... ADD VOLUME`) but FILE-column tables are not documented either way |
| Q6 | Databricks | Restating BLK-001 with the new stake **and the corrected scope**: registration is not the gate — credential vending is. `FILE EXTERNAL` makes that session policy the single thing standing between governed multimodal AI and NAS-resident data |

---

## Verification Status

### Verified in this environment (2026-08-12)

- FSx for ONTAP S3 AP: object tagging Put/Get/Delete, `x-amz-meta-*`, and write-time `x-amz-tagging` all work
- Limits match native Amazon S3: 10 tags, key 128, value 256
- Character set diverges: Latin-1 accepted, U+0100+ rejected for most strings, a stable but unexplained accepted subset
- Tags are file-scoped, not Access-Point-scoped
- Tags and user metadata are cleared by an object overwrite
- Presigned GET returns HTTP 200 — expected, because presigning is client-side and the request is a supported `GetObject`. "Not supported" in the table means do-not-rely-on, not will-fail
- `GetObjectTagging` median 52–59 ms (single caller, warm — sample run, not a benchmark)

### Verified on Databricks (2026-08-12)

Executed on a 14-day trial workspace via a serverless SQL warehouse (DBSQL 2026.20). Evidence: [`verification-pack/databricks/file-type/evidence/2026-08-12/`](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record.yaml).

| Claim | Result |
|---|---|
| FILE type is available | ✅ `FILE EXTERNAL` column created with **no Previews toggle touched**, on channel CURRENT. Do not generalise from one trial workspace |
| `FILE MANAGED` requires a FileSpace | ✅ Precise error: `FILE_TYPE_MISSING_FILESPACE.TABLE_PROPERTY_NOT_SET` |
| `list_files` → `FILE EXTERNAL` via CTAS | ✅ 3 rows; `DESCRIBE` reports the type as `file external` |
| A `FILE` value carries only the five documented fields | ✅ `uri`, `size`, `content_type` populated. **No tag or user-metadata field exists** — the central constraint of this document, now confirmed against a running engine |
| `checksum` is not always present | ✅ NULL when built by `list_files`; populated (`ETAG:…`) via `to_file` and for `FILE MANAGED`. Matches the documented rule |
| `ai_parse_document` accepts a `FILE` value | ✅ End to end on a PDF: `error_status: None`, one text element with correct content, bbox and confidence |
| FILE nested in `ARRAY` / `STRUCT` | ✅ |
| `PARTITIONED BY` a FILE column | ✅ Correctly rejected: `INVALID_PARTITION_COLUMN_DATA_TYPE` |
| **Q5: a FILE-column table can be shared via OpenSharing** | ✅ **Answered.** Both `FILE EXTERNAL` and `FILE MANAGED` tables were accepted into a share (`ENABLED`). Recipient-side reading is still untested |
| **No automatic GC of unreferenced managed files** | ✅ **Measured.** After unsharing and a successful `DROP TABLE`, all 3 managed files remained in the FileSpace. Storage grows silently until the manual sweep is run |
| `_object_metadata` returns null for UC-managed storage | ✅ **Measured.** Every field null over a managed volume — this is the fact the mutual exclusion in [§4.3](#43-the-mutual-exclusion) rests on |

Two sub-tests initially looked like findings and were not: a `DROP TABLE` refused because the table was still shared (so "files remained" proved nothing), and a malformed PDF fixture reported as a conversion failure. Both are recorded in the evidence with their invalid first attempt.

> **Escalated on the second run, once a contrast existed**: `GROUP BY` on a FILE column is *accepted*, though the reference says a FILE column cannot be a grouping expression. On the first run this was deliberately not raised — three files with one row each cannot distinguish correct grouping from coincidence. What made it reportable on 2026-08-12 was the contrast inside a single run: `GROUP BY` and `SELECT DISTINCT` are both accepted while `=` is refused with ``The `=` does not support ordering on type "FILE"`` and `ORDER BY` with the same class of error. Grouping and distinct both depend on the equality semantics the engine explicitly declines to provide. That is a statement about the type's operator surface rather than about row counts. Still treat the documented restriction as the contract and group by `uri`.

### The case that mattered most — answered 2026-08-12

`_object_metadata.tags` against an **FSx for ONTAP S3 Access Point** path was the question this repository actually needed answered. It was run on a purpose-built non-trial workspace in the same account and region as the file system, with a native-S3 control in the same session ([evidence](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)).

| Step | Result |
|---|---|
| `_object_metadata` over **native S3** (the control) | ✅ `tags`, `user_metadata`, `etag`, `mime_type`, `system_metadata` all populated and matching what the AWS CLI wrote |
| Storage credential → external location → external volume on the **S3 AP alias** | ✅ Created, with UC validation enabled |
| Reading `_object_metadata` / `list_files` / `to_file` through the S3 AP | ❌ 403 — and the cause is now known |

The cause is not a lack of support. AWS authorises an access-point request against the **access point ARN**, while the down-scoped session policy Unity Catalog vends is expressed in **bucket-style** ARNs, so the request is denied inside the session:

```
is not authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:<region>:<account>:accesspoint/<name>"
because no session policy allows the s3:ListBucket action
```

This reproduces **outside Databricks** using the credentials Unity Catalog vends, which is what rules out the network and the compute form. Seven other explanations were eliminated first; they are listed in the evidence record so they are not re-tested. There is no user-side workaround — the session policy is generated by Unity Catalog.

So the answer to "does `_object_metadata` read object tags through an S3 AP" is still unknown, but for a reason one step further along: the read never reaches the tag-reading code. The runner stays committed for the day the session policy is fixed: [`notebooks/10_file_type_object_metadata.py`](../../integrations/databricks/notebooks/10_file_type_object_metadata.py), cases `DBX-FILE-*` in [test-cases.yaml](../../verification-pack/databricks/test-cases.yaml).

| Item | Why it is still open |
|---|---|
| Whether `_object_metadata` would read tags through an S3 AP if the session policy were fixed | The read is refused before it reaches that code |
| VPC-origin Access Points, and Access Points with WINDOWS identity | One INTERNET-origin, UNIX-root Access Point was exercised |
| Q4: may a FileSpace be an **external** volume? | Not retested. Established separately: pointing the FileSpace at the volume holding the source files fails at `INSERT` with `Cannot get file metadata under managed storage`, so a dedicated volume is the working shape |
| Recipient-side reading of a shared FILE column | Needs a second party |
| Whether `GROUP BY` on a FILE column is *correct* at scale | Accepted on two rows; acceptance is not correctness |
| Whether the Previews toggle is ever required | Two independent workspaces did not need it. Two is not a sample, and this is an environment difference, not a documentation error |

### Not verified — ONTAP multiprotocol behaviour

| Item | Why it matters |
|---|---|
| Are object tags / user metadata visible from **NFS or SMB**? Do they survive a rewrite over NAS protocols? | The whole "onboard existing NAS assets" case depends on this. Tags being file-scoped is encouraging but not sufficient |
| Do tags survive SnapMirror, FlexClone, Snapshot restore, FabricPool tiering? | Determines whether tags are durable governance metadata or Access-Point-local convenience |
| Is the accepted-multibyte subset stable across ONTAP versions and regions? | Tested on one file system only |

---

## FAQ

**Q1. Does FILE type solve the Databricks × FSx for ONTAP governance gap?**

No, but the wall moved. `FILE EXTERNAL` requires a UC volume; a UC external volume on an S3 Access Point can be created and cannot be read (BLK-001, scope corrected 2026-08-12). `FILE MANAGED` works but copies the data. FILE type raises the value of fixing BLK-001; it does not fix it. The useful change is that the remaining gap is now a specific, reportable behaviour in credential vending rather than a blanket lack of support.

**Q2. Can object tags be used for access control?**

No. They are mutable by anyone with `s3:PutObjectTagging` and are cleared by an object overwrite. Use them for discovery and coarse filtering; keep enforcement on ONTAP ACL, the Access Point policy, IAM, and — for staged data — UC row filters. Same boundary as [S3 Annotations](./s3-annotations-governance-evaluation.md).

**Q3. Can Japanese be stored in object tags on an FSx for ONTAP S3 AP?**

Not reliably. Most multibyte strings are rejected with `InvalidTag`; a few are accepted, deterministically but unpredictably. Restrict tags to ASCII and put Japanese text in the metadata table.

**Q4. Are S3 Annotations an alternative to tags here?**

No. Annotations are not supported on Access Points attached to FSx for ONTAP volumes, and they target native general-purpose buckets only. See [s3-annotations-governance-evaluation](./s3-annotations-governance-evaluation.md). Tags are the mechanism that works directly on the Access Point.

**Q5. Should the Iceberg metadata catalog be migrated to FILE type?**

Not now. FILE type is Delta-only, so it is not a drop-in for an Iceberg-on-S3-Tables catalog, and it is Beta with no automatic garbage collection. The designs agree conceptually, which is the useful part. Revisit if BLK-001 is resolved and FILE type reaches GA with Iceberg support.

**Q6. Is FILE type an open format?**

Not today. The announcement states that support in Parquet, Delta Lake, Iceberg and Spark is being built with the community — a stated direction, not a current property. Treat portability as unavailable until the specs land.

---

## References

**Databricks (Public)**
- [Introducing FILE type: a native column type for multimodal data](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data)
- [FILE type and unstructured data](https://docs.databricks.com/aws/en/unstructured/file) ([日本語](https://docs.databricks.com/aws/ja/unstructured/file))
- [FILE type reference](https://docs.databricks.com/aws/en/sql/language-manual/data-types/file-type) · [Ingest files as the FILE type](https://docs.databricks.com/aws/en/ingestion/file) · [Tutorial: file-processing pipeline](https://docs.databricks.com/aws/en/ldp/tutorial-file-pipelines)
- [Object metadata column (`_object_metadata`)](https://docs.databricks.com/aws/en/ingestion/object-metadata-column) · [list_files](https://docs.databricks.com/aws/en/sql/language-manual/functions/list_files)
- [ABAC core concepts](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/core-concepts) · [Apply tags to securable objects](https://docs.databricks.com/aws/en/database-objects/tags)

**AWS (Public)**
- [Access point compatibility (FSx for ONTAP)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) · [Tagging a file using an S3 access point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/add-tag-set-ap.html)
- [S3 object tagging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-tagging.html) · [PutObjectTagging](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObjectTagging.html)

**This repository**
- Evidence: [s3ap-object-tagging (2026-08-12)](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml) · Reproduce: [`probe_s3ap_object_tagging.py`](../../shared/scripts/probe_s3ap_object_tagging.py)
- [Blocker tracker](./blocker-tracker.md) — BLK-001, BLK-002, BLK-003
- [Verification runbook](./databricks-verification-runbook.md) — reproduce this in your own account: CloudFormation, probe script, verdicts, teardown order
- [Databricks integration README](../../integrations/databricks/README.md) · [FSx for ONTAP → Databricks Unity Catalog guide](./fsx-ontap-to-databricks-unity-catalog-guide.md)
- [Iceberg metadata catalog](../../integrations/iceberg-metadata-catalog/README.md) · [iceberg-metadata-catalog (docs)](./iceberg-metadata-catalog.md)
- [Unstructured data access](./unstructured-data-access.md) · [Zero-copy media governance](./zero-copy-media-governance.md)
- [S3 Annotations / Metadata evaluation](./s3-annotations-governance-evaluation.md) · [OpenSharing and Unity Catalog explained](./opensharing-and-unity-catalog-explained.md)
- [DataSync to S3 guide](./datasync-to-s3-guide.md) — the recommended interim path under BLK-001
