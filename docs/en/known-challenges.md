🌐 **English** | [日本語](../ja/known-challenges.md)

# Known Challenges, by Originating Layer

> Compiled 2026-08-06 from the records in [`verification-pack/`](../../verification-pack/).
> This page groups every known problem by **where it comes from**, because that determines
> who can fix it and whether a workaround is even possible.
>
> Related pages: [blocker tracker](./blocker-tracker.md) lists what is known not to work.
> [Unverified inventory](./unverified-inventory.md) lists what is untested.
> [Compatibility matrix](./compatibility-matrix.md) is the per-engine reference.
> This page is the analysis that connects them.

## Why layer matters

"FSx for ONTAP S3 Access Points do not support Lakehouse writes" is a claim this
repository can no longer make. Iceberg writes through Athena and the Glue Data
Catalog work end to end, verified 2026-08-06. Delta Lake writes do not. Both run
against the same Access Point.

The difference is not the storage. It is **where the table format keeps its commit
pointer**. Iceberg keeps it in the catalog, so the commit is a conditional update
in Glue. Delta keeps it in `_delta_log` on the object store, so the commit needs a
conditional write on the object store itself — which returns HTTP 501.

That distinction only becomes visible once problems are sorted by layer. Sorted by
engine, it looks like a list of unrelated failures.

| Layer | Who can change it | Problems originating here |
|---|---|:---:|
| 1. S3 API surface of the Access Point | AWS (with NetApp) | 8 |
| 2. FSx managed-service boundary over ONTAP | AWS | 3 |
| 3. Table format specifications | Apache / Delta projects | 2 |
| 4. Engine implementations | Each engine vendor | 7 |
| 5. Network path | Adopter's own design | 2 |
| 6. Governance surfaces | AWS / platform vendors | 2 |

---

## Layer 1 — The S3 API surface of the Access Point

These are gaps between what the Access Point implements and what Amazon S3
implements. No amount of engine configuration works around them.

| # | Gap | Observed behaviour | Downstream effect | Workaround |
|---|---|---|---|---|
| 1.1 | Conditional writes (`If-None-Match`) | HTTP 501 `NotImplemented`. Confirmed as a product-level limitation, 2026-05-22 | Delta Lake and Hudi commits impossible. Iceberg unaffected when the catalog holds the pointer | Iceberg via Athena + Glue, or write to standard S3 |
| 1.2 | Upload checksums are not returned in the response | AWS documents this: unlike a general purpose bucket, the checksum value "is not stored in the FSx for NetApp ONTAP volume as object metadata and the object itself", so "checksum values are not returned in the response". The ETag is also documented as **not** an MD5 digest. A client that validates its computed checksum against the response cannot complete that step, and fails **after the write has landed** | Snowflake `COPY INTO @stage` fails while leaving a complete object behind ([BLK-009](./blocker-tracker.md)). Its error text points at encryption type (`aws:fsx` is neither `AWS_SSE_S3` nor `AWS_SSE_KMS`), which is the remediation hint rather than the mechanism | Do not unload to an Access Point |
| 1.3 | S3 Event Notifications | Not emitted | No Snowpipe auto-ingest, no Auto Loader notification mode, no EventBridge trigger | DataSync → standard S3, scheduled polling, or the ONTAP native audit log. **FPolicy is not a substitute**: writes arriving through the access point raise no notification (measured 2026-08-26, ONTAP 9.18.1P3D1) |
| 1.4 | Object Versioning | Not supported. `ListObjectVersions` returns `VersionId="null"` | No S3-native version history | ONTAP Snapshot for point-in-time recovery |
| 1.5 | Max single upload 50 GB | Objects larger than this can be downloaded but not uploaded. Multipart supported | Large-object writes need multipart | Chunk output files; target 128–256 MB anyway for scan efficiency |
| 1.6 | No Lifecycle policies, Object Lock, S3 Select, Cross-Region Replication | Not supported | Retention and tiering cannot be expressed in S3 terms | FabricPool tiering, SnapLock, query engines instead of S3 Select |
| 1.7 | Same region and same account required | Access Point must sit with the file system | No cross-account or cross-region Access Point topology | Share at the analytics layer instead of the storage layer |
| 1.8 | Presigned URLs officially unsupported | They work in practice, because presigning is a client-side signature and the server sees an ordinary signed request. AWS documents them as unsupported and does not guarantee stability | Anything built on them is unsupported | Do not depend on them in production |

**Minimum version**: ONTAP 9.17.1 for Access Points at all; 9.16.1 for multipart upload.

