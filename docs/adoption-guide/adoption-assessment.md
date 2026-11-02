# Adoption Assessment Guide

🌐 **English** | [日本語](./adoption-assessment-ja.md)

> Whether this pattern fits, how to size the configuration, and what not to claim.
> Every capability statement here traces to a record in
> [`verification-pack/`](../../verification-pack/); anything unverified is marked as
> such in the [unverified inventory](../en/unverified-inventory.md).

## Where This Applies

| Segment | Profile | Pain Points |
|---------|---------|-------------|
| Enterprise NAS users | On-premises NetApp ONTAP / NAS users with 10TB+ file data | Data copy required for analytics, S3-native services inaccessible from NAS |
| FSx for ONTAP adopters | Teams already running FSx for ONTAP on AWS for NFS/SMB workloads | Lakehouse/analytics platforms require S3, creating data silos |
| Hybrid cloud | Organizations with on-premises ONTAP + AWS, using SnapMirror for DR/migration | Want to leverage cloud analytics without re-architecting storage |

## The Problem Being Solved

Organizations with file-based data on NAS/ONTAP face a fundamental disconnect:

1. **Data duplication**: Analytics platforms (Databricks, Snowflake, Athena) require data in S3, forcing ETL pipelines to copy data from NAS to S3
2. **Governance fragmentation**: Separate access controls for NAS (UNIX/NTFS permissions) and S3 (IAM policies) create compliance gaps
3. **Operational overhead**: Synchronization pipelines add latency, cost, and failure points
4. **Stranded investment**: Existing ONTAP features (deduplication, snapshots, tiering) are lost when data is copied to S3

## The Pattern

Amazon FSx for ONTAP S3 Access Points enable S3 API access to file data stored on FSx for ONTAP volumes without data movement. Applications and AWS services that work with S3 can directly read and write file data through the access point.

**Key technical facts** (per [AWS documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)):
- Supported S3 operations: GetObject, PutObject, DeleteObject, ListObjectsV2, HeadObject, Multipart Upload, CopyObject (same access point only)
- Dual-layer authorization: IAM policy evaluation + file system user permissions (UNIX or Windows)
- Latency: Tens of milliseconds range, consistent with S3 bucket access
- Throughput: Depends on FSx for ONTAP file system provisioned throughput capacity
- Block Public Access enforced by default (cannot be disabled)
- Requires ONTAP version 9.17.1 or later

## What Changes

| Outcome | Metric |
|---------|--------|
| Eliminate data copies | N copies → 1 authoritative source |
| Remove sync pipelines | Eliminate NAS → S3 ETL jobs |
| Accelerate time-to-insight | Days of pipeline setup → hours of direct query |
| Preserve NFS/SMB access | Existing workloads unchanged |
| Unified governance | Single data location, dual-layer access control |
| Enable AI/ML on file data | Bedrock, SageMaker, EMR access via S3 AP |

## Three Configurations, by Scope

### Good: Single-Account Read-Only Analytics

**Scope**: Single AWS account, single SVM, read-only analytics

| Component | Configuration |
|-----------|--------------|
| FSx for ONTAP | Single-AZ, 1 SVM, 1 volume |
| S3 Access Point | Internet origin, read-only file system user |
| Analytics | Athena + Glue Data Catalog |
| Security | IAM role per analyst team, read-only UNIX user |
| Monitoring | CloudTrail for API calls |

**Use case**: Ad-hoc SQL queries on file data (CSV, Parquet, JSON) without data movement.

