# Iceberg Metadata Catalog for Unstructured Data: Bridging FSx for ONTAP and Modern Data Platforms

🌐 [日本語](../ja/iceberg-metadata-catalog.md) | English

## Executive Summary

This document defines an architecture pattern that uses **Apache Iceberg as a metadata catalog** for unstructured data stored on FSx for ONTAP. Rather than moving raw files into a data platform, we keep the actual data on ONTAP (preserving deduplication, multi-protocol access, and Snapshot capabilities) while managing metadata — file paths, tags, AI-generated classifications, and vector embeddings — in managed Iceberg tables accessible from any analytics engine.

### Problems This Architecture Solves

| # | Problem | Solution |
|---|---------|----------|
| 1 | Unstructured data is undiscoverable ("where is what?") | Iceberg metadata table catalogs all files. Instant SQL/natural language search |
| 2 | Sharing requires "copy and hand over" | Iceberg REST endpoint + governance policies enable instant sharing without data movement |
| 3 | AI/ML usage requires manual file selection and processing | FPolicy → Step Functions automates classification and embedding generation for new files |
| 4 | S3 copy storage costs keep growing | Raw data stays on FSx for ONTAP (50-70% dedup); only metadata in S3 Tables |
| 5 | No governance on unstructured data | Lake Formation LF-Tags / Horizon Row Access Policy controls both metadata and raw data access |

**Key Technologies**:
- **Amazon S3 Tables** — Fully managed Apache Iceberg tables with automatic compaction, 3x query performance, Iceberg REST endpoint
- **FSx for ONTAP S3 Access Points** — S3-compatible access to ONTAP volumes (read path for AI/analytics)
- **S3 Metadata** — Automatic Iceberg table generation from S3 object metadata (alternative path via DataSync)
- **Iceberg REST Catalog** — Cross-platform access from Databricks, Snowflake, Spark, and other engines

## Core Concept: Hot Metadata × Cold Data Separation

```
┌──────────────────────────────────────────────────────────────────────┐
│  HOT: Metadata Layer (Apache Iceberg on S3 Tables)                   │
│  - File path, tags, classification, embeddings                       │
│  - Fast SQL queries (Athena, Redshift, EMR)                          │
│  - Vector similarity search (OpenSearch)                             │
│  - Cross-platform access via Iceberg REST endpoint                   │
│  - Governed by Lake Formation / Horizon Catalog                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ file_path reference
┌──────────────────────────────▼───────────────────────────────────────┐
│  COLD: Data Layer (FSx for ONTAP)                                    │
│  - Actual files: PDF, images, CAD, video, audio, logs                │
│  - Deduplication (50-70% storage reduction)                          │
│  - Multi-protocol: NFS/SMB (existing workflows)+ S3 AP (AI/analytics)│
│  - Snapshot: consistent point-in-time for batch AI processing        │
│  - FabricPool: automatic tiering to lower-cost storage               │
└──────────────────────────────────────────────────────────────────────┘
```

**Why this separation?**

| Concern | Metadata Layer (S3 Tables) | Data Layer (FSx for ONTAP) |
|---------|---------------------------|---------------------------|
| Query speed | Sub-second (Iceberg optimized) | N/A (not queryable) |
| Storage efficiency | Minimal (~1GB per 100K files) | Dedup + compression (50-70% savings) |
| Multi-engine access | ✅ Iceberg REST endpoint | ✅ S3 AP + NFS/SMB |
| Governance | Lake Formation / Horizon | S3 AP policy + ONTAP ACLs |
| AI processing | Embeddings stored here | Raw files read from here |
| Cost | ~$5-15/month (metadata only) | Depends on data volume |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Governance Layer                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │Lake Formation│  │Snowflake Horizon │  │Databricks Unity      │   │ 
│  │LF-Tags       │  │Row Access Policy │  │Catalog (External)    │   │
│  │Column/Row    │  │Dynamic Masking   │  │                      │   │
│  └──────────────┘  └──────────────────┘  └──────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              Metadata Layer (Apache Iceberg)                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ S3 Tables (table bucket) — Primary Metadata Store            │   │
│  │                                                              │   │
│  │ Schema:                                                      │   │
│  │   file_id, file_path, file_name, file_type, file_size        │   │
│  │   created_at, modified_at, source_volume, access_point_arn   │   │
│  │   tags (map), classification, confidence_score               │   │
│  │   embedding_vector (binary), summary                         │   │
│  │   sensitivity_level, has_pii, anonymized_path                │   │
│  │                                                              │   │
│  │ Access: Iceberg REST endpoint → Databricks, Snowflake, Spark │   │
│  │ Governance: SageMaker Lakehouse + Lake Formation             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              Event & Processing Layer                               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Real-time Path: FPolicy → Fargate → SQS → Lambda            │    │
│  │   (file create/modify/delete → metadata sync within 5 min)  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ AI Enrichment: Step Functions → Bedrock/Cortex/Mosaic AI    │    │
│  │   (classification, embedding, summarization, PII detection) │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Batch Path (Alternative): DataSync → S3 → S3 Metadata       │    │
│  │   (automatic Iceberg table from S3 object metadata)         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              Storage Layer                                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ FSx for ONTAP                                               │    │
│  │   • S3 Access Point → AI/Analytics read access              │    │
│  │   • NFS/SMB → Existing workflows (CAD tools, editors)       │    │
│  │   • Deduplication + Compression (50-70% savings)            │    │
│  │   • Snapshot → Consistent batch processing input            │    │
│  │   • FPolicy → Real-time file event detection                │    │
│  │   • FabricPool → Automatic cold data tiering                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ On-premises ONTAP (optional)                                │    │
│  │   • SnapMirror → FSx for ONTAP (block-level replication)    │    │
│  │   • FlexCache S3 AP (future: ONTAP 9.18.1 on-prem ready)    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Platform-Specific Implementation Paths

### AWS Native Path (Athena + Lake Formation + Bedrock)

