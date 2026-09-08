> 🌐 Language: [日本語](../ja/s3ap-design-considerations.md) | **English**

# FSx for ONTAP S3 Access Points — Design Considerations

> Design guidance for exposing NAS data via S3 API using FSx for ONTAP S3 Access Points. Covers constraints, performance characteristics, and operational patterns to review before PoC.

---

## Premise: How S3 Access Points Work

FSx for ONTAP S3 Access Points make file data on NAS volumes accessible via S3-compatible API. Unlike Amazon S3 buckets, S3 API requests are processed through ONTAP's file system layer.

Key characteristics:

- S3 object keys map to NAS directory/file paths
- S3 API performance depends on NAS directory structure and file count
- Both NFS/SMB and S3 can access the same data, but consistency design is required
- Not all Amazon S3 features are available (e.g., Versioning is not supported)

---

## 1. Directory Design (Most Critical)

### Problem: Too Many Files in a Single Directory

When S3 clients write all files under the root prefix, ONTAP ends up with millions of files in a single directory.

| Symptom | Cause |
|---------|-------|
| ListObjectsV2 response time degrades severely | In-memory sort of all directory entries required |
| New file creation fails | maxdir-size (directory metadata size limit) reached |
| Load concentration on 1 node (FlexGroup) | Files in the same directory tend to land on the same constituent |
| NFS `ls` / `find` also slows down | Same directory metadata traversal |

### Recommended: Hierarchical Partitioning

```
/volume-root/
  └── {source}/{year}/{month}/{day}/
      └── {filename}.parquet
```

**Guidelines:**
- Keep files per directory below **100,000** as a rule of thumb
- Time-series data requires date partitioning (`year=YYYY/month=MM/day=DD/` or `dt=YYYY-MM-DD/`)
- For high-frequency writes, consider hash buckets (`bucket-{hash mod 256}/`)
- Aim for 5–8 levels of depth. Beyond 20 levels, NFS path length limits become a concern

### Volume Type Selection

| Type | Characteristics | Recommended For |
|------|----------------|-----------------|
| FlexVol | Single node. Simple but limited scale | Small scale (< 1M files) |
| FlexGroup | Auto-distributes across multiple constituents | Large scale (> 1M files, high throughput) |

With FlexGroup, **different directories are distributed across different constituents**. Proper directory distribution leverages multi-node parallelism.

References:
- https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues
- https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html

---

## 2. Object Key and Path Length Constraints

| Constraint | Value | Impact |
|-----------|-------|--------|
| Max S3 object key length | 1,024 bytes | NAS paths exceeding this are inaccessible via S3 |
| Max directory/file name | 255 characters | Key segments exceeding this are unusable |
| Multi-byte characters | Evaluated as UTF-8 byte count | 1 Japanese character = 3–4 bytes |

### Recommendations

- Keep individual path component names short
- Avoid embedding long unique strings in file names (use shortened UUIDs)
- Audit path lengths before exposing existing NAS data
- Define a safe character set for both S3 and NFS/SMB (alphanumeric + `-_./`)
- Test edge cases: spaces, special characters, Unicode normalization differences

---

## 3. Performance Characteristics

S3 Access Points access has different performance characteristics than direct Amazon S3 access.

### Tendencies

| Aspect | Characteristic |
|--------|---------------|
| Small files (< 64KB) | Metadata processing overhead is relatively large. Latency-bound, not throughput-bound |
| Large files (> 1MB) | Data transfer dominates. Performance gap with Amazon S3 narrows |
| ListObjectsV2 | Latency increases proportionally with directory file count. Seconds-level at millions |
| PUT (write) | Additional cost when directory creation is involved |
| Concurrent requests | Throttled by FSx for ONTAP throughput capacity |

### Mitigations

- **Narrow ListObjectsV2 scope**: Use prefix parameter to target specific directories
- **Avoid full enumeration**: Use HEAD/GET directly when object key is known
- **Maintain external index**: Glue Data Catalog, DynamoDB, or external catalog for file listings
- **Aggregate small files**: Batch convert many JSON/CSV → Parquet
- **Right-size FSx throughput capacity**: Match provisioned throughput to read/write patterns

---

## 4. ListObjectsV2 Design

ListObjectsV2 is the most performance-sensitive API operation.

### Internal Behavior on ONTAP

S3 ListObjectsV2 requests translate to NAS `readdir` (directory entry enumeration). Results must be returned **sorted**, so large directories incur in-memory sort costs.

### Design Patterns

| Pattern | Use Case | Notes |
|---------|----------|-------|
| Prefix-limited LIST | Files for a specific date/tenant | Deeper prefix = narrower scope |
| MaxKeys + pagination | UI display, incremental processing | Keep per-page count ≤ 1,000 |
| No-LIST design | Streaming writes → GET by known key | Kafka/Kinesis writes with deterministic keys |
| External catalog | Glue Crawler, Athena tables | Partition discovery without LIST |

