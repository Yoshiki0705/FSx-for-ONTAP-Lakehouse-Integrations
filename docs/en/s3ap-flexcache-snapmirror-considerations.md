> 🌐 Language: [日本語](../ja/s3ap-flexcache-snapmirror-considerations.md) | **English**

# S3 Access Points + FlexCache / SnapMirror — Additional Design Considerations

> Additional design guidance for distributing S3 AP-collected data via FlexCache (read acceleration) or SnapMirror (DR). Review [general S3 AP design considerations](s3ap-design-considerations.md) first.

---

## Premise

- FSx for ONTAP S3 Access Points are based on the ONTAP S3 NAS bucket mechanism
- S3 AP-attached volumes can be used with SnapMirror / FlexCache like any standard FlexVol/FlexGroup
- For compatibility details, see [research document](../../integrations/snapmirror-flexcache-multicloud/docs/en/research.md)

---

## 1. Directory Design Impact on FlexCache / SnapMirror

S3 AP directory design affects not only standalone performance but also FlexCache / SnapMirror efficiency.

### Impact on FlexCache

| Directory Layout | FlexCache Behavior | Impact |
|-----------------|-------------------|--------|
| 1M files in single directory | Files concentrate on one FlexGroup constituent | Cache load on 1 node only. FlexCache distribution benefit lost |
| Properly distributed directories | Spread across multiple constituents | Cache hits across multiple nodes. FlexCache parallelism utilized |
| Excessively deep hierarchy (>10 levels) | Recursive readdir becomes deep | Multiple Origin round-trips on cache miss |

**Guideline**: When FlexCache is planned, distribute files across directories to leverage FlexGroup constituent parallelism.

### Impact on SnapMirror

| Write Pattern | Effect on Incremental Transfer |
|--------------|-------------------------------|
| Many small files across multiple directories | Changed blocks distributed → efficient incremental transfer |
| Appending to one large file | Changed blocks concentrated → large transfer volume each time |
| Bulk creation in single directory | Directory metadata updates concentrated → transfer volume increase |

**Guideline**: When SnapMirror is planned, writing many small-to-medium files is more transfer-efficient than appending to a single large file.

---

## 2. FlexCache Considerations

### 2.1 Write Mode Selection

| Mode | Behavior | Origin Reflection | Relationship to S3 AP Writes |
|------|----------|:-----------------:|------------------------------|
| write-around (default) | Cache writes forwarded to Origin synchronously | Immediate | Low conflict with Origin-side S3 AP writes |
| write-back | Cache writes stored locally, flushed to Origin asynchronously | 30-90 seconds | Origin-side S3 AP writes revoke XLD, Cache dirty data lost |

**Design Rule**: For "S3 AP writes to Origin, FlexCache reads at destination" pattern, **use write-around mode**. If write-back is used, never write the same file from both S3 AP and FlexCache concurrently.

### 2.2 Cache Propagation and Data Visibility

| Aspect | Value | Notes |
|--------|-------|-------|
| New file visibility (cache miss) | ~3-6 seconds | Validated (intra-cluster ~6s, cross-region <3s) |
| Updated file visibility (cached) | After TTL expires (default 30s) | Adjustable via `read_after_write_flush_time` |
| FlexCache prepopulate | Not supported via S3 AP | NFS/SMB access can pre-warm cache |

**Design Rule**: First read after S3 AP write goes to Origin (cache miss). Subsequent reads within TTL are served from cache.

### 2.3 ListObjectsV2 on FlexCache

When ListObjectsV2 is run on a FlexCache Cache Volume (ONTAP 9.18.1+ with Cache S3):

- ListObjectsV2 is a directory metadata read operation
- Cached directory listings return at local speed
- Cache-miss directories require Origin round-trip (RTT added to latency)

**Recommendation**: Pre-warm frequently-listed prefixes via NFS access to improve response time.

---

## 3. SnapMirror Considerations

### 3.1 S3 AP Metadata Is Not Transferred

SnapMirror transfers volume data (files/directories) only. The following must be configured separately at the destination.

