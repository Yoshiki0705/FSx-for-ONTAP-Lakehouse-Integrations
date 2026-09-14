> 🌐 Language: [日本語](../ja/research.md) | **English**

# S3 AP + SnapMirror + FlexCache Multi-Cloud Data Distribution — Research Findings

> **Status**: Phase 3 Validation Complete | Phase 4 Communication Complete | Cross-Region SnapMirror Validated (2026-07-22)
> **Last Updated**: 2026-07-22
> **ONTAP Version Tested**: 9.17.1P7D1
> **Scope**: Multi-cloud data distribution of data collected via FSx for ONTAP S3 Access Points using SnapMirror/FlexCache
> **JA Primary**: Full research detail in `docs/ja/research.md` — this EN version provides equivalent technical depth for architecture-impacting findings

---

## Executive Summary

This research systematically evaluates the feasibility of distributing data collected via FSx for ONTAP S3 AP (S3 Access Points) to multi-cloud environments using SnapMirror and FlexCache, with NFS/SMB authenticated access at destinations.

### Findings Summary

| Classification | Count | Description |
|---------------|:-----:|-------------|
| **supported** | 32 | Confirmed via official documentation or Phase 3 validation |
| **partially_supported** | 3 | Supported under specific conditions or platform-dependent |
| **works_with_caveats** | 2+4 | Validated as working but with important operational constraints (original 2 + 4 cross-region validation findings) |
| **version_gated** | 1 | Supported from ONTAP 9.18.1; not supported on tested version (9.17.1) |
| **undocumented** | 1 | Not documented; requires hands-on validation to confirm |
| **unsupported** | 2 | Explicitly confirmed as unsupported |
| **Total** | **41** | |

### Key Conclusions

FSx for ONTAP S3 AP is based on ONTAP's "S3 NAS bucket (S3 multiprotocol)" mechanism — the volume itself remains a standard FlexVol/FlexGroup. This design enables S3 AP-attached volumes to be protected via **SnapMirror Asynchronous (Volume-level)**, making multi-cloud data distribution architecturally feasible. SnapMirror Synchronous and SVM-DR are not supported for configurations containing S3 NAS buckets.

### Top 3 Architecture-Impacting Findings

1. **SVM-DR unsupported (SM-004)**: Volume-level SnapMirror is the only option; destination SVM protocol configuration must be manually recreated
2. **ANF SnapMirror unsupported (XC-007)**: Azure data distribution requires CVO on Azure as intermediary
3. **S3 AP metadata not transferred via SnapMirror (SM-002)**: New S3 AP attachment required at destination; IAM policies must be separately configured

---

## Prerequisites & Constraints Summary

### Key Constraints (What doesn't work)

| Constraint | Finding ID | Impact |
|-----------|:----------:|--------|
| SVM-DR unsupported with S3 NAS bucket SVMs | SM-004 | Volume-level SnapMirror only. No automatic SVM config replication |
| ANF SnapMirror unsupported | XC-007 | Azure delivery requires CVO on Azure |
| SnapMirror Synchronous unsupported for S3 NAS bucket | SM-001 | RPO=0 not achievable. Async only (minimum 5-min intervals) |
| GCNV cannot be FlexCache Origin (Cache only) | FCXC-005 | Read distribution from GCNV requires SnapMirror |
| GCNV FlexCache does not support NFSv4 | FCXC-005 | NFSv3 access only to GCNV Cache Volumes |
| FlexCache write-back not recommended for RTT > 200ms | FCXC-006 | Write-around mode recommended for cross-cloud |

### Key Prerequisites (What you need)

| Prerequisite | Applicable Paths | Details |
|-------------|-----------------|---------|
| Intercluster LIF | All SnapMirror / FlexCache paths | Auto-configured on FSx for ONTAP; manual on on-premises/CVO |
| Cluster Peering (TLS 1.2 encryption) | All cross-cluster configs | Default enabled ONTAP 9.6+ |
| VPN / Direct Connect / Interconnect | On-premises / CVO / GCNV destinations | TCP 11104, 11105 + ICMP reachability required |
| Active Directory (for SMB access) | Destination SVM | AD join required. Same domain or trust relationship recommended |
| ONTAP 9.15.1+ (both Origin/Cache) | FlexCache write-back mode | 9.17.1P1+ recommended |
| ONTAP 9.12.1+ (Origin) | S3 NAS bucket + FlexCache | Minimum for S3 NAS bucket as FlexCache Origin |

### Supported Configuration Quick Reference

| Source | Destination | SnapMirror | FlexCache | Notes |
|--------|------------|:----------:|:---------:|-------|
| FSx for ONTAP | FSx for ONTAP (same region) | Yes | Yes | Simplest configuration |
| FSx for ONTAP | FSx for ONTAP (cross-region) | Yes | Yes | VPC Peering / Transit Gateway |
| FSx for ONTAP | On-premises ONTAP | Yes | Yes | Direct Connect / VPN |
| FSx for ONTAP | CVO on GCP | Yes | Yes | Cross-cloud VPN |
| FSx for ONTAP | CVO on Azure | Yes | Yes | Cross-cloud VPN |
| FSx for ONTAP | GCNV | Yes | Yes (Cache only) | External Replication / FlexCache Cache |
| FSx for ONTAP | ANF | No | No | Unsupported. Use CVO on Azure |

### S3 NAS Bucket Compatibility with FlexCache / SnapMirror

| Configuration | Supported | Min ONTAP | Official Source |
|---------------|:---------:|:---------:|----------------|
| S3 NAS bucket volume as **SnapMirror Async source** | ✅ | 9.12.1 | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) |
| S3 NAS bucket volume as **SnapMirror Synchronous source** | ❌ | — | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) |
| S3 NAS bucket volume in **SVM-DR** | ❌ | — | [S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html), [KB: SVM DR + S3](https://kb.netapp.com/onprem/ontap/dp/SnapMirror/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F) |
| S3 NAS bucket on **FlexCache Origin** volume | ✅ | 9.12.1 | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) |
| S3 NAS bucket on **FlexCache Cache** volume | ⚠️ ONTAP ✅ / FSx AP ❌ | **9.18.1** | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html), [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html). ONTAP native S3 NAS bucket supported on 9.18.1, but FSx for ONTAP S3 AP explicitly blocks FlexCache (validated 2026-07-24) |
| FlexCache Cache S3 NAS bucket + **write-back mode** | ❌ | — | [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html) (write-around required) |
| FlexCache Cache S3 — Origin/Cache **both must be 9.18.1+** | Required | 9.18.1 | [FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html) |
| FlexCache Origin with **SnapMirror Async relationship** | ✅ | 9.5+ | [FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) |

---

## S3 AP + SnapMirror Interaction

### Architecture Premise

FSx for ONTAP S3 AP is based on ONTAP's **S3 multiprotocol (S3 NAS bucket)** mechanism. This is architecturally distinct from ONTAP's native S3 object store server (`vserver object-store-server`). S3 AP provides S3 protocol access to existing NAS volumes via an AWS-managed layer — the volume itself remains a standard FlexVol/FlexGroup.

This distinction is critical for SnapMirror compatibility.

---

### SM-001: S3 AP-Attached Volume as SnapMirror Source

