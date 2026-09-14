> 🌐 Language: [日本語](../../README.md) | **English**

# S3 AP + SnapMirror + FlexCache Multi-Cloud Data Distribution

> Feasibility research and validation for distributing data collected via FSx for ONTAP S3 Access Points to multi-cloud destinations using SnapMirror/FlexCache, with NFS/SMB authenticated access at destinations.

## Overview

This project investigates and validates the use of Amazon FSx for NetApp ONTAP S3 Access Points (FSx for ONTAP S3 AP) to collect data via S3 API and distribute it using SnapMirror and FlexCache to:

- FSx for ONTAP (same/cross-region)
- On-premises ONTAP
- Cloud Volumes ONTAP on GCP / Azure
- Google Cloud NetApp Volumes (GCNV)

Destinations provide secure file-level authenticated access via NFS/SMB protocols.

### FlexCache vs SnapMirror — Choosing the right tool

- **FlexCache**: Remote read acceleration. Places a cache of origin data locally, providing NFS/SMB reads at local speed. Storage-efficient (only accessed data is cached).
- **SnapMirror**: DR (Disaster Recovery) / data migration. Creates a full copy at the destination for failover capability. RPO 5 minutes minimum.

## Status

| Phase | Status | Description |
|:-----:|:------:|-------------|
| 1. Research | ✅ Complete | 41 findings (32 supported, 3 partial, 2+4 caveats, 1 undocumented, 2 unsupported) |
| 2. Documentation | ✅ Complete | Research Document (JA/EN), Validation Plan, Version Matrix |
| 3. Validation | ✅ Complete | TC-01–TC-05 (intra-cluster) ALL PASS. Cross-region E2E validated (2026-07-22) |
| 4. Communication | ✅ Complete | Feature Requests (3), Stakeholder Briefs (4), Classification Matrix |

## Key Findings

