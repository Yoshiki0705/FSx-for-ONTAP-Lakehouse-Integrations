🌐 **English** | [日本語](../ja/fsx-ontap-feature-utilization-map.md)

# FSx for ONTAP Feature Utilization Map

> **Purpose**: Maps which FSx for ONTAP features are utilized by each connection path and document in this repository.
> **Last updated**: 2026-06-20

---

## Executive Summary

FSx for ONTAP provides **enterprise data protection + multiprotocol access + Lakehouse integration** on a single platform. Standard S3 + EBS cannot deliver the following combination:

- Simultaneous NFS / SMB / S3 API access to the same data
- Storage-efficient zero-cost FlexClone (instant test/dev environment creation)
- Consistent Point-in-Time Snapshots (DataSync source consistency)
- File-level event detection (FPolicy → real-time pipelines)
- Cross-region DR via SnapMirror (RPO in minutes)

---

## Feature × Connection Path Matrix

| FSx for ONTAP Feature | DataSync → S3 → UC | Kafka (FPolicy) → UC | Athena / Glue Direct | Snowflake Direct | Bedrock KB | AI Catalog |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **S3 Access Points** | — (NFS source) | — | ✅ Required | ✅ Required | ✅ Required | ✅ Required |
| **NFS v4.1** | ✅ Source protocol | — | — | — | — | — |
| **SMB** | — | — | — | — | — | — |
| **Multiprotocol Simultaneous Access** | ✅ Value basis | ✅ Value basis | ✅ Value basis | ✅ Value basis | ✅ Value basis | ✅ Value basis |
| **Snapshot** | ✅ Source consistency | — | — | — | — | ✅ Consistency |
| **FlexClone** | ✅ Production isolation | — | — | — | — | ✅ Test env |
| **FPolicy** | — | ✅ Event detection | — | — | — | — |
| **SnapMirror** | — | — | — | — | — | — |
| **FabricPool (Tiering)** | — | — | — | — | — | — |
| **SVM Isolation** | ✅ Tenant separation | ✅ Tenant separation | ✅ Tenant separation | ✅ Tenant separation | — | — |
| **ONTAP Volume Encryption** | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest | ✅ at-rest |

---

## Feature Details: Why Use This Feature

### S3 Access Points

| Attribute | Value |
|-----------|-------|
| **Used in** | Athena / Glue / EMR / Snowflake / Bedrock KB data access |
| **Characteristic** | Data written via NFS/SMB is readable via S3 API (no conversion/copy needed) |
| **Constraints** | Conditional writes not supported, Event Notifications not supported ([BLK-002](./blocker-tracker.md), [BLK-003](./blocker-tracker.md)) |
| **Related docs** | [Compatibility Matrix](./compatibility-matrix.md), [Networking](./fsx-ontap-s3ap-networking.md) |

> **The true value of multiprotocol**: The value of S3 AP is not "providing S3 API" but enabling analytics engines to read **the same data** that business users access via NFS/SMB — without transformation. With EBS + S3, data copy or ETL is always required.

### Snapshot

| Attribute | Value |
|-----------|-------|
| **Used in** | DataSync source consistency, AI catalog consistency, DR |
| **Characteristic** | Zero-cost (no capacity consumed until writes occur), instant creation, no application downtime |
| **Constraints** | Snapshot alone cannot replicate to other regions (combine with SnapMirror) |
| **Related docs** | [DataSync Guide](./datasync-to-s3-guide.md) (Phase 2), [Recovery Semantics](./recovery-semantics.md) |

> **DataSync + Snapshot pattern**: Executing Snapshot → FlexClone → DataSync achieves the triple benefit of "zero production impact + data consistency + incremental sync." Without Snapshot, there's a risk of data inconsistency from files changing during sync.

### FlexClone

| Attribute | Value |
|-----------|-------|
| **Used in** | DataSync production isolation, instant dev/test environment creation |
| **Characteristic** | **Zero additional storage** (no capacity consumed until writes occur), instant creation (seconds even for TB-scale) |
| **Constraints** | Storage consumption begins when writes to the clone increase |
| **Related docs** | [DataSync Guide](./datasync-to-s3-guide.md) (Phase 2), [ADR-001](../adr/ADR-001-datasync-as-primary-sync.md) |

> **What zero-cost means**: FlexClone uses WAFL (Write Anywhere File Layout) metadata references to create a complete volume clone without physical copy. Cloning a 1 TB volume adds 0 bytes of additional storage. Unlike EBS Snapshots, it's immediately mountable as an independent readable volume.

### FPolicy

| Attribute | Value |
|-----------|-------|
| **Used in** | Event source for Kafka → Structured Streaming path, near-real-time S3 sync |
| **Characteristic** | Real-time notification of file operations (create/modify/delete/rename) to external systems. Alternative to S3 Event Notifications |
| **Constraints** | Metadata events only (file content not transferred), operational complexity via Lambda |
| **Related docs** | [Kafka-ClickHouse-UC Connectivity](./kafka-clickhouse-unity-catalog-connectivity.md), [DataSync Guide](./datasync-to-s3-guide.md) (FPolicy alternative pattern) |

> **S3 Event Notifications alternative**: FSx for ONTAP S3 AP does not support Event Notifications (BLK-003). **FPolicy is not a substitute**: what FPolicy detects is NFS / SMB file operations, and operations through the S3 access point are neither detected nor blocked, even under a `mandatory` policy (measured 2026-08-26, ONTAP 9.18.1P3D1, [the measured FPolicy / S3 access point coverage](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/s3ap-monitoring-coverage-implications.md)). To drive something from a write through the access point, use EventBridge Scheduler polling or the ONTAP native audit log (which records access point operations as `Source=HTTP` / `Source=S3`). On volumes written over NFS or SMB, FPolicy remains usable.

