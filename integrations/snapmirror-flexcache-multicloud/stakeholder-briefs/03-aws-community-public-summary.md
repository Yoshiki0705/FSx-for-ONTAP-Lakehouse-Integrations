# Stakeholder Brief: AWS Community — Public Summary

> **Audience**: AWS Community (dev.to readers, re:Post users, conference attendees)
> **Classification**: Public (all content based on publicly verifiable information)
> **Date**: 2026-07-21
> **Format**: dev.to article candidate / conference talk material

---

## Title Candidates

- "FSx for ONTAP S3 AP + SnapMirror/FlexCache: Multi-Cloud Data Distribution Validated"
- "S3 API で書き込み、NFS/SMB で読み出す — マルチクラウドデータ配信の検証"
- Short form (dev.to): "S3 AP × FlexCache: Cross-Cloud NFS Access Validated"

---

## Key Message (1 paragraph)

FSx for ONTAP S3 Access Points enable S3 API data ingestion into ONTAP volumes. Because S3 AP is implemented as a "lens" on a standard FlexVol (via ONTAP's S3 NAS bucket mechanism), these volumes can be protected and distributed using ONTAP's native SnapMirror and FlexCache capabilities. This means you can write data via S3 API, replicate it across regions or clouds with SnapMirror, and provide low-latency NFS/SMB read access at remote sites via FlexCache — all on the same volume.

---

## What We Validated (ONTAP 9.17.1)

### Works

| Capability | How it works |
|-----------|--------------|
| S3 AP volume → SnapMirror Async | Standard volume-level replication. Data written via S3 is replicated. |
| SnapMirror break → S3 AP re-attach | After failover, create a new S3 AP on the destination volume (~60s wait for API sync). |
| **S3 AP on a live SnapMirror destination** | Reads work with the relationship still running — no break. Mount the DP volume through ONTAP, wait for the FSx API to report the junction path, attach. Writes return `AccessDenied`; a later transfer was readable through the same access point in 15 s. |
| **S3 AP on a clone of the destination** | Same, and writable, but frozen at the cloned Snapshot. |
| S3 AP volume → FlexCache Origin | Cache Volume provides NFS read access to data written via S3 AP. |
| Cross-region SnapMirror | FSx for ONTAP to FSx for ONTAP (any region pair). |
| Cross-cloud SnapMirror | FSx for ONTAP → CVO on GCP/Azure, on-premises ONTAP, GCNV. |
| FlexCache write-back | Remote sites can write via NFS/SMB on Cache; changes propagate to Origin. |
| Encryption in-transit | Cluster Peering Encryption (TLS 1.2) enabled by default. |

### Works With Caveats

| Capability | Caveat |
|-----------|--------|
| FlexCache write-back + S3 AP Origin writes | If S3 AP writes and Cache writes target the **same file**, Cache dirty data is overwritten. Design for non-overlapping file sets. |
| S3 AP re-attach timing | Poll `DescribeVolumes` for a non-null `JunctionPath`, not for `VolumeType: RW` — the junction path is the gate. After a break the FSx API keeps reporting `DP` for ~60 s same-region and over 10 min cross-region, while attachment already works. Standing up a read path on a destination that was never broken took 2298 s for the junction path to propagate. |
| GCNV FlexCache | Cache-only (not Origin). NFSv3 access only. |

### Does Not Work

| Limitation | Alternative |
|-----------|-------------|
| SVM-DR (SVM-level SnapMirror) | Use volume-level SnapMirror + pre-configure destination SVM manually. |
| FSx for ONTAP → ANF (SnapMirror) | Use CVO on Azure as SnapMirror destination, or file-level sync tools. |
| SnapMirror Synchronous | Async only for S3 NAS bucket volumes (minimum 5-min schedule). |

---

## Architecture Decision Guide

### When to use SnapMirror

- Disaster recovery (full copy at destination, immediate failover)
- Data migration (one-time copy)
- Multi-cloud distribution (cross-cloud replication)
- When RPO of 5+ minutes is acceptable

### When to use FlexCache

- Read acceleration at remote sites (low-latency local reads)
- Multiple teams accessing same dataset from different locations
- Storage efficiency (only cached data consumes space)
- When WAN RTT is <= 200ms (for write-back mode)

### When to use both

- DR (SnapMirror) + daily read performance (FlexCache) at different sites
- Primary: SnapMirror for full protection; secondary: FlexCache for hot data acceleration

---

## Supported Multi-Cloud Paths

| Source | Destination | SnapMirror | FlexCache | Notes |
|--------|------------|:----------:|:---------:|-------|
| FSx for ONTAP | FSx for ONTAP (same region) | Yes | Yes | Simplest |
| FSx for ONTAP | FSx for ONTAP (cross-region) | Yes | Yes | VPC Peering required |
| FSx for ONTAP | On-premises ONTAP | Yes | Yes | Direct Connect / VPN |
| FSx for ONTAP | CVO on GCP | Yes | Yes | Cross-cloud VPN |
| FSx for ONTAP | CVO on Azure | Yes | Yes | Cross-cloud VPN |
| FSx for ONTAP | GCNV | Yes | Cache only | External Replication |
| FSx for ONTAP | ANF | — | — | Not supported directly |

---

## Version Requirements

| Feature | Minimum ONTAP | Notes |
|---------|:-------------:|-------|
| S3 Access Point (basic) | 9.14.1 | FSx for ONTAP feature |
| S3 NAS bucket (multiprotocol) | 9.12.1 | Underlying mechanism |
| SnapMirror Async | 9.11.1 | FSx for ONTAP baseline |
| FlexCache write-back | 9.15.1 | Both Origin and Cache |
| Recommended | **9.17.1+** | All features validated |

---

## Failover Procedure Summary

```
1. Break SnapMirror relationship (ONTAP REST API or FSx API)
2. Set junction path on destination volume (if not already set)
3. Poll FSx API until VolumeType = RW (~60 seconds)
4. Create new S3 Access Point on destination volume
5. Update client applications with new S3 AP ARN/alias
6. Verify NFS/SMB access on destination (pre-configured SVM)
```

---

## Related Resources

- Full research document: `docs/en/research.md` (this repository)
- FSx for ONTAP S3 AP documentation: [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)
- SnapMirror concepts: [NetApp Docs](https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-replication-concept.html)
- FlexCache write-back: [NetApp Docs](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-overview.html)

---

## Article Series Context

This research is part of the "FSx for ONTAP S3 Access Points + Data Lakehouse" series on dev.to. Previous parts cover Athena, DuckDB, Databricks, Snowflake, and EMR integrations. This will be published as an upcoming part in the series.
