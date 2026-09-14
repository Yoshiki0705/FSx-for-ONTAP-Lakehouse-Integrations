# Stakeholder Brief: NetApp Field (TMC/CTC)

> **Audience**: NetApp Technical Marketing / Consulting Technical Center / Field SEs
> **Classification**: Shareable with NetApp field teams
> **Date**: 2026-07-21
> **From**: AWS Community Builder (Storage/Data Analytics)

---

## Purpose

Quick-reference for field engagements where customers ask about combining FSx for ONTAP S3 Access Points with SnapMirror or FlexCache for multi-cloud data distribution. Focus on constraints, recommended configurations, and common pitfalls.

---

## One-Sentence Summary

FSx for ONTAP S3 AP-attached volumes support SnapMirror Async and FlexCache (validated on 9.17.1) — use volume-level SnapMirror (not SVM-DR) and design for non-overlapping file sets if combining S3 AP ingestion with FlexCache write-back.

---

## Quick Decision Matrix

| Customer asks... | Answer | Reference |
|-----------------|--------|-----------|
| "Can I SnapMirror an S3 AP volume?" | Yes — Async, volume-level only | SM-001 |
| "Does SVM-DR work with S3 AP?" | No — use volume-level SnapMirror | SM-004 |
| "Can I FlexCache an S3 AP volume?" | Yes — Origin 9.12.1+, Cache any compatible | FC-001 |
| "Does write-back work with S3 AP?" | Yes, with caveat: avoid same-file S3+Cache writes | FC-004 |
| "Can I replicate to ANF?" | No — use CVO on Azure as intermediary | XC-007 |
| "Can I replicate to GCNV?" | Yes — External Replication (SnapMirror) or FlexCache Cache | XC-006 |
| "Is SnapMirror Sync supported?" | No — Async only for S3 NAS bucket volumes | SM-001 |
| "What about failover to the destination?" | Break → wait 60s (FSx API) → create new S3 AP | SM-005 |
| "Can analytics read the replica without failing over?" | Yes, reads only. Mount the DP destination through ONTAP, then attach an S3 AP. No break, relationship keeps running. Allow tens of minutes for the junction path to reach the FSx API | SM-VAL-013 |
| "What if the consumer needs to write?" | Clone the destination Snapshot and attach to the clone. Writable, but fixed at the cloned point in time | SM-VAL-013 |

---

## Top 3 Constraints to Communicate Early

### 1. SVM-DR is NOT supported (SM-004)

**What to tell the customer:**
> "When your SVM has S3 Access Points configured, you need to use volume-level SnapMirror for data protection. SVM-level DR (SVM-DR) is not supported because the S3 NAS bucket configuration cannot be replicated at the SVM level. Pre-configure the destination SVM's protocol settings (CIFS, export policies, name-mappings) separately."

**Common misconception:** Customers assume SVM-DR handles everything. Clarify that volume data is protected, but SVM configuration requires separate management.

### 2. S3 AP does NOT "move" on failover (SM-005)

**What to tell the customer:**
> "S3 Access Points are AWS-layer constructs — they don't travel with SnapMirror. After failover (SnapMirror break), you create a new S3 AP on the destination volume. The new AP gets a new ARN and alias. Applications must be updated to use the new endpoint."

**Failover sequence:**
1. SnapMirror break
2. Wait ~60s for FSx API to show `VolumeType: RW`
3. `aws fsx create-and-attach-s3-access-point` on destination volume
4. Update application S3 endpoint configuration

### 3. FlexCache write-back + S3 AP requires file-set separation (FC-004)

**What to tell the customer:**
> "If you're using FlexCache write-back AND S3 AP ingestion on the same Origin volume, ensure they operate on different files. S3 writes to Origin trigger XLD revoke — if the Cache has uncommitted writes to the same file, that data is lost (Origin wins). Separate by directory path or file naming convention."

**Safe patterns:**
- `/data/ingestion/` (S3 AP writes) + `/data/analysis/` (Cache NFS writes) → Safe
- Same file from both paths → Data loss risk

---

## Recommended Architecture (For Sizing Discussions)

```
┌─────────────────────────────────────────────┐
│  AWS Region A (Primary)                      │
│  ┌─────────────────────────────┐            │
│  │ FSx for ONTAP (Source)      │            │
│  │ ├── S3 AP (data ingestion)  │            │
│  │ ├── NFS/SMB (local access)  │            │
│  │ └── SnapMirror Source       │            │
│  └─────────────────────────────┘            │
└─────────────────────────────────────────────┘
         │ SnapMirror Async        │ FlexCache
         ▼                         ▼
┌────────────────────┐    ┌────────────────────┐
│ AWS Region B (DR)  │    │ On-prem / CVO      │
│ FSx for ONTAP      │    │ FlexCache Cache    │
│ (SnapMirror dest)  │    │ (read acceleration)│
│ + new S3 AP        │    │ NFS/SMB access     │
│   (post-failover)  │    │                    │
└────────────────────┘    └────────────────────┘
```

---

## Version Compatibility Reference

| Configuration | Source ONTAP | Destination ONTAP | Key Constraint |
|--------------|:-----------:|:-----------------:|----------------|
| SnapMirror (FSx → FSx) | 9.11.1+ | 9.11.1+ | Same or ±1 major version |
| SnapMirror (FSx → On-prem) | 9.11.1+ | Compatibility matrix | Check NetApp IMT |
| SnapMirror (FSx → CVO) | 9.11.1+ | CVO latest | Auto-updated |
| FlexCache (Origin → Cache) | 9.12.1+ | Within 4 minor versions | Origin must be >= Cache |
| FlexCache write-back | 9.15.1+ | 9.15.1+ | Both sides required |

---

## Common Pitfalls in Customer Engagements

| Pitfall | Correction |
|---------|-----------|
| "S3 AP is like a separate bucket service" | S3 AP is a lens on a FlexVol. The volume is the data. S3 AP provides S3 API access to that volume. |
| "SnapMirror will copy the S3 AP configuration" | No. S3 AP is AWS-layer. Data replicates; S3 AP must be recreated at destination. |
| "We'll use SVM-DR for everything" | Not possible with S3 NAS bucket. Use volume-level + manual SVM config. |
| "FlexCache write-back handles everything" | Write-back is powerful but needs file-set separation when combined with S3 AP Origin writes. |
| "ANF is a valid SnapMirror destination" | Not currently. Route to CVO on Azure. GCNV works via External Replication. |
| "SnapMirror Sync for zero RPO" | Not supported for S3 NAS bucket volumes. Minimum RPO = SnapMirror schedule interval. |

---

## Collateral References

| Document | Location | Audience |
|----------|----------|----------|
| Full Research (41 Findings) | `docs/ja/research.md` / `docs/en/research.md` | Technical deep-dive |
| Finding Classification | `docs/finding-classification-routing.md` | Routing decisions |
| Feature Request: SM-004 | `feature-requests/aws-fsx-pm/SM-004-svm-dr-s3-nas-bucket.md` | AWS FSx PM |
| Feature Request: XC-007 | `feature-requests/netapp-bu/XC-007-anf-external-cluster-peering.md` | NetApp ANF team |
| Documentation Request: FC-004 | `feature-requests/netapp-bu/FC-004-writeback-xld-s3ap-documentation.md` | NetApp Docs team |
| Validation Scripts | `scripts/validation/` | Reproducible test cases |
| Failover Runbook | `docs/ja/04-s3ap-snapmirror-failover.md` | Operations teams |