### SnapMirror

| Attribute | Value |
|-----------|-------|
| **Used in** | Cross-region DR, data mobility |
| **Characteristic** | Block-level efficient replication (RPO in minutes). Syncs entire volumes to another region |
| **Constraints** | SnapMirror **S3** (ONTAP S3 → AWS S3) is unavailable on FSx for ONTAP ([BLK-004](./blocker-tracker.md)). Volume-level SnapMirror IS available |
| **Related docs** | [ADR-002](../adr/ADR-002-snapmirror-s3-unavailability.md), [Blocker Tracker](./blocker-tracker.md) |

> **Volume SnapMirror vs SnapMirror S3 distinction**: Volume-level SnapMirror (replication between FSx for ONTAP instances) is fully available. What's unavailable is object replication from "ONTAP S3 bucket → AWS S3 bucket" (SnapMirror S3) only. DR designs can leverage Volume SnapMirror.

### FabricPool (Tiering)

| Attribute | Value |
|-----------|-------|
| **Used in** | Cost optimization (automatic cold data tiering to S3) |
| **Characteristic** | Automatically moves data from SSD → S3 based on access frequency. Transparent to applications (no path changes) |
| **Constraints** | Additional latency on first read of tiered data. Consider impact for analytics workloads |
| **Related docs** | [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) (Future Outlook section) |

### SVM (Storage Virtual Machine) Isolation

| Attribute | Value |
|-----------|-------|
| **Used in** | Tenant/workload isolation (production vs dev, factory A vs factory B) |
| **Characteristic** | Complete logical separation of network/authentication/storage on a single file system |
| **Constraints** | SVM count limits (FSx for ONTAP quota dependent) |
| **Related docs** | [Compatibility Matrix](./compatibility-matrix.md) (OT/IT Security) |

---

## Technical Comparison: FSx for ONTAP vs Alternative Storage

> **Note**: This is a comparison of technical characteristics, not a claim of superiority. The appropriate choice differs by use case.

| Requirement | FSx for ONTAP | Amazon S3 + EBS | Selection Guidance |
|---|:---:|:---:|---|
| NFS + SMB + S3 simultaneous access | ✅ Native | ❌ Not possible | When business users (NFS/SMB) and analytics engines (S3) access the same data |
| Zero-cost Clone (dev/test) | ✅ FlexClone | ❌ Separate copy | When instant test environments from production data are needed |
| Point-in-Time consistency | ✅ Snapshot (instant) | ⚠️ EBS Snapshot (minutes) | When DataSync source consistency is critical |
| File event detection | ✅ FPolicy | ❌ Not available | When event-driven pipelines are required |
| Capacity pool tiering | ✅ FabricPool | ✅ S3 Intelligent-Tiering | When automatic cold data tiering is needed (both options viable) |
| Conditional writes | ❌ Not supported | ✅ S3 supported | When Delta/Iceberg writes are needed → standard S3 |
| Event Notifications | ❌ Not supported | ✅ S3 supported | When Auto Loader notification mode is needed → standard S3 |
| Scale (unlimited capacity) | ⚠️ Volume size limits | ✅ Virtually unlimited | For petabyte-scale data lakes → standard S3 |

> **Right tool selection**: FSx for ONTAP is optimal when the primary requirements are "enterprise file data + multiprotocol access + data protection." For pure object storage use cases (massive data lakes, CDN origins), standard S3 is appropriate. Most enterprise environments **use both in combination** (FSx for ONTAP = source + business access, S3 = analytics copy + Lakehouse).

---

## Cross-Document Feature Coverage

| Document | S3 AP | Snapshot | FlexClone | FPolicy | SnapMirror | FabricPool | SVM | Multi-AZ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) | ● | ● | ● | ● | ○ | ○ | ○ | — |
| [DataSync → S3 Guide](./datasync-to-s3-guide.md) | — | ● | ● | ● | — | — | — | — |
| [Compatibility Matrix](./compatibility-matrix.md) | ● | — | — | — | — | — | ○ | ● |
| [Kafka-ClickHouse-UC](./kafka-clickhouse-unity-catalog-connectivity.md) | — | — | — | ● | — | — | — | — |
| [S3 Annotations Evaluation](./s3-annotations-governance-evaluation.md) | — | ○ | — | ● | — | — | — | — |
| [Recovery Semantics](./recovery-semantics.md) | — | ● | ● | — | ● | — | — | ● |
| [Networking](./fsx-ontap-s3ap-networking.md) | ● | — | — | — | — | — | ● | — |
| [Event-driven Architecture](./event-driven-architecture.md) | — | — | — | ● | — | — | — | — |
| [Blocker Tracker](./blocker-tracker.md) | ● | — | — | — | ○ | — | — | — |

**Legend**: ● = Primary topic (detailed) / ○ = Mentioned / — = Not mentioned

---

## Related Documents

- [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) — All connection paths overview
- [Blocker Tracker](./blocker-tracker.md) — Constraint details and resolution outlook
- [ADR-001](../adr/ADR-001-datasync-as-primary-sync.md) — DataSync adoption rationale (Snapshot/FlexClone usage)
- [Reading Path Guide](./reading-path-guide.md) — Overall document navigation