### Anti-patterns

- Periodic full LIST at root prefix
- Fetching all results then filtering client-side
- Recursive LIST ignoring directory hierarchy

---

## 5. Multi-Protocol Access Consistency

When the same data is accessed via NFS/SMB and S3 simultaneously, consistency must be designed.

### Scenarios to Watch

| Scenario | Risk |
|----------|------|
| S3 GET on a file being written via NFS | May read incomplete data |
| NFS read during S3 PUT in progress | File invisible until S3 PUT completes (S3 semantics) |
| NFS rename → S3 GET with old key | 404 Not Found |
| Concurrent NFS + S3 write to same file | Last-writer-wins. Data loss risk |

### Recommended Patterns

- **Limit write protocol to one** (e.g., S3 write → NFS read)
- Write to temporary directory (`_tmp/`), rename to publish directory on completion
- Define state transitions: "ingesting" → "published" → "processed"
- If both protocols write, ensure file-level mutual exclusion

---

## 6. Feature Compatibility

Compared to Amazon S3, the following features are unsupported or constrained.

| Feature | Status | Alternative |
|---------|:------:|------------|
| Versioning | ❌ Not supported | ONTAP Snapshot for point-in-time protection |
| Lifecycle Policies | ❌ Not supported | FabricPool auto-tiering + custom scripts |
| Object Lock / WORM | ❌ Not supported | SnapLock (ONTAP feature) |
| S3 Event Notification | ❌ Not supported | Scheduled polling, or the ONTAP native audit log. **FPolicy + EventBridge is not a substitute** — writes arriving through the access point raise no notification (measured 2026-08-26, ONTAP 9.18.1P3D1) |
| Conditional writes (If-None-Match) | ❌ 501 Not Implemented | Application-side locking |
| Cross-Region Replication | ❌ Not supported | SnapMirror ([see considerations](s3ap-flexcache-snapmirror-considerations.md)) |
| S3 Select | ❌ Not supported | Athena / DuckDB queries |
| Multipart Upload | ✅ Supported (9.16.1+) | Enable Advanced Capacity Balancing |

### Important Note

"S3 compatible" does not mean "identical to Amazon S3." E2E testing must cover APIs that SDKs call implicitly (HeadBucket, ListBuckets, GetBucketLocation, etc.).

---

## 7. Security Design

### Access Point Separation

Separate Access Points by purpose, each with least-privilege IAM policies.

```
ap-analytics-readonly     ← Athena / DuckDB (GetObject, ListBucket only)
ap-etl-ingestion          ← Glue ETL (PutObject, GetObject)
ap-sagemaker-training     ← SageMaker (GetObject only, specific prefix)
ap-audit-readonly         ← Audit team (GetObject, ListBucket, all prefixes)
```

### Dual-Layer Authorization Model

S3 Access Points implement **dual-layer authorization**:

1. **IAM + AP policy layer**: Evaluated when S3 API request is received
2. **File system permission layer**: ONTAP UNIX/NTFS ACL (determined by FileSystemIdentity)

Both checks must pass for access to be granted. IAM allow + NAS deny = access denied.

---

## 8. PoC Checklist

### Architecture

- [ ] Stakeholders understand this is NAS data exposed via S3, not an Amazon S3 bucket
- [ ] S3 APIs required by target AWS services are identified
- [ ] Supported features for the target FSx for ONTAP version are confirmed

### Namespace

- [ ] 1,024-byte key length constraint is considered
- [ ] 255-character per-component constraint is considered
- [ ] Multi-byte characters evaluated by byte count
- [ ] Large single directories are avoided
- [ ] Directory depth is reasonable (target: 5–8 levels)

### Performance

- [ ] ListObjectsV2 performance tested at production file counts
- [ ] Small file (< 64KB) workload PUT/GET latency measured
- [ ] Concurrent NFS/SMB + S3 load tested
- [ ] P95/P99 latencies confirmed (not just averages)

### Functionality

- [ ] Impact of Versioning unavailability evaluated
- [ ] Impact of conditional write unavailability (501) evaluated
- [ ] Multipart Upload support confirmed
- [ ] APIs called implicitly by SDKs also verified

### Operations

- [ ] Write protocol rules defined
- [ ] Snapshot-based protection designed
- [ ] S3-side and NAS-side audit methods defined
- [ ] Access Points separated by purpose

---

## Related Documents

- [FlexCache / SnapMirror Additional Considerations](s3ap-flexcache-snapmirror-considerations.md)
- [S3 AP + SnapMirror + FlexCache Research](../../integrations/snapmirror-flexcache-multicloud/docs/en/research.md)
- [S3 AP Data Collection CloudFormation Template (with DESIGN TIPs)](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/infrastructure/s3ap-data-collection)
- [AWS Docs: S3 Access Points for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [AWS Docs: Best practices — Optimizing S3 performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: How to avoid maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp Docs: FlexGroup volumes](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
