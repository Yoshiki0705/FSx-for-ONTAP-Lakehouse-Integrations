# Snowflake Integration

🌐 **English** | [日本語](docs/ja/README.md)

> **Validation Status: ✅ Verified for read and governance paths (with `AWS_ACCESS_POINT_ARN`)**
>
> Snowflake can query FSx for ONTAP S3 Access Point data when the external stage is configured with `AWS_ACCESS_POINT_ARN`.
>
> **Verified**: LIST, SELECT, External Table, COPY INTO load, Directory Table, Governance Tags.
> Added 2026-08-06: JSON/Avro/ORC reads, Snowpark `SnowflakeFile.open`, a Dynamic Table
> over data landed from the Access Point, and `COPY INTO` a Managed Iceberg Table on an
> External Volume — end to end
> ([evidence](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml)).
>
> **Not validated or not suitable**: Snowpipe AUTO_REFRESH, Iceberg write-back to the
> Access Point, transactional table writes, presigned URL as a governed production path,
> COPY INTO 64-day deduplication (needs 64 days of elapsed time), Horizon Catalog
> enforcement on external engines, PrivateLink (needs Business Critical).
>
> **Unload is a trap, not a no-op.** `COPY INTO @stage` against an AP-backed stage is not
> refused: the object is written and is intact, then the statement fails with
> `Remote upload failed checksum validation` because FSx for ONTAP reports encryption as
> `aws:fsx`. A complete object is left behind while the caller is told the write failed.
> If you have tried this, list the target prefix and remove orphans. See
> [BLK-009](../../docs/en/blocker-tracker.md).
>
> **Dynamic Table constraint**: a Dynamic Table cannot select from an EXTERNAL TABLE, so
> the stage has to be landed into a standard table first.
>
> **Ingestion, specifically**: Snowpipe is event-driven and cannot be scheduled.
> For scheduled ingestion use a **Snowflake Task running COPY INTO** — a
> different feature, and one that is verified. The Lambda-polling workaround that
> synthesizes S3 notifications is verified on the AWS side only, and six defects
> were found in its published artifacts. See
> [Snowpipe Verification Results](docs/en/snowpipe-verification-results.md).
>
> **ListObjectsV2 latency correction**: earlier revisions of this repository
> quoted 30-80x native S3. Re-measured 2026-08-05 at **1.3-1.4x** for up to 5,000
> objects; the 30-80x figure did not reproduce and has been withdrawn
> ([BLK-006](../../docs/en/blocker-tracker.md)).

## Start here

[Reading FSx for ONTAP files from Snowflake and writing Iceberg tables](../../docs/en/snowflake-iceberg-setup.md) walks through the whole path with
the parameters explained, common failures, and teardown. It is the fastest way
to a working setup if this is your first time.

| Task | Where |
|---|---|
| Read access to an Access Point | [`template.yaml`](./template.yaml), then [`scripts/update_trust_policy.sh`](./scripts/update_trust_policy.sh) |
| Write Iceberg tables | [`template-external-volume.yaml`](./template-external-volume.yaml), driven by [`scripts/setup_external_volume.sh`](./scripts/setup_external_volume.sh) |
| Check for objects a failed unload left behind | [`shared/scripts/check_orphaned_unload_objects.py`](../../shared/scripts/check_orphaned_unload_objects.py) |

## Observed Results

| Operation | Without `AWS_ACCESS_POINT_ARN` | With `AWS_ACCESS_POINT_ARN` |
|---|:---:|:---:|
| Storage Integration | ✅ | ✅ |
| Stage creation | ✅ | ✅ |
| LIST @stage | ✅ | ✅ |
| SELECT @stage (Parquet) | ❌ Access Denied | ✅ |
| SELECT @stage (CSV) | ❌ | ✅ |
| External Table | ❌ | ✅ |
| COPY INTO (load) | ❌ | ✅ |
| Governance Tags | N/A | ✅ |
| Snowpipe (auto-ingest) | ❌ | ❌ (S3 Event Notifications not supported) |
| Iceberg Table write | ❌ | ❌ (conditional writes not supported) |
| GET_PRESIGNED_URL | ✅ (observed) | ✅ |