**Best for**: Organizations already invested in AWS-native analytics stack.

```
FSx for ONTAP ──S3 AP──→ Bedrock KB (RAG, Vision)
                    │
                    └──→ Lambda (metadata extraction)
                              ↓
                    S3 Tables (Iceberg metadata)
                              ↓
                    Glue Catalog (SageMaker Lakehouse)
                              ↓
                    Lake Formation (LF-Tags governance)
                              ↓
                    Athena / EMR / Redshift Spectrum (queries)
```

**Key advantages**:
- FSx for ONTAP S3 AP direct access from Athena and Bedrock (no S3 copy needed for reads)
- Lake Formation enforces governance across all AWS analytics engines
- S3 Tables auto-compaction eliminates table maintenance
- Bedrock Knowledge Base indexes metadata for natural language search

**Governance model**: Lake Formation LF-Tags applied to metadata table columns/rows. Example tags: `department=engineering`, `sensitivity=confidential`, `classification=medical_image`.

> **Region availability note**: Verify S3 Tables availability in your target region before deployment. If S3 Tables is not yet available in ap-northeast-1, use Glue Catalog with self-managed Iceberg tables as fallback (same schema, manual compaction required). Migration to S3 Tables is straightforward once available.

### Databricks Path (Unity Catalog + Mosaic AI)

**Best for**: Organizations with existing Databricks investment (UC, Delta Lake, MLflow).

```
S3 Tables ──Iceberg REST endpoint──→ Databricks External Catalog
                                              ↓
                                    Unity Catalog governance
                                              ↓
                                    Spark SQL / Mosaic AI queries
                                              ↓
                                    Vector Search (similar file discovery)
```

**Key advantages**:
- Iceberg REST endpoint enables direct access to S3 Tables metadata from Databricks
- Mosaic AI for automated image/document classification pipeline
- Vector Search for embedding-based similar file discovery
- Delta Sharing for cross-organization metadata sharing

**Current constraint**: Unity Catalog session policy does not recognize S3 AP ARN format for direct file access. Workaround: metadata queries via Iceberg REST + file access via Bedrock/Lambda.

**Vector Search integration**: For Databricks-first organizations, embeddings can be synced from S3 Tables to Mosaic AI Vector Search Index for native Databricks similarity search. This provides tighter integration with Databricks notebooks and Model Serving compared to OpenSearch Serverless.

**Governance model**: Unity Catalog External Catalog + Lake Formation supplement for cross-engine enforcement.

**Future outlook — Lakehouse Federation**: Once Databricks Lakehouse Federation natively supports S3 Tables Iceberg REST endpoint, both metadata queries and raw data access can be completed within the Databricks workspace. Unity Catalog 2.0's native Iceberg support (announced 2025) accelerates this direction.

