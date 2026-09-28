# Zero-Copy Unstructured Data Governance: Eliminating S3 Duplication with FSx for ONTAP

🌐 [日本語](../ja/zero-copy-media-governance.md) | English

## Challenge and Background

| # | Challenge | Root Cause |
|---|-----------|-----------|
| 1 | S3 storage costs growing continuously; want to eliminate duplicate data | Generic file server → DataSync (file-level diff) → S3 full copy creates redundant storage |
| 2 | Need tag-based access control for unstructured data (images, videos, PDFs, CAD, logs, audio) across organizations | No governance layer on flat S3 copies |

### Target Data

| Category | Examples | Typical Size | AI/Analytics Use |
|----------|----------|-------------|-----------------|
| Images | Product photos, medical imaging (DICOM), satellite, blueprints | 1-100MB/file | Vision AI, quality inspection, object detection |
| Videos | Surveillance, manufacturing lines, training materials | 100MB-10GB/file | Anomaly detection, behavior analysis |
| Documents | PDF, Word, design specs, contracts, manuals | 1-50MB/file | RAG, summarization, search, compliance |
| CAD/3D | AutoCAD, SolidWorks, point clouds | 10MB-1GB/file | Digital twin, simulation |
| Logs/Sensors | IoT sensor data, application logs | Variable | Predictive maintenance, anomaly detection |
| Audio | Call center recordings, meeting recordings | 10-100MB/file | Transcription, sentiment analysis |

### Existing Environment Assumptions

Customers already operate one of the following data platforms and want to leverage accumulated assets, expertise, and team skills:

| Existing Platform | Context | Section |
|-------------------|---------|---------|
| **Databricks** | UC, Delta Lake, MLflow pipeline assets | [Databricks Path](#databricks-path) |
| **Snowflake** | Cortex AI, Data Sharing, Horizon Catalog expertise | [Snowflake Path](#snowflake-path) |
| **AWS Native** | Athena, Glue, Bedrock, Lake Formation-centric | [AWS Native Path](#aws-native-path) |

### Current Architecture (Problem State)

```
On-premises Generic File Server (NAS/Windows)
  ↓ DataSync (file-level diff — full file retransfer on any change)
Amazon S3 (full copy, no deduplication)
  ↓
Data Platform (Databricks / Snowflake / AWS Native)

Problems:
- No deduplication on either file server or S3
- DataSync file-diff: 1-byte change → entire file retransferred
- S3 cost grows linearly with data volume
- No governance on unstructured data assets
```

---

## Storage Optimization (All Platforms)

### Option A: S3 Optimization Only (Minimal Change)

**Cost reduction**: 20-40% (tiering only, no dedup)

### Option B: FSx for ONTAP Migration (Recommended)

**Cost reduction**: 50-70% (dedup + FabricPool + S3 copy elimination)

### Option C: On-prem ONTAP + SnapMirror (Hybrid)

**Bandwidth**: 2,500x more efficient than DataSync (block-level diff)

### Option D: FlexCache S3 Access Points (Future Roadmap)

> **Status**: FlexCache S3 AP support on FSx for ONTAP is expected soon (FSx for ONTAP availability timeline TBD).
>
> **Rationale**: NetApp ONTAP 9.18.1 officially supports S3 protocol access to FlexCache volumes (`-is-s3-enabled` option). This capability is already available on on-premises ONTAP, and FSx for ONTAP deployment builds on this technically established foundation.
>
> **References**:
> - [ONTAP 9.18.1 What's New](https://docs.netapp.com/us-en/ontap/release-notes/whats-new-9181.html)
> - [Create an ONTAP S3 NAS bucket on FlexCache volumes](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/create-nas-bucket-task.html) — "All nodes in the cluster must be running ONTAP 9.18.1 or later"

**Cost reduction**: 80% vs current (cache-only storage)

**Cost comparison (10TB unstructured data)**:

| Item | Current (S3 copy) | Option B | Option D (Future) |
|------|-----------------|----------|-----------------|
| Monthly storage | $230 | $450 (post-dedup) | $180 (cache only) |
| On-prem ops | Yes | None | None |
| **Reduction vs current** | — | 50% (TCO) | **80%** |

### Phased Adoption Roadmap

| Phase | Timeline | Action | Effect |
|-------|----------|--------|--------|
| **Phase 1** | Immediate (1-2 weeks) | S3 Intelligent-Tiering + Lifecycle | 20-40% cost reduction |
| **Phase 2** | 1-3 months | FSx for ONTAP + eliminate S3 copies | 50%+ cost reduction |
| **Phase 3** | After FlexCache S3 AP GA | Migrate to FlexCache S3 AP | 80% cost reduction |

---

## Databricks Path

**Context**: Leverage existing Databricks environment assets — UC, Delta Lake, MLflow pipelines, team skills.

### Governance: UC Volume + Tag-based Row Filter + OpenSharing

### AI Path: Mosaic AI (Vision), Vector Search (RAG), Model Serving (Whisper)

### Constraints
- UC Volume requires S3 backend (cannot register FSx for ONTAP S3 AP directly)
- UC Row Filter / Column Mask NOT enforced on external engines
- Lake Formation required for external engine governance

---

## Snowflake Path

**Context**: Leverage existing Snowflake environment — Cortex AI, Data Sharing, Horizon Catalog expertise.

### Governance: External Table + Row Access Policy + Masking + Secure Data Sharing

### AI Path: Cortex Search (RAG), Cortex AI Vision, PARSE_DOCUMENT

### Key Characteristics
- **Horizon Iceberg REST Catalog enforces governance on external engines** (Row Access Policy + Masking)
- All editions supported (billing starts H2 2026)
- Zero-copy Data Sharing (no data duplication for recipients)

### Constraints
- TO_FILE fails on FSx for ONTAP S3 AP stages (engineering investigation in progress)
- Only Vision AI (via TO_FILE) requires COPY FILES to internal stage. Cortex AI functions (COMPLETE, SUMMARIZE) and Cortex Search work directly on Managed Iceberg Tables (no internal table needed)
- AUTO_REFRESH not supported (Task + ALTER STAGE REFRESH workaround)

---

## AWS Native Path

**Context**: Leverage existing AWS-native environment — Athena, Glue, Bedrock, Lake Formation.

### Governance: Lake Formation LF-Tags + Cross-account grants

### AI Path: Bedrock KB (RAG), Textract, Transcribe, SageMaker

### Key Characteristics
- **FSx for ONTAP S3 AP direct access** from Athena and Bedrock (no S3 copy needed)
- **Lake Formation enforces governance across all engines** (Athena, Redshift, EMR)
- Bedrock Knowledge Base can use FSx for ONTAP S3 AP as direct data source

### Constraints
- Athena cannot access VPC-origin APs (Internet-origin required)
- No built-in data lineage (must build separately)
- Bedrock KB: unstructured auto-index only (structured queries via Athena)

---

## Platform Comparison

| Aspect | Databricks | Snowflake | AWS Native |
|--------|-----------|-----------|------------|
| **FSx for ONTAP S3 AP direct access** | ❌ (UC session policy) | ⚠️ (LIST only) | ✅ (Athena, Bedrock) |
| **Governance model** | UC Tags + Row Filter | Row Access Policy + Masking | Lake Formation LF-Tags |
| **Governance on external engines** | ❌ | ✅ (Horizon Catalog) | ✅ (Lake Formation) |
| **Cross-org sharing** | OpenSharing (open protocol) | Secure Data Sharing (zero-copy) | LF Cross-account + RAM |
| **Unstructured AI** | Mosaic AI, Vector Search | Cortex AI, Cortex Search | Bedrock, Textract, Transcribe |
| **Deduplication** | None (S3-dependent) | None (S3-dependent) | None (S3-dependent) |
| **With FSx for ONTAP** | ✅ (Option B/C/D) | ✅ (Option B/C/D) | ✅ (Option B/C/D) |

---

## Recommendation Matrix

| Priority | Recommendation | Rationale |
|----------|---------------|-----------|
| **Fastest cost reduction** | Phase 1 (S3 Tiering) + Phase 2 (FSx for ONTAP) | Immediate + root-cause fix |
| **Maximum bandwidth efficiency** | Option C (SnapMirror) | Block-level diff = 2,500x DataSync |
| **Future-optimal (lowest cost)** | Option D (FlexCache S3 AP) | Cache-only = 80% reduction |
| **Multi-engine governance** | Snowflake Horizon or Lake Formation | Enforce governance on external engines |
| **Cross-org sharing** | OpenSharing (broad compatibility) or Snowflake Sharing (zero-copy) | Choose based on requirements |

---

## Selection Guidance (Per-Path Summary)

| Path / Aspect | Key points |
|---------------|-----------|
| **Snowflake path** | Horizon Catalog can apply governance to external engines. Cortex Search + Data Sharing for AI use of unstructured data. Managed Iceberg Table → Horizon REST Catalog enables Databricks/Spark to read the same data. |
| **Databricks path** | UC Volumes + OpenSharing. Mosaic AI for automated tagging of unstructured data. Use FSx for ONTAP for S3 cost reduction. Future: Lakehouse Federation may enable virtual access to FSx for ONTAP S3 AP data. |
| **AWS-native path** | FSx for ONTAP S3 AP + Lake Formation reduces S3 copies + provides all-engine governance. Bedrock KB can read FSx for ONTAP S3 AP directly. Glue Catalog + Iceberg format is another Open Table Format option. |
| **Storage optimization** | ONTAP dedup is effective for identical file copies (versions, department copies). For similar image/video files, effective only where identical blocks exist. |
| **Migration / hybrid** | DataSync → FSx for ONTAP is an established path (10TB / Direct Connect 1Gbps ≈ 22 hours). FlexCache + FSx for ONTAP S3 AP is effective for hybrid environments. |
| **Data sovereignty** | Data sovereignty requirements may call for Option C (on-prem ONTAP + SnapMirror). Medical images (DICOM) and surveillance footage may be PII/PHI — consider an anonymization pipeline. |
| **Outcome metrics** | Goal: "cost reduction + governed cross-org sharing." Phased adoption (Phase 1→2→3) limits investment risk. Example metrics: storage cost reduction, data discovery time, share-request-to-access time. Industry examples: Manufacturing (design document reuse), Finance (contract compliance search), Healthcare (DICOM research sharing). |

---

## Recommendations by Concern

> Each row summarises the recommendation for one concern. These are derived from
> analysis of the options in this document, not from statements collected from
> individuals holding any particular role.

| Concern | Primary recommendation |
|---|---|
| **Governance across multiple engines** | Even on a Databricks decision, Snowflake Horizon can enforce governance on the same data for external engines; consider using Horizon alongside for other consumers. |
| **Catalog integration and S3 cost** | UC Volumes + OpenSharing works well. For S3 cost, use S3 Intelligent-Tiering short-term and FSx for ONTAP strategically. |
| **Avoiding data copies** | FSx for ONTAP S3 AP removes the need to copy to S3. FlexCache S3 AP (roadmap) reduces cost further. |
| **Storage efficiency** | ONTAP dedup is effective for storage efficiency (S3 has no native dedup). Migrating to FSx for ONTAP addresses the root cause. |
| **Operations and monitoring** | Operate and monitor via Amazon CloudWatch and the ONTAP REST API. DataSync migration to FSx for ONTAP is a supported path. FlexCache S3 AP (roadmap) is a viable option for hybrid architectures. |
| **Data sovereignty** | Data-sovereignty requirements may mandate on-prem ONTAP + SnapMirror (Option C). FlexCache S3 AP enables cloud analytics without full replication. |
| **Business outcome alignment** | The customer goal is "cost reduction + governed sharing." FlexCache S3 AP (roadmap) helps achieve both with minimal data movement. |

---

## Operational Monitoring & Security

For Observability and Security Monitoring (SIEM) of the architectures proposed in this document, refer to the following dedicated projects:

| Area | Repository | Content |
|------|-----------|---------|
| **Observability** | [FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) | Ship FSx for ONTAP audit logs to Datadog, Splunk, Grafana, Elastic via S3 AP + Lambda pipeline. |
| **SLO / Alerts** | [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | SLO Observability patterns, FPolicy event-driven pipeline, capacity guardrails. |

### Key Metrics to Monitor

| Metric | Target | Alert Condition Example |
|--------|--------|------------------------|
| DataSync / SnapMirror sync lag | Sync pipeline | lag > 1 hour |
| FSx for ONTAP S3 AP latency | S3 API response time | p99 > 5s |
| FlexCache hit rate | Cache efficiency | hit rate < 80% |
| Storage utilization / dedup ratio | Cost optimization | utilization > 85% |
| Access denied events | Security | AccessDenied > 10/10min |
| Unstructured data access patterns | DLP / Anomaly detection | 10x normal download volume |