## Partner Decision Card (Quick Reference)

| Requirement | Status | Action |
|---|:---:|---|
| Query NAS files from Snowflake | ✅ | Set `AWS_ACCESS_POINT_ARN` on stage |
| Governed external tables | ✅ | Create External Table + apply tags |
| Unstructured data catalog | ✅ | Enable Directory Table + manual REFRESH |
| AI text processing (OCR, summarize, translate) | ✅ | Cortex functions on External Table — no copy needed |
| AI Vision (image analysis) | ✅ | COPY FILES to internal stage → TO_FILE workaround |
| AI RAG / Semantic Search (Cortex Search) | ✅ | External Table → COPY INTO → Cortex Search Service (198ms query) |
| Automated enrichment (Dynamic Table) | ✅ | External Table → Dynamic Table (TARGET_LAG = '1 hour', FULL refresh) — confirmed May 2026 |
| Share curated data with partners | ✅ | External Table or Dynamic Table → Snowflake Data Sharing |
| Open format for multi-engine access | ✅ | COPY INTO → Managed Iceberg Table → Databricks/Athena can read — confirmed May 2026 |
| Scheduled ingestion (every N minutes) | ✅ | Snowflake Task + COPY INTO — Snowpipe itself cannot be scheduled |
| Real-time auto-ingest (Snowpipe) | ❌ | No S3 Event Notifications. Synthesized-notification workarounds are [unverified end-to-end](docs/en/snowpipe-verification-results.md) |
| Iceberg write-back on FSx for ONTAP S3 AP | ❌ | Use native S3 for transactional writes |

> Choose Snowflake when governed external tables, AI functions, data sharing, or multi-engine Iceberg interoperability are required. Choose Athena when lightweight AWS-native serverless SQL over NAS data is sufficient.

### Partner Conversation Script

**For customers with NAS data + AI requirements:**
> "Snowflake can query and run AI on your FSx for ONTAP NAS data directly — without copying. Eight out of ten tested Cortex AI functions work on FSx data, including OCR, summarization, translation, and semantic search (Cortex Search at 198ms query latency). For image analysis, a one-step staging workaround enables Vision AI. All with full governance: tags, masking, and row-level security on the same data your NFS/SMB users access."

**For customers concerned about data movement:**
> "With External Tables, your data stays on FSx for ONTAP. No copy to Snowflake storage. Same files accessible via NFS, SMB, and S3 AP simultaneously. ONTAP features like Snapshot, FlexClone, and SnapLock continue to protect the data. Snowflake adds governance and AI on top — without owning the storage."

**For customers evaluating Snowflake vs Databricks for NAS integration:**
> "Snowflake's External Table with `AWS_ACCESS_POINT_ARN` provides governed read access today — including AI functions. Databricks Unity Catalog currently cannot create tables on S3 Access Points due to a session policy limitation. For governed analytics on NAS data, Snowflake is the validated path."

> **Note (using Databricks via standard-S3 staging)**: the above assumes querying an FSx for ONTAP S3 Access Point directly. With Databricks, staging to a standard S3 bucket makes unstructured-data AI work under UC governance (`ai_query` Vision, `ai_parse_document` OCR, `FILE EXTERNAL`, AI Functions, Genie) — verified in the [standard-S3 PoC](../../docs/en/databricks-standard-s3-unstructured-poc.md) ([日本語](../../docs/ja/databricks-standard-s3-unstructured-poc.md)). An organization using both engines can choose by use: zero-copy in-place querying (Snowflake External Table) versus governed processing after staging to standard S3 (either engine)."

### Customer Qualification Questions

Use these questions to determine the right architecture pattern:

1. **Data residency**: Must the data remain on FSx for ONTAP, or can it be copied to Snowflake-managed storage?
   - Stay on FSx → External Table pattern
   - Can copy → COPY INTO for maximum performance

2. **AI/ML requirements**: Do you need text AI (summarize, translate, OCR) or Vision AI (image analysis)?
   - Text AI only → External Table (direct, no copy)
   - Vision AI needed → Hybrid pattern (External Table + COPY FILES for images)