| Item | Transferred? | Destination Action |
|------|:------------:|-------------------|
| File data | ✅ | — |
| UNIX permissions (uid/gid/mode) | ✅ | — |
| NTFS ACLs | ✅ | — |
| S3 Access Point | ❌ | Create new via `aws fsx create-and-attach-s3-access-point` |
| S3 AP IAM policy | ❌ | Configure in destination region |
| S3 user metadata (x-amz-meta-*) | ⚠️ | May persist as ONTAP stream attributes (version-dependent) |
| S3 Object Tags | ⚠️ | Same as above |

**Design Rule**: DR failover procedure must include S3 AP creation + IAM policy configuration. Automate with Lambda or Step Functions.

### 3.2 S3 AP Attachment at the Destination

**A live SnapMirror destination can be served through an S3 AP, for reads, with no break and no clone.** Measured 2026-09-13. This section previously said the opposite; the correction and what caused the error are below.

**The gate is the junction path, not the volume type.** AWS states that attaching an access point requires the volume to be [mounted](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html), and says nothing about `RW` versus `DP`.

**And setting that junction path is an ONTAP operation, not an FSx one.** ONTAP mounts a DP volume — `vol mount` on a DP volume is a worked example in NetApp's [SVM DR testing KB](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror/SnapMirror-KBs/Can_we_do_the_SVM_level_DR_test_without_stopping_the_Production_SVM_and_cloning_the_destination_volumes), and it was confirmed here. The FSx API refuses the same change: `CreateVolume` rejects `JunctionPath` for a DP volume by name, and `UpdateVolume` accepts it and silently discards it. Mount through ONTAP and the FSx API eventually reports the junction path, after which attachment succeeds.

| Destination-side subject | S3 AP Attachment | Reads | Writes | Notes |
|---|:---:|:---:|:---:|---|
| DP volume, junction path attempted via the **FSx API** | ❌ | — | — | `CreateVolume` refuses the field by name; `UpdateVolume` returns 200 and silently discards it. Attachment fails with `the volume is not mounted` |
| **DP volume, mounted via ONTAP** | ✅ | ✅ | ❌ `AccessDenied` | Replication stays `snapmirrored`/healthy. New data from a later transfer appeared through the same access point in **15 s**, with no access point change |
| **FlexClone of a destination Snapshot** | ✅ | ✅ | ✅ | Relationship unaffected. Frozen at the cloned Snapshot — a later transfer does not advance it |
| DP → break → RW | ✅ | ✅ | ✅ | The DR failover path. SM-005, SM-VAL-008/010 |

Evidence: [S3AP-DP-ATTACH-002](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml), on ONTAP 9.18.1P5. The FSx-API-only rows come from [S3AP-DP-ATTACH-001](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml).

**The real constraint is setup latency, not capability.** Both ONTAP-side routes then wait on FSx control-plane propagation before the volume is attachable:

| Phase | Duration |
|---|--:|
| ONTAP operation (mount, or create the clone) | seconds, under 20 s |
| **FSx API reports the volume / junction path** | **665 s, 1011 s, 2298 s** |
| Access point CREATING → AVAILABLE | 31-32 s |
| First successful S3 call | seconds |

Three samples, one file system, same day. Two of them — 665 s and 2298 s — are the *same operation* on the same file system, so **the spread is not explained by which route you take.** Quote it as "minutes to tens of minutes, not under your control" and design a polling loop; do not quote a figure. Steady state after setup is a different matter: on the DP route new data was readable seconds after a transfer.

**An analytics engine cannot tell the difference.** Amazon Athena was pointed at a DP-backed access point and at an RW-backed control built from identical Parquet files, in one session: identical rows, identical aggregates, 7493 ms against 7804 ms. Partition discovery and partition pruning both worked against the read-only volume, and `INSERT` failed cleanly with S3 403 surfaced as `PERMISSION_DENIED`. A partition added by a later transfer became queryable after a catalog refresh, with no change to the access point or the table. Evidence: [S3AP-DP-ATHENA-001](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-athena-on-dp/evidence-record.yaml).