**Validated AWS integration**: [Query files with SQL using Amazon Athena](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

---

### Better: VPC-Restricted Access with Catalog Integration

**Scope**: VPC-restricted access, Glue Catalog / Unity Catalog integration, read-write for ETL

| Component | Configuration |
|-----------|--------------|
| FSx for ONTAP | Single-AZ or Multi-AZ, multiple volumes |
| S3 Access Point | VPC origin (bound to specific VPC), read-write file system user |
| Analytics | Databricks Unity Catalog / Snowflake External Stage / Glue ETL |
| Security | VPC endpoint policy + access point policy + file system permissions |
| Networking | Gateway endpoint (in-VPC) + Interface endpoint (on-premises via Direct Connect) |
| Monitoring | CloudTrail + CloudWatch metrics |

**Use case**: ETL pipelines reading source data from FSx for ONTAP, transforming with Glue/EMR, writing curated results back.

**Validated AWS integrations**:
- [Build ETL pipelines using AWS Glue](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html)
- [Run Spark jobs using Amazon EMR Serverless](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html)

---

### Best: Multi-Account Governance with DR and AI

**Scope**: Multi-account, Lake Formation / IAM / S3 AP policy, SnapMirror DR, audit logging, AI/RAG

| Component | Configuration |
|-----------|--------------|
| FSx for ONTAP | Multi-AZ, multiple SVMs, SnapMirror to DR region |
| S3 Access Points | Per-consumer access points with scoped IAM policies |
| Analytics | Databricks + Snowflake + Athena (multi-platform) |
| AI/ML | Amazon Bedrock Knowledge Bases for RAG |
| Security | Lake Formation + S3 AP policy + VPC origin + file system ACLs |
| Governance | CloudTrail, ONTAP audit logs, data classification tags |
| DR | SnapMirror cross-region replication, ONTAP Snapshots |

**Use case**: Enterprise data mesh with domain-specific access points, AI-powered document search, and regulated data governance.

**Validated AWS integrations**:
- [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- All integrations from the Good and Better configurations

---

## Use Case Patterns by Industry

| Use Case Name | Industry | Pattern | Configuration |
|---------------|----------|---------|------|
| Zero-Copy NAS Analytics for Manufacturing | Manufacturing | Read-Only Analytics | Good |
| Regulated Data Lakehouse for Healthcare Research | Healthcare | Managed Tables (Read) | Better |
| Financial Data Mesh with FSx for ONTAP and S3 Access Points | Financial Services | Data Sharing | Best |
| AI-Powered Document Intelligence on Enterprise Files | Cross-industry | RAG with Bedrock | Best |
| Hybrid Cloud Analytics Bridge | Cross-industry | ETL Pipeline | Better |
| Media Asset Analytics without Data Migration | Media & Entertainment | Read-Only Analytics | Good |

## Implementation Steps per Use Case

### Zero-Copy NAS Analytics for Manufacturing

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Deploy FSx for ONTAP with S3 Access Point | Day 1-2 |
| 2 | Configure Glue Crawler on access point | Day 2 |
| 3 | Validate Athena queries on sample data | Day 3 |
| 4 | Connect BI tools (QuickSight) | Day 4-5 |
| **Success criteria** | Query latency < 10s for 1GB dataset, zero data copies | |

### Regulated Data Lakehouse for Healthcare Research

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Deploy Multi-AZ FSx for ONTAP with VPC-origin S3 AP | Week 1 |
| 2 | Configure Lake Formation permissions | Week 1 |
| 3 | Set up Glue ETL for de-identification pipeline | Week 2 |
| 4 | Register external tables in analytics platform | Week 2 |
| 5 | Validate audit trail and access controls | Week 3 |
| **Success criteria** | PHI never leaves VPC, audit trail complete, query < 30s | |

### Financial Data Mesh with FSx for ONTAP and S3 Access Points

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Multi-account setup with per-domain SVMs | Week 1-2 |
| 2 | Per-consumer S3 Access Points with scoped policies | Week 2-3 |
| 3 | Cross-account IAM roles and VPC endpoints | Week 3 |
| 4 | SnapMirror DR configuration | Week 4 |
| 5 | Databricks Unity Catalog + Snowflake External Stage | Week 4-5 |
| **Success criteria** | Domain isolation verified, DR RTO < 1h, multi-platform query | |

---

## Anti-Patterns: Where Not to Apply This

| Anti-Pattern | Why It Fails | What to Propose Instead |
|-------------|-------------|------------------------|
| Delta Lake write / MERGE / compaction on FSx for ONTAP S3 AP | Delta commit protocol requires atomic rename, which is not supported by FSx for ONTAP S3 AP ([API support](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)) | Read-only analytics on Delta tables, or use native S3 for Delta write path |
| Iceberg write (CREATE TABLE / INSERT) on FSx for ONTAP S3 AP | Iceberg S3FileIO cannot handle S3 AP alias for metadata write/verify. NullPointerException during commit (verified 2026-05-24). | Read-only analytics on pre-existing Iceberg tables, or use native S3 for Iceberg warehouse |
| **Any transactional table format write on FSx for ONTAP S3 AP** | **All Lakehouse formats (Delta, Iceberg, Hudi) require metadata operations that fail on S3 AP** — atomic rename (Delta/Hudi) or metadata file write/verify (Iceberg). | **Use FSx for ONTAP S3 AP for read-only analytics and flat file writes (Parquet append). Use native S3 for transactional table writes.** |
| Internet-origin AP as default for regulated industries | Regulated data requires network-level isolation; VPC-origin provides built-in explicit Deny for non-VPC traffic | VPC-origin AP for Confidential/Regulated data (note: Athena requires internet-origin) |
| Claiming "S3 fully compatible" | FSx for ONTAP S3 AP supports a subset of S3 operations. No Object Versioning, no conditional writes, no presigned URLs, 50 GiB upload limit | Use precise language: "S3 API access for supported operations" with link to compatibility matrix |
| Treating every Iceberg write path as equivalent | Iceberg via Athena and the Glue Data Catalog is verified for read and write (2026-08-06), because the commit pointer lives in Glue. Iceberg via EMR Serverless still fails, and Delta cannot commit at all | Name the engine. "Iceberg writes work" is only true for Athena here |
| Ignoring FSx for ONTAP throughput provisioning | Teams expect S3-like unlimited throughput; FSx for ONTAP S3 AP throughput is bounded by provisioned capacity | Size FSx for ONTAP throughput to workload requirements; include in PoC validation |
| Proposing FSx for ONTAP S3 AP for high-concurrency, small-file workloads | Tens of milliseconds latency + provisioned throughput limits make this suboptimal vs native S3 | Use for large sequential scans, batch analytics, document retrieval; not for high-frequency API calls |

### Claims Not to Make

1. **Never** claim FSx for ONTAP S3 AP is a drop-in replacement for S3 buckets
2. **Never** propose Delta/Hudi write operations without the adopting team explicitly acknowledging the limitations
3. **Never** use real PHI/PII in PoC environments
4. **Never** propose internet-origin AP for healthcare/financial without documenting the security trade-off
5. **Always** include compatibility matrix reference in technical proposals

---

## Architecture Selection Guidance

### When to Use FSx for ONTAP S3 Access Points

| Approach | Data Copy? | NAS Impact | Time to Analytics | Governance | AI/RAG | Best For |
|----------|-----------|-----------|-------------------|-----------|--------|----------|
| **FSx for ONTAP S3 AP (this solution)** | No | None | Hours | Unified (dual-layer) | Yes (Bedrock) | Existing NAS data, read-heavy analytics, AI on documents |
| **Native S3 + DataSync** | Yes (full copy) | None | Days (initial sync) | Separate (S3 vs NAS) | Yes | Write-heavy Lakehouse, Delta/Iceberg managed tables |
| **Native S3 + ETL pipeline** | Yes (transformed) | None | Days-weeks | Separate | Yes | Complex transformations, medallion architecture on S3 |
| **Snowflake External Stage on FSx for ONTAP S3 AP** | No (zero-copy read) | None | Hours | Snowflake-managed (Tags, Row Policy, Masking) | Yes (Cortex AI, Cortex Search) | Snowflake users needing governed AI on NAS data. COPY INTO → Managed Iceberg for open format sharing. |
| **Databricks on native S3** | Yes (to S3 first) | None | Days | Unity Catalog on S3 | Yes | Databricks-centric, Delta write-heavy |
| **FabricPool tiering** | Partial (cold tier) | Minimal | N/A (not analytics) | ONTAP-managed | No | Cost optimization, not analytics |
| **On-premises analytics** | No | None | Weeks (setup) | On-prem tools | Limited | Air-gapped environments |

### Decision Framework

```
Q1: Do you need to WRITE Lakehouse tables (Delta/Iceberg)?
  → Yes: Use native S3 for the write path; FSx for ONTAP S3 AP for read-only source data
       (exception: Iceberg via Athena + Glue Data Catalog is verified for write)
  → No: FSx for ONTAP S3 AP fits

Q2: Do you need sub-millisecond latency or unlimited concurrency?
  → Yes: Use native S3
  → No: FSx for ONTAP S3 AP (tens of ms latency, provisioned throughput)

Q3: Do you have existing NAS/ONTAP data you want to analyze?
  → Yes: FSx for ONTAP S3 AP eliminates the copy
  → No: Native S3 is simpler

Q4: Do you need NFS/SMB access alongside S3 analytics?
  → Yes: FSx for ONTAP S3 AP (multi-protocol on same data)
  → No: Native S3 may be sufficient

Q5: Do you need AI/RAG on existing documents?
  → Yes: FSx for ONTAP S3 AP + Bedrock Knowledge Bases
  → No: Evaluate based on Q1-Q4
```

---

### Assessment Questions

1. "How much file data do you currently copy to S3 for analytics? What does that cost monthly?"
2. "How long does it take from data creation to analytics availability?"
3. "Do you have separate access controls for NAS and S3? How do you audit cross-system access?"
4. "Are there documents on your file shares that you'd like to make searchable with AI?"
5. "What analytics platforms are you using or evaluating (Databricks, Snowflake, Athena)?"
6. "What compliance requirements affect your data architecture decisions?"

### Prerequisites Checklist

- [ ] File data on NAS/ONTAP at a scale where copying it is the actual problem (roughly 10 TB and up)
- [ ] An AWS account with a VPC you can attach the file system to
- [ ] A specific analytics query or workload to run, not just "we want analytics"
- [ ] The file system can run ONTAP 9.17.1 or later
- [ ] The analytics engine and the file system can sit in the same region
- [ ] Confirmed which operations the chosen engine needs, checked against the [compatibility matrix](../en/compatibility-matrix.md)

### Common Concerns, and What the Evidence Says

| Concern | What the evidence says |
|-----------|----------|
| "We already copy to S3, it works fine" | "What's the monthly cost of that pipeline? What happens when it fails? FSx for ONTAP S3 AP eliminates that entirely." |
| "Is it really S3 compatible?" | "It supports the core S3 operations for analytics (Get, Put, List, Delete). Here's the exact compatibility matrix. Read-only analytics is fully verified." |
| "What about performance?" | "Latency is tens of milliseconds — same as S3. Throughput depends on your FSx for ONTAP provisioning. We size it to your workload in the PoC." |
| "We need Delta Lake write" | "Delta write requires atomic rename which isn't supported. We recommend FSx for ONTAP S3 AP for source data reads, native S3 for Delta write targets." |
| "Our security team will block this" | "Block Public Access is enforced by default. Dual-layer auth (IAM + file system). VPC-origin option for network isolation. Here's the governance doc." |

## References

- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [Configuring network access for Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)
- [Amazon FSx for NetApp ONTAP performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