3. **Query performance**: Is sub-second query response required, or is seconds-level acceptable?
   - Sub-second → COPY INTO internal table (micro-partitions, clustering)
   - Seconds acceptable → External Table (S3 AP latency)

4. **Compliance constraints**: Are there regulatory requirements (HIPAA, SOX, GDPR) that restrict data movement?
   - Yes → External Table + SnapLock + FPolicy audit (data never leaves FSx)
   - No → Choose based on performance/cost trade-off

5. **Multi-protocol access**: Do NFS/SMB users need to access the same data that Snowflake queries?
   - Yes → External Table (zero-copy, multi-protocol)
   - No → Either pattern works

## Overview

Integrate Amazon FSx for NetApp ONTAP (FSx for ONTAP) S3 Access Points with Snowflake
External Stages, using them as the storage layer for External Tables and Iceberg Tables.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                              AWS Account                              │
│                                                                       │
│  ┌─────────────────┐     ┌──────────────────┐     ┌───────────────┐   │
│  │ FSx for ONTAP   │     │ FSx for ONTAP    │     │ IAM Role      │   │
│  │ (NFS Volume)    │◀───▶│ S3 Access Point  │◀────│ (Snowflake    │   │
│  │                 │     │ (Internet origin)│     │  AssumeRole)  │   │
│  └─────────────────┘     └─────────┬────────┘     └─────────┬─────┘   │
│                                    │                        │         │
└────────────────────────────────────┼────────────────────────┼─────────┘
                                     │ S3 API                 │ STS
                                     ▼                        ▼
                          ┌────────────────────────────────────────────┐
                          │  Snowflake (SaaS — ap-northeast-1)         │
                          │                                            │
                          │  Storage Integration → External Stage      │
                          │       → External Table / Iceberg Table     │
                          │       → Snowpipe (via FPolicy + SNS)       │
                          └────────────────────────────────────────────┘