> **DAIS 2026 update (2026-06-16, evidence tier: Public)**: Databricks announced Iceberg v3 GA, Managed Iceberg GA, Foreign Iceberg GA, new federation connectors, and cross-engine ABAC ([What's new with Unity Catalog](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026)). Two items relate directly to this architecture:
> - **FILE type (Beta)**: managed Delta/Iceberg tables can now natively govern unstructured data (PDFs, images, audio, video). This is a managed option for *governing* unstructured payloads inside UC tables — complementary to (not a replacement for) this architecture's role of AI-enriched, cross-engine *discovery* (classification, PII handling, vector similarity) over files that remain on FSx for ONTAP and stay accessible to non-Databricks engines (Athena, Snowflake, EMR). It also relates to UC Volumes (directory-level governance) and the OpenSharing Volumes asset.
> - **External access to managed Delta tables (Public Preview)** and the new federation connectors may affect the S3 AP / S3 Tables access constraint noted above. **Re-verification needed**: confirm whether Foreign Iceberg can now resolve S3 Tables internal buckets (the prior blocker was External Location validation rejecting the standard S3 API).
> - **Iceberg v4 / Delta 5.0 convergence (roadmap)**: Databricks has proposed that Delta Lake 5.0 adopt the Iceberg v4 metadata tree as its native content metadata, producing a single on-disk structure that both Delta and Iceberg clients read and write directly — no translation layers or conversion overhead ([UC blog](https://www.databricks.com/blog/unity-catalog-and-next-era-apache-icebergtm), [DAIS session](https://www.databricks.com/dataaisummit/session/format-co-evolution-how-iceberg-v4-and-delta-50-share-unified-metadata)). Long-term implication: the format choice between Delta and Iceberg becomes moot; UniForm (the current translation layer) would no longer be needed; and cross-engine access to this architecture's Iceberg metadata tables simplifies further.

### Snowflake Path (Horizon Catalog + Cortex AI)

**Best for**: Organizations with existing Snowflake investment (Cortex AI, Data Sharing, Horizon).

```
FSx for ONTAP ──S3 AP Stage──→ COPY INTO → Managed Iceberg Table
                                                    ↓
                                          Cortex AI (PARSE_DOCUMENT, Vision)
                                                    ↓
                                          Horizon Iceberg REST Catalog
                                                    ↓
                                          External engines (Spark, Databricks)
                                          with Row Access Policy enforcement
```

**Key advantages**:
- Cortex AI processes unstructured data directly (PARSE_DOCUMENT, COMPLETE, Vision)
- Horizon Catalog enforces governance on external engine access (Row Access Policy, Masking)
- STORAGE_REQUEST_HISTORY audits external engine access
- Secure Data Sharing for zero-copy cross-organization metadata sharing

**Current constraint**: TO_FILE fails on S3 AP stages (engineering investigation in progress). Workaround: COPY FILES to internal stage for Vision AI processing.

**Governance model**: Horizon Catalog Row Access Policies + Dynamic Masking, enforced on both Snowflake and external engines.

---

## Decision Matrix: Metadata Layer Selection

| Criteria | S3 Tables | Snowflake Managed Iceberg | Glue Catalog (self-managed Iceberg) |
|----------|-----------|--------------------------|-------------------------------------|
| **Management overhead** | None (fully managed) | None (fully managed) | Medium (manual compaction, snapshot expiry) |
| **Query performance** | 3x vs self-managed | Comparable | Baseline |
| **Cross-platform access** | ✅ Iceberg REST endpoint | ✅ Horizon REST Catalog | ✅ Glue Catalog + Iceberg |
| **Governance** | Lake Formation + SageMaker Lakehouse | Horizon (Row Access Policy, Masking) | Lake Formation |
| **External engine enforcement** | ✅ (via Lake Formation) | ✅ (via Horizon) | ✅ (via Lake Formation) |
| **Auto-compaction** | ✅ Built-in | ✅ Built-in | ❌ Manual or Glue job |
| **Cost (100K records)** | ~$5-15/month | Included in Snowflake compute | ~$5/month + maintenance compute |
| **Region availability** | Expanding (check current) | All Snowflake regions | All AWS regions |
| **Best for** | AWS-native + multi-engine | Snowflake-first + external sharing | Maximum flexibility |

**Recommendation**: Start with S3 Tables for AWS-native path. Add Snowflake Managed Iceberg if Horizon governance is required for external engines. Use Glue Catalog as fallback for regions where S3 Tables is not yet available.

---

## Event Detection: FPolicy Pipeline vs DataSync + S3 Metadata

| Aspect | FPolicy Pipeline | DataSync + S3 Metadata |
|--------|-----------------|----------------------|
| **Latency** | ~5 seconds (real-time) | Minutes to hours (batch) |
| **Data copy required** | No (metadata only) | Yes (full file copy to S3) |
| **Storage cost** | Minimal (metadata in S3 Tables) | Significant (S3 copy of all files) |
| **Setup complexity** | Medium (FPolicy Server + Lambda) | Low (DataSync task + enable S3 Metadata) |
| **Metadata richness** | Custom (any field extractable) | Standard S3 object metadata + custom tags |
| **AI enrichment** | Separate pipeline (Step Functions) | Separate pipeline (same) |
| **Best for** | Real-time catalog, no S3 copy budget | Batch processing, S3 already required |

**Recommendation**: Use FPolicy pipeline as primary path (eliminates S3 copy cost). Use DataSync + S3 Metadata as supplementary path when S3 copy is already required for other reasons (e.g., Bedrock KB data source, cross-region access).

> **Iceberg implementation note**: When writing to S3 Tables via the FPolicy pipeline, use PyIceberg SDK's `append` operation. Iceberg format-version=2 supports Row-level Deletes (Position Delete Files), enabling efficient soft delete implementation for file deletions. S3 Tables' automatic compaction periodically merges Position Delete Files, minimizing read performance impact.

> **Hybrid architecture note**: FPolicy pipeline and DataSync path are **not mutually exclusive** — they can be combined. For example, use FPolicy for real-time metadata sync while maintaining DataSync for Bedrock KB S3 copies. In this case, JOIN the S3 Metadata table with the S3 Tables metadata table in Athena for unified queries across both metadata sources.

### Hybrid Architecture: FPolicy + DataSync Combined

```
FSx for ONTAP
  ├── FPolicy → SQS → Lambda → S3 Tables (real-time metadata)
  │                                  ↓
  │                          Athena / Databricks / Snowflake
  │
  └── DataSync (daily) → S3 General Purpose Bucket
                              ├── S3 Metadata (auto Iceberg)
                              ├── Bedrock KB (RAG data source)
                              └── Cross-region DR copy
```

**Decision criteria**:
- Metadata search only needed → FPolicy pipeline only (no S3 copy)
- Bedrock KB RAG also needed → FPolicy + DataSync combined
- DR requirement → DataSync for cross-region S3 copy + S3 Metadata

### Production Notes: S3 AP I/O and Checkpoint Design

#### S3 Access Point Throughput Impact

FSx for ONTAP S3 Access Point reads consume from the file system's provisioned throughput capacity. Key sizing considerations:

| Scenario | Typical Throughput | Production Impact |
|----------|-------------------|-------------------|
| Event-driven metadata scan (this pipeline) | < 10 MB/s | Negligible on NFS/SMB workloads |
| Backfill (scanning thousands of historical files) | 50-200 MB/s burst | Schedule during off-peak hours |
| High-frequency polling (sub-minute) | Varies | Set Lambda concurrency limit to prevent thundering herd |

**Mitigations:**
- Monitor `DataReadBytes` CloudWatch metric for the file system
- Use Lambda reserved concurrency to cap parallel S3 AP reads
- For initial backfill, use `burst` throughput mode or schedule off-peak

#### Production Checkpoint: DynamoDB Migration

The PoC uses SSM Parameter Store for scan position checkpointing. For production, migrate to DynamoDB with lease-based locking to prevent duplicate processing under Lambda concurrency:

```
DynamoDB Table: metadata-scan-checkpoints
  PK: scan_path (S)          # S3 AP path prefix being scanned
  Attributes:
    status:       S           # PENDING | PROCESSING | COMPLETED | FAILED
    lease_expiry: N           # Unix timestamp — lock auto-releases after this time
    processor_id: S           # Lambda request ID (unique per invocation)
    last_offset:  S           # Last processed file path or marker
    ttl:          N           # Auto-delete COMPLETED records after 7 days
```

**Conditional write pattern (ghost lock prevention):**

```python
# Acquire lease — only succeeds if no active processor holds it
table.put_item(
    Item={...},
    ConditionExpression=(
        'attribute_not_exists(scan_path) OR '  # New scan
        'status = :failed OR '                  # Previously failed
        'lease_expiry < :now'                   # Ghost lock expired
    )
)
```

**Key design decisions:**
- `lease_expiry` = Lambda timeout + 5 min buffer (e.g., 15 min total)
- CloudWatch alarm on items with `status=PROCESSING` older than 2× lease duration (ghost detection)
- DynamoDB TTL auto-deletes COMPLETED records after 7 days (cost control)
- On Lambda crash/timeout: lease auto-expires, next invocation acquires lock

---

## AI Enrichment Pipeline

### Processing Modes by File Type

| File Type | AI Service | Output | Latency | Cost (per file) |
|-----------|-----------|--------|---------|-----------------|
| PDF/Document | Bedrock Claude (summarize, extract) | summary, entities, classification | 5-30s | $0.01-0.05 |
| Image | Bedrock Claude Vision (classify, describe) | description, classification, objects | 3-10s | $0.01-0.03 |
| Audio | Transcribe → Bedrock (summarize) | transcript, summary, sentiment | 30-120s | $0.02-0.10 |
| Video | Frame extraction → Vision (sample) | scene descriptions, classifications | 60-300s | $0.05-0.50 |
| CAD/3D | Metadata extraction only | dimensions, layers, components | 1-5s | $0.001 |
| Log/Sensor | Pattern detection (Bedrock) | anomalies, patterns, statistics | 5-15s | $0.01-0.03 |

### Embedding Generation

All file types receive a 1536-dimension vector embedding (Amazon Titan Embeddings V2) based on:
- Documents: Full text content
- Images: AI-generated description
- Audio: Transcription text
- Video: Concatenated scene descriptions

Embeddings enable **similarity search**: "Find files similar to this one" via kNN on OpenSearch Serverless or brute-force scan on the Iceberg embedding column.

### Model Selection Guide

| Use Case | Recommended Model | Dimensions | Cost/1K tokens | Accuracy |
|----------|------------------|-----------|---------------|----------|
| General text search | Amazon Titan Embeddings V2 | 1024 | $0.00002 | High |
| High-precision semantic search | Cohere Embed v3 | 1024 | $0.0001 | Highest |
| Multilingual (JP+EN mixed) | Amazon Titan Embeddings V2 (multilingual) | 1024 | $0.00002 | High |
| Image+text unified | Amazon Titan Multimodal Embeddings | 1024 | $0.0008/image | Medium-High |

### Error Handling and Retry Strategy

```
AI Enrichment failure flow:

1. Bedrock ThrottlingException
   → exponential backoff (1s, 2s, 4s, 8s, max 30s)
   → After 3 retries: enrichment_status = "failed", retry_count++
   → CloudWatch Alarm → reduce parallelism

2. File read failure (S3 AP AccessDenied / Timeout)
   → enrichment_status = "failed", error_reason = "access_denied"
   → Retry on next reconciliation cycle

3. Low-quality AI result (confidence < 0.3)
   → enrichment_status = "low_confidence"
   → Add to human review queue (SNS → admin notification)

4. Lambda timeout (large files: >100MB)
   → Fallback to ECS Fargate task (no timeout limit)
   → Video/large CAD files default to Fargate path
```

### PII Detection and Anonymization

```
File → PII Detection (Comprehend / Bedrock)
         │
         ├─ No PII → has_pii=false, anonymization_status="not_required"
         │
         └─ PII detected → has_pii=true
                              ↓
                    Anonymization Pipeline
                    (face blur, PII redaction, DICOM de-id)
                              ↓
                    anonymized_path = path to clean version
                    anonymization_status = "completed"
```

### PII Detection Engine Selection by Language

| Language | Recommended Engine | Detectable PII Types | Verification |
|----------|-------------------|---------------------|-------------|
| **English** | Amazon Comprehend (`detect_pii_entities`) | NAME, EMAIL, PHONE, ADDRESS, SSN, CREDIT_DEBIT_NUMBER, DATE_TIME, etc. | ✅ 7/7 detected (confidence >= 0.8) |
| **Spanish** | Amazon Comprehend (`detect_pii_entities`) | Same as English | — (not tested) |
| **Japanese** | **Bedrock Claude** (prompt-based) | Name, email, phone, address, My Number, credit card, date of birth | ✅ 8/8 detected (confidence 1.0) |
| **Other languages** | Bedrock Claude (prompt-based) | Any PII type specified in prompt | — |

> **Constraint**: Amazon Comprehend `detect_pii_entities` API supports only `en` (English) and `es` (Spanish) as of May 2026. For Japanese and other languages, use Bedrock Claude as the PII detection engine.

### Japanese PII Detection Pattern (Bedrock Claude)

**Verification results (2026-05-31)**:

| PII Type | Detected Value | Confidence |
|----------|---------------|-----------|
| NAME | 山田太郎 | 1.0 |
| EMAIL | taro.yamada@example.co.jp | 1.0 |
| PHONE | 090-1234-5678 | 1.0 |
| ADDRESS | 〒150-0002 東京都渋谷区渋谷1-2-3 | 1.0 |
| MY_NUMBER | 1234 5678 9012 | 1.0 |
| CREDIT_CARD | 4111-1111-1111-1111 | 1.0 |
| DATE_OF_BIRTH | 1985年3月15日 | 1.0 |
| OTHER (employee ID) | EMP-2024-0042 | 1.0 |

### PII Detection Engine Comparison

| Aspect | Comprehend | Bedrock Claude |
|--------|-----------|---------------|
| Languages | en, es only | All languages |
| Latency | ~200ms | ~2-5 seconds |
| Cost | $0.0001/100 chars | ~$0.003/request (Haiku) |
| Accuracy | High (trained model) | Very high (LLM inference) |
| My Number (Japan) detection | ❌ Not supported | ✅ Supported |
| Custom PII types | ❌ Fixed set | ✅ Configurable via prompt |
| Best for | English bulk processing | Japanese, multilingual, custom PII |

**Data Clean Room pattern**: Original metadata table (restricted access) + Clean metadata table (broader access, anonymized files only). Lake Formation enforces separation.

---

## Cost Estimation

### Scenario: 10TB unstructured data, 100K files, 1000 changes/day

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| **S3 Tables (metadata storage)** | ~$5 | ~1GB for 100K records |
| **S3 Tables (requests)** | ~$10 | Writes from Lambda + reads from queries |
| **Lambda (metadata sync)** | ~$5 | 1000 events/day × 200ms × 128MB |
| **Lambda (AI enrichment)** | ~$50 | 100 new files/day × 30s × 512MB. Measured: 6 sec/file (image classification + embedding) |
| **Bedrock (AI processing)** | ~$100-500 | Depends on model choice and volume. Measured: $0.01/file (Claude 3 Haiku Vision) |
| **Step Functions** | ~$5 | State transitions |
| **SQS** | ~$1 | Message processing |
| **OpenSearch Serverless (optional)** | **$0 (idle)** | NextGen scale-to-zero (GA May 2026). Active: $0.24/OCU-hour. PoC/dev environments cost $0 when idle |
| **FSx for ONTAP (existing)** | — | Already provisioned for primary storage |
| | | |
| **Total (without vector search)** | **~$175-575/month** | |
| **Total (with vector search)** | **~$175-575/month (active)** | NextGen scale-to-zero: no additional idle cost for vector search |

### Cost comparison vs alternatives

| Approach | Monthly Cost (10TB) | Metadata Latency | Governance |
|----------|-------------------|-----------------|------------|
| **This architecture (FPolicy + S3 Tables)** | $175-575 | ~5 seconds | Lake Formation / Horizon |
| S3 full copy + Glue Crawler | $230-256 (S3)* + $50 (Glue) | Hours | Lake Formation |
| S3 full copy + S3 Metadata | $230-256 (S3)* + $15 (Metadata) | Minutes | Lake Formation |
| Custom DynamoDB catalog | $50-200 | Seconds | Custom IAM |

> *S3 Standard storage pricing: us-east-1 $0.023/GB ($230/10TB), ap-northeast-1 $0.025/GB ($256/10TB). Verified 2026-06-01.

> **Cost evaluation note**: Above costs are direct costs only. The true ROI of this architecture includes "data discovery time reduction," "sharing lead time elimination," and "AI automation labor savings." If 10 data scientists spend 5 hours/week on data exploration, annual labor savings of $150K+ are achievable.

### TCO Comparison (3-year, 10TB, 100K files)

| Item | Current (S3 copy + manual) | This Architecture |
|------|--------------------------|-------------------|
| Storage (S3 + FSx) | $8,280 (S3) + $16,200 (FSx) | $0 (no S3 needed) + $16,200 (FSx) |
| Metadata management | $0 (none) | $540 (S3 Tables, 3 years) |
| AI processing | $0 (manual) | $3,600-18,000 (Bedrock) |
| Labor (data exploration) | $450,000 (10 people × 5h/week × 3 years) | $45,000 (90% reduction) |
| **3-year TCO** | **$474,480** | **$65,340-$79,740** |
| **Reduction** | — | **83-86%** |

> **Benchmark caveat**: The 90% labor reduction is an assumption. Actual effectiveness depends on organizational data usage patterns. Use PoC-measured "data discovery time" Before/After to calculate customer-specific ROI.

---

## Operational Monitoring

### Pipeline Health Dashboard

| Metric | Source | Alert Condition | Action |
|--------|--------|----------------|--------|
| FPolicy events processed/min | CloudWatch (Lambda) | 0 for >10 minutes | Check FPolicy Server / SQS |
| Metadata sync latency (p99) | CloudWatch (Lambda Duration) | > 30 seconds | Adjust Lambda memory/timeout |
| DLQ message count | CloudWatch (SQS) | > 0 | Inspect DLQ messages, redrive |
| AI enrichment pending count | Athena query (S3 Tables) | > 1000 | Adjust Step Functions parallelism |
| Reconciliation gap count | CloudWatch (Step Functions) | > 100 | Investigate FPolicy event loss |
| Bedrock throttling | CloudWatch (Bedrock) | ThrottlingException > 0 | Adjust request rate, add backoff |
| S3 AP AccessDenied | CloudTrail | > 10/10min | Review IAM/AP policy |

### Storage-Layer Metrics Integration

Monitor the following storage-layer metrics from Amazon FSx for NetApp ONTAP CloudWatch metrics and the ONTAP REST API alongside metadata catalog health:

| Metric | Source | Check Point | Metadata Catalog Relevance |
|--------|--------|------------|---------------------------|
| Volume utilization | CloudWatch (FSx) / ONTAP REST API | Alert at >85% | New file additions stop → metadata sync also stops |
| Deduplication ratio | ONTAP REST API | Deviation from expected | Identify duplicate files → visualize in metadata |
| FabricPool tiering ratio | ONTAP REST API | Cold data percentage | Affects access latency for AI processing target files |
| Snapshot usage | CloudWatch (FSx) / ONTAP REST API | Unexpected growth | Forgotten AI batch processing Snapshots |

For detailed observability pipelines, see [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations).

---

## Success KPIs

| KPI | Before (Current State) | After (This Architecture) | Measurement |
|-----|----------------------|--------------------------|-------------|
| **Data discovery time** | Days (manual search, ask colleagues) | Seconds (SQL metadata search, natural language) | Time from "I need X" to "I found X" |
| **Sharing lead time** | Weeks (copy, approve, transfer) | Immediate (Iceberg REST + governance policy) | Time from share request to access granted |
| **AI processing throughput** | Manual (human selects files, runs tools) | Automated (FPolicy → Step Functions pipeline) | Files processed per day without human intervention |
| **Storage cost** | Baseline (S3 full copy + no dedup) | 30-70% reduction (ONTAP dedup + S3 copy elimination) | Monthly storage spend |
| **Governance coverage** | 0% (no metadata, no access control on unstructured data) | 100% (all files cataloged, LF-Tags/Horizon applied) | % of files with classification + access policy |
| **Cross-org data reuse** | Near zero (siloed copies) | Measurable (Delta Sharing / Secure Data Sharing metrics) | Unique datasets accessed by >1 organization |

---

## Industry Use Case Examples

| Industry | Use Case | Key Files | AI Processing | Business Value |
|----------|----------|-----------|--------------|----------------|
| **Manufacturing** | Design document similarity search | CAD (DWG, STEP), blueprints (PDF) | Embedding → similarity search | Past design reuse rate ↑, R&D time ↓ |
| **Financial Services** | Contract auto-classification + compliance search | Contracts (PDF), statements | Entity extraction, classification | Compliance search time: days → seconds |
| **Healthcare** | DICOM image anonymized sharing for research | Medical images (DICOM), reports (PDF) | DICOM de-id, PII redaction | Research dataset construction without privacy risk |
| **Media & Entertainment** | Video asset tag search + content reuse | Video (MP4), images (RAW, JPEG) | Scene classification, object detection | Content reuse efficiency ↑, licensing compliance |
| **Public Sector** | Surveillance footage governance + anomaly detection | Video (H.264), sensor logs | Face detection (for blur), anomaly detection | Citizen privacy protection + security |
| **Energy / Utilities** | IoT sensor log pattern detection | Sensor data (CSV, Parquet), maintenance logs | Anomaly detection, predictive maintenance | Unplanned downtime ↓, maintenance cost ↓ |

---

## Data Sovereignty, Encryption, and Audit Retention

> **Regulatory compliance note**: In regulated industries, "where data resides," "who accessed it," and "when it was deleted" must always be explainable. This architecture ensures both metadata and raw data remain in the same region, with all access tracked via CloudTrail + Lake Formation logs. However, this document provides governance guidance only and does not substitute for legal/compliance judgment. Final regulatory determinations should be confirmed with legal and compliance teams.

### Data Sovereignty

| Component | Location | Cross-region Transfer |
|-----------|----------|---------------------|
| Raw files (FSx for ONTAP) | Same region as FSx for ONTAP file system | None (S3 AP same-region only) |
| Metadata table (S3 Tables) | Same region (configurable) | None (query results stay in region) |
| AI processing (Bedrock/Lambda) | Same region | None (processing in-region) |
| Governance (Lake Formation) | Same region | Cross-account possible (same region) |

**Guarantee**: Both metadata and raw data remain in the same AWS region. No cross-border data transfer occurs in the default architecture. This satisfies data residency requirements for regulated industries.

### Encryption at Rest

| Layer | Encryption | Key Management |
|-------|-----------|---------------|
| FSx for ONTAP | SSE-FSX (AES-256) | AWS KMS managed, transparent |
| S3 Tables | SSE-S3 or SSE-KMS | Customer choice (KMS recommended for compliance) |
| SQS messages | SSE-SQS or SSE-KMS | AWS managed or customer KMS |
| Lambda environment | Encrypted by default | AWS managed |
| OpenSearch Serverless | Encrypted by default | AWS managed or customer KMS |

### Audit Log Retention

| Regulation | Required Retention | Recommended Configuration |
|-----------|-------------------|--------------------------|
| HIPAA (Healthcare) | 6-7 years | CloudTrail: S3 archive (7 years), Lake Formation logs: 7 years |
| SOX / Financial | 5-7 years | CloudTrail: S3 archive (7 years), query logs: 5 years |
| GDPR (EU) | Duration of processing + reasonable period | CloudTrail: 3 years minimum, deletion audit: indefinite |
| General enterprise | 1-3 years | CloudTrail: 90 days hot + S3 archive (3 years) |

**Implementation**: Configure CloudTrail to deliver logs to S3 with lifecycle policy matching retention requirements. Lake Formation access logs follow the same pattern.

---

## ONTAP Snapshot and FlexClone for AI Processing

> **Storage efficiency note**: ONTAP deduplication operates at the block level (4KB). Identical file copies across departments (e.g., design drawings held by 5 departments) can achieve up to 80% reduction. However, "similar but different" files (e.g., PDF version differences) show limited effect (10-30%). This architecture's metadata catalog makes "which files are identical" visible, supporting decisions to eliminate unnecessary copies.

### Deduplication Effectiveness Guide

| Data Pattern | Dedup Ratio | Example |
|-------------|------------|---------|
| Identical file copies across departments | 70-80% | Design drawings held by 5 departments → effectively 1 copy |
| Version-managed documents | 30-50% | Contract v1, v2, v3 → shared common blocks |
| Unique images/video | 5-15% | Product photos, surveillance footage → header/metadata only |
| Log/sensor data | 20-40% | Text data with repeating patterns |
| Pre-compressed files (ZIP, MP4) | 0-5% | Already compressed, few block duplicates |

> **Note**: Above figures are general guidelines; actual effectiveness depends on data characteristics. PoC measurement recommended. Use `volume efficiency show` command to verify actual reduction ratios.

### Pattern: Snapshot-based Batch AI Processing

```
1. Create Snapshot before AI batch processing
   → Guarantees consistent point-in-time view
   → Files cannot change during processing

2. AI pipeline reads from Snapshot (via S3 AP)
   → No interference with production NFS/SMB workloads
   → Deterministic results (same input = same output)

3. After processing completes, Snapshot can be deleted
   → Zero additional storage cost (ONTAP Snapshot is space-efficient)
```

**Use case**: Nightly AI enrichment batch that processes all new files. Snapshot ensures no file is modified mid-processing, preventing partial reads or inconsistent classifications.

### Pattern: FlexClone for AI Sandbox

```
1. FlexClone the production volume
   → Instant (metadata-only operation)
   → Zero additional storage (copy-on-write)

2. AI team experiments on FlexClone
   → Can modify, delete, reorganize files freely
   → No impact on production volume

3. Validated results written to metadata table
   → FlexClone deleted after experiment
```

**Use case**: Data science team wants to test new classification models on production data without risk. FlexClone provides a full copy in seconds with zero storage overhead.

---

## Periodic Full-Scan Reconciliation

### Why It's Needed

FPolicy asynchronous mode may drop events under extreme load (>10,000 events/second sustained). Additionally, files created before FPolicy was enabled won't have metadata records. A periodic reconciliation ensures the metadata table stays complete.

### Design

```
EventBridge Schedule (daily at 02:00 UTC)
  → Step Functions: FullScanReconciliation
    → Lambda: ListObjectsV2 on FSx for ONTAP S3 AP (paginated)
    → Lambda: Compare with Metadata_Table (anti-join)
    → Lambda: Insert missing records (enrichment_status = "pending")
    → CloudWatch Metric: reconciliation_gap_count
```

### Configuration

| Parameter | Default | Notes |
|-----------|---------|-------|
| Schedule | Daily 02:00 UTC | Low-traffic window |
| Scope | All volumes with FPolicy enabled | Configurable per volume |
| Batch size | 1000 objects per Lambda invocation | Pagination |
| Alert threshold | gap_count > 100 | Indicates FPolicy event loss |

---

## Snowflake Cortex Search for Natural Language Metadata Discovery

### Pattern: Cortex Search on Metadata Table

```
Managed Iceberg Table (metadata)
  → Cortex Search Service (index on: summary, tags, classification, file_name)
    → Natural language query: "Find all engineering drawings from 2025 related to pump design"
      → Returns: ranked list of file_path + metadata
```

### Configuration

```sql
-- Create Cortex Search service on metadata table
CREATE OR REPLACE CORTEX SEARCH SERVICE metadata_search
  ON unstructured_file_metadata
  WAREHOUSE = 'COMPUTE_WH'
  TARGET_LAG = '1 hour'
  ATTRIBUTES = 'file_type, classification, sensitivity_level'
  COLUMNS = 'summary, file_name, tags'
  AS (
    SELECT
      file_id,
      file_path,
      file_name,
      file_type,
      classification,
      sensitivity_level,
      summary,
      OBJECT_CONSTRUCT_KEEP_NULL(*) AS tags_json
    FROM unstructured_file_metadata
    WHERE is_deleted = FALSE
      AND enrichment_status = 'completed'
  );
```

### Advantages over SQL-only Search

| Aspect | SQL (Athena/Redshift) | Cortex Search |
|--------|----------------------|---------------|
| Query type | Exact match, LIKE, regex | Natural language, semantic |
| Setup | None (standard SQL) | Cortex Search service creation |
| Relevance ranking | Manual (ORDER BY) | Automatic (ML-based) |
| Fuzzy matching | Limited | Built-in |
| Best for | Structured filters (date, type, tag) | Discovery ("find documents about X") |

**Recommendation**: Use SQL for structured queries (known filters) and Cortex Search for discovery (unknown or fuzzy requirements). Both access the same underlying Iceberg metadata table.

---

## Anonymization Quality Assurance Process

### Challenge

AI-based PII detection is not 100% accurate. False negatives (missed PII) create compliance risk. False positives (over-redaction) reduce data utility.

### Recommended Process

```
┌─────────────────────────────────────────────────────────┐
│ Stage 1: Automated PII Detection                         │
│   Comprehend + Bedrock → has_pii flag                    │
│   Expected accuracy: 95-98%                              │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 2: Automated Anonymization                         │
│   Face blur, PII redaction, DICOM de-id                  │
│   Output: anonymized file + anonymized_path              │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 3: Human Sampling Review (Weekly)                   │
│   - Random 5% sample of anonymized files                 │
│   - Reviewer checks: PII fully removed? Over-redacted?   │
│   - Feedback loop → model fine-tuning                    │
│   - Escalation: if miss rate > 2%, pause pipeline        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ Stage 4: Audit Trail                                     │
│   - Who reviewed, when, what decision                    │
│   - Pipeline version that processed each file            │
│   - Retention: matches regulatory requirement            │
└─────────────────────────────────────────────────────────┘
```

### DICOM De-identification Methods

| Method | HIPAA Compliance | Data Utility | Complexity |
|--------|-----------------|-------------|-----------|
| **Safe Harbor** | ✅ (18 identifiers removed) | Lower (aggressive removal) | Low |
| **Expert Determination** | ✅ (statistical verification) | Higher (selective removal) | High |
| **Hybrid** (recommended) | ✅ | Medium-High | Medium |

**Recommendation**: Start with Safe Harbor for initial deployment (simpler, guaranteed compliance). Transition to Expert Determination for research datasets where data utility is critical.

---

## Constraints and Limitations

### Anti-Patterns (Designs to Avoid)

| Anti-Pattern | Why It's Problematic | Correct Approach |
|-------------|---------------------|-----------------|
| Write Iceberg tables directly to FSx for ONTAP S3 AP | conditional writes not supported → commit failures | Metadata on S3 Tables, raw data on FSx for ONTAP (separate) |
| Copy all files to S3 then use S3 Metadata | Negates the "eliminate S3 copy" core value | FPolicy pipeline for metadata-only sync |
| Store embeddings in DynamoDB | Inefficient kNN search, disconnected from Iceberg ecosystem | S3 Tables BINARY column or OpenSearch Serverless |
| Process all files with AI (no filter) | Cost explosion (100K files × $0.05 = $5,000/run) | Process only new/changed files, filter by file_type |
| Store raw data (binary) in metadata table | Table size explosion, query performance degradation | Store file_path reference only, raw data stays on FSx for ONTAP |
| Single monolithic Lambda for all processing | Timeouts, debugging difficulty, coarse retry granularity | Step Functions with per-file-type Lambda functions |
| Expose metadata without governance | File paths leak → unauthorized access to raw data | Always apply Lake Formation / Horizon column/row controls |

| Constraint | Impact | Mitigation |
|-----------|--------|-----------|
| FSx for ONTAP S3 AP: No conditional writes | Cannot write Iceberg tables directly to FSx for ONTAP S3 AP | Metadata on S3 Tables (not on FSx); raw files on FSx for ONTAP |
| FSx for ONTAP S3 AP: No S3 Event Notifications | Cannot use native S3 events for change detection | FPolicy provides equivalent real-time detection |
| FSx for ONTAP S3 AP: ListObjectsV2 latency | 1.3-1.4x native S3 up to 5,000 objects and 0.7x at 10,000 and 20,000, so not a practical concern at that scale; above 20,000 unmeasured ([BLK-006](./blocker-tracker.md)) | Metadata table removes the LIST operation entirely, making the question scale-independent |
| Databricks: Session policy blocks S3 AP | Cannot access FSx for ONTAP files directly from UC | Access metadata via Iceberg REST; files via Bedrock/Lambda |
| Databricks: SQL Warehouse doesn't support S3 Tables | `CREATE CONNECTION TYPE iceberg_rest` not supported (verified May 2026) | Use Spark cluster with Iceberg REST Catalog config, or query via Athena |
| Snowflake: TO_FILE fails on S3 AP | Vision AI requires internal stage workaround | COPY FILES to internal stage; PARSE_DOCUMENT works directly |
| Snowflake: Cannot directly read S3 Tables | `CATALOG = 'ICEBERG_REST'` not supported (verified May 2026) | COPY INTO → Managed Iceberg Table; External Volume creation succeeds |
| S3 Tables: Region availability | Not available in all regions | Fallback to Glue Catalog + self-managed Iceberg |

See [Compatibility Matrix](compatibility-matrix.md) for detailed platform × format × mode verification status.

---

## Relationship to Other Documents

| Document | Relationship |
|----------|-------------|
| [Zero-Copy Unstructured Data Governance](zero-copy-media-governance.md) | Storage optimization options (A/B/C/D) — this document focuses on the metadata catalog layer |
| [Compatibility Matrix](compatibility-matrix.md) | Detailed verification status for each platform × format × mode |
| [Governance and Compliance](governance-and-compliance.md) | Horizon Catalog, Lake Formation, audit logging details |
| [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations) | Monitoring pipeline for FSx for ONTAP audit logs |

---

## Design Considerations

| Aspect | Recommendation | Reflected In |
|--------|---------------|-------------|
| **Open Table Format selection** | S3 Tables as primary metadata store. Iceberg REST endpoint enables engine-agnostic access. S3 Metadata as supplementary batch path. | Architecture, Decision Matrix |
| **Multi-engine access** | External Catalog configuration via Iceberg REST endpoint. Platform session policy constraints documented with workarounds. | Platform Paths, Constraints |
| **Cross-engine governance** | Horizon Catalog / Lake Formation enforce governance on external engines. Row Access Policy / LF-Tags for consistent cross-platform access control. | Governance Layer, Snowflake Path |
| **Storage efficiency** | Hot metadata × cold data separation design. Maximize ONTAP deduplication benefits while keeping metadata layer at minimal cost. | Core Concept, Cost Estimation |
| **Event-driven design** | FPolicy pipeline leverages existing infrastructure for real-time detection. DataSync + S3 Metadata as batch alternative. Hybrid combination supported. | Event Detection, Hybrid Architecture |
| **Regulatory compliance** | PII detection + anonymization pipeline. Data clean room pattern. Audit retention periods specified per regulation. Data sovereignty (same-region guarantee). | AI Enrichment, Data Sovereignty |
| **Business value demonstration** | Incremental adoption (Quick Start → full deployment). Quantified success KPIs. Go/No-Go criteria minimize investment risk. | Success KPIs, Next Steps |

---

## Next Steps

### Quick Start: Minimal Viable Deployment (1 week)

> **Incremental adoption note**: Rather than building all features at once, demonstrate "data discovery time reduction" with a minimal configuration to gain stakeholder buy-in, then expand incrementally.

**Week 1 goal**: Register metadata for 1000 existing files on FSx for ONTAP into S3 Tables and make them searchable via Athena.

```bash
# Step 1: Create S3 Tables table bucket (5 min)
aws s3tables create-table-bucket \
  --name fsxn-metadata-catalog \
  --region ap-northeast-1

# Step 2: Run initial metadata scan script (30 min)
python scripts/initial-metadata-scan.py \
  --access-point-alias <AP_ALIAS> \
  --table-bucket fsxn-metadata-catalog \
  --max-files 1000

# Step 3: Verify with Athena query (5 min)
# "Show all PDF files created since 2025"
SELECT file_name, file_path, created_at, file_size
FROM metadata_catalog.unstructured_files
WHERE file_type = 'application/pdf'
  AND created_at >= TIMESTAMP '2025-01-01'
ORDER BY created_at DESC;
```

**Week 1 success criteria**: Demonstrate that "finding a specific file" is reduced from days to seconds.

### Full Deployment Roadmap

1. **Phase 1**: Deploy S3 Tables table bucket + Iceberg schema (1 week)
2. **Phase 2**: Build FPolicy → SQS → Lambda metadata sync pipeline (1-2 weeks)
3. **Phase 3**: Implement AI enrichment Step Functions workflow (2-3 weeks)
4. **Phase 4**: Configure cross-platform access (Databricks, Snowflake, EMR) (1-2 weeks)
5. **Phase 5**: Build search & discovery features (SQL + vector) (1-2 weeks)
6. **Phase 6**: Implement anonymization pipeline (1-2 weeks)

### Go/No-Go Criteria for Each Phase

| Phase Transition | Go Condition | No-Go Action |
|-----------------|-------------|-------------|
| Phase 1 → 2 | Athena query returns within 3 seconds | S3 Tables not available in region → Glue Catalog fallback |
| Phase 2 → 3 | FPolicy events reflected in S3 Tables within 5 minutes | FPolicy Server unstable → switch to DataSync batch path |
| Phase 3 → 4 | AI classification precision > 0.7 | Model accuracy insufficient → prompt tuning or model change |
| Phase 4 → 5 | 2+ platforms successfully query metadata | Session policy issues → switch to Lambda API Gateway proxy |
| Phase 5 → 6 | Similar files appear in top-5 search results | Embedding quality insufficient → model change or chunking strategy revision |

See [Tasks](../../tasks.md) for detailed implementation plan.