| Item | Details |
|------|---------|
| **Finding ID** | SM-001 |
| **Classification** | `supported` (Async only) |
| **Disclosure** | publicly verifiable |

**Finding:**

NetApp ONTAP documentation states: "S3 NAS 'buckets' are simply mappings of NAS data for S3 clients, they are not standard S3 buckets. Therefore, there is no need to protect S3 NAS buckets using NetApp SnapMirror S3 functionality. Instead, you can protect volumes containing S3 NAS buckets using **SnapMirror asynchronous volume replication**."

S3 AP-attached volumes can serve as SnapMirror Async sources because the underlying volume is a standard NAS volume.

**Constraints:**
- SnapMirror **Synchronous** is NOT supported for volumes with S3 NAS buckets
- SnapMirror **Asynchronous** (schedule-based) is the only supported mode

**Evidence:**
- [NetApp Docs: ONTAP S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [AWS Docs: Replicating data using SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)

---

### SM-002: S3 AP Metadata Preservation After SnapMirror Transfer

| Item | Details |
|------|---------|
| **Finding ID** | SM-002 |
| **Classification** | `supported (validated)` |
| **Disclosure** | validation evidence |

**Finding:**

S3 AP metadata exists on two layers:
1. **AWS layer (S3 AP itself)**: AP attachment, IAM policies, VPC config — AWS-managed resources not stored in ONTAP volume data
2. **ONTAP layer (`s3_unix` name-mapping)**: Auto-created by FSx on the SVM when S3 AP is attached (pattern: `amazon-fsx-<RANDOM>` → specified UNIX user)

**Phase 3 Validation (TC-01/TC-02):**
- S3 AP attachment is NOT transferred via SnapMirror (expected — it's an AWS-managed resource)
- `s3_unix` name-mapping is an SVM-level config, not transferred by volume-level SnapMirror
- Creating a new S3 AP on destination volume causes FSx to auto-create the corresponding `s3_unix` name-mapping — **no manual configuration required**
- Data (files, directories, UNIX permissions, ACLs) transfers correctly via SnapMirror

**Conclusion:** S3 AP metadata not transferring is "by design," not a limitation. Attach a new S3 AP at the destination and it works.

---

### SM-003: Object Store Server Exclusion Constraint on Destination SVM

| Item | Details |
|------|---------|
| **Finding ID** | SM-003 |
| **Classification** | `supported` (no impact) |
| **Disclosure** | publicly verifiable |

**Finding:**

The Object Store Server exclusion constraint ("ONTAP native S3 object-store-server and FSx for ONTAP S3 AP cannot coexist on the same SVM") does NOT propagate to the destination SVM via volume-level SnapMirror. Source and destination are independent SVMs. The destination SVM can have a new S3 AP attached as long as it does not have `vserver object-store-server` configured independently.

---

### SM-004: SVM-DR Compatibility with S3 Configurations

| Item | Details |
|------|---------|
| **Finding ID** | SM-004 |
| **Classification** | `unsupported` |
| **Disclosure** | publicly verifiable |

**Finding:**

SVM-DR is NOT supported for SVMs containing S3 NAS buckets.

**Evidence 1:** NetApp S3 multiprotocol documentation: "SnapMirror synchronous and **SVM disaster recovery are not supported**."

**Evidence 2:** NetApp KB: Error: "A Vserver DR relationship between Vserver [Source SVM] and Vserver [Destination/DR SVM] is not supported because Vserver [Source SVM] contains either an object store server, object store policy, object store user or object store bucket."

**What SVM-DR normally preserves (but cannot be used here):**
- SMB server settings (CIFS server name, AD domain)
- Name mapping and group mapping
- NFS export policies and rules
- DNS, LDAP, Kerberos settings
- UNIX user and UNIX group
- Audit information

Since SVM-DR is blocked, volume-level SnapMirror is the only option, and all above SVM configurations must be independently maintained at the destination.

**Evidence:**
- [NetApp Docs: ONTAP S3 multiprotocol](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: Is SVM DR of S3 buckets supported?](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [NetApp Docs: SVM replication concept](https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html)

---

### SM-005: S3 AP Re-Attachment After SnapMirror Failover

| Item | Details |
|------|---------|
| **Finding ID** | SM-005 |
| **Classification** | `supported (validated)` |
| **Disclosure** | validation evidence |

**Phase 3 Validated Procedure:**

1. Break SnapMirror relationship
2. Set junction path on destination volume (may be unset immediately after break)
3. Wait ~60s for FSx API `VolumeType` to reflect `RW` (ONTAP-level is RW immediately, but FSx API has propagation lag)
4. Create new S3 AP on destination volume:
```bash
aws fsx create-and-attach-s3-access-point \
  --name <ap-name> \
  --type ONTAP \
  --ontap-configuration \
    'VolumeId=<dest-vol-id>,FileSystemIdentity={Type=UNIX,UnixUser={Name=<unix-user>}}'
```

**Important considerations:**
- S3 AP does NOT "migrate" — a new one must be created at the destination
- New AP gets a new ARN and alias (different from source)
- Client applications must update to use the new S3 endpoint
- Cross-region: S3 AP can only be attached to volumes in the same region
- **Estimated RTO**: ~2 minutes (SnapMirror break ~instant + FSx API sync ~60s + S3 AP creation ~30s + DNS propagation ~30s)

**Additional finding (SM-VAL-004/007):** FSx API `describe-volumes` shows `VolumeType: DP` for ~60s after ONTAP break. S3 AP attachment requires `RW`. Automation scripts need a polling loop.

---

### SM-006: S3 AP IAM Policy AWS-Layer Independence

| Item | Details |
|------|---------|
| **Finding ID** | SM-006 |
| **Classification** | `supported` |
| **Disclosure** | publicly verifiable |

**Finding:** S3 AP IAM policies are AWS-layer constructs completely independent of ONTAP replication. IAM identity policies, AP resource policies, and VPC configurations exist in the AWS control plane and are not affected by SnapMirror operations. Destination S3 AP requires its own IAM configuration.

---

### SM-007: ONTAP S3 + SnapMirror Compatibility Overview

| Item | Details |
|------|---------|
| **Finding ID** | SM-007 |
| **Classification** | `supported` (Async Volume-level only) |
| **Disclosure** | publicly verifiable |

**Summary of supported/unsupported SnapMirror modes for S3 NAS bucket volumes:**

| SnapMirror Mode | Supported? | Notes |
|----------------|:----------:|-------|
| Asynchronous (Volume-level) | Yes | Standard data protection path |
| Synchronous | No | Explicitly listed as unsupported |
| SVM-DR | No | Blocked if SVM contains object-store-server |
| SnapMirror Cloud | No | Not supported for S3 NAS bucket |
| SnapMirror S3 (native S3) | N/A | Different mechanism; not applicable to S3 AP |

---

## S3 AP + FlexCache

### FC-001: S3 AP-Attached Volume as FlexCache Origin

| Item | Details |
|------|---------|
| **Finding ID** | FC-001 |
| **Classification** | `supported (validated)` |
| **Disclosure** | validation evidence |

**Finding:** S3 AP-attached volumes (S3 NAS bucket mechanism) can serve as FlexCache Origin Volumes. Validated on ONTAP 9.17.1 (intra-cluster). Origin requires ONTAP 9.12.1+ for S3 NAS bucket support.

**Phase 3 Validation (TC-03):** Cache Volume creation succeeded. NFS read from Cache returned data written via S3 AP to Origin. Data integrity confirmed with checksum comparison.

---

### FC-002: Independent S3 AP Attachment on Cache Volume

| Item | Details |
|------|---------|
| **Finding ID** | FC-002 |
| **Classification** | `not_supported_on_fsx` — ONTAP 9.18.1 supports S3 NAS bucket on Cache, but FSx for ONTAP S3 Access Points explicitly blocks attachment to FlexCache volumes |
| **Disclosure** | validation evidence (2026-07-24) |

**Finding:** NetApp ONTAP documentation states that FlexCache Cache Volumes support S3 NAS bucket starting from ONTAP 9.18.1. However, FSx for ONTAP S3 Access Points — which operate at the AWS managed layer — **explicitly reject** attachment to FlexCache volumes regardless of ONTAP version.

**Validation (2026-07-24):**

| Step | Result | Details |
|------|:------:|---------|
| FSx for ONTAP deployment (us-west-2) | ✅ | SINGLE_AZ_2, ONTAP 9.18.1P3D1 |
| FlexGroup Origin volume creation (FSx API) | ✅ | 800 GiB, VolumeStyle: FLEXGROUP |
| S3 AP attachment to FlexGroup Origin | ✅ | AVAILABLE, S3 PutObject + ListObjectsV2 confirmed |
| FlexCache Cache volume creation (ONTAP REST API) | ✅ | 400 GiB, write-around mode |
| FlexCache → FSx API propagation | ✅ | ~30 min, fsvol-* ID obtained |
| **S3 AP attachment to FlexCache Cache volume** | **❌ Blocked** | Error: `Amazon FSx is unable to attach S3access point because the volume is a FlexCache.` |

**Interpretation:** FSx for ONTAP S3 Access Points and ONTAP native S3 NAS buckets are **different mechanisms** at different layers:

- **ONTAP S3 NAS bucket** (`-is-s3-enabled`, `vserver object-store-server`): ONTAP-native feature. Cache Volume support added in 9.18.1.
- **FSx for ONTAP S3 Access Points** (`aws fsx create-and-attach-s3-access-point`): AWS managed-layer feature. FlexCache volume attachment is explicitly blocked by the FSx API.

**Implication for FSx for ONTAP users:**
- S3 AP on FlexCache Cache Volume is **not available** on FSx for ONTAP as of 2026-07-24
- This may require FSx service-side enablement in a future update (separate from ONTAP version)
- NFS/SMB access to FlexCache Cache Volumes remains the primary remote read acceleration path
- For S3 API **read** access at a SnapMirror destination, no break is needed: mount the DP volume through ONTAP and attach (SM-VAL-013). Break is only for taking over production service

**Evidence:**
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html) — "ONTAP S3 NAS bucket: Cache — Supported beginning with ONTAP 9.18.1"
- [NetApp Docs: FlexCache duality FAQ](https://docs.netapp.com/us-en/ontap/flexcache/flexcache-duality-faq.html) — write-around required, both clusters 9.18.1+
- FSx for ONTAP validation error (2026-07-24, ONTAP 9.18.1P3D1): `Amazon FSx is unable to attach S3access point because the volume is a FlexCache.`
- **Re-confirmed 2026-09-13 on ONTAP 9.18.1P5**, ap-northeast-1, against an already-mounted Cache volume that the FSx API reported as type RW with a junction path — so the documented attachment gate was satisfied and the refusal is by volume kind. Error verbatim identical. Nothing was created by the probe. [Evidence](../../../../verification-pack/ontap-features/evidence/2026-09-13/volume-recovery-queue-and-fc002.yaml), Finding B. This is now measured on two ONTAP 9.18.1 patch levels in two regions, which closes the question of whether 9.18.1 changes it: it does not.

---

### FC-003: FlexCache Version Compatibility Requirements

| Item | Details |
|------|---------|
| **Finding ID** | FC-003 |
| **Classification** | `supported` |
| **Disclosure** | publicly verifiable |

**Finding:** Origin and Cache clusters must be within 4 minor ONTAP versions of each other. Example: Cache on 9.14.1 requires Origin on 9.10.1 or later. NFSv4.x access to Cache Volumes requires both Origin and Cache on ONTAP 9.10.1+.

---

### FC-004: FlexCache Write-Back Mode + S3 AP Compatibility

| Item | Details |
|------|---------|
| **Finding ID** | FC-004 |
| **Classification** | `works_with_caveats` |
| **Disclosure** | validation evidence |

**Phase 3 Validation (TC-03/TC-05, ONTAP 9.17.1):**

FlexCache write-back mode combined with S3 AP-attached Origin volumes is functional. However, critical caveats exist:

**Confirmed behavior:**
1. Write-back FlexCache + S3 AP Origin works — Cache Volume local writes function normally
2. S3 AP writes to Origin trigger XLD (Exclusive Lock Delegation) revoke — Cache dirty data for the affected file is discarded (Origin version wins)
3. Concurrent writes to the same file from S3 AP (Origin) and NFS/SMB (Cache) result in Cache data loss

**Mechanism:**
```
S3 AP write to Origin
  → Origin detects conflicting XLD on Cache
  → XLD revoke sent to Cache
  → Cache dirty data flushed (overwritten by Origin version)
  → S3 AP write committed to Origin
  → Cache fetches updated data on next access (after TTL ~30s)
```

**Safe/Unsafe patterns:**

| Scenario | Risk | Recommendation |
|---------|------|----------------|
| S3 AP write (Origin) only, Cache is read-only | Safe | Recommended pattern |
| Cache write (NFS/SMB) only, S3 AP is read-only | Safe | Standard write-back use case |
| S3 AP write + Cache write (different files) | Safe | Per-file XLD protects |
| S3 AP write + Cache write (same file) | **Dangerous** | Cache dirty data lost. Avoid by design |

**Evidence:**
- [NetApp Docs: FlexCache write-back architecture](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html)
- [NetApp Docs: FlexCache write-back guidelines](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-guidelines.html)
- Phase 3: TC-03, TC-05 (PASS)

---

### FC-005: NFS v4 Delegation and Lock Propagation

| Item | Details |
|------|---------|
| **Finding ID** | FC-005 |
| **Classification** | `partially_supported` |
| **Disclosure** | publicly verifiable |

**Finding:**
- NFSv4.0/4.1 access to Cache Volumes: supported since ONTAP 9.10.1
- FlexCache uses its own XLD mechanism (separate from NFSv4 protocol-level delegation)
- Write-back mode disconnected behavior: if WAN cuts out, XLD-holding Cache's files become inaccessible from all locations (consistency guarantee)
- Write-around mode: disconnection allows continued read from Origin

---

### FC-006: Eviction Policy and Cache Hit Ratio Measurement

| Item | Details |
|------|---------|
| **Finding ID** | FC-006 |
| **Classification** | `supported` |
| **Disclosure** | publicly verifiable |

**Eviction policies:**
1. **Space-based**: LRU eviction at 90% Cache Volume usage
2. **mtime-based scrubber**: 5-min cycle, flushes files unchanged for 2+ minutes
3. **RW lock limit**: Recalls lock delegations when per-constituent count exceeds 170

**Measurement:** `GET /api/storage/volumes/{uuid}/statistics` — fields: `client_requested_blocks`, `cache_miss_blocks`. Miss rate = `cache_miss_blocks / client_requested_blocks * 100`.

---

### FC-007: FlexGroup + S3 AP + FlexCache Origin

| Item | Details |
|------|---------|
| **Finding ID** | FC-007 |
| **Classification** | `partially_supported` |
| **Disclosure** | publicly verifiable |

**Finding:** FlexGroup volumes with S3 AP can serve as FlexCache Origin (ONTAP 9.13.1+). However, FlexGroup-backed FlexCache has specific constraints around constituent mapping and write-back mode stability. Recommended for read-heavy workloads; write-back with FlexGroup Origin requires validation.

---

## Cross-Cloud SnapMirror Paths

### XC-001 through XC-006: Supported Paths

| Finding ID | Path | Classification | Min ONTAP (Source) | Min ONTAP (Dest) | Network |
|:---:|------|:---:|:---:|:---:|------|
| XC-001 | FSx for ONTAP → FSx for ONTAP (same region) | `supported` | 9.11.1 | 9.11.1 | VPC internal (auto) |
| XC-002 | FSx for ONTAP → FSx for ONTAP (cross-region) | `supported` | 9.11.1 | 9.11.1 | Cross-region (auto) |
| XC-003 | FSx for ONTAP → On-Premises ONTAP | `supported` | 9.11.1 | IMT reference | DX / VPN |
| XC-004 | FSx for ONTAP → CVO on GCP | `supported` | 9.11.1 | CVO latest | AWS↔GCP VPN |
| XC-005 | FSx for ONTAP → CVO on Azure | `supported` | 9.11.1 | CVO latest | AWS↔Azure VPN |
| XC-006 | FSx for ONTAP → GCNV (External Replication) | `supported` | 9.11.1 (est.) | GCNV managed | AWS↔GCP VPN |

All paths use standard Cluster Peering with TLS 1.2 encryption (default enabled since ONTAP 9.6).

---

### XC-007: FSx for ONTAP → Azure NetApp Files (ANF)

| Item | Details |
|------|---------|
| **Finding ID** | XC-007 |
| **Classification** | `unsupported` |
| **Disclosure** | publicly verifiable |

**Finding:** ANF supports only Cross-Volume Replication (CVR) — an ANF-to-ANF mechanism. External ONTAP systems (including FSx for ONTAP) cannot establish SnapMirror relationships with ANF because ANF does not expose Cluster Peering interfaces.

**Technical reason:** ANF is built on Azure infrastructure and does not currently expose Intercluster LIF endpoints or Cluster Peering passphrase authentication to external systems. Its replication model is limited to ANF-to-ANF (Cross-Volume Replication).

**Alternatives:**
1. FSx for ONTAP → CVO on Azure (SnapMirror) → NFS/SMB from CVO
2. FSx for ONTAP → CVO on Azure (SnapMirror) → ANF (via AzCopy/DataSync for file-level sync)
3. AWS DataSync / rsync for direct file-level sync to ANF

**Context:** GCNV supports External Replication from external ONTAP systems (GA 2024). ANF does not currently offer an equivalent external peering interface. Each managed service has its own architectural decisions regarding external connectivity.

**Evidence:**
- [Microsoft Docs: Understand ANF Replication](https://learn.microsoft.com/en-us/azure/azure-netapp-files/replication)
- [Microsoft Docs: ANF Replication Requirements](https://learn.microsoft.com/en-us/azure/azure-netapp-files/cross-region-replication-requirements-considerations)

---

### XC-008: Encryption and Snapshot Consistency (Cross-Cloud)

| Item | Details |
|------|---------|
| **Finding ID** | XC-008 |
| **Classification** | `supported` |
| **Disclosure** | publicly verifiable |

**Cluster Peering Encryption:** TLS 1.2 AES-256 GCM, default enabled since ONTAP 9.6 for new peer relationships. No performance impact per NetApp KB. All data transferred between clusters is encrypted in transit.

**Encryption at rest (NAE/NVE):** At the storage layer, SnapMirror decrypts data at the source WAFL layer before transfer (since encryption keys are cluster-local), transmits over TLS-encrypted link, and the destination re-encrypts with its own key. Source/destination can independently use NVE, NAE, or plaintext — the at-rest encryption configuration is independent on each side.

**Snapshot + S3 AP write consistency:** ONTAP Snapshots are crash-consistent by default. Each completed S3 API PutObject is atomically committed to WAFL. SnapMirror transfers Snapshot-based content — always file-system consistent.

---

## NFS/SMB Authentication

| Finding ID | Topic | Classification | Key Point |
|:----------:|-------|:--------------:|-----------|
| AUTH-001 | NFS auth on SnapMirror destination | supported | All modes (AUTH_SYS, Kerberos v5/v5i/v5p) available after break |
| AUTH-002 | NFS auth on FlexCache Cache Volume | supported | Same authentication modes as Origin; credential caching at Cache |
| AUTH-003 | SMB auth on SnapMirror destination | supported | Destination SVM must be AD-joined (independent from source AD) |
| AUTH-004 | Volume security style preservation | supported | UNIX/NTFS/MIXED style preserved through SnapMirror transfer |
| AUTH-005 | Cross-domain AD trust & name-mapping | supported | Cross-domain trust or independent AD join at destination |

**Key point for AUTH-003:** After SnapMirror break, the destination SVM must have CIFS service configured and AD-joined BEFORE SMB clients can access data. This is SVM-level configuration not transferred by volume-level SnapMirror (reinforces SM-004 impact).

### Data Sovereignty Note

Cross-region and cross-cloud SnapMirror transfers move data to different geographic locations. For regulated data (GDPR, HIPAA, data residency requirements), verify that replication destinations comply with your organization's data governance policies before configuring SnapMirror relationships. FlexCache (read-only mode) also caches data blocks at remote sites — consider whether cached data residency meets compliance requirements.

---

## FlexCache Cross-Region/Cross-Cloud

| Finding ID | Topic | Classification | Key Detail |
|:----------:|-------|:--------------:|-----------|
| FCXC-001 | FSx for ONTAP inter-region FlexCache | supported (validated) | Same as intra-region; VPC Peering/TGW required. Validated 2026-07-22: ap-northeast-1 → us-west-2, data propagation <3s |
| FCXC-002 | FSx for ONTAP → On-premises (DX/VPN) | supported | Direct Connect or VPN; RTT impacts performance |
| FCXC-003 | FSx for ONTAP → CVO (GCP/Azure) | supported | Cross-cloud VPN; write-around recommended for high RTT |
| FCXC-004 | Intercluster LIF requirements | supported | TCP 11104/11105 + ICMP; auto-configured on FSx for ONTAP |
| FCXC-005 | GCNV/ANF FlexCache support | partially_supported | GCNV: Cache only (not Origin), NFSv3 only. ANF: unsupported |
| FCXC-006 | Network latency impact | supported | Read-heavy: tolerant to high RTT. Write-back: <= 200ms recommended |
| FCXC-007 | FlexCache disconnect mode | supported | Write-back: hung I/O until reconnect. Write-around: Origin reads continue |

### FCXC-005 Detail: GCNV FlexCache Constraints

- GCNV supports FlexCache as **Cache only** (cannot serve as Origin)
- NFSv3 access only to GCNV FlexCache Cache Volumes (NFSv4 not supported on GCNV FlexCache)
- If GCNV is the desired data access point, use SnapMirror (External Replication) rather than FlexCache for NFSv4 requirements

### FCXC-006 Detail: RTT Recommendations

| Mode | Max Recommended RTT | Rationale |
|------|:-------------------:|-----------|
| Read-only (write-around) | No hard limit (200+ ms acceptable) | Only metadata fetches traverse WAN; data cached locally |
| Write-back | <= 200ms | XLD acquisition/revocation latency impacts write performance |
| Cross-cloud typical RTT | 20–100ms (AWS↔GCP/Azure) | Within write-back tolerance for most regions |

---

## Conditional Writes Impact

### CW-001: FSx for ONTAP S3 AP `If-None-Match` Unsupported

| Item | Details |
|------|---------|
| **Finding ID** | CW-001 |
| **Classification** | `supported` (limitation confirmed) |

FSx for ONTAP S3 AP returns `501 Not Implemented` for requests with `If-None-Match` header. This affects Delta Lake, Apache Iceberg, and other table formats that use conditional writes for concurrent commit protection. Workaround: use ONTAP-level locking or application-level coordination.

### CW-002: Conditional Writes and SnapMirror Consistency

| Item | Details |
|------|---------|
| **Finding ID** | CW-002 |
| **Classification** | `supported` (no impact on SnapMirror integrity) |

**Analysis:** The absence of `If-None-Match` does NOT compromise SnapMirror data integrity because:
1. Each S3 API `PutObject` is atomically committed to WAFL
2. ONTAP Snapshots capture crash-consistent state (all committed writes included; in-flight writes excluded)
3. SnapMirror transfers Snapshot content — always consistent
4. Last-writer-wins semantics at the S3 layer do not affect ONTAP-level file system consistency

**Conclusion:** No SnapMirror integrity risk from conditional writes absence.

---

## Cross-Region SnapMirror Validation Findings (2026-07-22)

> Validated: ap-northeast-1 → us-west-2, ONTAP 9.17.1P7D1 both clusters

### SM-VAL-008: FSx API VolumeType:DP Display Lag (Cross-Region)

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-008 |
| **Classification** | `works_with_caveats` |
| **Disclosure** | validation evidence |

**Finding:** After SnapMirror break, FSx API continues to report `OntapVolumeType: DP` for the destination volume for **>10 minutes** in cross-region scenarios (previous same-region testing showed ~60s). However, S3 AP attachment succeeds immediately once junction path is set — the check is at the ONTAP level, not the FSx API level.

**Scope clarification:** This lag is FSx-specific (AWS control-plane synchronization delay). On-premises ONTAP does not have this issue as there is no separate control plane layer. The ONTAP REST API correctly reports `type: rw` immediately after break in both scenarios.

**Impact on automation:**
- Do NOT poll `describe-volumes → OntapVolumeType` as the gate for S3 AP attachment
- Instead: (1) Break SnapMirror, (2) Set junction path via `update-volume`, (3) Wait for junction path to appear in FSx API (~2 min), (4) Attach S3 AP immediately

### SM-VAL-009: DP Volume Must Be Created via FSx API for S3 AP Attachment

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-009 |
| **Classification** | `works_with_caveats` |
| **Disclosure** | validation evidence |

**Finding:** Volumes created exclusively via ONTAP REST API (`POST /api/storage/volumes {type: dp}`) do NOT immediately appear in the FSx API (`describe-volumes`). FSx control plane synchronization takes approximately **30 minutes** for ONTAP-created volumes to become visible. S3 AP attachment requires a FSx volume ID (`fsvol-*`).

**Recommended approach:** Create DP volumes using `aws fsx create-volume --ontap-configuration '{"OntapVolumeType":"DP"}'` for immediate visibility. If ONTAP REST API is used (e.g., for FlexCache which has no FSx API equivalent), wait ~30 minutes for FSx API propagation before attempting S3 AP attachment.

**Workaround for ONTAP-created volumes:** Wait for FSx control plane sync (~30 min), then use the propagated `fsvol-*` ID. Do NOT recreate — the volume will eventually appear.

### SM-VAL-010: Cross-Region S3 AP Re-Attach RTO

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-010 |
| **Classification** | `supported (validated)` |
| **Disclosure** | validation evidence |

**Measured RTO (ap-northeast-1 → us-west-2):**

| Phase | Duration | Notes |
|-------|:--------:|-------|
| SnapMirror break | ~instant | ONTAP REST API PATCH |
| Junction path set + FSx API propagation | ~2 min | `update-volume` + polling |
| S3 AP creation (CREATING → AVAILABLE) | ~30s | `create-and-attach-s3-access-point` |
| First successful S3 API call | ~30s | ListObjectsV2 / GetObject |
| **Total** | **~3 min** | Cross-region. Same-region estimated ~2 min |

**RPO context**: SnapMirror Async replication runs on a schedule (minimum 5-minute intervals for FSx for ONTAP). The RPO is equal to the time since the last successful SnapMirror transfer. In a worst-case scenario, up to 5 minutes of data written to the source after the last transfer could be lost.

**Cross-region data transfer cost note**: SnapMirror transfers between regions incur standard AWS inter-region data transfer charges ($0.01–$0.02/GB depending on regions). Initial baseline transfer of large volumes should be factored into cost estimates. Subsequent incremental transfers are typically much smaller (only changed blocks).

### SM-VAL-011: Teardown Order — Critical Dependency

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-011 |
| **Classification** | `works_with_caveats` |
| **Disclosure** | validation evidence |

**Finding:** Deleting VPC Peering or network routes before SVM peer deletion completes causes **permanent orphaned SVM peer records** that cannot be deleted via REST API. The FSx SVM enters MISCONFIGURED state and blocks file system deletion.

**Required teardown order:**
1. Delete SnapMirror relationships (both sides: `destination_only=true` on dest)
2. Delete SVM peers (both sides) — **wait until `num_records: 0` on BOTH clusters**
3. Delete Cluster peers
4. Delete VPC Peering / routes
5. Delete SVM via FSx API
6. Delete File System via FSx API

**Never:** Delete VPC Peering before step 2 is confirmed. The two-phase SVM peer deletion protocol requires bidirectional connectivity.

**Recovery if orphaned:** Use ONTAP CLI via SSH (`sshpass -p <pass> ssh fsxadmin@<mgmt-ip>`).

### SM-VAL-012: UpdateVolume Accepts a Junction Path on a DP Volume and Silently Discards It

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-012 |
| **Classification** | `works_with_caveats` |
| **Disclosure** | validation evidence |
| **Measured** | 2026-09-13, ap-northeast-1 ([evidence](../../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml)) |

**Finding:** `aws fsx update-volume --ontap-configuration '{"JunctionPath":"..."}'` against a **DP** volume returns HTTP 200 with the full Volume object, and has no effect. 30 s later `DescribeVolumes` still reports `JunctionPath: None`, with no `AdministrativeActions` entry and no failure message. A subsequent access point attachment fails with `the volume is not mounted`, confirming nothing changed.

By contrast, `CreateVolume` refuses the same field explicitly: `Invalid fields provided for a DP volume. JunctionPath, StorageEfficiency, SnapshotPolicy and SecurityStyle cannot be specified for a DP Volume.` The two APIs disagree on how to reject the same invalid input, and the mutating one is the quiet one.

**Interaction with SM-VAL-008, which is the operationally important part.** SM-VAL-008 correctly says not to gate access point attachment on `OntapVolumeType`, because the FSx API keeps reporting `DP` for over ten minutes after a successful cross-region break. Combined with this finding, that leaves an operator unable to distinguish two states from the volume type alone:

| Actual state | FSx API `OntapVolumeType` | `update-volume` with a junction path |
|---|---|---|
| Broken, FSx API still lagging | `DP` | Takes effect |
| Never broken, or resynced | `DP` | Accepted, silently discarded |

**The junction path itself is the only reliable signal.** Set it, then poll `DescribeVolumes` for a non-null `JunctionPath` before attempting attachment. Do not treat the `UpdateVolume` response as confirmation, and do not retry with additional flags — a silent discard looks identical to a slow propagation, and adding flags to a call that was already accepted changes nothing.

**Scope, and what this does NOT mean.** This is an FSx control-plane restriction, not an ONTAP one, and it does **not** mean a DP volume cannot carry an access point. Measured 2026-09-13 in-VPC (SM-VAL-013): ONTAP mounts a DP volume, the FSx API reports that junction path after ~2298 s, and attachment then succeeds and serves reads off a live SnapMirror destination. The correct reading of SM-VAL-012 is narrow: **the FSx API is not a usable way to mount a DP volume, and it fails silently rather than loudly.** Separately, the DP subject in this run had no active SnapMirror relationship; a live destination was tested in SM-VAL-013 and behaved the same way.

### SM-VAL-013: An S3 Access Point Serves a Live SnapMirror Destination

| Item | Details |
|------|---------|
| **Finding ID** | SM-VAL-013 |
| **Classification** | `supported (validated)` |
| **Disclosure** | validation evidence |
| **Measured** | 2026-09-13, ap-northeast-1, ONTAP 9.18.1P5, intra-SVM async volume SnapMirror ([evidence](../../../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml)) |

**Finding:** a SnapMirror destination can be read through an S3 access point with the relationship left running — no break, no clone. Mount the DP volume through ONTAP (`vol mount` / `PATCH nas.path`), wait for the FSx API to report the junction path, then attach. Reads succeed, `PutObject` returns `AccessDenied` because a DP volume is read-only, and the relationship stays `snapmirrored` and healthy throughout. **A subsequent SnapMirror transfer became visible and readable through the same access point within 15 s, with no access point change.**

A FlexClone of the destination Snapshot is the alternative and differs in one property: it accepts writes, and it stays frozen at the Snapshot it was cut from.

| Phase | Duration |
|---|--:|
| ONTAP operation (mount, or create the clone) | seconds, under 20 s |
| FSx API reports the volume / junction path | **665 s, 1011 s, 2298 s** |
| Access point CREATING → AVAILABLE | 31-32 s |

**Automation impact:** FSx control-plane propagation, not the ONTAP operation, dominates first-time setup. Poll `DescribeVolumes` for a non-null `JunctionPath` (DP route) or for the `fsvol-*` identifier to appear (clone route), and do not attempt attachment before then — it fails with `the volume is not mounted`. Three samples on one file system, and the 665 s and 2298 s cases are the same operation, so the spread is not a property of the route. Design for minutes to tens of minutes; do not quote a figure.

**Engine equivalence (S3AP-DP-ATHENA-001).** Amazon Athena over a DP-backed access point returned results identical to an RW-backed control built from the same Parquet files, in one session — same rows, same aggregates, 7493 ms against 7804 ms. Partition discovery (`MSCK REPAIR`) and partition pruning both worked against the read-only volume; `INSERT` failed with S3 403 surfaced as `PERMISSION_DENIED`, leaving nothing on the volume. A partition added by a later transfer became queryable after a catalog refresh alone. Snowflake was **not** tested on a DP-backed access point — the read surface is the same, but that is inference, not measurement.

**Teardown, and a diagnosis that took two passes:** deleting the FlexClone through the FSx API left the parent flagged `clone.has_flexclone=true`, and the parent then refused to delete through both APIs. The first reading — a stale flag, no clone present, not resolvable with the privileges available — was wrong. `aws fsx delete-volume` does not destroy a volume: ONTAP renames it `<name>_NNNN` and moves it into the **volume recovery queue** with type `del`, and the queued clone was still holding the parent's Snapshot. It is invisible to `/api/storage/volumes` and to `volume show` at default privilege, and appears under `privilege_level=diagnostic`, in `volume clone show`, and in `volume recovery-queue show`. `volume recovery-queue purge` cleared it and the parent then deleted normally, with `fsxadmin` privilege alone. Full account: [ONTAP-RECOVERY-QUEUE-001](../../../../verification-pack/ontap-features/evidence/2026-09-13/volume-recovery-queue-and-fc002.yaml). Also note that an access point's internal `amazon-fsx-fsvol-*` object-store bucket briefly blocks volume deletion and is **not** listed by `GET /api/protocols/s3/buckets`.

**Not established:** whether an analytics engine reads a DP-backed access point identically to an RW-backed one (only the S3 API was exercised); cross-region behaviour; survival across a break/resync cycle with the access point in place; scale beyond four small objects; WINDOWS identity or NTFS security style.

> **Note**: SSH access to `fsxadmin` must be enabled on the FSx file system (Settings → Administrative Endpoints). For production automation, prefer SSH key-based auth or AWS Systems Manager Session Manager over `sshpass`. Resolution time with AWS Support (if self-recovery fails): typically 1-3 business days.

1. From the **source** cluster: `snapmirror release -destination-path <dest> -source-path <src> -force true` (for each stale destination)
2. From the **source** cluster: `vserver peer delete -vserver <local-svm> -peer-vserver <remote-svm>` (triggers two-phase cleanup on both sides)
3. Retry `aws fsx delete-storage-virtual-machine` — should now succeed
4. Reference: [AWS re:Post — Delete SVM from FSx for ONTAP](https://repost.aws/knowledge-center/fsx-ontap-delete-svm), [FSx User Guide — Can't delete SVM](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/cannot-delete-svm.html)

---

## Version Matrix

| Feature | Minimum ONTAP | Notes |
|---------|:-------------:|-------|
| S3 Access Point (basic) | 9.14.1 | FSx for ONTAP feature |
| S3 NAS bucket (multiprotocol) | 9.12.1 | Underlying ONTAP mechanism |
| S3 NAS bucket on FlexCache Origin | 9.12.1 | Origin volume with S3 AP as FlexCache source |
| S3 NAS bucket on FlexCache Cache | **9.18.1** | Cache Volume S3 AP attachment (FC-002) |
| SnapMirror Async | 9.11.1 | FSx for ONTAP baseline |
| FlexCache (read-only) | 9.5 | Long-standing feature |
| FlexCache write-back | 9.15.1 | Both Origin and Cache |
| FlexCache write-back (recommended) | 9.17.1P1+ | Stability improvements |
| FlexCache Origin/Cache version gap | Within 4 minor | e.g., Cache 9.14.1 → Origin >= 9.10.1 |
| Cluster Peering Encryption | 9.6 | TLS 1.2, default enabled |
| NFSv4.x on FlexCache | 9.10.1 | Both Origin and Cache |
| FlexGroup as FlexCache Origin | 9.13.1 | With constraints |
| GCNV External Replication | Source 9.11.1+ (est.) | GCNV manages destination version |

---

## Recommended Architecture Patterns

### Pattern A: Single-Cloud Data Distribution (FSx for ONTAP cross-region)

- **Use case**: Distribute S3 AP-collected data across AWS regions for low-latency NFS/SMB access
- **Components**: SnapMirror Async for DR + FlexCache for read acceleration
- **Constraints**: SnapMirror Sync unsupported; S3 AP must be newly created at destination

### Pattern B: Hybrid Cloud (FSx for ONTAP to On-premises ONTAP)

- **Use case**: Deliver AWS-collected data to on-premises data centers for existing NFS/SMB clients
- **Components**: Direct Connect/VPN + SnapMirror or FlexCache
- **Constraints**: On-premises ONTAP version compatibility; FlexCache write-back requires RTT <= 200ms

### Pattern C: Multi-Cloud (FSx for ONTAP to GCP/Azure)

- **Use case**: Access AWS-collected data from GCP or Azure workloads
- **GCP options**: GCNV External Replication (SnapMirror), GCNV FlexCache Cache, CVO on GCP
- **Azure options**: CVO on Azure (SnapMirror/FlexCache). ANF is not supported
- **Constraints**: Cross-cloud VPN latency (20-100ms typical); write-around mode recommended

---

## Decision Tree: SnapMirror vs FlexCache

SnapMirror and FlexCache are **complementary technologies suited to different use cases**, not competing approaches.

| Use Case | Recommended | Rationale |
|----------|------------|-----------|
| Disaster Recovery | SnapMirror | Full copy at destination, immediate failover capability |
| Remote read acceleration | FlexCache | Local-speed cache hits, minimal storage consumption |
| Data migration (one-time) | SnapMirror | Full copy then release relationship |
| Remote write (synchronous) | FlexCache (write-around) | Writes forwarded to Origin synchronously. Default mode |
| Remote write (asynchronous) | FlexCache (write-back) | Writes cached locally, flushed to Origin asynchronously (RTT <= 200ms required) |
| DR + daily read acceleration | SnapMirror + FlexCache hybrid | SnapMirror for DR, FlexCache for daily performance |
| Multi-cloud distribution | SnapMirror | More reliable than FlexCache write-back across clouds |

---

## Hybrid and On-Premises Patterns: Data Gravity and Locality

The cross-region validation in this project was performed between AWS regions (FSx for ONTAP to FSx for ONTAP). However, SnapMirror and FlexCache are ONTAP-universal features — the same architecture applies to on-premises ONTAP (AFF/FAS/ONTAP Select) and edge deployments.

### The Data Gravity Problem

As datasets grow, the cost of moving them (time, bandwidth, egress charges) increases proportionally. This "data gravity" creates a practical constraint: it is often more efficient to bring compute to where data already resides, rather than moving data to where compute is available.

Two complementary directions address this:

| Direction | Pattern | Example |
|-----------|---------|---------|
| **Bring data to on-prem compute** | S3 AP collects data in AWS → SnapMirror replicates to on-prem ONTAP → NFS access from local GPU/HPC/licensed tools | EDA verification, CAE simulation, MATLAB analysis, AI model training on on-prem GPU |
| **Bring cloud compute to on-prem data** | On-prem ONTAP (Origin) → FlexCache to FSx for ONTAP (Cache) → EMR/SageMaker/Spark process cached data | Cloud-burst rendering, large-scale batch analytics, model training on cloud GPU |

```
Pattern A: Collect in cloud, process on-premises
  AWS (S3 AP ingest) ──SnapMirror──▶ On-prem ONTAP ──NFS──▶ Local analytics
                                                              GPU cluster
                                                              Licensed tools

Pattern B: On-prem data, cloud-burst compute
  On-prem ONTAP (Origin) ──FlexCache──▶ FSx for ONTAP (Cache) ──▶ EMR / SageMaker
```

### When This Pattern Is Effective

| Scenario | Rationale |
|----------|-----------|
| Regulatory or policy constraints prevent data from leaving premises | SnapMirror replicates within private network (VPN/Direct Connect, encrypted in transit) |
| Expensive on-prem licensed tools (EDA, CAE, MATLAB, SAS) | Moving data to tools is more practical than migrating licenses to cloud |
| Factory-floor real-time inference requires low latency | FlexCache at edge/factory; Origin updates auto-reflect |
| Minimize cloud egress costs | SnapMirror: incremental only after baseline. FlexCache: only accessed data is cached |
| Consolidate multi-site data for centralized analysis | SnapMirror from each site to AWS → Athena/EMR cross-query |
| Air-gapped or isolated network analytics | SnapMirror one-way to isolated ONTAP; no outbound connectivity required after transfer |

### Data Sovereignty and Compliance Considerations

For organizations with data residency requirements:

- SnapMirror transfers can be confined to specific network paths (Direct Connect, site-to-site VPN)
- Data at rest is encrypted (NAE/NVE on ONTAP, AWS-managed encryption on FSx)
- Data in transit is encrypted (Cluster Peering Encryption: TLS 1.2, enabled by default since ONTAP 9.6)
- No data needs to traverse public internet if Direct Connect or VPN is in place
- Audit trail: ONTAP FPolicy + S3 AP access logs provide dual-layer access logging

### Demo Guides for On-Premises Patterns

| Guide | Pattern | Network |
|-------|---------|---------|
| [Guide 03: FlexCache On-Premises](demo-guide-03-flexcache-on-premises.md) | FSx for ONTAP → On-prem ONTAP (FlexCache) | Direct Connect / VPN |
| [Guide 08: SnapMirror On-Premises](demo-guide-08-snapmirror-on-premises.md) | FSx for ONTAP → On-prem ONTAP (SnapMirror DR) | Direct Connect / VPN |

> These guides are currently at procedure-level (commands documented, not yet E2E validated on physical hardware). Validation will be performed when on-premises lab access is available.

---

## Industry Use Cases

The following table organizes expected application patterns by industry. These are architecture patterns based on validated FlexCache/SnapMirror behavior with S3 Access Points — individual industry deployments require workload-specific validation.

### Data Collection + Analytics Burst (FlexCache)

| Industry | Workload | FlexCache Role |
|----------|----------|----------------|
| Automotive (AV/ADAS) | HiL testing — replay cloud-collected driving data on-prem | Distribute golden dataset to test rigs; Origin updates auto-reflect |
| Media / VFX | Render burst — deliver scene files + textures to cloud render farm | Render nodes read assets at local speed |
| Semiconductor (EDA) | DRC/LVS circuit verification — burst design data to cloud | Cache placement near compute; jobs start without transfer wait |
| Healthcare | Medical imaging (DICOM) — distribute hospital NAS images to research AI | Parallel reads from multiple research sites |
| IoT / Manufacturing | Sensor data collection → analytics environment | NFS batch throughput (advantageous over S3 API in some access patterns) |
| Energy | Seismic / simulation data — HPC cluster delivery | Transfer PB-scale dataset once, reuse via FlexCache |
| Construction | BIM models — multi-site design teams reference same 3D model | Cache per site; write-around syncs changes to Origin immediately |

### DR + Compliance Retention (SnapMirror)

| Industry | Workload | SnapMirror Role |
|----------|----------|-----------------|
| Financial Services | Regulatory DR — trade records and audit logs to alternate region | Async replication (RPO ≤ 5 min); geo-redundancy for audit trails |
| Public Sector | Government BC/DR — service continuity during disaster | Full copy to alternate region; S3 AP re-attach ~3 min for failover |
| Healthcare | HIPAA compliance — patient data backup to alternate region | In-transit encryption (TLS 1.2) + at-rest encryption standard; incremental transfer |
| Telco | Network logs / CDR long-term retention + DR | Daily replication of large logs; NFS mount at dest for analytics |
| Retail / E-commerce | POS / behavioral data delivery to analytics environment | Daily batch sync; avoid per-API-call S3 charges |

### Hybrid (FlexCache + SnapMirror)

| Industry | Workload | Combined Pattern |
|----------|----------|-----------------|
| Manufacturing | Quality images + IoT → AI inference + DR | FlexCache: read acceleration for inference / SnapMirror: raw data DR |
| Media | Source NAS → multi-site post-production + HQ DR | FlexCache: editing access per site / SnapMirror: master DR |
| Logistics | Delivery image recognition → analytics + archive | FlexCache: real-time analytics / SnapMirror: compliance archive |
| Advertising / AdTech | Log collection → real-time analytics + DR | FlexCache: low-latency to analytics cluster / SnapMirror: audit DR |
| Agriculture / Food | Drone imagery → AI analysis + long-term retention | FlexCache: GPU cluster delivery / SnapMirror: original preservation |
| Real Estate | 3D scan / point cloud → VR viewing + archive | FlexCache: branch office viewer delivery / SnapMirror: asset preservation |

### Design Considerations

- **S3 API call costs**: For workloads that reference many small files, NFS mount via FlexCache may be more cost-effective (S3 charges per GET/LIST call). This depends on access pattern and file size.
- **Latency**: S3 API has higher per-operation latency for metadata operations compared to NFS. NFS is advantageous for frequent random file access. Conversely, S3 parallel large-object download may be better suited for certain patterns.
- **SnapMirror incremental transfer**: After the initial baseline, only changed blocks are transferred. Even TB-scale datasets have minimal daily sync network overhead.

References:
- [AWS Blog — Accelerating HiL Testing for AV/ADAS with a Hybrid Cloud Approach](https://aws.amazon.com/jp/blogs/industries/accelerating-hil-testing-for-av-adas-with-a-hybrid-cloud-approach-aws-and-netapp/)
- [NetApp Blog — Transform Your EDA Workflows with FlexCache](https://www.netapp.com/ja/blog/transform-eda-workflows-flexcache/)
- [NetApp Blog — Global data consistency made simple with FlexCache](https://www.netapp.com/blog/flexcache-global-data-gigaom-radar/)

---

## Open Questions

| # | Question | Finding ID | Priority | Resolution Path |
|---|---------|:----------:|:--------:|----------------|
| ~~1~~ | ~~Can Cache Volume have independent S3 AP attachment?~~ | FC-002 | ~~P2~~ | **Resolved**: Supported from ONTAP 9.18.1. Not supported on 9.17.1 (tested). |
| 2 | GCNV External Replication minimum source ONTAP version? | XC-006 | P2 | GCP docs or validation |
| 3 | FlexGroup + S3 AP + FlexCache Origin stability? | FC-007 | P2 | Hands-on validation |
| 4 | ANF alternative path (via CVO on Azure) practicality? | XC-007 | P3 | Architecture + cost eval |

### Resolved in Phase 3

| # | Question | Finding ID | Resolution |
|---|---------|:----------:|-----------|
| ~~1~~ | S3 AP-attached volume as FlexCache Origin? | FC-001 | **Yes** — validated on 9.17.1 |
| ~~2~~ | S3 AP writes + XLD interaction in write-back? | FC-004 | **Works with caveats** — XLD revoke on same-file |
| ~~3~~ | S3 AP attach to destination after SnapMirror break? | SM-005 | **Yes** — break → junction → ~60s → create AP |
| ~~4~~ | `s3_unix` name-mapping regeneration at destination? | SM-002 | **Yes** — FSx auto-manages on AP creation |

---

## Phase 3 Validation Summary

Validated on FSx for ONTAP (ONTAP 9.17.1P7D1, 2nd Generation, Single-AZ, ap-northeast-1).

### Test Case Results

| TC | Scope | Result | Key Finding |
|:--:|-------|:------:|-------------|
| TC-01 | S3 AP + SnapMirror create + transfer | PASS | Volume-level async works with S3 AP volume |
| TC-02 | SnapMirror break + S3 AP re-attach | PASS | ~60s FSx API lag; new AP works immediately after |
| TC-03 | S3 AP + FlexCache Origin | PASS | Cache reads data written via S3 AP |
| TC-04 | FlexCache NFS read verification | PASS | Data integrity confirmed (checksum match) |
| TC-05 | FlexCache write-back + S3 AP | PASS | XLD revoke on same-file; different-file is safe |

### Operational Notes (from validation)

| ID | Finding | Impact |
|:--:|---------|--------|
| FC-VAL-001 | Minimum FlexCache size on FSx for ONTAP: 50GB | Sizing constraint |
| FC-VAL-002 | `use_tiered_aggregate: true` required for FlexCache creation | API parameter |
| FC-VAL-003 | Intra-cluster SVM Peering required for same-cluster FlexCache | Setup requirement |
| FC-VAL-004 | S3 AP write propagates to Cache within ~30s (TTL) | Latency expectation |

### Classification Changes (Phase 2 → Phase 3)

| Finding | Before | After |
|---------|--------|-------|
| SM-002 | undocumented | supported (validated) |
| SM-005 | undocumented | supported (validated) |
| FC-001 | undocumented | supported (validated) |
| FC-004 | undocumented | works_with_caveats |
| SM-VAL-004/007 | (new) | works_with_caveats |

---

## References

### Primary Sources

- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP FlexCache](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: ONTAP S3 multiprotocol](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
- [NetApp Docs: FlexCache write-back](https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-architecture.html)
- [NetApp Docs: SnapMirror SVM replication](https://docs.netapp.com/us-en/ontap/data-protection/snapmirror-svm-replication-concept.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [GCP Docs: GCNV External Replication](https://cloud.google.com/netapp/volumes/docs/protect-data/replicate-ontap/overview)
- [GCP Docs: GCNV FlexCache](https://docs.cloud.google.com/netapp/volumes/docs/configure-and-use/volumes/cache-ontap-volumes/overview)
- [Microsoft Docs: ANF Replication](https://learn.microsoft.com/en-us/azure/azure-netapp-files/replication)