```

**Key Architecture Points:**
- FSx for ONTAP S3 Access Point is created via `aws fsx create-and-attach-s3-access-point` (not CloudFormation `AWS::S3::AccessPoint`)
- Network Origin is **Internet** (Snowflake is SaaS, so VPC-scoped is not usable)
- IAM Role trust policy requires two-phase setup (Snowflake AWS Account ID + External ID)

## FSx for ONTAP S3 Access Point — Supported S3 Operations

| Operation | Supported | Notes |
|-----------|-----------|-------|
| ListObjectsV2 | ✅ | High latency (tens of seconds to minutes) |
| GetObject | ✅ | |
| PutObject | ✅ | Max 50 GB |
| DeleteObject | ✅ | |
| HeadObject | ✅ | |
| **Pre-signed URL** | ✅ | AWS docs say unsupported, but works in practice |
| **TO_FILE / FILE data type** | ❌ | "Remote file not found" — Cortex multimodal cannot resolve S3 AP files |
| **PARSE_DOCUMENT** | ✅ | Uses different file access mechanism (stage path string) |
| S3 Event Notifications | ❌ | Use FPolicy as alternative |
| Object Versioning | ❌ | |

> ℹ️ **Note**: AWS documentation states Pre-signed URLs are "Not supported," but testing confirms `GET_PRESIGNED_URL()` works correctly with FSx for ONTAP S3 AP.

> ⚠️ **TO_FILE limitation**: Snowflake's `TO_FILE()` function (used by multimodal AI_COMPLETE/Vision AI) cannot resolve files on FSx for ONTAP S3 AP external stages. Workaround: `COPY FILES` to an unencrypted internal stage (SNOWFLAKE_SSE), then use `TO_FILE(BUILD_SCOPED_FILE_URL(@internal_stage, path))`.

## Data Format Support

| Format | Read | Write | Table Type |
|--------|------|-------|------------|
| Parquet | ✅ | ✅ | External Table / Iceberg |
| CSV | ✅ | ✅ | External Table |
| JSON | ✅ | ✅ | External Table |
| ORC | ✅ | ❌ | External Table |
| Avro | ✅ | ❌ | External Table |
| Iceberg | ✅ | ✅ | Iceberg Table |

## Internal Table vs External Table — Design Guide

Understanding the difference between internal (managed) tables and external tables is critical for architecture decisions when integrating FSx for ONTAP with Snowflake.

> **Key concepts**: [External Stage](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage) (S3/cloud storage) | [Internal Stage](https://docs.snowflake.com/en/user-guide/data-load-local-file-system-create-stage) (Snowflake-managed) | [External Table](https://docs.snowflake.com/en/user-guide/tables-external) (reads from stage) | [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table) (loads to internal table)
>
> For analytics and AI/ML-specific implications (which Cortex functions work on each pattern), see the [Analytics & AI Demo Guide](docs/en/ai-demo-guide.md#cortex-ai-comprehensive-compatibility-matrix).

### Comparison Matrix

| Aspect | External Table (on FSx for ONTAP S3 AP) | Internal Table (COPY INTO) |
|---|---|---|
| **Data location** | Remains on FSx for ONTAP (zero-copy) | Copied into Snowflake-managed storage |
| **Data ownership** | Customer owns and manages data lifecycle | Snowflake manages storage lifecycle |
| **DROP TABLE behavior** | Data NOT deleted (only metadata removed) | Data IS deleted from Snowflake storage |
| **Multi-protocol access** | Same data via NFS/SMB/S3 AP simultaneously | Only accessible via Snowflake |
| **Data freshness** | Real-time (reads current file state) | Stale until next COPY INTO / Snowpipe |
| **Query performance** | Slower (S3 API latency, no micro-partitions) | Faster (optimized micro-partitions, pruning) |
| **Governance (Tags, Masking)** | ✅ Full support (Enterprise Edition) | ✅ Full support |
| **Time Travel** | ❌ Not available | ✅ Available (up to 90 days) |
| **Clustering / Optimization** | ❌ Not available | ✅ AUTO_CLUSTERING, OPTIMIZE |
| **Cortex AI (text functions)** | ✅ Direct (SUMMARIZE, TRANSLATE, etc.) | ✅ Direct |
| **Cortex AI (Vision/TO_FILE)** | ❌ TO_FILE blocked on FSx for ONTAP S3 AP | ✅ Works on internal stage |
| **ONTAP features preserved** | ✅ Snapshot, FlexClone, Dedup, FPolicy | ❌ Data is outside ONTAP |
| **Storage cost** | FSx for ONTAP only (no Snowflake storage) | FSx + Snowflake storage (duplicate) |
| **Compliance (data residency)** | ✅ Data stays on FSx (controlled location) | ⚠️ Data in Snowflake-managed storage |

### When to Use External Table (Zero-Copy Pattern)

```
FSx for ONTAP ──S3 AP──▶ Snowflake External Table ──▶ Query / Governance / AI
     │
     └── Same data accessible via NFS/SMB (no copy)
```

**Choose External Table when:**
- Data must remain on FSx for ONTAP (compliance, data residency, multi-protocol access)
- Real-time access to current file state is required
- ONTAP features (Snapshot, FlexClone, FPolicy, SnapLock) must be preserved
- Storage cost optimization is a priority (avoid duplicate storage)
- Data is read-heavy with infrequent updates
- Multiple consumers (NFS users, Snowflake, Athena, etc.) need the same data

**Limitations:**
- No Time Travel, no clustering, no micro-partition optimization
- Query performance depends on FSx for ONTAP S3 AP latency and file layout
- TO_FILE (Vision AI) does not work directly — requires COPY FILES workaround
- AUTO_REFRESH not available (manual REFRESH or scheduled Task required)

### When to Use Internal Table (COPY INTO Pattern)

```
FSx for ONTAP ──S3 AP──▶ COPY INTO ──▶ Snowflake Internal Table ──▶ Query / AI / Time Travel
                                              │
                                              └── Optimized micro-partitions, full Snowflake features
