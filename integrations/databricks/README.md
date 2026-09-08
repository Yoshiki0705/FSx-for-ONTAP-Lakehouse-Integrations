# Databricks Integration

🌐 **English** | [日本語](docs/ja/README.md)

> **Validation Status: Experimental — S3 AP Not Supported by UC (Confirmed)**
> - Unity Catalog External Locations do not currently support S3 Access Points as storage targets (confirmed by Databricks Support, May 2026). The `access_point` field was never released as GA and has been removed from documentation.
> - The partial success observed (root-level listing, explicit file read) is "a side effect of incomplete internal handling, not a supported code path."
> - Instance Profile + boto3 succeeded only as a controlled driver-node PoC.
> - Kernel NFS mount from Databricks Dedicated cluster was blocked by a local runtime boundary in the tested environment.
> - This repository does not claim production support for Databricks + FSx S3 Access Points.
>
> For production Delta Lake tables, use [Databricks-supported cloud storage patterns](https://docs.databricks.com/aws/en/connect/storage/amazon-s3). S3 Access Point ARNs are not a supported storage target for UC External Locations.
>
> **Partner / Marketplace scope**: This repository is not a Databricks Marketplace listing, certified integration, or production-ready partner solution. It is an experimental validation package intended to document observed behavior and collect reproducible evidence.

## Overview

> 📖 **Looking for a comprehensive connection guide?** See the [FSx for ONTAP → Databricks Unity Catalog Connection Guide](../../docs/en/fsx-ontap-to-databricks-unity-catalog-guide.md) ([日本語](../../docs/ja/fsx-ontap-to-databricks-unity-catalog-guide.md)) for all available paths, file format support, FAQ, and recommendations. This README documents the S3 Access Point validation experiment specifically.

This is an experimental validation package exploring integration paths between
Amazon FSx for NetApp ONTAP (FSx for ONTAP) and Databricks via S3 Access Points.

Some README sections describe intended integration patterns, while the
[Verification Status](#verification-status-2026-05-17) section documents the
current validation results and observed platform boundaries.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                              AWS Account                              │
│                                                                       │
│  ┌────────────────────┐                                               │
│  │  Databricks        │                                               │
│  │  Unity Catalog     │                                               │
│  │  ┌──────────────┐  │     ┌──────────────┐     ┌───────────────┐    │
│  │  │ External     │  │     │ S3 Access    │     │ FSx for ONTAP │    │
│  │  │ Location     │──┼────▶│ Point        │────▶│ Volume        │    │
│  │  │              │  │     │ (VPC-scoped) │     │ (S3 protocol) │    │
│  │  └──────────────┘  │     └──────────────┘     └───────────────┘    │
│  │  ┌──────────────┐  │            │                    │             │
│  │  │ Storage      │  │     ┌──────▼──────┐      ┌──────▼──────┐      │
│  │  │ Credential   │──┼────▶│ IAM Role    │      │ Dedup/Snap/ │      │
│  │  │ (IAM Role)   │  │     │ (AssumeRole)│      │ FlexClone   │      │
│  │  └──────────────┘  │     └─────────────┘      └─────────────┘      │
│  └────────────────────┘                                               │
└───────────────────────────────────────────────────────────────────────┘
```

## S3 Access Point Paths

```
s3://<s3ap-alias>/bronze/    # Raw ingested data
s3://<s3ap-alias>/silver/    # Cleaned & transformed
s3://<s3ap-alias>/gold/      # Business-ready aggregates
```

## Key Concepts: Databricks Storage & Ingestion Architecture

Understanding Databricks' storage and ingestion concepts is essential for evaluating FSx for ONTAP S3 AP integration.

> **Partner Quick Reference**: If your customer asks "Can Databricks read our NAS data via S3 Access Points?" — the answer is "partially, with limitations." File-level read works under UC governance, but table creation and directory listing are blocked. For governed analytics on NAS data today, recommend Snowflake External Table or Athena. For Databricks-specific workloads, recommend staged ingestion to S3 → UC Managed Table (see [Recommended Architecture Pattern](#recommended-architecture-pattern-today)). If the customer already uses Databricks, the FPolicy → Lambda → S3 → Auto Loader pattern preserves full UC governance on ingested data.

> **Partner Quick Reference (OpenSharing)**: If your customer asks "Can Databricks read our FSx for ONTAP data via **OpenSharing**?" — the first-line answer:
> - **Protocol layer is verified**: OpenSharing OSS reference server → STS credential vending → S3 AP read (re-confirmed 2026-07). Reproducible implementation: [opensharing-server](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/integrations/opensharing-server).
> - **Native recipient in Databricks UC (Foreign Volume/Table recognition) is pending** (expected via the year-end Storage Ecosystem partner delivery).
> - **What works today**: a notebook-mediated PoC (`requests` + `boto3` → credential vending → S3 AP read → optionally write to a UC table). On a trial (Serverless-only) workspace, watch for notebook-compute activation issues — that is *environment-specific*, not a general Databricks Serverless limitation.
> - **If governed ingestion is needed in production today**, use the established DataSync → S3 → UC managed table path.

### Storage Credential → External Location → External Table/Volume

```
Storage Credential (IAM Role ARN + External ID)
    │
    └── External Location (cloud storage path + credential)
            │
            ├── External Table (tabular data: Parquet, Delta, Iceberg)
            └── External Volume (non-tabular: images, documents, audio)
```

| Concept | Description | FSx for ONTAP S3 AP Status | Reference |
|---|---|:---:|---|
| **[Storage Credential](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)** | IAM Role that Databricks assumes to access cloud storage. During AssumeRole, Databricks generates a session policy that restricts what the assumed session can do — even if the IAM role itself has broader permissions. | ✅ Created | [Docs](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials) |
| **[External Location](https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual)** | Maps S3 path to a Storage Credential; defines access boundary | ⚠️ Created (with `access_point` field — not GA; see [Where the denial originates](#where-the-denial-originates)) | [Docs](https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual) |
| **[External Table](https://docs.databricks.com/aws/en/tables/external)** | UC-governed table whose data resides in External Location | ❌ CREATE TABLE blocked | [Docs](https://docs.databricks.com/aws/en/tables/external) |
| **[External Volume](https://docs.databricks.com/aws/en/volumes/managed-vs-external)** | UC-governed volume for unstructured files in External Location | ❌ Blocked (same session policy issue) | [Docs](https://docs.databricks.com/aws/en/volumes/managed-vs-external) |
| **[Managed Table](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external)** | UC-managed table (data lifecycle controlled by Databricks) | ✅ Works (on standard S3) | [Docs](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external) |
| **[Managed Volume](https://docs.databricks.com/aws/en/volumes/managed-vs-external)** | UC-managed volume for unstructured files (Databricks-managed storage) | ✅ Works (on standard S3) | [Docs](https://docs.databricks.com/aws/en/volumes/managed-vs-external) |

### Auto Loader (Incremental Ingestion)

[Auto Loader](https://docs.databricks.com/ingestion/auto-loader/index.html) is Databricks' equivalent of Snowflake's Snowpipe — it incrementally processes new files as they arrive in cloud storage.

| Mode | Description | S3 Event Notifications Required | FSx for ONTAP S3 AP Status |
|---|---|:---:|:---:|
| **[Directory Listing](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/directory-listing-mode)** | Periodically lists directory to find new files | ❌ No | ⚠️ Requires External Location (blocked) |
| **[File Notification](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/file-notification-mode)** | Uses S3 Event Notifications + SQS for real-time detection | ✅ Yes | ❌ Not possible (FSx for ONTAP S3 AP doesn't support S3 Events) |

**Comparison with Snowflake:**

| Feature | Snowflake (Snowpipe) | Databricks (Auto Loader) | FSx for ONTAP S3 AP Support |
|---|---|---|:---:|
| Event-driven ingestion | Snowpipe (S3 Events → SNS → Snowflake) | File Notification mode (S3 Events → SQS) | ❌ Both blocked (no S3 Events on FSx for ONTAP S3 AP) |
| Polling-based ingestion | Scheduled `ALTER STAGE REFRESH` (Task) | Directory Listing mode | ⚠️ Snowflake: works; Databricks: blocked by UC |
| Alternative for FSx | FPolicy → Lambda → SNS → Snowpipe | FPolicy → Lambda → write to S3 → Auto Loader | ✅ Workaround available |
| Incremental processing | Snowpipe tracks loaded files | Auto Loader tracks processed files (checkpoint) | — |

### Supported Ingestion Formats

**Auto Loader supported formats:**

| Format | Auto Loader | Schema Inference | Schema Evolution | Notes |
|---|:---:|:---:|:---:|---|
| JSON | ✅ | ✅ | ✅ | Nested structures supported |
| CSV | ✅ | ✅ | ✅ | Header detection, delimiter options |
| Parquet | ✅ | ✅ | ✅ | Column pruning, predicate pushdown |
| Avro | ✅ | ✅ | ✅ | Schema registry compatible |
| ORC | ✅ | ✅ | ❌ | Read-only schema |
| XML | ✅ | ✅ | ✅ | Native support |
| TEXT | ✅ | — | — | Line-by-line ingestion |
| BINARYFILE | ✅ | — | — | Images, PDFs, audio — ingested as binary |

**Formats NOT supported by Auto Loader (require alternative ingestion):**

| Format | Alternative Ingestion Method | Considerations |
|---|---|---|
| Delta Lake (existing) | `CONVERT TO DELTA` or `SHALLOW CLONE` | For pre-existing Delta tables on external storage |
| Iceberg (existing) | `CREATE TABLE ... USING ICEBERG LOCATION` | Register existing Iceberg metadata |
| Video (MP4, MOV) | `BINARYFILE` format → custom UDF processing | Large files; consider streaming frame extraction |
| Audio (WAV, MP3) | `BINARYFILE` format → transcription UDF | Use Spark ML or external API for transcription |
| Database exports (mysqldump, pg_dump) | Custom ETL (Spark SQL parsing) | Parse SQL statements into structured data |
| Compressed archives (ZIP, TAR.GZ) | Custom UDF to decompress → process contents | Extract before ingestion |

### Data Ingestion Alternatives for FSx for ONTAP (When Auto Loader Is Blocked)

Since Auto Loader requires External Location (currently blocked on FSx for ONTAP S3 AP), use these alternatives:

| Method | Description | Latency | Governance | Reference |
|---|---|---|---|---|
| **FPolicy → Lambda → S3 → Auto Loader** | FPolicy detects file changes on FSx → Lambda copies to S3 bucket → Auto Loader ingests | Seconds | ✅ Full UC (on S3 copy) | [FPolicy docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| **AWS Glue ETL** | Glue job reads from FSx for ONTAP S3 AP → writes to S3/Delta | Minutes | AWS-side | [Glue + FSx tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| **EMR Serverless** | Spark job reads from FSx for ONTAP S3 AP → writes to S3/Delta | Minutes | AWS-side | [EMR + FSx tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html) |
| **AWS DataSync** | Scheduled sync from FSx NFS → S3 bucket | Minutes-Hours | AWS-side | [DataSync docs](https://docs.aws.amazon.com/datasync/latest/userguide/create-ontap-location.html) |
| **SnapMirror to S3** | ONTAP-native replication to S3 bucket | Minutes | ONTAP-side | [SnapMirror S3](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-snapmirror.html) |
| **Instance Profile + boto3 (PoC)** | Direct S3 AP read from Databricks driver | Real-time | ❌ No UC | Bypasses governance |

> **SnapMirror to S3 — Verified NOT available on FSx for ONTAP (May 2026)**: SnapMirror S3 (`snapmirror object-store` commands and `/api/cloud/targets` API) is **disabled on FSx for ONTAP** as a managed service restriction. While ONTAP S3 server and bucket creation work, the SnapMirror S3 replication commands return "not a recognized command" at all privilege levels (admin/advanced/diagnostic). The SnapMirror S3 "Continuous" policy exists but is unusable. This was verified on ONTAP 9.17.1P6. Feature request submitted to AWS. **Use AWS DataSync as the only validated sync mechanism from FSx for ONTAP to S3.**

**Recommended production pattern:**
```
FSx for ONTAP ──FPolicy──▶ Lambda ──▶ S3 Bucket ──▶ Auto Loader ──▶ Delta Table (UC governed)
     │                                                                      │
     └── NFS/SMB users access same data                                     └── Full UC governance
```

### Volumes: Unstructured Data Governance

[Unity Catalog Volumes](https://docs.databricks.com/aws/en/volumes/managed-vs-external) are the Databricks equivalent of Snowflake's Directory Table — they provide governed access to non-tabular files (images, documents, audio, video).

| Concept | Snowflake Equivalent | Description | FSx for ONTAP S3 AP Status |
|---|---|---|:---:|
| **External Volume** | Directory Table on External Stage | Governed file access on external storage | ❌ Blocked (requires External Location) |
| **Managed Volume** | Internal Stage + Directory Table | Governed file access on Databricks-managed storage | ✅ Works (standard S3) |
| **Volume path** (`/Volumes/catalog/schema/volume/`) | `@stage/path/` | Unified path for file access in SQL/Python | ❌ Not available for FSx for ONTAP S3 AP |

**Key difference**: Snowflake's Directory Table works on FSx for ONTAP S3 AP external stages today. Databricks' External Volumes require External Location creation, which is blocked by the session policy.

### Concept Mapping: Snowflake ↔ Databricks

| Snowflake Concept | Databricks Equivalent | Purpose | FSx for ONTAP S3 AP (Snowflake) | FSx for ONTAP S3 AP (Databricks) |
|---|---|---|:---:|:---:|
| Storage Integration | Storage Credential | IAM Role reference | ✅ | ✅ |
| External Stage | External Location | Cloud storage path mapping | ✅ | ✅ (partial) |
| External Table | External Table | Governed read on external data | ✅ | ❌ Blocked |
| Directory Table | External Volume | File catalog for unstructured data | ✅ | ❌ Blocked |
| Snowpipe | Auto Loader | Incremental file ingestion | ⚠️ (no S3 Events) | ❌ Blocked |
| COPY INTO | COPY INTO / Auto Loader | Batch data load | ✅ | ❌ Blocked |
| Internal Stage | Managed Volume | Snowflake/Databricks-managed storage | ✅ | ✅ |
| `AWS_ACCESS_POINT_ARN` | `access_point` field | S3 AP ARN for session policy | ✅ (resolves all) | ⚠️ (partial resolution) |

## Data Format Support

> **Important**: The table below represents intended validation targets, not production support status. Unity Catalog External Location did not succeed in the tested environment due to a session policy boundary. The Databricks Unity Catalog + FSx for ONTAP S3 AP path is currently documented as an observed boundary in this validation.

| Format | Validation Status | Notes |
|--------|-------------------|-------|
| Parquet | Not validated as production Databricks path on FSx for ONTAP S3 AP | Requires UC External Location (currently blocked by session policy) |
| Delta Lake | Not validated for write-path semantics on FSx for ONTAP S3 AP | Delta commit requires atomic rename (not available on S3 AP) |
| Iceberg | Not validated for production use on FSx for ONTAP S3 AP | S3FileIO metadata write fails on AP alias |
| CSV | Driver-only boto3 PoC possible | Bypasses UC governance; not a production path |
| JSON | Driver-only boto3 PoC possible | Bypasses UC governance; not a production path |
| ORC | Not validated | — |

## Managed Table vs External Table — Design Guide

Understanding the difference between managed and external tables in Unity Catalog is critical for architecture decisions — especially given the current FSx for ONTAP S3 AP session policy limitation.

> **Key concepts**: [External Table](https://docs.databricks.com/aws/en/tables/external) (UC governs metadata, not storage) | [Managed Table](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external) (UC governs both) | [External Location](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials) (maps cloud path to credential)
>
> For analytics and AI/ML-specific implications, see the [Analytics & AI Demo Guide](docs/en/ai-demo-guide.md).

### Comparison Matrix

| Aspect | UC External Table (on FSx for ONTAP S3 AP) | UC Managed Table (on S3 bucket) | boto3 PoC (no UC table) |
|---|---|---|---|
| **Data location** | FSx for ONTAP (zero-copy) | Databricks-managed S3 | FSx for ONTAP |
| **UC governance** | ❌ **Blocked** (CREATE TABLE fails) | ✅ Full (tags, masks, lineage) | ❌ None |
| **ONTAP features preserved** | ✅ Snapshot, FlexClone, FPolicy | ❌ Data outside ONTAP | ✅ (read-only) |
| **Multi-protocol access** | ✅ NFS/SMB/S3 AP | ❌ S3 only | ✅ NFS/SMB/S3 AP |
| **Query performance** | N/A (table creation blocked) | ✅ Optimized Delta/Iceberg | ❌ No Spark optimization |
| **Delta Lake features** | ❌ Blocked | ✅ ACID, Time Travel, MERGE | ❌ Not applicable |
| **ML Feature Store** | ❌ Blocked | ✅ Full support | ❌ Not applicable |
| **Data freshness** | Would be real-time (if supported) | Depends on ingestion pipeline | Real-time (boto3 reads current state) |
| **Storage cost** | FSx only | FSx + S3 (duplicate) | FSx only |
| **Production suitability** | ❌ Not viable today | ✅ Recommended | ⚠️ PoC only |

### Current State: What Works and What Doesn't

```
FSx for ONTAP S3 AP
     │
     ├── UC External Location (access_point field set)
     │     ├── Top-level ls: ✅ (287 items)
     │     ├── Explicit file read (spark.read.csv): ✅ (1000 rows)
     │     ├── Subdirectory listing: ❌ (AccessDenied)
     │     ├── CREATE TABLE: ❌ (UC_CLOUD_STORAGE_ACCESS_FAILURE)
     │     └── Write operations: ❌ (PutObject AccessDenied)
     │
     └── Instance Profile + boto3 (Customer VPC, Dedicated cluster)
           ├── GetObject: ✅
           ├── ListObjectsV2: ✅
           └── UC governance: ❌ (bypassed entirely)
```

### Recommended Architecture Pattern (Today)

Since UC External Tables on FSx for ONTAP S3 AP are blocked, the recommended pattern is a **staged ingestion** approach:

```
FSx for ONTAP ──S3 AP──▶ Ingestion Job ──▶ S3 Bucket ──▶ UC Managed Table ──▶ ML/AI
     │                    (Glue/EMR/Lambda)                    │
     │                                                         └── Full UC governance
     └── Same data via NFS/SMB (source of truth)
```

**Or for read-only analytics:**
```
FSx for ONTAP ──S3 AP──▶ Athena (SQL analytics, no copy needed)
                    └──▶ Snowflake External Table (governed, no copy needed)
```

### When to Use Each Pattern

| Requirement | Recommended Pattern | Why |
|---|---|---|
| Governed ML training data | S3 bucket → UC Managed Table | Full UC governance, Feature Store, lineage |
| Read-only SQL analytics on NAS | Athena + FSx for ONTAP S3 AP | No copy, serverless, governed |
| Governed external tables on NAS | Snowflake External Table | Works today with full governance |
| Exploratory data access (PoC) | Instance Profile + boto3 | Quick access, no governance |
| Production Delta Lake tables | S3 bucket (standard pattern) | Required for ACID, MERGE, OPTIMIZE |
| Real-time NAS data + UC governance | Wait for platform support | UC session policy resolution needed |

### Cost & Governance Trade-off

| Pattern | Storage Cost | Governance | Performance | ONTAP Features |
|---|---|---|---|---|
| **Athena + FSx for ONTAP S3 AP** | Lowest (FSx only) | AWS-side (IAM, S3 AP) | Good (serverless) | ✅ Preserved |
| **Snowflake External Table** | Low (FSx only) | ✅ Full (tags, masking) | Moderate | ✅ Preserved |
| **Staged to S3 → UC Table** | Higher (FSx + S3) | ✅ Full UC | Best (Delta optimized) | ❌ Lost on copy |
| **boto3 PoC** | Lowest (FSx only) | ❌ None | Poor (driver-only) | ✅ Preserved |

### AI Readiness Score

| Pattern | Access Pattern | Governance | Performance | AI Capability | Cost | Operational Simplicity | Overall |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Athena + FSx for ONTAP S3 AP** | Zero-copy | ★★★☆☆ | ★★★★☆ | ★☆☆☆☆ (SQL only) | ★★★★★ | ★★★★★ | **3.6** |
| **Snowflake External Table** | Zero-copy | ★★★★☆ | ★★★☆☆ | ★★★★☆ (Cortex AI) | ★★★★★ | ★★★★☆ | **4.0** |
| **Staged to S3 → UC Table** | With S3 sync | ★★★★★ | ★★★★★ | ★★★★★ (full Mosaic AI) | ★★☆☆☆ | ★★☆☆☆ | **3.8** |
| **boto3 PoC (Databricks)** | Zero-copy (no governance) | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ (driver-only) | ★★★★★ | ★★★☆☆ | **2.8** |
| **Bedrock KB + FSx for ONTAP S3 AP** | Zero-copy | ★★★☆☆ | ★★★★☆ | ★★★★☆ (RAG) | ★★★★☆ | ★★★★☆ | **3.8** |

- **Access Pattern**: Whether data is read directly from FSx for ONTAP S3 AP (zero-copy) or requires sync to S3 first
- **Governance**: UC lineage, tags, masking, row filters
- **Performance**: Query latency, distributed processing
- **AI Capability**: Breadth of AI/ML functions available
- **Cost**: Storage efficiency, compute cost
- **Operational Simplicity**: Setup, maintenance, pipeline complexity

> **Scoring methodology**: Each dimension rated by the author based on validated evidence in this repository. This is not an official AWS assessment. Scores reflect observed capabilities in one test environment (DBR 17.3 LTS, ap-northeast-1).

> **Performance note**: Performance scores reflect relative comparison within FSx for ONTAP S3 AP access patterns, not comparison with native S3 bucket performance. All patterns accessing FSx for ONTAP S3 AP have higher latency than equivalent native S3 operations.

> **How to use this score**: Use Overall score as a starting point for pattern selection. Scores ≥ 4.0 indicate strong fit for governed production workloads. Scores 3.5–3.9 indicate viable paths with trade-offs to evaluate. Scores < 3.0 indicate PoC-only paths requiring compensating controls and explicit approval.

**When to choose which:**
- Choose **Snowflake External Table** (4.0) when governed AI on NAS data without copying is the priority
- Choose **Staged to S3 → UC Table** (3.8) when maximum Databricks performance and full Mosaic AI are required (accepts data duplication cost)
- Choose **Bedrock KB** (3.8) when AWS-native RAG with zero-copy on FSx is the primary requirement
- Choose **boto3 PoC** (2.8) only for time-limited exploration with explicit approval

### References

- [Unity Catalog External Tables](https://docs.databricks.com/aws/en/tables/external)
- [Managed vs External Assets](https://docs.databricks.com/aws/en/data-governance/unity-catalog/managed-versus-external)
- [External Locations](https://docs.databricks.com/aws/en/connect/unity-catalog/storage-credentials)
- [Delta Lake on Databricks](https://docs.databricks.com/aws/en/delta/index)

## Unstructured Data Support

| Format | Support | Access Method | Use Case |
|--------|:---:|--------------|----------|
| Images (JPEG, PNG, TIFF) | ⚠️ | Instance Profile + boto3 (driver only) | Image classification, quality inspection |
| Video (MP4, MOV) | ⚠️ | Instance Profile + boto3 (driver only) | Frame extraction, video analytics |
| Documents (PDF, DOCX) | ⚠️ | Instance Profile + boto3 (driver only) | Text extraction, RAG pipeline |
| Audio (WAV, MP3) | ⚠️ | Instance Profile + boto3 (driver only) | Transcription, speech analytics |
| Binary / Archives | ⚠️ | Instance Profile + boto3 (driver only) | Download, custom processing |

**Current limitations:**
- Unity Catalog External Table creation is blocked → no governed unstructured data catalog
- `spark.read.binaryFile` works for explicit file paths (with `access_point` field set)
- Instance Profile + boto3 bypasses UC governance (PoC only, not production-recommended)
- No equivalent to Snowflake's Directory Table or GET_PRESIGNED_URL
- Executor-scale processing not yet validated

### FILE type (Beta, 2026-08) — evaluated, does not lift the blocker

Databricks introduced the [FILE type](https://www.databricks.com/blog/introducing-file-type-native-column-type-multimodal-data): a Delta column holding a governed reference to an unstructured file, queryable and passable to AI functions alongside structured columns. It is the closest thing yet to a governed unstructured-data catalog in Unity Catalog.

It does not change the status above. `FILE EXTERNAL` is supported only for files **inside a UC volume**, and a UC external volume cannot be created on an S3 Access Point (BLK-001), so the only reachable mode is `FILE MANAGED`, which **copies** the bytes into UC-managed storage.

A separate feature did move the picture: the [`_object_metadata` column](https://docs.databricks.com/aws/en/ingestion/object-metadata-column) (DBR 18.2+) exposes S3 **object tags** and user-defined metadata as queryable columns — and object tagging **is** supported on an FSx for ONTAP S3 AP (verified 2026-08-12). Whether Databricks can read those tags through an Access Point path is **not yet verified**.

| Read this for | Where |
|---|---|
| Full evaluation, three-layer design, open questions | [databricks-file-type-evaluation](../../docs/en/databricks-file-type-evaluation.md) ([日本語](../../docs/ja/databricks-file-type-evaluation.md)) |
| FSx for ONTAP-side object tag measurements (limits, ASCII constraint, file-scope, overwrite behaviour) | [s3ap-object-tagging evidence](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml) |
| Runnable verification of the Databricks side | [`notebooks/10_file_type_object_metadata.py`](notebooks/10_file_type_object_metadata.py) · cases `DBX-FILE-*` in [test-cases.yaml](../../verification-pack/databricks/test-cases.yaml) |

**Recommended alternative for unstructured data on FSx for ONTAP:**
- Use **Snowflake** (Directory Table + GET_PRESIGNED_URL) for file catalog and secure URL generation
- Use **AWS Lambda** for serverless file processing ([AWS tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html))
- Use **Amazon Bedrock** for RAG over documents ([AWS tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html))

## ONTAP Value for Databricks

| ONTAP Feature | Databricks Benefit | Reference |
|---|---|---|
| **FlexCache** | Cache training data across regions/sites for low-latency access; write-back mode for feature engineering | [FlexCache docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | Immutable training data protection — admin cannot delete during retention; compliance for regulated ML | [SnapLock on FSx](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI** | AI-powered ransomware detection; auto-snapshot protects training data and model artifacts | [ARP on FSx](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | Instant dev/test dataset provisioning without full copy; zero-copy ML experimentation | [FlexClone docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | Table-level point-in-time recovery (complements Delta Time Travel); feature pipeline versioning | [Snapshot docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | Auto-tier cold partitions to S3 (transparent to Databricks compute) | [FabricPool docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **Storage Efficiency** | Up to 65% savings via deduplication + compression + compaction on Delta version files | [Storage efficiency](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | Cross-region DR for lakehouse data and ML pipelines | [SnapMirror docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **Multi-protocol** | NFS (data scientists) + SMB (Windows users) + S3 AP (Databricks/Spark) — same data, no copy | [Multi-protocol](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | File operation monitoring and blocking; audit trail for data access compliance | [FPolicy docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

## Governance & AI/ML Guides

| Guide | Description |
|---|---|
| [Analytics & AI Demo Guide](docs/en/ai-demo-guide.md) | Analytics & AI capabilities, current status, working demos, blocked paths |
| [Delta Sharing & Volume Sharing Guide](docs/en/delta-sharing-volume-guide.md) | How to share FSx-backed structured and unstructured data with Databricks via Delta Sharing — 3 patterns (metadata table, AI-enriched, raw file) |
| [Governance: Tags & Data Protection (ABAC)](docs/en/ai-demo-guide.md#governance-tags--data-protection-abac) | UC ABAC, governed tags, column masks, row filters — current limitations |
| [Governance: File-Level Access Control](docs/en/ai-demo-guide.md#file-level-access-control-ontap-native-layer) | ONTAP dual-layer auth, FPolicy, per-team S3 AP isolation (compensating control) |
| [Integration: ONTAP × Databricks Tags](docs/en/ai-demo-guide.md#integration-ontap-file-level-control--databricks-tag-governance) | Combined governance matrix, current vs future state, design patterns |
| [FILE type (Beta) evaluation](../../docs/en/databricks-file-type-evaluation.md) | Multimodal data via FILE columns, why BLK-001 still applies, the `_object_metadata` object-tag bridge, and the recommended three-layer metadata design |

## Quick Start

1. Deploy CloudFormation template: `template.yaml`
2. Configure Databricks Storage Credential (Terraform or UI)
3. Create External Location pointing to S3 AP
4. Run notebooks in order (01 → 06)

## Files

| File | Description |
|------|-------------|
| `template.yaml` | CloudFormation: S3 AP + IAM Role for Databricks (UC integration) |
| `customer-vpc-network.yaml` | CloudFormation: Customer-managed VPC network (for NFS verification) |
| `vpc-peering.yaml` | CloudFormation: VPC Peering (Managed VPC ↔ FSx VPC, reference) |
| `deploy.sh` | S3 AP + UC integration deployment script |
| `deploy-customer-vpc.sh` | Customer-managed VPC deploy/delete script |
| `params.example.json` | CloudFormation parameter example |
| `terraform/` | Databricks Unity Catalog resources (Storage Credential, External Location) |
| `notebooks/01-09` | Databricks notebooks (setup through ML) |
| `docs/ja/` | Japanese documentation |
| `docs/en/` | English documentation |
| `tests/` | Integration tests |

## Infrastructure as Code (IaC) Structure

### 1. S3 Access Point Integration (`template.yaml` + `terraform/`)

```bash
# Phase 1: AWS Resources (S3 AP, IAM Role)
cp params.example.json params.json  # Edit parameters
./deploy.sh

# Phase 2: Databricks Resources (Storage Credential, External Location)
cd terraform/
cp terraform.tfvars.example terraform.tfvars  # Edit parameters
terraform init && terraform apply
```

### 2. Customer-managed VPC (`customer-vpc-network.yaml`)

Build Databricks networking in the same VPC as FSx for ONTAP:

```bash
# Deploy (creates NAT Gateway → ~$45/month)
./deploy-customer-vpc.sh deploy

# Check status
./deploy-customer-vpc.sh status

# Delete (cost reduction)
./deploy-customer-vpc.sh delete
```

Post-deployment manual steps:
1. Register in Databricks Account Console → Cloud Resources → Networks
2. Create a new Workspace (specify Network Configuration)
3. Create a Dedicated (Single user) cluster

### 3. VPC Peering (`vpc-peering.yaml`, reference)

Connection from Managed VPC to FSx VPC. NFS mount is blocked by seccomp,
so retained for ONTAP REST API access and future re-verification.

## Verification Status (2026-05-17)

> **Note**: Instance Profile is classified as a [legacy data access pattern](https://docs.databricks.com/en/admin/sql/data-access-configuration.html) by Databricks. Unity Catalog external locations are the recommended governance model. The Instance Profile path documented below bypasses Unity Catalog governance and should be treated as a controlled PoC only.

| Approach | Result | Notes |
|----------|--------|-------|
| S3 AP + Unity Catalog | ❌ | Session policy does not support S3 AP ARN |
| S3 AP + Unity Catalog (`access_point` field) | ⚠️ Not GA | `access_point` field never released as GA; partial success is side effect of incomplete internal handling (confirmed by Databricks Support, May 2026) |
| S3 AP + boto3 (Managed VPC) | ❌ | IMDS blocked |
| NFS mount (Managed VPC) | ❌ | Egress restriction + seccomp |
| NFS mount (Customer VPC) | ❌ | seccomp filter blocks NFS mount |
| NFS RPC direct (Customer VPC) | ✅ | All operations succeed via Python RPC |
| ONTAP REST API (Customer VPC) | ✅ | Authentication and config changes possible |
| Instance Profile + boto3 (Customer VPC, Dedicated) | ✅ | S3 AP read from driver-node succeeded. Bypasses UC governance — PoC only |

## Where the denial originates

Demonstrated here on 2026-08-12, with a native-S3 control in the same session — same role, same
network, credentials issued by Unity Catalog itself
(`POST /api/2.0/unity-catalog/temporary-path-credentials`):

1. **Registering an S3 access point path as an External Location succeeds.** The read is what
   fails. An earlier reading of this, that registration itself was unsupported, was wrong and is
   corrected in [BLK-001](../../docs/en/blocker-tracker.md).
2. The down-scoped session policy Unity Catalog issues is written with a **bucket-form ARN**
   (`arn:aws:s3:::<alias>`), while AWS authorises an access point request against the
   **access point ARN** (`arn:aws:s3:<region>:<account>:accesspoint/<name>`). The two do not
   match, and a session policy intersects with the role policy — so the role permitting it is not
   enough.
3. Credentials issued for the native S3 path, in the same session, are accepted. That control is
   what makes the session policy the mechanism rather than an inference from a failure.
4. The `access_point` field is not in current Unity Catalog documentation. Whether it was ever
   released and why it was removed is **open**.
5. Asked Databricks 2026-05-26. Filed as a feature gap; no published timeline.

**Recommended interim path**: Sync data from FSx for ONTAP into a standard S3 bucket (DataSync), then register that S3 bucket as a UC External Location.

For read-only analytics without UC governance, use AWS-native services (Athena, EMR Serverless, DuckDB Lambda) or Snowflake directly on FSx for ONTAP S3 AP.