> **Note on 1.1 and 1.2 together**: these are the two gaps that produce residue
> rather than clean refusals. See [the partial-write hazard](#the-partial-write-hazard-two-causes-one-symptom).

---

## Layer 2 — The FSx managed-service boundary over ONTAP

ONTAP implements these. FSx for ONTAP does not expose them. The capability exists
in the product but not in the managed service.

| # | Gap | Observed behaviour | Effect |
|---|---|---|---|
| 2.1 | SnapMirror S3 disabled | `snapmirror object-store show` → `"object-store" is not a recognized command` at admin, advanced and diagnostic privilege. `/api/cloud/targets` → `not authorized for that command`. Tested on ONTAP 9.17.1P6. The `Continuous` SnapMirror policy exists in the system but cannot be referenced | ONTAP-native S3 replication unavailable. AWS DataSync (NFS → S3) is the only verified sync mechanism. On-premises ONTAP supports this from 9.10.1+, so migration plans that assume it need revising |
| 2.2 | One object-store server per SVM | `vserver object-store-server create` on an SVM that already has Access Points → `Only one object store server is supported per Vserver`. Access Points install an internal object-store server that `show` does not display | An SVM cannot host both Access Points and a native ONTAP S3 bucket. Structural, not a timing issue — use a separate SVM |
| 2.3 | Name-service stack sits in the S3 data path | If an SVM has DNS servers configured for AD membership and those become unreachable, **every Access Point on that SVM times out** — even with UNIX security style volumes, permissive export policies, and an `AVAILABLE` Access Point lifecycle state | An unrelated AD or DNS outage presents as an S3 storage outage. Diagnosis lands in the wrong layer. See [networking considerations](./fsx-ontap-s3ap-networking.md) |

---

## Layer 3 — Table format specifications

Nothing here is an FSx for ONTAP defect. These are consequences of how each format
defines a commit, interacting with gap 1.1.

| Format | Commit mechanism | Result on an Access Point | Status |
|---|---|:---:|---|
| Apache Iceberg | Current-metadata pointer held in the catalog. Commit is an atomic update in Glue | ✅ Works | Verified 2026-08-06 via Athena + Glue: CREATE, INSERT, UPDATE, DELETE, time travel, `OPTIMIZE`, `VACUUM`, and two concurrent commits all succeeded, with data and metadata both on the Access Point |
| Delta Lake | Commit log in `_delta_log/` on the object store. Needs put-if-absent — the log file must be created only if not already present | ❌ Fails **in the default configuration** | `Server returned non-2xx status code: 501 Not Implemented` on the initial commit file (delta-rs 1.2.1, 2026-05-23). Read path works normally. See the note below on `S3DynamoDBLogStore`, which is untested here |
| Apache Hudi | Timeline requires atomic rename (`.inflight` → `.commit`) | ❓ **Not tested** | The recorded conclusion is a deduction from the Delta result plus Hudi's architecture, not a measurement. An attempted EMR run did not proceed because the Hudi catalog plugin was absent from the default EMR 7.1.0 configuration. Tracked as UNV-023 |

> Hudi is the one entry in this document where the repository states a conclusion it
> did not measure. The reasoning is sound — the same atomic-rename requirement, the
> same missing primitive — but it is inference. It is listed here as inference.

### Delta Lake: the requirement is put-if-absent, and it can be externalised

Worth separating, because "Delta cannot write here" is easy to over-read.

What Delta needs is not specifically an S3 conditional write. It is put-if-absent on
the commit file. The Delta project has stated this requirement since 2019:
[delta-io/delta#39](https://github.com/delta-io/delta/issues/39) records that the S3
filesystem "does not provide a way to perform 'put if absent', hence multiple
concurrent writers can easily commit the same version file multiple times". The
[multi-cluster writes post](https://delta.io/blog/2022-05-18-multi-cluster-writes-to-delta-lake-storage-in-s3/)
describes the commit as creating a log file "only if it is not already present".

Amazon S3 gained `If-None-Match` conditional writes in
[August 2024](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-s3-functionality-conditional-writes/),
and FSx for ONTAP S3 Access Points have not received parity. But Delta shipped a
different answer to the same problem two years earlier: **`S3DynamoDBLogStore`**,
added in Delta Lake 1.2, moves the put-if-absent decision into a DynamoDB conditional
write instead of relying on the object store
([storage configuration](https://docs.delta.io/latest/delta-storage.html)).

That is structurally the same trick Iceberg uses with the Glue Data Catalog, which is
why Iceberg writes work here. So the honest statement is:

| Configuration | Status here |
|---|---|
| Default `LogStore` on `s3a://` | ❌ Measured failing — 501 on the commit file |
| `S3DynamoDBLogStore` with a DynamoDB commit table | ❓ **Untested.** Mechanically it should not need a conditional write on the Access Point. Not run, so not claimed |
| `delta-rs` with `AWS_S3_ALLOW_UNSAFE_RENAME=true` | ❓ Untested, and it is named "unsafe" for a reason — it removes the concurrency protection rather than providing it. Single-writer only, if at all |

Until the middle row is measured, treat Delta writes on an Access Point as unavailable
in practice. The point of recording this is that the ceiling is a configuration that
has not been tried, not a proven impossibility.

---

## Layer 4 — Engine implementations

Same Access Point, same S3 API. These failures come from how each engine's client
code handles an Access Point alias, or from constraints unrelated to storage.

| # | Engine | Problem | Verbatim symptom | Workaround |
|---|---|---|---|---|
| 4.1 | EMR Serverless (Iceberg write) | S3FileIO does not handle the Access Point alias during metadata write | `java.lang.NullPointerException: Cannot invoke "org.apache.iceberg.TableMetadata.metadataFileLocation()" because "metadata" is null` | Use Athena for Iceberg writes — the same table format succeeds there |
| 4.2 | Databricks Unity Catalog | Registration succeeds; the read is what fails, because the down-scoped session policy Unity Catalog issues is written with a bucket-form ARN (demonstrated here 2026-08-12) | `UC_CLOUD_STORAGE_ACCESS_FAILURE` on `CREATE TABLE` | DataSync → standard S3 → External Location ([BLK-001](./blocker-tracker.md)) |
| 4.3 | Databricks Unity Catalog | `iceberg_rest` is not an accepted Connection Type, so S3 Tables cannot be referenced as a Foreign Catalog | `CONNECTION_TYPE_NOT_SUPPORTED` (2026-05-31) | Glue HMS Federation (`CREATE CONNECTION TYPE glue`) is a GA path |
| 4.4 | Databricks Runtime | The runtime seccomp profile prohibits `mount` and `umount`, so NFS/SMB cannot be mounted from a cluster | — | Intentional security design; no resolution expected. Use the network paths instead |
| 4.5 | Snowflake | A Dynamic Table cannot select from an External Table | `Object ref EXT_FMT_JSON of type EXTERNAL_TABLE not supported in Dynamic Table definition` | `COPY INTO` a standard table first, then define the Dynamic Table over that. Verified working 2026-08-06 |
| 4.6 | Snowflake | An inline `FILE_FORMAT` is not accepted in the stage table-function form | — | Use a named `FILE FORMAT` object. Snowflake syntax, not an Access Point limitation |
| 4.7 | ClickHouse | `s3()` cannot receive an STS session token, so temporary credentials cannot be used | `UNKNOWN_SETTING: s3_session_token is neither a builtin setting` (v26.5.1) | IAM user long-term keys, or an EC2 Instance Profile via IMDS |
| 4.8 | Databricks FILE type (Beta) | `FILE EXTERNAL` stores references only for files inside a Unity Catalog volume, and a UC external volume cannot be created on an Access Point, so ONTAP-resident files cannot be referenced without copying | — (structural; documented restriction rather than a runtime error) | `FILE MANAGED`, which copies bytes into UC-managed storage — and then object tags are no longer readable. [Evaluation](./databricks-file-type-evaluation.md) |
| 4.9 | Access Point object tags | Tag keys and values at U+0100 and above are rejected for most strings but accepted for a few, deterministically per string, with no rule inferable from outside | `InvalidTag: The TagValue you have provided is invalid` | Restrict object tags to ASCII; keep localised text in the metadata table. Raised with AWS ([evidence](../../verification-pack/s3ap-object-tagging/evidence/2026-08-12/evidence-record.yaml)) |

### Not an Access Point problem, but it will look like one

| Symptom | Actual cause |
|---|---|
| Spark, Glue or EMR cannot read Parquet that Athena and DuckDB read fine | Nanosecond timestamps. pandas and DuckDB `COPY TO` emit `TIMESTAMP(NANOS)` by default; Spark 3.3+ rejects it. Generate microsecond timestamps for cross-engine data |
| Redshift Serverless is slower than Athena on identical data | Serverless cold start. 5M rows: 4,277 ms versus 2,196 ms (2026-05-23) |

---

## Layer 5 — Network path

Both of these are decisions the adopting team makes, not service defects. They are
here because they are the most common first-hour failure.

| # | Problem | Mechanism | Resolution |
|---|---|---|---|
| 5.1 | VPC-attached compute times out against an internet-origin Access Point | The alias resolves to `s3-r-w.<region>.amazonaws.com`, which may not be in the S3 prefix list that an S3 Gateway Endpoint uses. The Gateway Endpoint intercepts the traffic and fails to route it | Place the compute outside the VPC, route through a NAT Gateway, or use a VPC-origin Access Point with an S3 Interface Endpoint |
| 5.2 | Athena, EMR Serverless and Redshift Spectrum cannot use VPC-origin Access Points | They run on AWS-managed infrastructure outside the adopter's VPC | Internet-origin Access Point is required for these engines |

> **`HeadBucket` is not a health check.** It succeeds at the S3 layer without
> touching the file system, so it returns 200 even when data operations fail. Probe
> with `ListObjectsV2 --max-keys 1` instead.

---

## Layer 6 — Governance surfaces

| # | Problem | Effect | Workaround |
|---|---|---|---|
| 6.1 | Lake Formation column-level permissions are not implemented for S3 Tables federated catalogs | Table-level grants work; column masking does not | Put tables needing column-level control on ordinary Glue Catalog tables over general-purpose S3 |
| 6.2 | Unity Catalog governance cannot reach Access Point data | Lineage, tags, masks and row filters do not apply to FSx for ONTAP data directly. This follows from 4.2 | DataSync → standard S3 → External Location. Costs roughly $27/month/TB in transfer and storage against the governance gained |

---

## The partial-write hazard: two causes, one symptom

This is the finding with the largest operational consequence, and it is easy to
miss because the two causes sit in different layers.

Both produce the same shape: **the statement reports failure, and a complete or
partial object remains on the Access Point.**

| Cause | Layer | What is left behind |
|---|---|---|
| Delta commit hits the 501 (gap 1.1) | 1 | Delta writes Parquet first and commits second, so the data files stay with no `_delta_log`. Each retry adds more. Observed 2026-08-06: four prefixes with orphaned data files, one holding three files written a minute apart |
| Unload fails checksum validation (gap 1.2) | 1 | A complete, valid object. Measured: 25 bytes, valid gzip, correct content, `ServerSideEncryption: aws:fsx`. The statement failed in 479 ms |

A caller that treats a failed statement as "nothing happened" will be wrong in both
cases. Sweep for the residue with:

```bash
./shared/scripts/check_orphaned_unload_objects.py --access-point <alias>
```

It reports prefixes holding engine output with no completion marker
(`_SUCCESS`, `_delta_log/`, `_committed_*`) — the storage-side signature of an
interrupted write.

> Setting `ENCRYPTION=(TYPE='AWS_SSE_S3')` on a Snowflake stage does not fix 1.2. It
> replaces a fast failure with a hang: cancelled after 2 m 54 s, nothing written.

---

## What was withdrawn

Two claims this repository previously made did not survive measurement. They are
recorded because a withdrawn claim is also a result.

| Claim | What happened |
|---|---|
| ListObjectsV2 is 30–80x slower than native S3 | Re-measured 2026-08-05: **0.9–1.4x** for 10 to 5,000 objects, flat and nested layouts alike. The 30–80x figure did not reproduce and the origin was not determined. Behaviour above 5,000 objects in one directory remains unmeasured, and ONTAP sorts directory entries in memory, so file consolidation and partition structure remain sound design practice — just not because of a measured penalty at small scale |
| Snowflake external stages are read-only by design | Wrong, and it concealed 1.2. The write is not refused. It lands, then fails validation |
| Concurrent Iceberg writes risk corruption on an Access Point | That was inference, not measurement. Two concurrent Athena commits produced the correct row count with no lost update. A two-writer test is not a concurrency limit, but it does show the risk is not categorical |

---

## Where the boundaries of current knowledge are

Twenty-two items are untested; see the [unverified inventory](./unverified-inventory.md).
The three that most affect how the verified results should be read:

| Gap | Why it matters |
|---|---|
| Every Iceberg and Snowflake result used single-digit row counts | Manifest growth, compaction cost and partition evolution at realistic table size are unmeasured (UNV-021) |
| The Athena concurrency run was cache-resident | 25/25 queries succeeded and full scans degraded about 2x, but roughly 389 MB/s aggregate moved through a file system provisioned at 128 MBps. Caching did significant work. This is evidence that concurrency is not a failure mode up to 25, not a throughput model (UNV-022) |
| Hudi has never been run | See layer 3 |

---

## Reading this alongside the other pages

| If you want | Read |
|---|---|
| Whether a specific engine and operation works | [Compatibility matrix](./compatibility-matrix.md) |
| The status and workaround for a specific known failure | [Blocker tracker](./blocker-tracker.md) |
| What has not been tested, and what it would take | [Unverified inventory](./unverified-inventory.md) |
| Whether the pattern fits at all | [Adoption assessment](../adoption-guide/adoption-assessment.md) |