```

**Choose Internal Table when:**
- Maximum query performance is required (micro-partitions, pruning, clustering)
- Time Travel (point-in-time queries, UNDROP) is needed
- Vision AI / TO_FILE is required without workaround
- Data transformation (ELT) is part of the pipeline
- Snowflake-native features (streams, tasks, dynamic tables) are needed
- Data can tolerate staleness between COPY INTO runs

**Limitations:**
- Data is duplicated (FSx + Snowflake storage cost)
- Data freshness depends on COPY INTO frequency
- ONTAP features (Snapshot, FlexClone) no longer apply to the copy
- Data residency shifts to Snowflake-managed storage

### Hybrid Pattern (Recommended for AI/ML Workloads)

```
FSx for ONTAP
     │
     ├── External Table (structured data) ──▶ Text AI (SUMMARIZE, TRANSLATE, SENTIMENT)
     │                                        Governance (Tags, Masking, Row Policy)
     │
     └── COPY FILES → Internal Stage ──▶ Vision AI (COMPLETE multimodal)
                                          Document AI (when TO_FILE is needed)
```

**Best practice**: Use External Tables for governed read access and text-based AI. Use COPY FILES to internal stage only when Vision AI (TO_FILE) is required.

### Decision Flowchart

```
Q: Does the data need to stay on FSx for ONTAP?
├── YES → External Table
│         Q: Do you need Vision AI on images?
│         ├── YES → COPY FILES to internal stage for Vision AI only
│         └── NO → External Table is sufficient (text AI works directly)
│
└── NO → COPY INTO internal table
          Q: Do you need real-time freshness?
          ├── YES → Snowpipe (if S3 bucket) or scheduled COPY INTO (if FSx for ONTAP S3 AP)
          └── NO → Batch COPY INTO on schedule
```

### Cost Comparison

| Pattern | FSx Storage | Snowflake Storage | Snowflake Compute | Total Cost |
|---|---|---|---|---|
| External Table only | ✅ (existing) | None | Query time only | 💰 Minimal |
| COPY INTO (full) | ✅ (existing) | + full copy | Query + COPY time | 💰💰💰 Highest |
| Hybrid (External + selective COPY) | ✅ (existing) | + images only | Query + selective COPY | 💰💰 Moderate |

### Industry-Specific Recommendations

| Industry | Recommended Pattern | Rationale | PoC Success Criteria |
|---|---|---|---|
| **Manufacturing** | External Table + PARSE_DOCUMENT (OCR) | Data stays on FSx; inspection images processed in place | OCR extracts text from 10+ inspection images in <10s each |
| **Financial Services** | Hybrid (External Table + COPY INTO for Cortex Search) | Compliance requires data on FSx; RAG needs internal table | Cortex Search returns relevant compliance docs in <500ms |
| **Healthcare** | External Table + SnapLock | PHI must not leave controlled storage; immutable audit | SELECT on External Table succeeds with governance tags applied |
| **Media / Entertainment** | External Table + COPY FILES (Vision AI) | Large media files stay on FSx; selective staging for AI | Vision AI describes image content correctly via staging path |
| **Cross-Industry Analytics** | COPY INTO (full) | Maximum query performance; data duplication acceptable | COPY INTO completes in <10s for representative dataset |

### AI Readiness Score

| Pattern | Governance | Performance | AI Capability | Cost | Operational Simplicity | Overall |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **External Table only** | ★★★★☆ | ★★☆☆☆ | ★★★★☆ (text AI direct) | ★★★★★ | ★★★★☆ | **4.0** |
| **COPY INTO (full)** | ★★★★★ | ★★★★★ | ★★★★★ (all AI) | ★★☆☆☆ | ★★★☆☆ | **3.8** |
| **Hybrid (External + COPY for Vision)** | ★★★★☆ | ★★★☆☆ | ★★★★★ (all AI) | ★★★★☆ | ★★★☆☆ | **3.8** |

- **Governance**: Tag-based masking, row policies, audit trail
- **Performance**: Query latency, optimization features
- **AI Capability**: How many Cortex functions work without workaround
- **Cost**: Storage efficiency (avoid duplication)
- **Operational Simplicity**: Setup and maintenance effort

> **Scoring methodology**: Each dimension rated by the author based on validated evidence in this repository. This is not an official AWS or Snowflake assessment. Scores reflect observed capabilities in one test environment (Snowflake Standard, ap-northeast-1).

> **How to use this score**: Use Overall score as a starting point for pattern selection. Scores ≥ 4.0 indicate strong fit for governed production workloads. Scores 3.5–3.9 indicate viable paths with trade-offs. Scores < 3.0 indicate PoC-only paths.

**When to choose which:**
- Choose **External Table only** (4.0) when data must stay on FSx and text-based AI is sufficient
- Choose **COPY INTO (full)** (3.8) when maximum performance, Time Travel, and Vision AI are required
- Choose **Hybrid** (3.8) when both data residency and full AI capability are needed

### References

- [Snowflake External Tables](https://docs.snowflake.com/en/user-guide/tables-external)
- [COPY INTO table](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)
- [COPY FILES](https://docs.snowflake.com/en/sql-reference/sql/copy-files)
- [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables)
- [Time Travel](https://docs.snowflake.com/en/user-guide/data-time-travel)

## Unstructured Data Support

| Format | Access Method | Use Case |
|--------|--------------|----------|
| Images (JPEG, PNG, TIFF) | GET_PRESIGNED_URL / BUILD_SCOPED_FILE_URL | Thumbnail generation, ML inference, quality inspection |
| Video (MP4, MOV) | GET_PRESIGNED_URL | Streaming, frame extraction |
| Documents (PDF, DOCX) | GET_PRESIGNED_URL / Snowpark File Access | Text extraction, RAG, document processing |
| Audio (WAV, MP3) | GET_PRESIGNED_URL | Transcription, speech analytics |
| Binary / Archives | GET_PRESIGNED_URL | Download, transfer |

**How to access unstructured data:**
1. **Directory Table** — Catalog all files with metadata (path, size, last_modified)
2. **GET_PRESIGNED_URL()** — Generate time-limited download URLs for applications
3. **BUILD_SCOPED_FILE_URL()** — Generate Snowflake-proxied secure URLs
4. **Snowpark File Access** — Process files directly in UDFs/UDTFs (requires validation)

```sql
-- Enable Directory Table for file catalog
ALTER STAGE fsxn_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_stage REFRESH;

