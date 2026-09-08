🌐 **English** | [日本語](../ja/fsx-ontap-to-databricks-unity-catalog-guide.md)

# FSx for ONTAP → Databricks Unity Catalog: Comprehensive Connection Guide

> **Status**: Initial version (2026-06-18). Consolidates verification results from this repository.
> **Audience**: AWS SAs, partner SIs/ISVs, data engineers. Post-DAIS 2026 FAQ reference.
> **Evidence tier**: Verification results are **Project-context** (reproducible within this repo). Official information is **Public**.

---

## Executive Summary

**Q: Can FSx for ONTAP data be used as a Databricks Unity Catalog data source?**

**A: Yes. However, not via direct External Location registration — indirect paths are required.**

| Conclusion | Detail |
|-----------|--------|
| ✅ Usable | Multiple paths exist to bring FSx for ONTAP data under UC governance |
| ❌ Zero-copy direct connection not supported | UC External Location does **not support** S3 AP / ONTAP S3 / NFS mount |
| ✅ Recommended paths available | DataSync → S3 → UC tables, Kafka → Structured Streaming → UC Delta |
| ⚠️ DAIS 2026 features do not directly resolve this | OpenSharing is a sharing protocol, not a storage connector |

### Why FSx for ONTAP (Multi-Protocol Value)

The core value of FSx for ONTAP is that **the same data is simultaneously accessible via NFS / SMB / S3 AP**. While Databricks requires an indirect path, understand the overall positioning:

```
Same data (FSx for ONTAP volume)
  │
  ├── NFS → Data scientists (Linux workstations)
  ├── SMB → Business users (Windows file shares)
  ├── S3 AP → AWS services (Athena, Glue, EMR, Bedrock, Snowflake)
  │
  └── DataSync / FPolicy → S3 → Databricks UC
       (analytics copy under UC governance)
```

Data that business users access daily via NFS/SMB can be used **without conversion** by AWS analytics services (Athena, Glue, EMR) via S3 AP. For Databricks UC, an indirect path is required, but by syncing an **analytics copy** via DataSync, full UC governance (lineage, tags, masks, row filters) can be applied.

---

## Common Misconceptions and FAQ

### Q1: Can OpenSharing connect directly to FSx for ONTAP?

**A: No. OpenSharing is a "sharing protocol", not a "storage connector".**