| Topic | Status | Notes |
|-------|:------:|-------|
| S3 AP volume as SnapMirror Async source | ✅ Validated | S3 NAS bucket mechanism enables volume-level replication |
| S3 AP re-attach after SnapMirror failover | ✅ Validated | break → junction path → ~60s → create S3 AP. Cross-region RTO ~3 min |
| SVM-DR with S3 AP | ❌ Unsupported | Volume-level SnapMirror only. Destination SVM config is manual |
| FSx for ONTAP → ANF (SnapMirror) | ❌ Unsupported | ANF has no external Cluster Peering. Use CVO on Azure instead |
| S3 AP volume as FlexCache Origin | ✅ Validated | Confirmed on ONTAP 9.17.1 (intra-cluster + cross-region). [Evidence](#flexcache-origin-validation-evidence) |
| S3 AP on FlexCache Cache Volume | 🔒 Version-gated | Supported from ONTAP 9.18.1. Not available on current FSx for ONTAP (9.17.1). [FC-002 details](#fc-002-s3-ap-on-flexcache-cache-volume) |
| FlexCache write-back + S3 AP | ⚠️ Caveats | Works, but S3 AP Origin write revokes Cache XLD (data loss risk on same file) |
| Cross-cloud encryption | ✅ Confirmed | Cluster Peering Encryption (TLS 1.2) enabled by default |
| SnapMirror data integrity | ✅ Confirmed | WAFL atomicity + crash-consistent Snapshot protects all paths |

Legend: ✅ Confirmed/Validated | ❌ Unsupported | ⚠️ Works with caveats

## Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/Yoshiki0705/fsxn-lakehouse-integrations.git
cd fsxn-lakehouse-integrations/integrations/snapmirror-flexcache-multicloud

# 2. Copy and edit parameters
cp scripts/validation/cross-region-params.env.example scripts/validation/cross-region-params.env
# Edit: FS_ID_A, VPC_ID_A, SECRET_ARN_A, SVM_NAME_A, REGION_B, FSX_PASSWORD_B

# 3. Deploy cross-region infrastructure (VPC B + Peering + FSx B)
./scripts/validation/cross-region-deploy.sh deploy    # ~50 min (includes FSx creation)

# 4. Run cross-region FlexCache + SnapMirror test
./scripts/validation/cross-region-test.sh             # ~15 min

# 5. Safe teardown (follows SM-VAL-011 order)
./scripts/validation/cross-region-teardown.sh         # ~35 min
```

> ⚠️ **Prerequisites**: `sshpass` must be installed (`brew install sshpass` or `apt install sshpass`). The teardown script uses SSH to execute `vserver peer delete` and `snapmirror release` — operations that require CLI access for reliable two-phase cleanup.

## Demo Guides

> ⏱️ Estimated times assume FSx for ONTAP is already deployed. Add ~30 minutes for initial creation.

### FlexCache Patterns

| # | Guide | Pattern | Network | Time |
|:-:|-------|---------|:-------:|:----:|
| 00 | [Prerequisites](demo-guide-00-prerequisites.md) | — | — | — |
| 01 | [FlexCache Same Region](demo-guide-01-flexcache-same-region.md) | FSx → FSx (same region) | VPC | ~45min |
| 02 | [FlexCache Cross-Region](demo-guide-02-flexcache-cross-region.md) | FSx → FSx (cross-region) | VPC Peering | ~60min |
| 03 | [FlexCache On-Premises](demo-guide-03-flexcache-on-premises.md) | FSx → On-prem ONTAP | DX / VPN | ~90min |
| 04 | [FlexCache CVO on GCP](demo-guide-04-flexcache-cvo-gcp.md) | FSx → CVO on GCP | HA VPN | ~120min |
| 05 | [FlexCache CVO on Azure](demo-guide-05-flexcache-cvo-azure.md) | FSx → CVO on Azure | Azure VPN GW | ~120min |
| 06 | [FlexCache GCNV](demo-guide-06-flexcache-gcnv.md) | FSx → GCNV (Cache only) | HA VPN | ~90min |

### SnapMirror Patterns

| # | Guide | Pattern | Network | Time |
|:-:|-------|---------|:-------:|:----:|
| 07 | [SnapMirror Cross-Region](demo-guide-07-snapmirror-cross-region.md) | FSx → FSx (DR + S3 AP re-attach) | VPC Peering | ~60min |
| 08 | [SnapMirror On-Premises](demo-guide-08-snapmirror-on-premises.md) | FSx → On-prem ONTAP | DX / VPN | ~60min |
| 09 | [SnapMirror CVO on GCP](demo-guide-09-snapmirror-cvo-gcp.md) | FSx → CVO on GCP | HA VPN | ~120min |
| 10 | [SnapMirror CVO on Azure](demo-guide-10-snapmirror-cvo-azure.md) | FSx → CVO on Azure | Azure VPN GW | ~120min |
| 11 | [SnapMirror GCNV](demo-guide-11-snapmirror-gcnv.md) | FSx → GCNV (External Replication) | HA VPN | ~90min |

### Path Selection Guide

```
Which pattern should you use?

├─ Destination is within AWS
│   ├─ Same region → Guide 01 (FlexCache) or Guide 07 (SnapMirror DR)
│   └─ Cross-region → Guide 02 (FlexCache) or Guide 07 (SnapMirror DR)
│
├─ Destination is on-premises
│   ├─ Read acceleration → Guide 03 (FlexCache, RTT < 200ms recommended)
│   └─ DR / data migration → Guide 08 (SnapMirror)
│
├─ Destination is GCP
│   ├─ Full ONTAP features needed → Guide 04 (FlexCache CVO) or Guide 09 (SnapMirror CVO)
│   ├─ Managed, simple setup → Guide 06 (FlexCache GCNV, read-only)
│   └─ Managed DR → Guide 11 (SnapMirror GCNV External Replication)
│
└─ Destination is Azure
    ├─ CVO available → Guide 05 (FlexCache CVO) or Guide 10 (SnapMirror CVO)
    └─ Want to use ANF → ❌ Direct SnapMirror unsupported (XC-007). Use CVO instead.
```

## Directory Structure

```
integrations/snapmirror-flexcache-multicloud/
├── README.md                           # Japanese README
├── docs/en/README.md                   # This file (English)
├── template.yaml                       # CloudFormation: inter-cluster validation stack
├── docs/
│   ├── ja/                             # Japanese documentation
│   │   ├── research.md                 # Research document (41 findings, ~2400 lines)
│   │   ├── validation-plan.md          # Validation plan (8 test cases, ~1400 lines)
│   │   └── demo-guide-00–11.md         # 12 demo guides
│   ├── en/                             # English documentation
│   │   ├── README.md                   # This file
│   │   ├── research.md                 # Research document (~730 lines)
│   │   └── demo-guide-00–11.md         # 12 demo guides
│   └── finding-classification-routing.md  # Phase 4: 4-category classification
├── scripts/validation/                 # Validation scripts (automated deploy/test/teardown)
├── feature-requests/                   # Feature Request templates
└── stakeholder-briefs/                 # Stakeholder communication artifacts
```

## FlexCache Origin Validation Evidence

S3 AP-attached volumes work as FlexCache Origin, validated in two scenarios:

### Intra-cluster (TC-03, 2026-07-21)

| Step | Result | Details |
|------|:------:|---------|
| Create volume with S3 AP attached | ✅ | UNIX security style, 10GB |
| Write test data via S3 API | ✅ | sensor-001.json, sensor-002.json, metrics.csv |
| Create FlexCache (Origin = S3 AP volume) | ✅ | 60GB FlexGroup, `use_tiered_aggregate: true` |
| NFS mount Cache Volume + read data | ✅ | All files readable, content matches |
| S3 AP → Origin write → Cache propagation | ✅ | ~30s (TTL) for Cache to reflect new data |

**Environment**: FSx for ONTAP Single-AZ / ONTAP 9.17.1P7D1 / ap-northeast-1
**Evidence**: `.private/evidence/s3ap-multicloud/tc03-*.json` (16 files)
**Summary**: `.private/evidence/s3ap-multicloud/tc03-tc05-results-summary.md`

### Cross-region (2026-07-22)

| Step | Result | Details |
|------|:------:|---------|
| VPC Peering (ap-northeast-1 ↔ us-west-2) | ✅ | Established |
| Cluster Peering + SVM Peering | ✅ | `available` / `peered` |
| Create FlexCache (Region A Origin → Region B Cache) | ✅ | Created successfully |
| Write via NFS in Region A | ✅ | Test files created |
| Read from Cache Volume NFS in Region B | ✅ | **Propagation <3 seconds** (~120ms RTT) |

**Environment**: FSx for ONTAP Single-AZ (ap-northeast-1) → FSx for ONTAP Single-AZ (us-west-2)
**Script**: `scripts/validation/cross-region-test.sh` (Test 6)
**Demo Guide**: [Guide 02: FlexCache Cross-Region](demo-guide-02-flexcache-cross-region.md)

---

## FC-002: S3 AP on FlexCache Cache Volume

| Item | Details |
|------|---------|
| **Classification** | `version_gated` — supported from ONTAP 9.18.1 |
| **Current FSx for ONTAP (9.17.1)** | ❌ Not available |
| **Future FSx for ONTAP (9.18.1+)** | ⚠️ Unreleased — cannot be verified |

### What this enables

From ONTAP 9.18.1, FlexCache Cache Volumes can have an independent S3 AP attached:

```
Origin Volume (Region A)
  ↓ FlexCache
Cache Volume (Region B)
  ↓ S3 AP attached
S3 API access (directly from Region B)
```

Cache Volume access is NFS/SMB only: the FSx API refuses attachment outright with `the volume is a FlexCache`, independently of ONTAP version. For S3 API access to remote data, replicate with SnapMirror instead and serve the destination — **no break required**, see [§3.2 of the design considerations](../../../../docs/en/s3ap-flexcache-snapmirror-considerations.md#32-s3-ap-attachment-at-the-destination).

### Source

NetApp official documentation: [Supported and unsupported features for FlexCache volumes](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)

> ONTAP S3 NAS bucket: Cache — Supported beginning with ONTAP 9.18.1

### Current workarounds

| Goal | Pattern | Guide |
|------|---------|-------|
| S3 API read access to remote data | SnapMirror, then mount the destination through ONTAP and attach an S3 AP to it — no break ([§3.2](../../../../docs/en/s3ap-flexcache-snapmirror-considerations.md#32-s3-ap-attachment-at-the-destination)) | — |
| S3 API **write** access to a remote copy | SnapMirror, then clone the destination Snapshot and attach to the clone | — |
| Failover to the destination | break → mount → attach | [Guide 07](demo-guide-07-snapmirror-cross-region.md) |
| Remote read acceleration (NFS/SMB) | FlexCache (works today) | [Guide 01](demo-guide-01-flexcache-same-region.md)–[06](demo-guide-06-flexcache-gcnv.md) |
| S3 API access to Origin data | Use S3 AP on Origin Volume directly | Works today |

### Full details

Research document: [FC-002 in research.md](research.md)

---

## Related

- [S3 AP Design Considerations (directory layout, performance, PoC checklist)](../../../../docs/en/s3ap-design-considerations.md)
- [FlexCache / SnapMirror Additional Considerations](../../../../docs/en/s3ap-flexcache-snapmirror-considerations.md)
- [FSx for ONTAP S3 AP Networking](../../../../docs/en/fsx-ontap-s3ap-networking.md)
- [Research Document (EN)](research.md)
- [Spec Definition](../../../../.kiro/specs/s3ap-snapmirror-flexcache-multicloud/)