-- Query file catalog
SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED FROM DIRECTORY(@fsxn_stage);

-- Generate download URL (valid for 1 hour)
SELECT GET_PRESIGNED_URL(@fsxn_stage, 'images/photo001.jpg', 3600);
```

> **Note**: AUTO_REFRESH is not available because FSx for ONTAP S3 AP does not support S3 Event Notifications. Use `ALTER STAGE REFRESH` manually or on a schedule (via Snowflake Task).

## ONTAP Value for Snowflake

| ONTAP Feature | Snowflake Benefit | Reference |
|---|---|---|
| **FlexCache** | Cache data across regions/sites for low-latency Snowflake access; reduce WAN bandwidth | [FlexCache docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | Immutable data protection for compliance — admin cannot delete during retention period | [SnapLock on FSx](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI** | AI-powered ransomware detection; auto-snapshot before damage spreads to analytics data | [ARP on FSx](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | Instant staging environment with production data (zero-copy) | [FlexClone docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | Recover data beyond Snowflake Time Travel retention; version control for data pipelines | [Snapshot docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | Auto-tier historical partitions to S3 (transparent to Snowflake queries) | [FabricPool docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **Storage Efficiency** | Up to 65% savings via deduplication + compression + compaction on file data | [Storage efficiency](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | Cross-region data availability for Snowflake replication and DR | [SnapMirror docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **Multi-protocol** | NFS (ingest) + SMB (Windows users) + S3 AP (Snowflake) — same data, no copy | [Multi-protocol](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | Event-driven Snowpipe ingestion via Lambda (<30s latency) | [FPolicy docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

## Governance & AI/ML Guides

| Guide | Description |
|---|---|
| [Analytics & AI Demo Guide](docs/en/ai-demo-guide.md) | Analytics & AI capabilities (Cortex AI, OCR, Vision), industry use cases, ONTAP value |
| [Internal Table Ingestion Guide](docs/en/internal-table-ingestion-guide.md) | When COPY INTO is required — feature availability matrix (External vs Internal Table), ingestion patterns, dual management challenges |
| [Governance: Tags & Data Protection](docs/en/ai-demo-guide.md#governance-tags--data-protection) | Tag-based masking, row access policies, edition requirements |
| [Governance: File-Level Access Control](docs/en/ai-demo-guide.md#file-level-access-control-ontap-native-layer) | ONTAP dual-layer auth, FPolicy, per-consumer S3 AP isolation |
| [Integration: ONTAP × Snowflake Tags](docs/en/ai-demo-guide.md#integration-ontap-file-level-control--snowflake-tag-governance) | Combined governance matrix, design patterns, flow diagram |

## Snowpipe & Ingestion Formats

### Snowpipe Supported Formats

| Format | Snowpipe | COPY INTO | External Table | Notes |
|---|:---:|:---:|:---:|---|
| CSV | ✅ | ✅ | ✅ | Delimiter, header, encoding options |
| JSON | ✅ | ✅ | ✅ | Nested, semi-structured |
| Parquet | ✅ | ✅ | ✅ | Column pruning, predicate pushdown |
| Avro | ✅ | ✅ | ✅ | Schema evolution supported |
| ORC | ✅ | ✅ | ✅ | Read-only |
| XML | ✅ | ✅ | ✅ | Native support |

**Formats NOT directly supported by Snowpipe/COPY INTO (require alternative):**

| Format | Alternative Method | Considerations |
|---|---|---|
| Images (JPEG, PNG, TIFF) | Directory Table + GET_PRESIGNED_URL / PARSE_DOCUMENT (OCR) | Use Cortex AI for text extraction; Vision AI via COPY FILES workaround |
| Video (MP4, MOV) | Directory Table + GET_PRESIGNED_URL → external processing | Stream via CloudFront or process frames externally |
| Audio (WAV, MP3) | Directory Table + GET_PRESIGNED_URL → transcription service | Use external ASR (Bedrock, Whisper) or future AI_TRANSCRIBE |
| Documents (PDF, DOCX) | PARSE_DOCUMENT (direct on stage) | OCR/LAYOUT mode extracts text directly from FSx for ONTAP S3 AP |
| Binary / Archives | GET_PRESIGNED_URL → external processing | Download and process outside Snowflake |
| Database exports | Custom parsing via Snowpark UDF | Parse SQL/dump format into structured data |

### Data Ingestion Alternatives for FSx for ONTAP (When Snowpipe Is Unavailable)

Since FSx for ONTAP S3 AP does not support S3 Event Notifications, standard Snowpipe auto-ingest is not available. Use these alternatives:

| Method | Description | Latency | Complexity | Reference |
|---|---|---|---|---|
| **FPolicy → Lambda → SNS → Snowpipe** | FPolicy detects file changes → Lambda sends SNS notification → Snowpipe REST API triggers load | Seconds (<30s) | Medium | [FPolicy docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| **Snowflake Task + COPY INTO** | Scheduled Task runs COPY INTO from stage at intervals | Minutes (configurable) | Low | [Tasks docs](https://docs.snowflake.com/en/user-guide/tasks-intro) |
| **Snowflake Task + ALTER STAGE REFRESH** | Scheduled Task refreshes Directory Table metadata | Minutes | Low | [Tasks docs](https://docs.snowflake.com/en/user-guide/tasks-intro) |
| **External function + Lambda** | Snowflake calls Lambda to check for new files | On-demand | Medium | [External functions](https://docs.snowflake.com/en/sql-reference/external-functions) |
| **AWS Glue → Snowflake** | Glue reads FSx for ONTAP S3 AP → writes to Snowflake via connector | Minutes | Medium | [Glue + FSx tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| **Snowpipe REST API (manual trigger)** | Application calls Snowpipe REST API with file list | Seconds | Low | [Snowpipe REST](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-rest-overview) |

> **FPolicy throughput note**: FPolicy introduces minimal latency on the NFS/SMB I/O path (typically <1ms per operation for passthrough mode). However, under high-frequency file write workloads (thousands of files/second), validate throughput impact on the FSx for ONTAP file system before production deployment.

**Recommended production pattern:**
```
FSx for ONTAP ──FPolicy──▶ Lambda ──▶ SNS ──▶ Snowpipe REST API ──▶ COPY INTO target table
     │                                              │
     └── NFS/SMB users access same data             └── Snowflake governance on loaded data
