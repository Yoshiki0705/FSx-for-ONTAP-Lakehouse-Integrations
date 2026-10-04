# Recovery Semantics: ONTAP Snapshot vs. Lakehouse Time Travel

## Overview

This document clarifies the relationship between ONTAP Snapshot (storage-level point-in-time recovery) and Lakehouse time travel (Delta Lake / Apache Iceberg metadata-based logical recovery). These are **complementary but fundamentally different mechanisms** that protect against different failure modes.

## Mechanism Comparison

| Aspect | ONTAP Snapshot | Delta Lake Time Travel | Iceberg Time Travel |
|--------|---------------|----------------------|---------------------|
| **Layer** | Storage (block-level) | Table metadata (transaction log) | Table metadata (manifest list) |
| **Granularity** | Entire volume | Single table | Single table |
| **What is captured** | All files on volume at point-in-time | Table state per committed transaction | Table state per snapshot |
| **Recovery method** | Restore volume or access `.snapshot` directory | Query with `VERSION AS OF` or `TIMESTAMP AS OF` | Query with `snapshot_id` or `as_of_timestamp` |
| **Retention** | Configurable snapshot policy (hourly/daily/weekly) | Configurable `delta.logRetentionDuration` (default 30 days) | Configurable `history.expire.max-snapshot-age-ms` |
| **Space efficiency** | Copy-on-write (only changed blocks stored) | Previous data files retained until VACUUM | Previous data files retained until expiration |
| **Cross-table consistency** | Yes (volume-level atomic snapshot) | No (per-table only) | No (per-table only) |
| **Protects against** | Accidental deletion, corruption, ransomware, volume-level disasters | Logical errors in table operations, bad writes, schema mistakes | Same as Delta |
| **Does NOT protect against** | Logical application errors already committed | Storage-level failures, volume loss, multi-table inconsistency | Same as Delta |

## When to Use Which

### Use ONTAP Snapshot when:

| Scenario | Why Snapshot |
|----------|-------------|
| Volume-level disaster recovery | Restores all files atomically to a consistent point |
| Ransomware recovery | Immutable snapshots cannot be modified by compromised applications |
| Cross-table consistency | Need to restore multiple tables/files to the same point-in-time |
| Accidental volume deletion | Snapshot + SnapMirror provides off-volume protection |
| Compliance: long-term retention | SnapLock + Snapshot for WORM compliance |
| Pre-maintenance checkpoint | Quick rollback if maintenance causes issues |

### Use Lakehouse Time Travel when:

| Scenario | Why Time Travel |
|----------|----------------|
| Undo a bad table write | Revert a single table without affecting other data |
| Audit table changes | Query historical table state for compliance |
| Reproduce analytics results | Re-run queries against past table versions |
| Debug data pipeline | Compare table state before/after a transformation |
| Schema evolution rollback | Revert a schema change on a single table |

### Use Both Together when:

| Scenario | Approach |
|----------|----------|
| Defense in depth | Snapshot for storage-level protection + time travel for logical-level protection |
| Regulated environments | Snapshot for disaster recovery SLA + time travel for audit trail |
| Multi-table pipeline failure | Snapshot to restore volume to consistent state, then time travel to verify individual table states |

## Important Caveats for FSx for ONTAP S3 Access Point Context

Lakehouse time travel requires write access. Delta Lake and Iceberg time travel depend on transaction logs/metadata being written alongside data. Since FSx for ONTAP S3 Access Points have limitations on atomic rename (required by Delta) and conditional writes, time travel is only available for tables whose transaction logs are managed externally (for example, Iceberg with Glue Catalog as metadata store) or for read-only access to pre-existing versioned tables.

ONTAP Snapshot works regardless of access method. Snapshots capture the volume state at the block level, independent of whether data was written via NFS, SMB, or S3 API. This makes Snapshot the primary recovery mechanism for data accessed through S3 Access Points.

Snapshot does not understand table semantics. Restoring a snapshot restores all files, including potentially in-progress writes. For Lakehouse tables, this means the table's transaction log and data files are restored together, which may leave the table in a state that requires repair (for example, orphaned data files referenced by a rolled-back commit).

## Recovery Decision Matrix

| Failure Type | Primary Recovery | Secondary Recovery |
|-------------|-----------------|-------------------|
| Accidental file deletion | ONTAP Snapshot (`.snapshot` directory access) | — |
| Bad data written to table | Lakehouse time travel (if available) | ONTAP Snapshot |
| Volume corruption | ONTAP Snapshot restore | SnapMirror failover |
| Ransomware | ONTAP Snapshot (immutable) | SnapMirror to isolated DR |
| Region failure | SnapMirror cross-region | — |
| Schema migration error | Lakehouse time travel | ONTAP Snapshot |
| Multi-table inconsistency | ONTAP Snapshot (volume-level atomic) | Manual reconciliation |
| Compliance audit (table history) | Lakehouse time travel | — |
| Compliance audit (storage history) | ONTAP Snapshot + SnapLock | — |

## RTO / RPO Comparison

| Mechanism | Typical RPO | Typical RTO | Notes |
|-----------|-------------|-------------|-------|
| ONTAP Snapshot | Minutes to hours (per policy) | Seconds to minutes | Near-instant restore from snapshot |
| SnapMirror (async) | Minutes (per schedule) | Minutes | Failover to DR volume |
| SnapMirror (sync) | Zero | Minutes | Synchronous replication |
| Delta time travel | Per-commit (every write) | Seconds | Query-level, no restore needed |
| Iceberg time travel | Per-commit (every write) | Seconds | Query-level, no restore needed |
| FSx for ONTAP Backup | Daily (automatic) | Hours | Full volume restore from backup |

## References

- [Protecting your data with volume backups](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-backups.html)
- [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Amazon FSx for NetApp ONTAP performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