> **Why this section was wrong until 2026-09-13.** The original row asserted ❌ for a DP volume with the reason "read-only; junction path cannot be set", carrying no evidence record. A first pass tested it from outside the VPC, reproduced the FSx API's refusal, and confirmed the ❌ — which looked like verification but had only measured the FSx API. The ONTAP management endpoint is a private address, so the layer that actually decides was never reached. **Testing the reachable API is not testing the claim.**

#### Serving replica data without breaking the relationship

Breaking is not required to read a destination. Two routes keep the relationship running, and they differ in exactly one property that decides between them: **whether the consumer needs to write.**

**Read-only, always current — mount the DP destination.** `vol mount` the destination through ONTAP, wait for the FSx API to report the junction path, attach. Reads work, writes return `AccessDenied`, and each SnapMirror transfer becomes visible through the same access point within seconds. Nothing has to be rebuilt per transfer.

**Writable, fixed point in time — clone the destination.** From ONTAP 9.14.1, NetApp documents creating a **volume clone of a SnapMirror destination to test failover without disrupting the active relationship** ([procedure](https://docs.netapp.com/us-en/ontap/data-protection/create-delete-snapmirror-failover-test-task.html)): same storage VM as the destination, FlexVol and FlexGroup, synchronous and asynchronous. The clone accepts writes through its access point, and stays at the Snapshot it was cut from — a later transfer does not advance it. NetApp's [destination data-access procedure](https://docs.netapp.com/us-en/ontap/data-protection/configure-destination-volume-data-access-concept.html) is written around break because its subject is taking over production service, a different requirement from either of these.

Constraints on the clone route: **one test clone per relationship** at a time, SnapLock vault relationships excluded, and — from the KB above — **a DP volume in an SVM-DR relationship cannot be cloned directly**. The last does not bite on FSx for ONTAP, where SVM-DR is unavailable and volume-level SnapMirror is the only option (SM-007), but it does on-premises.

**Design Rule**: choose by requirement, not by default.

| Requirement | Shape |
|---|---|
| Read the destination, current with each transfer | Mount the DP destination via ONTAP, attach the S3 AP to it |
| Write, or hand consumers an isolated point in time | Clone the destination Snapshot, attach the S3 AP to the clone |
| Take over production service at the destination | Break, mount, attach — the DR failover path |
| Near-real-time visibility of source writes | FlexCache, not SnapMirror (§2.2) |

Still unmeasured, and worth stating before a customer commitment: **Snowflake specifically** — Athena is good evidence that the engine layer does not care about the volume type, and Snowflake reads through the same `GetObject` and `ListObjectsV2` surface, but Snowflake was not run against a DP-backed access point, so do not present it as measured. Also unmeasured: behaviour across a break-and-resync cycle with the access point left in place, propagation cross-region or on a second-generation file system, scale beyond a handful of small objects, and WINDOWS file-system identity.

### 3.3 RPO and Data Visibility

| Item | Value | Notes |
|------|-------|-------|
| SnapMirror Async minimum schedule | 5 minutes | FSx for ONTAP constraint |
| Typical incremental transfer duration | 10-30 seconds | Depends on data volume and throughput capacity |
| Failover RTO (time to S3 AP access) | ~3 minutes | break + junction path + S3 AP creation |
| RPO | = time since last transfer | Worst case: 5 min + in-flight data |

**Design Rule**: Use FlexCache for near-real-time needs, SnapMirror for DR/compliance. Combine both when required.

---

## 4. Integrated Directory Pattern

Recommended directory structure considering S3 AP + FlexCache + SnapMirror together.

```
/volume-root/
  └── {source-id}/                    ← Separate by tenant/source
      └── {year}/{month}/{day}/       ← Time-series partition (Hive-style)
          └── {hour}/                 ← Control files per directory
              ├── {uuid-short}.json
              ├── {uuid-short}.parquet
              └── ...
```

### Requirements This Structure Satisfies

| Requirement | How |
|-------------|-----|
| ListObjectsV2 performance | Prefix narrows target directory; small sort set |
| FlexGroup distribution | Many directories → auto-distributed across constituents |
| FlexCache efficiency | Reads distributed across multiple constituents |
| SnapMirror incremental transfer | Small files × many directories → distributed changed blocks |
| Athena partition pruning | Hive-style partitions auto-recognized by Glue Crawler |
| NFS batch processing | Date directories enable efficient `find` / `rsync` |
| Access control | Tenant directories align with export-policy / AP policy prefix restrictions |

---

## 5. FlexCache Deletion Procedure

FlexCache deletion must use the **ONTAP REST API**, not FSx API `delete-volume`.

### Correct Procedure

```bash
# 1. Get FlexCache UUID
ONTAP_API: GET /api/storage/flexcache/flexcaches?name={cache_name}

# 2. Delete FlexCache (ONTAP REST API)
ONTAP_API: DELETE /api/storage/flexcache/flexcaches/{uuid}
# → 202 Accepted (async job). Wait for job completion.

# 3. If ghost entry remains in FSx API (blocks SVM deletion)
aws fsx delete-volume --volume-id fsvol-XXXXX --ontap-configuration '{"SkipFinalBackup":true}'

# 4. Delete SVM (after all volumes gone from FSx API)
aws fsx delete-storage-virtual-machine --storage-virtual-machine-id svm-XXXXX
```

### Why ONTAP REST API Instead of FSx API `delete-volume`

- FlexCache is managed internally as a special FlexGroup with Origin relationship metadata
- ONTAP REST API `DELETE /api/storage/flexcache/flexcaches/{uuid}` properly cleans up this relationship
- FSx API `delete-volume` uses a standard volume deletion path that may not perform FlexCache-specific cleanup
- 404 response = success (idempotent). 409 Conflict = wait and retry (volume busy)

### FSx Control Plane Propagation Delay (Deletion)

- After ONTAP REST API deletion completes, FSx API (`describe-volumes`) may still show the fsvol-* entry
- If SVM deletion fails with "Cannot delete storage virtual machine while it has non-root volumes", run `delete-volume` via FSx API to clear the ghost entry
- This propagation delay is similar to creation (~30 minutes)

---

## 6. Monitoring

### FlexCache

| Metric | Method | Threshold |
|--------|--------|-----------|
| Cache hit rate | ONTAP REST API: `GET /api/storage/flexcache/flexcaches/{uuid}?fields=*` | < 50% → review directory distribution |
| Origin query latency | `statistics show -object flexcache` | > RTT × 2 → Origin-side bottleneck |
| Cache volume utilization | `volume show -fields percent-used` | > 80% → increased eviction frequency |

### SnapMirror

| Metric | Method | Threshold |
|--------|--------|-----------|
| Lag Time | CloudWatch: `SnapMirrorLagTime` | > RPO target (e.g., 900s) → alert |
| Transfer Duration | CloudWatch: `SnapMirrorTransferDuration` | Increasing trend → write rate exceeds throughput |
| Healthy | CloudWatch: `SnapMirrorHealthy` | < 1 → investigate immediately |

---

## 7. Anti-Patterns

| Pattern | Problem | Mitigation |
|---------|---------|-----------|
| All files in root directory | maxdir-size overflow + FlexCache skew + LIST degradation | Hierarchical partition |
| Appending to one large file | SnapMirror incremental transfer large each time | Split into small files |
| S3 AP + FlexCache write-back on same file | XLD revoke → dirty data lost | Use write-around or separate files |
| Try to mount a DP volume through the FSx API | Refused. `CreateVolume` rejects `JunctionPath` by name; `UpdateVolume` returns 200 and discards it | Mount through ONTAP instead, then wait for the FSx API to report the junction path before attaching (§3.2) |
| Treat a 200 from `UpdateVolume` as proof the junction path was set | On a DP volume the call returns the full Volume object and **silently does nothing** — no error, no `AdministrativeActions` entry, no failure message. Automation proceeds on a false premise | Re-read `JunctionPath` from `DescribeVolumes` and gate on that value, never on the `UpdateVolume` response |
| Reject a destination-side S3 AP design because "SnapMirror must be broken" | Wrong. A live destination serves reads through an access point once ONTAP has mounted it, and a clone serves writes. Break is only for taking over production service | §3.2 |
| Promise a clone or a newly mounted destination "in minutes" | The ONTAP operation is seconds, but the FSx control plane took 1011 s and 2298 s to report the volume as attachable | Budget tens of minutes for first-time setup. Steady-state freshness after that is seconds |
| Read `aws fsx delete-volume` as "deleted" | It is "queued for deletion". ONTAP renames the volume and moves it to the **volume recovery queue** (type `del`, default retention 12 h) while the FSx API reports it gone. A queued FlexClone still holds its parent's Snapshot, so the parent refuses to delete with "has one or more clones" and no clone is visible through `DescribeVolumes`, `/api/storage/volumes`, or `volume show` at default privilege | Query `volume recovery-queue show`, then `volume recovery-queue purge` (advanced privilege). The parent then deletes normally. Mechanism and the retention setting: [Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook), `docs/ja/domains/block-storage/notes/lun-layout-decides-recovery-granularity.md` |
| Build a teardown runbook on ONTAP `volume delete` for AP-attached volumes | The access point's volume-scoped internal bucket blocks it **permanently**, not briefly — including for a volume whose attach attempt *failed* | Delete through the AWS API. Same playbook, `s3-access-point-constraints.md`, 「撤去時の停滞」 |
| Conclude a clone is absent because the object API does not list it | Queued clones appear only under `privilege_level=diagnostic`, in `volume clone show`, and in the recovery queue | Ask the recovery queue |
| Conclude there is no Snapshot dependency from an empty snapshot list | `snapshot show` returns nothing for an **offline** volume, and the CLI passthrough says why while the object API does not. Online, the same volume reported the held Snapshot as `busy` with `owners: ["volume clone"]` | Bring the volume online before believing a snapshot query |
| Read an empty `GET /api/protocols/s3/buckets` as proof no access point bucket remains | The access point's internal `amazon-fsx-fsvol-*` bucket is not listed there, but still blocks volume deletion and is named in the error | Retry deletion after it clears rather than forcing |
| Create DP volume via ONTAP REST API only | FSx API propagation takes ~30 min. S3 AP not attachable immediately | Use `aws fsx create-volume` for immediate visibility. For FlexCache (ONTAP API only), wait ~30 min |
| Delete VPC Peering before SVM peer deletion | Zombie SVM peer → MISCONFIGURED → difficult recovery | Follow SM-VAL-011 order |
| Periodic full LIST at root | Latency grows with directory size | Prefix-limited or external catalog |
| Assume cloud-only architecture when data gravity favors on-prem processing | Unnecessary egress costs; latency for time-sensitive workloads | Evaluate SnapMirror to on-prem for licensed tool / low-latency scenarios |

---

## Related Documents

- [General S3 AP Design Considerations](s3ap-design-considerations.md)
- [S3 AP Data Collection CloudFormation Template (with DESIGN TIPs)](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/infrastructure/s3ap-data-collection) — Includes Mermaid data distribution decision flow
- [S3 AP + SnapMirror + FlexCache Research](../../integrations/snapmirror-flexcache-multicloud/docs/en/research.md)
- Evidence: [S3AP-DP-ATTACH-002 — serving a live SnapMirror destination (2026-09-13, in-VPC)](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml) · [S3AP-DP-ATTACH-001 — the FSx-API-only first pass](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13/evidence-record.yaml)
- [Demo Guide 07: SnapMirror Cross-Region + S3 AP Re-Attach](../../integrations/snapmirror-flexcache-multicloud/docs/en/demo-guide-07-snapmirror-cross-region.md)
- [Demo Guide 01: FlexCache Same-Region](../../integrations/snapmirror-flexcache-multicloud/docs/en/demo-guide-01-flexcache-same-region.md)
- [AWS Docs: S3 performance best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [NetApp KB: maxdir-size issues](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_do_I_avoid_maxdir-size_issues)
- [NetApp Docs: FlexGroup definition](https://docs.netapp.com/us-en/ontap/flexgroup/definition-concept.html)
- [NetApp Docs: FlexCache hotspot remediation](https://docs.netapp.com/us-en/ontap/flexcache-hot-spot/flexcache-hotspot-remediation-architecture.html)
- [NetApp Blog: FlexGroups and Advanced Data Distribution](https://community.netapp.com/t5/Tech-ONTAP-Blogs/FlexGroups-and-Advanced-Data-Distribution/ba-p/456416)