```

**Simple alternative (no FPolicy):**
```
Snowflake Task (every 5 min) ──▶ COPY INTO from @fsxn_stage
                                      │
                                      └── Tracks loaded files automatically (COPY history)
```

## Quick Start

```bash
# 1. Create FSx for ONTAP S3 Access Point (prerequisite)
aws fsx create-and-attach-s3-access-point \
  --name snowflake-ap --type ONTAP \
  --ontap-configuration 'VolumeId=fsvol-xxx,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'

# 2. Deploy IAM Role via CloudFormation
cp params.example.json params.json  # Edit: set S3AccessPointArn
./deploy.sh

# 3. Run SQL scripts in Snowflake (01 → 09)
```

## Files

| File | Description |
|------|-------------|
| `template.yaml` | CloudFormation: IAM Role for Snowflake Storage Integration |
| `deploy.sh` | Deployment script (Phase 1 + Phase 2) |
| `params.example.json` | Parameter template |
| `scripts/update_trust_policy.sh` | Phase 2: Update trust with Snowflake info |
| `scripts/configure_fpolicy.py` | ONTAP FPolicy configuration |
| `sql/01-10` | Snowflake SQL setup scripts |
| `docs/ja/` | Japanese documentation |
| `docs/en/` | English documentation |
| `tests/` | Integration tests |

## Known Limitations

> ⚠️ **Important premise**: Snowflake does NOT officially document FSx for ONTAP S3 Access Points as a supported External Stage storage backend. Our validation confirms that read and governance operations work when `AWS_ACCESS_POINT_ARN` is configured, but this is NOT an officially supported configuration by Snowflake. Consult Snowflake Support before production use.

The following limitations are observed when using FSx for ONTAP S3 AP as a Snowflake External Stage:

1. **FSx for ONTAP S3 AP listing latency**: measured at 1.3-1.4x native S3 for up to 5,000 objects (2026-08-05) and 0.7x at 10,000 and 20,000 objects (2026-09-14), so listing is not a practical constraint at that scale. Behaviour above 20,000 objects per directory is unmeasured — consolidate files and partition the key space for large datasets. The earlier "tens of seconds to minutes" and "30-80x" claims did not reproduce ([evidence](../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml))
2. **Pre-signed URL (FSx for ONTAP S3 AP limitation)**: AWS FSx for ONTAP S3 AP documentation states Pre-signed URLs are "Not supported," but Snowflake's `GET_PRESIGNED_URL()` function generates working download URLs in practice. Use at own risk as this is outside official FSx for ONTAP S3 AP support
3. **S3 Event Notifications not supported (FSx for ONTAP S3 AP limitation)**: FSx for ONTAP S3 AP does not support S3 Event Notifications, so Snowpipe auto-ingest trigger is not possible (use FPolicy + Lambda as alternative)
4. **Max upload size**: 50 GB (Multipart Upload supported)
5. **AUTO_REFRESH unavailable**: Depends on S3 Event Notifications which are not supported. Use manual `ALTER STAGE REFRESH` or schedule via Snowflake Task
6. **TO_FILE / FILE data type (Snowflake limitation)**: `TO_FILE()` returns "Remote file not found" on FSx for ONTAP S3 AP external stages — Vision AI cannot be used directly. Workaround: `COPY FILES` to unencrypted internal stage (SNOWFLAKE_SSE), then use `TO_FILE(BUILD_SCOPED_FILE_URL(@internal_stage, path))`