OpenSharing (successor to Delta Sharing, announced at DAIS 2026) provides:
- Cross-organization sharing of data, models, and agent skills
- Apache Iceberg IRC client support
- Zero-copy **sharing** (granting read access from provider's storage to recipients)

However, OpenSharing:
- ❌ Does **not** register FSx for ONTAP as UC storage
- ❌ Does **not** make S3-compatible endpoints recognized as UC External Locations
- ❌ Does **not** connect NFS/SMB file systems to UC

What OpenSharing can do (FSx for ONTAP related):
- ✅ After FSx for ONTAP data is ingested to S3 and converted to Delta tables, share those tables via OpenSharing to other organizations
- ✅ A self-managed OpenSharing server can vend scoped STS credentials for zero-copy reads from FSx for ONTAP S3 AP (validated in this repository)
- ✅ Databricks Storage Ecosystem (DAIS 2026): NetApp committed to native OpenSharing integration by end of 2026 — this may enable direct connectivity in the future

```
FSx for ONTAP → [DataSync/ETL] → S3 → UC Delta table → OpenSharing → recipient
                                                          ↑ OpenSharing scope is here

FSx for ONTAP → OpenSharing Server (credential vending) → recipient (zero-copy, no UC governance)
                  ↑ This repository's reference implementation
```

### Q2: Can OpenSharing directly share FSx for ONTAP files?

**A: No. OpenSharing is a "sharing protocol", not a mechanism for sharing arbitrary files without transformation.**

OpenSharing prerequisites:
- Shared assets must be **Tables** (Delta or Iceberg), **Volumes**, **Models**, or **AgentSkills**
- Table data must reside on **UC-recognized storage** (standard S3 / ADLS / GCS)
- There is **no capability** to share files on FSx for ONTAP (CSV, images, PDFs) directly via OpenSharing without prior conversion or a provider-side credential vending server

To share FSx for ONTAP data via OpenSharing:
1. Ingest from FSx for ONTAP → S3
2. Register as a Delta/Iceberg table on S3
3. Share via OpenSharing

Alternatively, an independent OpenSharing provider server (such as the reference implementation in this repository) can vend scoped STS credentials to recipients, enabling zero-copy reads — but this bypasses UC governance unless consumed via a native UC recipient.

### Q3: Can't Databricks NFS-mount FSx for ONTAP?

**A: Databricks runtime seccomp policies block kernel NFS mounts.**

- Databricks serverless and shared clusters restrict `mount` system calls for security
- Even dedicated clusters (Classic) cannot NFS-mount due to runtime boundaries (verified)
- FUSE-based mounts (`s3fs-fuse`, etc.) are similarly restricted

### Q4: Can't I register FSx for ONTAP S3 Access Points as a UC External Location?

**A: As of May 2026, Databricks does not officially support S3 Access Points for UC External Locations.**

Verification results (this repository, re-measured 2026-08-12):
- The `access_point` field was never GA-released and has been removed from documentation
- Partial operations (top-level listing, explicit file reads) are "a side effect of incomplete internal handling: the listing that succeeds does not go through the denied path (measured here 2026-08-12)
- CREATE TABLE, subdirectory listing return `AccessDenied` / `UC_CLOUD_STORAGE_ACCESS_FAILURE`

### Q5: Can't ONTAP S3 (S3-compatible endpoint) be registered with UC?

**A: UC External Location supports only the following:**

| Supported Storage | Status |
|-------------------|--------|
| Amazon S3 (native) | ✅ |
| Azure Data Lake Storage Gen2 | ✅ |
| Google Cloud Storage | ✅ |
| Cloudflare R2 | ✅ |
| S3-compatible endpoints (MinIO, ONTAP S3, etc.) | ❌ Not supported |

ONTAP S3 is S3 API-compatible, but UC's session policy generation logic only handles standard S3 bucket ARNs.

### Q6: Can't the Volumes connector (OpenSharing) share unstructured data?

**A: As of June 2026, while the Volumes connector is designed as an OpenSharing Agent Asset type, there is no capability to register FSx for ONTAP directly as a UC Volume.**

UC Volume requirements:
- External Volume → requires UC External Location (blocked for S3 AP)
- Managed Volume → Databricks-managed S3 storage (not FSx for ONTAP)

---

## Connection Path Overview: What Works and What Doesn't

### RPO (Data Freshness) and Trade-offs by Path

| Path | RPO (Data Freshness) | Throughput | UC Governance | Data Copy |
|------|---------------------|-----------|--------------|-----------|
| DataSync → S3 → UC | 5 min – 24 hours (schedule-dependent) | High (DataSync optimized) | ✅ Full | Selective (structured subset to S3; see [strategies below](#what-gets-copied-vs-what-stays-a-concrete-example)) |
| Kafka → SS → UC | Seconds – 10s (streaming latency) | Medium–High (partition parallelism) | ✅ Full | Event-level (stream records to Delta) |
| Glue/EMR ETL → UC | Minutes – hours (job schedule) | High (Spark distributed) | ✅ Full | ETL output only (transformed data to S3) |
| Foreign Iceberg | Near-real-time (REFRESH dependent) | Read-only | ✅ Read | Minimal (metadata only) |
| Athena + S3 AP (outside UC) | Real-time (S3 AP direct read) | Medium | ❌ AWS-side only | None (zero-copy) |
| boto3 PoC | Real-time | Low (driver only) | ❌ None | None |

### Snowflake vs Databricks Connection Comparison

Connectivity differences for FSx for ONTAP S3 AP:

| Capability | Snowflake | Databricks (UC) | Reason |
|-----------|-----------|-----------------|--------|
| External Table (S3 AP) | ✅ Works | ❌ Blocked | Snowflake resolves S3 AP via `AWS_ACCESS_POINT_ARN`. UC session policy doesn't handle S3 AP |
| Directory Table / Volume | ✅ Works | ❌ Blocked | Same (External Location dependency) |
| Event-driven Snowpipe / Auto Loader | ⚠️ Via FPolicy | ❌ Blocked | S3 Event Notifications not available on FSx for ONTAP S3 AP. Both need FPolicy alternative |
| Zero-copy read | ✅ | ❌ | UC requires standard S3 buckets only |
| Governance (Tags, Masking) | ✅ | ✅ (after S3 ingestion) | UC governance applies to S3-resident tables |
| AI/ML capabilities | Cortex AI (limited) | Mosaic AI (full) | ML training / Feature Store stronger on Databricks |

**Selection guidance**: If zero-copy + governance is top priority, choose Snowflake. If full AI/ML pipeline is needed, choose Databricks (via DataSync). The two are not mutually exclusive — both can access the same FSx for ONTAP data concurrently.

### Full Picture

```
FSx for ONTAP
  │
  ├─── S3 Access Point ───┬── UC External Location ──── ❌ Not supported
  │                       ├── Athena / EMR / Glue ───── ✅ Works
  │                       ├── Bedrock KB ────────────── ✅ Works (official tutorial)
  │                       └── Snowflake External Table ─ ✅ Works
  │
  ├─── ONTAP S3 ──────────── UC External Location ──── ❌ S3-compatible not supported
  │
  ├─── NFS ───────────────┬── Databricks NFS mount ─── ❌ seccomp blocked
  │                       ├── DataSync → S3 → UC ───── ✅ Verified (recommended)
  │                       └── EMR / Glue via NFS ────── ✅ Works
  │
  ├─── SMB ───────────────── Databricks SMB mount ──── ❌ Not supported
  │
  └─── Kafka (via FPolicy) ── Structured Streaming ─── ✅ UC Delta tables
```

> **Note: Lakehouse Federation** — UC Lakehouse Federation issues read queries from UC to MySQL / PostgreSQL / SQL Server / Snowflake / Redshift / BigQuery, etc. FSx for ONTAP is not an RDBMS and is not a direct Federation target. However, Federation to ClickHouse via its PostgreSQL-compatible port (9005) is theoretically possible (unverified). See [Kafka-ClickHouse-UC connectivity guide](./kafka-clickhouse-unity-catalog-connectivity.md).

### Connection Method × File Format Cross-Matrix

| File Format | DataSync→S3→UC | Kafka→SS→UC Delta | Glue/EMR ETL→UC | Foreign Iceberg | boto3 PoC |
|---|:---:|:---:|:---:|:---:|:---:|
| **CSV** | ✅ | ✅ (after Kafka message conversion) | ✅ | — | ✅ (no governance) |
| **Parquet** | ✅ | — | ✅ | — | ✅ (no governance) |
| **JSON** | ✅ | ✅ (native) | ✅ | — | ✅ (no governance) |
| **Delta Lake** | ✅ (convert on S3) | ✅ (output target) | ✅ | — | — |
| **Iceberg** | ✅ (convert on S3) | — | ✅ | ✅ (via Glue REST, validating) | — |
| **Images (JPEG/PNG)** | ✅ (Volume registration) | — | ✅ (BinaryFile) | — | ✅ (no governance) |
| **PDF / Office** | ✅ (Volume registration) | — | ✅ (BinaryFile) | — | ✅ (no governance) |
| **Video (MP4)** | ✅ (Volume registration) | — | ⚠️ (large file caution) | — | ✅ (no governance) |
| **Audio (WAV/MP3)** | ✅ (Volume registration) | — | ✅ (BinaryFile) | — | ✅ (no governance) |

**Legend**: ✅ = Verified or officially supported / ⚠️ = Constraints apply / — = Not applicable

---

## What Gets Copied vs What Stays: A Concrete Example

> A common misconception is that "DataSync → S3 → UC" means replicating the entire FSx for ONTAP volume to a standard S3 bucket. In practice, only the **analytically relevant subset** is extracted and written to the appropriate AWS storage service — typically less than 1% of the source volume.

### S3 Storage Services Used in This Architecture

Before diving into examples, clarify the distinct S3-related services:

| Service | Role in this architecture | Data written to it |
|---------|--------------------------|-------------------|
| **FSx for ONTAP S3 Access Points** | READ source (zero-copy access to NFS/SMB data) | Nothing — read-only in this pipeline |
| **Standard S3 bucket** | Write destination for DataSync sync or UC Managed Tables (Delta) | Synced files or Delta table data files |
| **S3 Tables** (Iceberg, auto-compaction) | Write destination for structured metadata (Iceberg format) | ETL-extracted metadata, measurements, AI classifications |
| **S3 Vectors** | Write destination for vector embeddings | Titan Embeddings output for semantic search |

> **Key insight**: The ETL pipeline reads from FSx for ONTAP S3 AP and writes to **S3 Tables, S3 Vectors, or standard S3 buckets** depending on the downstream consumer. These are separate services with different characteristics.

### Example: Manufacturing Quality Inspection (200 lots/day)

**Source on FSx for ONTAP** (accessed via NFS/SMB by factory systems, read via S3 AP by ETL):

```
/quality-inspection/2026-06-20/
├── lot-A001-report.pdf          (2.3 MB)   ← Inspection report PDF
├── lot-A001-image-front.tiff    (15 MB)    ← Visual inspection image
├── lot-A001-image-back.tiff     (14 MB)    ← Visual inspection image
├── lot-A001-measurements.csv    (48 KB)    ← Dimensional measurements
└── lot-A001-sensor-log.json     (120 KB)   ← Manufacturing sensor log
    (× 200 lots/day ≈ 6 GB/day total on FSx for ONTAP)
```

**ETL output by destination**:

| Destination | Table / Collection | Content | Size/day | Format | Downstream consumer |
|-------------|-------------------|---------|:--------:|--------|-------------------|
| **S3 Tables** | `quality.inspection_metadata` | AI-classified metadata per lot | ~100 KB | Iceberg (auto-compacted) | Athena, EMR, Glue (native); Databricks (via Foreign Iceberg / Glue HMS) |
| **S3 Tables** | `quality.measurements` | Dimensional values per point | ~800 KB | Iceberg | Same as above |
| **S3 Vectors** | `quality-embeddings` | Document embeddings (1024-dim) | ~800 KB | Vector index | Bedrock Knowledge Bases, OpenSearch semantic search |
| **Standard S3 bucket** | `catalog.schema.sensor_data` (UC) | Aggregated sensor stats | ~50 KB | Delta (UC Managed Table) | Databricks UC (full governance: lineage, tags, masks) |

**Total written to AWS storage: ~1.75 MB/day** — **0.03% of the 6 GB/day source on FSx for ONTAP**

**What stays on FSx for ONTAP**: Images (TIFF), full PDFs, raw sensor logs. Accessed on-demand via FSx for ONTAP S3 AP or OpenSharing STS credential vending.

### Choosing the Write Destination

| If downstream consumer is... | Write to | Why |
|------------------------------|----------|-----|
| Athena / EMR / Glue (AWS native analytics) | **S3 Tables** (Iceberg) | Native integration, auto-compaction, no table management overhead |
| Databricks UC (full governance needed) | **Standard S3 bucket** (Delta, UC Managed Table) | UC requires standard S3 for External Location / Managed Table |
| Semantic search / RAG / similarity queries | **S3 Vectors** | Purpose-built for vector embeddings, integrates with Bedrock |
| Both Databricks UC AND AWS native engines | **S3 Tables** + UC Foreign Iceberg | Write to S3 Tables (Iceberg); Databricks reads via Foreign Iceberg (Glue HMS Federation) |
| Snowflake | **Standard S3 bucket** or **S3 Tables** | Snowflake reads via External Stage (standard S3) or Managed Iceberg (user-managed S3) |

### Three Ingestion Strategies (Revised)

| Strategy | Read from | Write to | Size on AWS storage | UC Governance | Complexity |
|----------|-----------|----------|:------------------:|:---:|:---:|
| **A. Selective ETL** (recommended) | FSx for ONTAP S3 AP | S3 Tables + S3 Vectors + Standard S3 (mixed) | Minimal (~0.03% of source) | Full (per destination) | Medium (ETL pipeline) |
| **B. File-type filtering** | FSx for ONTAP NFS (via DataSync) | Standard S3 bucket | Moderate (target files only) | Full (COPY INTO → Delta on UC) | Low (DataSync + SQL) |
| **C. Full volume sync** | FSx for ONTAP NFS (via DataSync) | Standard S3 bucket | High (= source volume) | External Table (read-only) or selective COPY INTO | Lowest (DataSync only) |

### Strategy A: Selective ETL Pipeline (Recommended)

```
FSx for ONTAP (6 GB/day, all file types)
    │
    ▼ Read via FSx for ONTAP S3 AP (or OpenSharing STS credential vending)
ETL (Databricks Job / Glue / Lambda)
    │
    ├── CSV → parse → S3 Tables (Iceberg): measurements table
    ├── JSON → aggregate → S3 Tables (Iceberg): sensor_summary table
    ├── PDF → Bedrock AI → S3 Tables (Iceberg): metadata table
    ├── PDF/images → Titan Embeddings → S3 Vectors: semantic index
    └── TIFF → reference URI only recorded in metadata (no file copy)
    │
    ▼ (Optional) For Databricks UC consumers:
Standard S3 bucket → UC Managed Delta Table (sensor aggregates)
    or
S3 Tables → Glue Catalog → UC Foreign Iceberg (zero additional copy)
```

The source images and documents remain on FSx for ONTAP. AWS storage services hold only **derived, structured, analytics-ready data** — not copies of the raw files.

### Strategy B: File-Type Filtering with DataSync

DataSync copies selected files from FSx for ONTAP NFS to a standard S3 bucket:

```bash
# Sync only CSV and Parquet files (skip images, PDFs)
aws datasync create-task \
  --source-location-arn <SRC> \
  --destination-location-arn <DST> \
  --includes '[{"FilterType":"SIMPLE_PATTERN","Value":"*.csv"},{"FilterType":"SIMPLE_PATTERN","Value":"*.parquet"}]'
```

Then in Databricks (reads from the standard S3 bucket, writes to UC Managed Delta):
```sql
COPY INTO quality.measurements
FROM 's3://<STANDARD-BUCKET>/quality-inspection/'
FILEFORMAT = CSV
PATTERN = '*/measurements.csv';
```

### Strategy C: Full Volume Sync (Simplest, Highest Cost)

DataSync copies all files from FSx for ONTAP NFS to a standard S3 bucket. Appropriate only when analytics need access to all file types (e.g., image ML training). Even then, create External Tables (read-only) rather than converting everything to Delta.

---

## Recommended Path Details

### Path 1: DataSync → S3 → UC (Recommended for production)

**The only verified production path. FSx for ONTAP NFS → S3 periodic sync → UC External/Managed tables.**

```
FSx for ONTAP (NFS)
  ↓ AWS DataSync (rate(5 minutes) to daily)
Amazon S3 bucket (standard)
  ↓
UC External Location (Storage Credential + IAM Role)
  ↓
UC External Table / Managed Table / Volume
```

**Procedure overview** ([detailed guide](./datasync-to-s3-guide.md)):

```bash
# 1. DataSync source (FSx for ONTAP NFS)
aws datasync create-location-fsx-ontap \
  --storage-virtual-machine-arn <SVM_ARN> \
  --protocol NFS={} \
  --subdirectory /vol1/data/

# 2. DataSync destination (S3)
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::<BUCKET> \
  --s3-config BucketAccessRoleArn=<ROLE_ARN>

# 3. DataSync task
aws datasync create-task \
  --source-location-arn <SRC> \
  --destination-location-arn <DST> \
  --options '{"TransferMode":"CHANGED","PreserveDeletedFiles":"REMOVE"}'

# 4. Schedule
aws datasync update-task --task-arn <TASK> \
  --schedule ScheduleExpression="rate(5 minutes)"
```

> **Note**: `rate(5 minutes)` is for small environments. In high-file-count environments, task overlap risk exists (next invocation starts before previous completes). For production, recommend `rate(15 minutes)` to `rate(1 hour)`. If file counts exceed tens of thousands, split targets with includes/excludes filters across multiple tasks.

> **Bandwidth estimation**: DataSync transfer time is constrained by FSx for ONTAP throughput capacity + VPC network bandwidth. Estimate before implementation:
> - Example: 100GB data, 1Gbps bandwidth → theoretical ~13 min (effective 60-70% → ~20 min)
> - Enable VPC jumbo frames (MTU 9001) for significant NFS throughput improvement
> - FSx for ONTAP throughput capacity (128MB/s–4GB/s) may be the bottleneck

> **IAM least privilege**: Restrict the DataSync execution IAM Role to:
> - S3 destination: `s3:PutObject`, `s3:DeleteObject`, `s3:GetBucketLocation` only (resource ARN constrained to specific bucket/prefix)
> - FSx for ONTAP source: `fsx:DescribeFileSystems`, `datasync:*` minimum required
> - Wildcard permissions (`s3:*`, `fsx:*`) are prohibited

```sql
-- 5. Register UC External Location
CREATE EXTERNAL LOCATION fsxn_synced
  URL 's3://<BUCKET>/fsxn-sync/'
  WITH (STORAGE CREDENTIAL <credential_name>);

-- 6. Create table
CREATE TABLE catalog.schema.sensor_data
USING DELTA
AS SELECT * FROM parquet.`s3://<BUCKET>/fsxn-sync/sensor-data/`;
```

**Applicable scenarios**: Periodic analytics on structured data, ML training data, reporting

> **Recommendation: Sync from Snapshot**: Syncing directly from a production volume risks data inconsistency if files change during the sync. The recommended pattern is "Snapshot → FlexClone → DataSync":
> 1. Take a Snapshot (point-in-time consistent copy)
> 2. Create a FlexClone (instant, zero-copy)
> 3. Run DataSync against the FlexClone
> 4. Delete FlexClone after sync completes
>
> This ensures zero production impact and guarantees data consistency.

> **Auto Loader integration** (Data Engineering SA findings): After DataSync syncs to S3, use **Auto Loader** for incremental ingestion. Defining as a **DLT (Spark Declarative Pipelines)** streaming table further automates monitoring, error handling, and schema evolution:
> ```python
> # DLT pipeline definition
> import dlt
>
> @dlt.table
> def sensor_data():
>     return (spark.readStream
>         .format("cloudFiles")  # Auto Loader
>         .option("cloudFiles.format", "parquet")
>         .load("s3://<BUCKET>/fsxn-sync/sensor-data/")
>     )
> ```

> **Medallion architecture mapping**: DataSync → S3 is the **Bronze layer** (raw data). Silver (cleansed) / Gold (business aggregates) transformations are defined in DLT:
> ```
> Bronze: DataSync → S3 (raw files) → Auto Loader → streaming_table
> Silver: DLT quality checks (expectations: null/range/referential integrity) + schema normalization
> Gold:   DLT aggregation + business logic + Liquid Clustering + OPTIMIZE (BI query optimization)
> ```

> **Auto Loader mode selection**: The DataSync target S3 bucket supports **S3 Event Notifications** (unlike FSx for ONTAP S3 AP). Use Auto Loader's **file notification mode** (via SQS) — significantly reduces scan costs compared to directory listing mode.

---

### Path 2: Kafka → Structured Streaming → UC Delta (Real-time)

**FPolicy detects file changes, Lambda sends to Kafka, Databricks writes to UC Delta tables.**

```
FSx for ONTAP
  ↓ FPolicy (file operation event detection)
AWS Lambda
  ↓ Kafka Producer
Amazon MSK (Kafka)
  ↓ Structured Streaming (DBR 16.1+, UC service credentials)
UC-managed Delta Table
```

**Procedure overview** ([detailed guide](./kafka-clickhouse-unity-catalog-connectivity.md)):

```python
# Databricks Structured Streaming
df = (spark.readStream
  .format("kafka")
  .option("kafka.bootstrap.servers", "<MSK_BOOTSTRAP>")
  .option("subscribe", "fsxn-events")
  .option("kafka.security.protocol", "SASL_SSL")
  .option("kafka.sasl.mechanism", "AWS_MSK_IAM")
  .load()
)

# Write to UC-managed Delta table
(df.selectExpr("CAST(value AS STRING) as json_payload")
  .writeStream
  .format("delta")
  .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/")
  .toTable("catalog.schema.fsxn_events")
)
```

**Applicable scenarios**: Event-driven ingestion, near-real-time quality inspection, streaming ETL

> **Note: FPolicy delivers metadata events only**: FPolicy detects file **operation events** (create, update, delete, rename) but does not transfer file **content**. Typical design pattern:
> - **Kafka messages**: Metadata only (file path, size, operation type, timestamp)
> - **Payload reads**: Databricks Spark reads file content directly via S3 AP (outside UC path), or reads from DataSync-synced S3 copy
>
> For large files (video, etc.), note Lambda's 15-minute timeout and 10GB memory limit. For large payloads, combine with the DataSync path.

> **Manufacturing data flow origin**: PLCs / SCADA systems typically cannot act as Kafka Producers directly. The typical manufacturing data flow is:
> ```
> PLC / SCADA → NFS/SMB write → FSx for ONTAP → FPolicy detection → Lambda → Kafka
> ```
> FPolicy detects events "after a file is written", not direct streaming from PLCs.
> In environments where OT networks (FSx for ONTAP) and IT networks (Databricks / MSK) are separated, design Lambda / DataSync communication paths via Transit Gateway / VPC Peering.

> **Industrial protocol data flows**: In real manufacturing environments, intermediate layers are more common than direct PLC file output:
> ```
> Pattern A: PLC → OPC UA Server → Historian → CSV/Parquet export → FSx for ONTAP (NFS)
> Pattern B: PLC → MQTT Broker (Sparkplug B) → Kafka Bridge → MSK → UC Delta
> Pattern C: PLC → AWS IoT SiteWise Edge → FSx for ONTAP (NFS) → FPolicy / DataSync
> Pattern D: PLC → AWS IoT Greengrass (Lambda@Edge) → FSx for ONTAP (NFS) → DataSync → S3 → UC
> ```
> PLC output may be in proprietary binary format (.dat, .bin), requiring custom parser development for CSV/JSON conversion.

> **OT/IT security boundary**:
> - **Purdue Level 3.5 (IDMZ)**: FPolicy Lambda and DataSync agents should be placed in Level 3.5 (Industrial DMZ), avoiding direct OT (Level 0-3) to IT (Level 4-5) connections
> - **IDMZ allowed ports**: NFS 2049 (FSx for ONTAP → DataSync), HTTPS 443 (Lambda → MSK IAM / DataSync → S3), Kafka 9094-9098 (Lambda → MSK TLS/IAM)
> - **IEC 62443 compliant environments**: NFS communication should use `krb5p` (Kerberos encryption), with traffic routed through IDMZ conduits meeting channel security requirements
> - **Encryption**: DataSync uses TLS (in-transit) + S3 SSE-KMS (at-rest). FSx for ONTAP uses volume encryption (at-rest) + NFS krb5p (in-transit). Regulated industries (GxP, ITAR) require documentation of this encryption chain
> - **Data diode environments** (high-security): FSx for ONTAP → S3 one-way DataSync flow serves as a logical alternative to physical data diodes
> - **Audit log 4 layers** (Security Audit Analyst findings): Four layers of audit logs are generated across the data flow. Design correlation analysis for incident response:
>   1. ONTAP FPolicy / audit log (file operations)
>   2. DataSync CloudTrail (transfer operations)
>   3. S3 access logs / CloudTrail data events (object operations)
>   4. UC audit logs (table access, queries)
> - **Evidence preservation**: During security incidents, FSx for ONTAP **SnapLock** preserves tamper-proof Snapshots. Ensures forensic data integrity via WORM (Write Once Read Many)
> - **Secrets management**: Passwords for Lakehouse Federation external DB connections must be managed via **Databricks Secrets** (`secret('scope', 'key')` function). Plaintext in code is prohibited. AWS Secrets Manager integration also available

> **DLT / CDC patterns** (Data Engineering SA findings):
> - **DLT (Streaming Table)**: For production, define streaming tables in DLT instead of writing Structured Streaming directly. Built-in monitoring, error handling, and schema evolution.
> - **CDC (Change Data Capture)**: To replicate PostgreSQL / MySQL master data changes to UC Delta in real-time, use the **Debezium → Kafka → DLT** pattern:
>   ```
>   EC2 PostgreSQL (on FSx for ONTAP) → Debezium Connector → MSK → DLT Streaming Table → UC Delta
>   ```
>   Applicable for real-time replication of manufacturing master data (product masters, equipment registries) to the analytics platform.

> **Delivery guarantees and deduplication**: The FPolicy → Lambda → Kafka path provides **at-least-once** delivery. Network retries and Lambda retries may produce duplicate events. Design **event_id-based deduplication (MERGE / dedup)** on the UC Delta table side:
> ```sql
> MERGE INTO catalog.schema.fsxn_events AS target
> USING (SELECT * FROM stream_batch) AS source
> ON target.event_id = source.event_id
> WHEN NOT MATCHED THEN INSERT *;
> ```

> **Zerobus Ingest vs Kafka selection criteria**:
>
> | Dimension | Zerobus Ingest | Kafka (MSK) |
> |---|---|---|
> | Management | Databricks fully managed | User-managed or MSK managed |
> | Latency | Sub-second (direct to Databricks) | Seconds (via Spark Streaming) |
> | External consumers | ❌ Databricks only | ✅ Multiple consumers (ClickHouse, etc.) |
> | Edge connectivity | HTTPS REST / SDK | Kafka protocol (9094, etc.) |
> | Existing Kafka | Not needed | Leverage if available |
> | Best for | IoT events consumed only by Databricks | Multi-system fan-out |
>
> **Selection guidance**: Use Zerobus if Databricks is the only consumer. Use Kafka if fan-out to other systems (ClickHouse, etc.) is needed. Using both (Kafka + Zerobus → separate tables) is also valid.

---

### Path 3: Glue / EMR ETL → UC (Batch transformation)

**AWS Glue or EMR reads directly from FSx for ONTAP S3 AP, writes Delta/Parquet to S3.**

```
FSx for ONTAP (S3 AP)
  ↓ Glue ETL Job / EMR Spark
Amazon S3 (Delta / Parquet)
  ↓
UC External Location → Table
```

**Official tutorials**:
- [AWS Glue + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html)
- [EMR Serverless + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html)

**Applicable scenarios**: Large-scale batch transformation, schema conversion, data quality checks

---

### Path 4: Foreign Iceberg (via Glue REST, validating)

**Iceberg-format FSx for ONTAP data exposed to UC Foreign Catalog via Glue Iceberg REST endpoint.**

```
FSx for ONTAP (S3 AP)
  ↓ PyIceberg / Glue (write Iceberg tables)
S3 Tables / Glue Catalog (Iceberg metadata)
  ↓ Iceberg REST endpoint
UC Foreign Catalog (read-only)
```

**Status**: ❌ **Blocked confirmed (2026-06-21)**. `iceberg_rest` connection type not available in ap-northeast-1 workspace. S3 Tables managed bucket UC External Location registration also fails. ([Validation results](../../integrations/iceberg-metadata-catalog/databricks/uc-foreign-iceberg-validation.md#validation-execution-results-2026-06-21))

> **Operational note**: `REFRESH FOREIGN TABLE` does not execute automatically (Databricks does not auto-detect external Iceberg metadata updates). If periodic refresh is needed, configure a **Databricks Workflow** scheduled job.

---

### Path 5: ClickHouse → UC (DataLakeCatalog, reverse read)

**ClickHouse reads UC Delta/Iceberg tables via credential vending.**

After FSx for ONTAP data is ingested into UC Delta tables, ClickHouse can also reference the same data under UC governance.

```sql
-- ClickHouse side
CREATE DATABASE uc_delta
ENGINE = DataLakeCatalog('unity', '<WORKSPACE_URL>', '<TOKEN>')
SETTINGS catalog_type = 'unity';

SELECT * FROM uc_delta.catalog.schema.sensor_data LIMIT 10;
```

**Details**: [Kafka-ClickHouse-UC connectivity guide](./kafka-clickhouse-unity-catalog-connectivity.md)

---

## Verification Status Summary

| Path | Status | Date | Evidence |
|------|--------|------|----------|
| S3 AP → UC External Location | ⚠️ **Registers; reads denied** | 2026-08-12 | measured here, native-S3 control |
| ONTAP S3 → UC External Location | ❌ **Not supported confirmed** | 2026-05 | 02_research_findings.md |
| NFS mount from Databricks | ❌ **Blocked** | 2026-05 | seccomp restriction |
| DataSync → S3 → UC | ✅ **Verified** | 2026-05 | datasync-to-s3-guide.md |
| Kafka → Structured Streaming → UC | ✅ **Design verified** | 2026-06 | [kafka-clickhouse-unity-catalog-connectivity.md](./kafka-clickhouse-unity-catalog-connectivity.md) |
| Glue/EMR → S3 → UC | ✅ **Official tutorial** | — | AWS official documentation |
| Foreign Iceberg (Glue REST) | ❌ **Blocked confirmed** | 2026-06-21 | `iceberg_rest` type not supported + S3 Tables bucket EL creation fails |
| boto3 PoC (no governance) | ✅ **Working confirmed** | 2026-05 | ai-demo-guide.md |
| S3 AP → Athena (outside UC) | ✅ **Working confirmed** | 2026-04 | S3 AP Serverless Patterns repo |
| S3 AP → Bedrock KB (outside UC) | ✅ **Official tutorial** | — | AWS official documentation |

---

## DAIS 2026 Announcements Impact Analysis

| DAIS 2026 Announcement | Impact on FSx for ONTAP → UC | Explanation |
|---|---|---|
| **OpenSharing** | ❌ Does not directly resolve | Sharing protocol. Not a storage connector |
| **Delta Sharing Iceberg IRC** | ❌ Does not directly resolve | Table sharing. Requires tables to already exist in UC |
| **LTAP / Lakebase** | ❌ Does not directly resolve | Operational DB. Different storage layer from FSx for ONTAP |
| **Lakehouse//RT** | ❌ Does not directly resolve | Query engine. Does not operate on FSx for ONTAP |
| **Document Intelligence** | ⚠️ Indirectly usable | Available if documents are ingested via S3 |
| **Lakeflow Zerobus Ingest** | ⚠️ Indirectly usable | Kafka alternative. ap-northeast-1 available. Input is Databricks-side |
| **Unity AI Gateway** | ❌ Not related | Agent/model governance. Not a storage connector |
| **Agent Bricks** | ❌ Not related | Agent execution platform. Not a storage connector |
| **UC Foreign Iceberg GA** | ❌ **Blocked confirmed (2026-06-21)** | `iceberg_rest` type not available in ap-northeast-1. S3 Tables managed bucket cannot be registered as UC External Location. Not established publicly; asked Databricks |
| **OpenSharing SecureConnect** | ⚠️ Indirectly usable | Secures external sharing of UC tables. No per-recipient FW changes needed (one-time provider setup). Strengthens security for FSx for ONTAP data → S3 → UC → external organization sharing path |

---

## Why Direct Connection Is Not Possible: Technical Reasons

### UC External Location Session Policy Constraint

When Databricks assumes an IAM Role via AssumeRole, it internally generates a **session policy**. This policy is built assuming:

1. Storage paths are in `s3://<bucket-name>/prefix/` format
2. `arn:aws:s3:::<bucket-name>` is a valid S3 bucket ARN
3. ListObjectsV2 / GetObject / PutObject work via standard S3 API

For S3 Access Points:
- Paths are in `s3://<access-point-alias>/prefix/` format
- ARN is `arn:aws:s3:region:account:accesspoint/name`
- The session policy resource constraints do not correctly handle S3 AP ARNs

**Result**: Some top-level operations succeed (as a side effect), but subdirectory operations, table creation, and writes all return `AccessDenied`.

### NFS/SMB Mount Constraints

Databricks runtime runs on Docker containers with **seccomp (Secure Computing Mode) profiles** that prohibit `mount` / `umount` system calls:
- Kernel NFS mount (`mount -t nfs`) → blocked
- FUSE mounts (`s3fs`, `nfs-ganesha`) → blocked
- SMB mount (`mount -t cifs`) → blocked

This is a security design constraint with no workaround.

### ONTAP S3 Constraints

ONTAP S3 provides an S3 API-compatible protocol, but:
- No API exists to specify a custom endpoint URL for UC External Location
- UC only accepts `s3://<bucket-name>/` format paths and has no `endpoint_url` parameter for custom S3 endpoints

---

## Selection Guide: Recommendations by Use Case

```
Q: Data freshness requirement?
│
├── Real-time (seconds) ──── Path 2: Kafka → Structured Streaming
│
├── Near-real-time (minutes) ─ Path 1: DataSync (rate(5 min)) → UC
│
├── Batch (hours to daily) ── Path 1: DataSync (daily) or Path 3: Glue/EMR
│
└── Ad-hoc analytics ──────── Athena + S3 AP (no UC needed) or boto3 PoC
```

```
Q: Governance requirement?
│
├── Full UC governance required ── Path 1 or 2 (via S3, create UC tables)
│
├── AWS-side governance sufficient ── Athena + S3 AP + IAM policies
│
├── Snowflake governance ───── Snowflake External Table (S3 AP directly supported)
│
└── No governance (PoC) ────── boto3 PoC (Instance Profile)
```

```
Q: Data copy acceptable?
│
├── Copy acceptable ───── Path 1 (DataSync) / Path 2 (Kafka) / Path 3 (ETL)
│
├── Minimize copies ───── UC Foreign Iceberg (validating) / Athena (outside UC)
│
└── Zero-copy required ── Not possible with UC today. Recommend Athena or Snowflake
```

---

## Phased Adoption Recommended Steps

(Manufacturing IT/OT Convergence Program Manager findings)

For large manufacturing environments, implement paths incrementally rather than all at once:

| Phase | Content | Duration | Success Criteria |
|-------|---------|----------|------------------|
| **1. PoC** | DataSync → S3 → UC table (1 volume, structured data only) | 2-4 weeks | Queryable in UC, data freshness OK |
| **2. Production** | DataSync schedule optimization + Auto Loader + DLT (medallion) | 4-8 weeks | Bronze/Silver/Gold pipeline running |
| **3. Real-time** | FPolicy → Lambda → Kafka → SS → UC Delta (event-driven) | 4-8 weeks | Near-real-time event ingestion |
| **4. AI/ML** | UC Volume + Feature Store + AI Search + Bedrock KB | 4-12 weeks | ML pipeline operational |
| **5. Multi-system** | Lakehouse Federation (EC2 DB) + ClickHouse integration | 4-8 weeks | Unified analytics view |

> **Note**: Phases 1-2 apply to nearly all environments. Phases 3+ are use-case-driven and selectively implemented.

---

## EC2 Self-Managed DB × FSx for ONTAP × UC Connection Patterns

### Overview

When running self-managed databases/streaming platforms on EC2 with FSx for ONTAP as the data store, this section covers how each connects to Databricks UC.

### UC Lakehouse Federation Supported Databases

UC Lakehouse Federation executes **pushdown queries** against external databases via JDBC, providing UC governance on reads:

| Database | Federation Status | EC2 Self-Managed | FSx for ONTAP as Data Store | UC Connection |
|---|:---:|:---:|:---:|---|
| **PostgreSQL** | ✅ GA | ✅ | ✅ NFS mountable | `CREATE CONNECTION TYPE postgresql` |
| **MySQL** | ✅ GA | ✅ | ✅ NFS mountable | `CREATE CONNECTION TYPE mysql` |
| **SQL Server** | ✅ GA | ✅ | ⚠️ SMB only (Linux version: NFS) | `CREATE CONNECTION TYPE sqlserver` |
| **Oracle** | ✅ Public Preview | ✅ | ✅ NFS (ASM not supported, FS-based only) | `CREATE CONNECTION TYPE oracle` |
| **Teradata** | ✅ Public Preview | ✅ | ⚠️ Limited (proprietary storage preferred) | `CREATE CONNECTION TYPE teradata` |
| **Snowflake** | ✅ GA | — (SaaS) | — | `CREATE CONNECTION TYPE snowflake` |
| **Redshift** | ✅ GA | — (Managed) | — | `CREATE CONNECTION TYPE redshift` |
| **BigQuery** | ✅ GA | — (SaaS) | — | `CREATE CONNECTION TYPE bigquery` |
| **Databricks** | ✅ GA | — | — | `CREATE CONNECTION TYPE databricks` |

> **Critical constraints**:
> - Lakehouse Federation is **read-only**. INSERT / UPDATE / DELETE from UC to external DBs is not supported. Data ingestion to external DBs must be designed separately.
> - **Network prerequisites**: If the EC2 DB is in a private subnet, connecting from Databricks serverless compute requires **NCC (Network Connectivity Config)** or **PrivateLink** configuration. Classic compute requires VPC Peering / Transit Gateway.
>   - NCC limits (AWS): Max 10 NCCs / region per account, 30 Private Endpoints / region
>   - NCC cost: Per-hour charge per Private Endpoint + per-GB data processing charge
> - **Query characteristics**: Federation uses JDBC pushdown, making it unsuitable for full-scan analytics on large datasets. It is optimized for filtering / lookup / small-to-medium aggregation queries. For large-scale analytics, use Path 1 (DataSync → UC Delta).
> - **Non-pushdown operations** (Federation Query Optimizer findings): WINDOW functions, complex UDFs, some LIKE patterns (leading wildcard `%abc`) are NOT pushed down — all rows are transferred over the network causing performance degradation. Check query plans with `EXPLAIN` and verify PushedFilters / PushedAggregates.

### EC2 Self-Managed DBs That Can Use FSx for ONTAP as Data Store

| DB / Middleware | Data Directory | FSx for ONTAP Protocol | Practicality | UC Connection |
|---|---|---|:---:|---|
| **PostgreSQL** | `data_directory` | NFS | ✅ Recommended | Lakehouse Federation (JDBC) |
| **MySQL / MariaDB** | `datadir` | NFS | ✅ Recommended | Lakehouse Federation (JDBC) |
| **MongoDB** | `dbPath` | NFS | ⚠️ Works but WiredTiger journal fsync tuning required. **Lakehouse Federation not supported** (Spark MongoDB Connector only) | Spark MongoDB Connector → UC Delta |
| **ClickHouse** | `path` | NFS / ONTAP S3 (cold tier) | ✅ Verified | DataLakeCatalog (UC → CH) / reverse only |
| **Kafka** | `log.dirs` | NFS | ⚠️ If latency increase acceptable | Structured Streaming → UC Delta |
| **Redis / Valkey** | RDB/AOF files | NFS | ⚠️ Persistence only (cache-primary) | Spark Redis Connector → UC Delta |
| **Elasticsearch / OpenSearch** | `path.data` | NFS | ❌ data NOT recommended ([officially unsupported](https://www.elastic.co/guide/en/elasticsearch/reference/current/storage-types.html), translog corruption risk). ✅ Snapshot repository via NFS is supported | Spark ES Connector → UC Delta |
| **Apache Cassandra** | `data_file_directories` | NFS | ❌ Not recommended (local SSD design) | Spark Cassandra Connector → UC Delta |
| **Neo4j** | `dbms.directories.data` | NFS | ⚠️ Small-scale only | Spark Neo4j Connector → UC Delta |
| **InfluxDB** | `data-dir` | NFS | ⚠️ Small-scale only | Spark JDBC (Flux SQL) → UC Delta |
| **TimescaleDB** | `data_directory` (PG extension) | NFS | ✅ Same as PostgreSQL (Federation supported) | Lakehouse Federation (JDBC) — same path as PostgreSQL |
| **Apache Druid** | `druid.storage.*` | NFS (deep storage) / ONTAP S3 | ✅ Suitable as deep storage (when using ONTAP S3, custom endpoint URL configuration via `druid.storage.baseKey` required) | Spark JDBC → UC Delta |
| **Apache Pinot** | segment store | NFS / ONTAP S3 | ⚠️ Viable as deep storage | Spark Connector → UC Delta |
| **MinIO** | `MINIO_VOLUMES` | NFS / block storage | ✅ | S3-compatible → Spark read → UC Delta |

### DB × FSx for ONTAP × UC Connection Pattern Classification

```
Pattern A: Lakehouse Federation (JDBC pushdown)
  EC2 DB (PostgreSQL/MySQL/SQL Server/Oracle)
    ↑ data on FSx for ONTAP (NFS/SMB)
    ↓ JDBC
  Databricks UC Foreign Catalog
    → UC governance applied (tags, row filters, lineage)
    → No data movement (queries execute remotely)

Pattern B: Structured Streaming → UC Delta
  EC2 Streaming platform (Kafka/Pulsar)
    ↑ logs on FSx for ONTAP (NFS)
    ↓ Kafka protocol
  Databricks Structured Streaming
    → Write to UC-managed Delta tables
    → Near-real-time

Pattern C: Spark Connector → UC Delta (Batch ETL)
  EC2 DB (MongoDB/Cassandra/Elasticsearch/Redis)
    ↑ data on FSx for ONTAP (NFS)
    ↓ Dedicated Spark Connector (JDBC/API)
  Databricks ETL Job
    → Write to UC-managed Delta tables
    → Batch (scheduled)

Pattern D: Reverse read (external engine → UC)
  EC2 DB (ClickHouse)
    ↓ UC Iceberg REST / credential vending
  Read Databricks UC Delta/Iceberg tables
    → External engines consume data under UC governance
```

### Kafka × FSx for ONTAP Details

| Aspect | NFS (FSx for ONTAP) | Local EBS |
|--------|---------------------|-----------|
| Latency | +1-3ms (network hop) | ~0.1ms |
| `log.dirs` usage | ✅ Works | ✅ Recommended |
| Snapshot recovery | ✅ Full broker PIT recovery | EBS Snapshot (AZ-scoped) |
| SnapMirror DR | ✅ Cross-region | EBS is AZ-scoped, separate design needed |
| Multi-broker sharing | ❌ Not recommended (partition exclusivity assumed) | — |
| MSK usage | ❌ Not possible (managed storage fixed) | — |
| Tiered Storage | FabricPool auto-tiers cold segments to S3 | Kafka native Tiered Storage |

**Recommended patterns**:
- **Latency-critical (production streaming)**: EBS (io2/gp3) + Kafka MirrorMaker 2 for DR
- **Data protection / operational integration**: FSx for ONTAP NFS + Snapshot/SnapMirror (when latency acceptable)
- **Hybrid**: Hot data = EBS, cold segments = FSx for ONTAP (FabricPool to S3 tier)

### ClickHouse × FSx for ONTAP Details

**storage_policy tiered design**:

```xml
<!-- ClickHouse storage_policy configuration example -->
<storage_configuration>
  <disks>
    <hot>
      <type>local</type>
      <path>/var/lib/clickhouse/</path> <!-- local SSD -->
    </hot>
    <cold>
      <type>s3</type>
      <endpoint>https://<SVM_S3_ENDPOINT>:443/<BUCKET>/</endpoint>
      <access_key_id>***</access_key_id>
      <secret_access_key>***</secret_access_key>
    </cold>
  </disks>
  <policies>
    <tiered>
      <volumes>
        <hot><disk>hot</disk></hot>
        <cold><disk>cold</disk></cold>
      </volumes>
      <move_factor>0.1</move_factor> <!-- move to cold at 10% usage -->
    </tiered>
  </policies>
</storage_configuration>
```

**UC connection — DataLakeCatalog type selection**:
- `catalog_type = 'unity'` → Read UC **Delta tables**
- `catalog_type = 'rest'` → Read **Iceberg tables** via UC Iceberg REST endpoint

```sql
-- Read Delta tables
CREATE DATABASE uc_delta ENGINE = DataLakeCatalog('unity', '<URL>', '<TOKEN>')
SETTINGS catalog_type = 'unity';

-- Read Iceberg tables
CREATE DATABASE uc_iceberg ENGINE = DataLakeCatalog('rest', '<URL>', '<TOKEN>')
SETTINGS catalog_type = 'rest';
```

> **⚠️ ClickHouse Keeper / ZooKeeper on FSx for ONTAP is NOT recommended**: Keeper transaction logs require ultra-low-latency (<1ms) fsync. The additional 1-3ms from NFS impacts cluster-wide replication performance. Place Keeper / ZK data on **local SSD (io2)**.

### PostgreSQL / MySQL × FSx for ONTAP Details

PostgreSQL and MySQL are the **most recommended** combinations with FSx for ONTAP:

- PostgreSQL: `data_directory = '/mnt/fsxn/pgdata'` → WAL / tablespaces on NFS
- MySQL: `datadir = /mnt/fsxn/mysql` → InnoDB tablespaces on NFS

> **Recommended NFS mount options** (NFS Performance Architect / PostgreSQL DBA findings):
> ```bash
> # DB workload-optimized FSx for ONTAP NFS mount
> mount -t nfs4.1 <SVM_NFS_LIF>:/vol1/pgdata /mnt/fsxn/pgdata \
>   -o hard,nointr,rsize=1048576,wsize=1048576,noac,nfsvers=4.1
> ```
> - `nfsvers=4.1`: Session trunking + delegation for improved performance
> - `noac`: Disable attribute caching (ensures DB write-read consistency)
> - `hard`: Infinite retry on server non-response (prevents data corruption)
> - `rsize/wsize=1048576`: 1MB I/O (maximizes throughput)

> **MySQL-specific note**: On NFS, use `innodb_flush_method = fsync`. `O_DIRECT` may not function correctly on NFS.

> **Lakebase migration option**: If PostgreSQL workloads prioritize UC governance integration, **Databricks Lakebase** (managed PostgreSQL-compatible DB, GA) is an alternative. Lakebase offers native UC integration + Lakehouse//RT queries + Private Link. Note: not available in ap-northeast-1 (as of 2026-06-18).

**UC connection**:
```sql
-- Databricks side
CREATE CONNECTION pg_on_fsxn TYPE postgresql
OPTIONS (
  host = '<EC2_PRIVATE_IP>',
  port = '5432',
  user = 'readonly_user',
  password = secret('scope', 'pg_password')
);

CREATE FOREIGN CATALOG pg_catalog
USING CONNECTION pg_on_fsxn
OPTIONS (database = 'manufacturing');

-- Query (pushdown execution)
SELECT * FROM pg_catalog.public.sensor_readings
WHERE timestamp > '2026-06-01';
```

**FSx for ONTAP value**:
- Snapshot → No logical backup needed (consistent PIT recovery)
- FlexClone → Instant dev/test DB creation (zero-copy clone of production data)
- SnapMirror → DR site replication (no pg_basebackup / mysqldump needed)
- Multi-protocol → Same volume's DB data also analyzable via S3 AP from Glue/Athena

> **WAL performance note** (Databricks SA findings): PostgreSQL WAL fsync over NFS adds 1-3ms latency vs local disk. For high-throughput write environments, consider:
> - `synchronous_commit = off` (only if data loss risk is acceptable)
> - Separate WAL on local EBS, data files only on FSx for ONTAP NFS
> - Streaming replication (primary: EBS, standby: FSx for ONTAP → connect Lakehouse Federation to standby)

### AI/ML Data Access Paths

Paths for using FSx for ONTAP data with Databricks AI/ML features :

| AI/ML Feature | Required Data Form | Path from FSx for ONTAP |
|---|---|---|
| **Feature Store** | UC table | DataSync → S3 → UC table → Feature Table registration. Feature freshness depends on DataSync RPO (5 min – 24 hours). Use Path 2 (Kafka → SS) for real-time feature updates |
| **AI Search (Vector Search)** | UC Volume or table | DataSync → S3 → UC Volume → AI Search Pipeline |
| **MLflow Artifact** | UC Volume or S3 | DataSync → S3 → UC Volume path |
| **Model Serving (input data)** | API request | App layer reads via S3 AP → call serving API |
| **Bedrock KB (RAG)** | S3 AP direct | FSx for ONTAP S3 AP → Bedrock KB (outside UC, official tutorial) |
| **Document Intelligence** | Via S3 | DataSync → S3 → Lakeflow → structured table |

> **Edge AI image inspection path**: Path for managing inspection images (with inference results) from NVIDIA Jetson / AWS Panorama edge AI cameras in UC:
> ```
> Edge AI camera → local NVMe buffer → batch transfer → FSx for ONTAP (NFS) → DataSync → S3 → UC Volume
> ```
> High-speed capture (10-100 images/sec/line) requires local buffering. Direct NFS write is not recommended due to bandwidth constraints.

> **RAG / AI Search pipeline**: Concrete flow to make FSx for ONTAP documents searchable via AI Search:
> ```
> FSx for ONTAP (documents) → DataSync → S3 → UC Volume
>   → Spark UDF (chunking: RecursiveCharacterTextSplitter etc.)
>   → Embedding Model (Databricks FMAPI or Bedrock)
>   → AI Search Index (sync index on UC table)
>   → Agent retriever tool (RAG query)
> ```

> **Image embedding pipeline**: To enable similarity search on inspection images via AI Search:
> ```
> UC Volume (inspection images) → Spark UDF (CLIP / ViT embedding generation) → AI Search Index → similar image search
> ```

---

## Cost Comparison

| Path | Storage Cost | Compute Cost | Operational Overhead |
|------|-------------|--------------|---------------------|
| DataSync → S3 → UC | FSx for ONTAP + S3 (duplicate) | DataSync transfer + Databricks | Medium (schedule management) |
| Kafka → SS → UC | FSx for ONTAP (metadata only in Kafka) | MSK + Databricks Streaming | High (pipeline management) |
| Glue/EMR ETL | FSx for ONTAP + S3 (duplicate) | Glue/EMR job execution | Medium (job scheduling) |
| Athena (outside UC) | FSx for ONTAP only | Query scan-based billing | Low (serverless) |
| boto3 PoC | FSx for ONTAP only | Databricks cluster | Low (no governance) ⚠️ Data exfiltration risk |

> **boto3 PoC security warning**: The boto3 PoC path completely bypasses UC governance, creating risk of users downloading data locally and exfiltrating externally. If used:
> - Enable Databricks workspace **egress controls** (S3 bucket policy + VPC endpoint policy to restrict destinations)
> - Apply **IP ACL** for source access restriction
> - Enable **audit logging** (CloudTrail + UC audit logs)
> - Time-limited approval (PoC period only)

---

## Related Documentation

| Document | Content |
|----------|---------|
| [Industry Solution Catalog](./industry-solution-catalog.md) | **Paired with this guide**. Per-industry use case → recommended path → governance mapping |
| [DataSync → S3 Guide](./datasync-to-s3-guide.md) | Detailed DataSync procedures and schedule design |
| [Kafka-ClickHouse-UC Connectivity Guide](./kafka-clickhouse-unity-catalog-connectivity.md) | Streaming + catalog connectivity technical details |
| [Databricks Integration README](../../integrations/databricks/README.md) | S3 AP verification results, error evidence, recommended patterns |
| [OpenSharing & Volume Guide](../../integrations/databricks/docs/en/delta-sharing-volume-guide.md) | Detailed design for 3 OpenSharing patterns |
| [AI Demo Guide](../../integrations/databricks/docs/en/ai-demo-guide.md) | Evidence of working and blocked demos |
| [Foreign Iceberg Validation Plan](../../integrations/iceberg-metadata-catalog/databricks/uc-foreign-iceberg-validation.md) | UC Foreign Catalog validation SQL via Glue REST |
| [OpenSharing Integration Analysis](./opensharing-integration-analysis.md) | OpenSharing × FSx for ONTAP touchpoint evaluation |
| [AWS Official: FSx for ONTAP + Bedrock KB](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) | Official RAG tutorial (path outside UC) |
| [AWS Official: FSx for ONTAP + Glue](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) | Official Glue ETL tutorial |
| [AWS Official: FSx for ONTAP + EMR](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html) | Official EMR Serverless tutorial |

---

## Future Outlook

> **Note on FabricPool and UC**: Data tiered to S3 via FSx for ONTAP's FabricPool technically resides on standard S3 buckets and is UC External Location-accessible. However, the FabricPool tier target is ONTAP-managed internal storage not intended for direct user registration in UC. This path is not practical and is not recommended.

| Item | Status | Unblocking Condition |
|------|--------|---------------------|
| UC External Location S3 AP support | ❌ Not supported (feature request filed) | Databricks platform development |
| UC Foreign Iceberg × S3 Tables | ❌ Blocked confirmed (2026-06-21) | `iceberg_rest` type not supported + S3 Tables EL registration fails. Awaiting Databricks Support |
| OpenSharing Volumes connector | 🔲 Design phase | Databricks development + FSx for ONTAP support |
| Lakebase × FSx for ONTAP | ⚠️ Lakebase not in ap-northeast-1 | Databricks region expansion |

