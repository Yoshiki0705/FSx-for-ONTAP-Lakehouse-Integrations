# Stakeholder Brief: AWS FSx for ONTAP Product Management

> **Audience**: AWS FSx PM Team
> **Classification**: Shareable with AWS internal
> **Date**: 2026-07-21
> **From**: AWS Community Builder (Storage/Data Analytics)

---

## Purpose

This brief summarizes validation findings from a systematic feasibility study of FSx for ONTAP S3 Access Points combined with SnapMirror and FlexCache for multi-cloud data distribution. The study was conducted on ONTAP 9.17.1P7D1 (2nd Generation FSx for ONTAP) and includes 41 findings across 7 categories.

The purpose is to:
1. Confirm what works well (feedback for product positioning)
2. Identify one product enhancement request (SM-004)
3. Provide architecture patterns validated for customer guidance

---

## Executive Summary

**Overall assessment**: FSx for ONTAP S3 AP + SnapMirror/FlexCache multi-cloud distribution is architecturally feasible and validated. The S3 NAS bucket design (S3 AP is a lens on a FlexVol) means standard ONTAP data protection works as expected.

| Classification | Count | Interpretation |
|:---:|:---:|---|
| Works as expected | 32 | Solid product foundation |
| Works with caveats | 5 | Operational guidance needed (documented) |
| Feature request | 2 | Product gap with workarounds |
| Blocked | 2 | Architectural constraint (SM-004 is the primary item) |

---

## What Works Well (Product Strengths)

These findings validate current product positioning:

1. **S3 AP volume as SnapMirror source** — "S3 ingestion + SnapMirror DR" is a clean story
2. **S3 AP re-attach after failover** — ~60s FSx API lag is manageable with polling
3. **Cross-region and cross-cloud SnapMirror** — All 6 tested paths work (FSx-to-FSx, on-prem, CVO GCP/Azure, GCNV)
4. **FlexCache with S3 AP origin** — Read acceleration at remote sites validated
5. **IAM policy independence** — S3 AP IAM is AWS-layer only; ONTAP replication is orthogonal
6. **Encryption defaults** — Cluster Peering Encryption (TLS 1.2) is enabled by default

---

## Feature Request: SM-004 — SVM-DR + S3 NAS Bucket

**Priority**: High (most-impactful gap for multi-cloud S3 AP adoption)

**Summary**: SVM-DR (`-identity-preserve true`) is blocked when the source SVM contains an S3 NAS bucket (object-store-server). This forces volume-level SnapMirror only, requiring manual SVM protocol configuration at the destination.

**Customer impact**:
- +15-30 min to failover RTO (manual SVM config)
- Configuration drift risk between source/destination SVMs
- More complex runbooks vs. standard SVM-DR procedure

**Workaround**: Volume-level SnapMirror + pre-configured destination SVM (functional, documented in our runbook)

**Detailed request**: See `feature-requests/aws-fsx-pm/SM-004-svm-dr-s3-nas-bucket.md`

---

## FSx API Observation: VolumeType Lag (SM-005)

During validation, we observed that `describe-volumes` returns `VolumeType: DP` for approximately 60 seconds after a SnapMirror break operation (over 10 minutes cross-region), even though ONTAP-level status is already `RW`.

**Correction, 2026-09-13:** an earlier version of this brief said attachment requires `VolumeType: RW`. It does not. The gate is the **junction path**, which is why attachment succeeds while the FSx API still reports `DP`. Two consequences worth AWS's attention:

1. **A DP volume can carry an access point, but only if ONTAP set the junction path.** `CreateVolume` rejects `JunctionPath` for a DP volume by name, and `UpdateVolume` **accepts it and silently discards it** — HTTP 200 with the full Volume object, no `AdministrativeActions` entry, no failure message. A loud rejection would be better than a silent one.
2. **Junction-path propagation to the FSx control plane took 2298 s** for an ONTAP-mounted DP volume and **1011 s** for an ONTAP-created FlexClone, against ~30 min previously recorded for ONTAP-created volumes. Attachment fails with `the volume is not mounted` until it lands. This is the dominant cost of standing up a read path on replicated data.

**Impact**: automation must poll `DescribeVolumes` for a non-null `JunctionPath` rather than for `VolumeType: RW`, and budget tens of minutes. Evidence: [S3AP-DP-ATTACH-002](../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml).

---

## Validated Architecture Patterns (Ready for Guidance)

| Pattern | Components | Status |
|---------|-----------|:------:|
| S3 AP ingestion + cross-region DR | SnapMirror Async + S3 AP re-attach | Validated |
| S3 AP ingestion + FlexCache read acceleration | FlexCache read-only Cache | Validated |
| S3 AP + hybrid cloud (on-premises NFS access) | SnapMirror + DX/VPN | Validated (doc-based) |
| S3 AP + GCP distribution | GCNV External Replication | Validated (doc-based) |

---

## Non-Actionable Items (For Awareness)

- **ANF SnapMirror (XC-007)**: Routed to NetApp BU (ANF does not expose Cluster Peering — an Azure/NetApp decision)
- **FlexCache write-back + S3 AP XLD (FC-004)**: Routed to NetApp docs team (documentation enhancement, not a bug)
- **Conditional Writes 501 (CW-001)**: Known FSx for ONTAP S3 AP limitation; no SnapMirror integrity impact

---

## Next Steps (From Our Side)

1. Publish community-facing architecture guidance (dev.to article)
2. Create AWS re:Post Knowledge Center-style FAQ on "S3 AP + SnapMirror failover procedure"
3. Monitor ONTAP release notes for SM-004 (SVM-DR + S3) resolution
