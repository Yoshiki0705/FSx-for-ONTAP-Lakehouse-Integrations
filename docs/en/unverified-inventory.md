# Unverified Item Inventory

🌐 **English** | [日本語](../ja/unverified-inventory.md)

> Compiled 2026-08-06. Every claim in this repository that is **not** backed by a recorded run, with what blocks it.

This exists so the gaps are countable. A claim marked ⚠️ or 🔲 in the [compatibility matrix](./compatibility-matrix.md) should appear here; if it does not, the matrix is ahead of this page and this page is wrong.

Things that are known **not** to work are tracked separately in the [blocker tracker](./blocker-tracker.md). This page is about the unknown, not the broken.

**Total: 24 items.** Two were added and closed the same day on 2026-09-13 (UNV-031, UNV-032 — serving a live SnapMirror destination through an access point). One closed on 2026-08-12 (UNV-030, FILE-column sharing). Five were closed on 2026-08-06 — see Recently closed.

## Summary

| Blocked by | Items | Meaning |
|---|:---:|---|
| Feasible now, not yet run | 12 | Only AWS services this project already uses. These are the realistic next candidates. |
| Needs a Snowflake session | 1 | Credentials are not held in this repository. These are runnable in a single sitting once signed in. |
| Needs a Databricks workspace | 5 | The workspaces used in May 2026 were torn down. Note that BLK-001 blocks the Unity Catalog path regardless. |
| Needs another engine deployed | 3 | No ClickHouse instance is running. |
| Blocked by account tier or cost | 1 | Requires a paid tier or chargeable resource. |
| Blocked by elapsed time | 1 | Cannot be compressed. |
| Not verifiable | 1 | Depends on something unreleased. |

## Feasible now, not yet run

Only AWS services this project already uses. These are the realistic next candidates.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| Snowflake | Managed Iceberg Table write, end to end (COPY INTO from an AP-backed stage) | Verified — External Volume passed all checks, table created, rows loaded and read back, real Iceberg layout on the destination bucket | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Dynamic Table over Access Point data | Verified with a constraint — `TARGET_LAG='60 seconds'` and `REFRESH_MODE=FULL` behave as specified, but a Dynamic Table cannot select from an EXTERNAL TABLE, so the stage must be landed into a standard table first | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Snowpark `SnowflakeFile.open` on an AP-backed stage | Verified — returned the file contents | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Read JSON, Avro and ORC from an AP-backed stage | Verified — identical content in all three formats returned identical rows | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | COPY INTO unload back to the Access Point | **Does not work, and the reason recorded here was wrong.** The write is not refused: the object lands intact and Snowflake then fails the statement on checksum validation because FSx for ONTAP reports encryption as `aws:fsx`. A complete object is left behind — a partial-write hazard | [2026-08-06](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| UNV-012 | Databricks | No automated tests exist for the integration (`integrations/databricks/tests/` holds only `.gitkeep`) | Test authoring. Snowflake has 8 test files; Databricks has none. |
| UNV-016 | EMR Serverless | Iceberg write commit | An EMR Serverless run. Recorded as failing with a NullPointerException in S3FileIO; the failure is noted but no evidence record exists. |
| UNV-017 | AWS Glue ETL | Delta Lake write commit protocol | A Glue job run. Expected to fail for the same reason Delta fails elsewhere. |
| UNV-018 | AWS Glue ETL | Iceberg write with concurrent writers | Two simultaneous Glue jobs against one table. |
| UNV-019 | AWS Glue ETL / EMR Spark | Iceberg REST Catalog against S3 Tables | A job configured with the REST catalog. Inferred from the PyIceberg result. |
| UNV-020 | Redshift Spectrum | Glue federated catalog path to S3 Tables | A Redshift Serverless workgroup and a federated catalog. The plain Glue-table path over the AP is verified (2026-05-23). |
| UNV-021 | Athena | Iceberg at realistic table size — manifest growth, compaction cost, partition evolution | A larger dataset. The 2026-08-06 run used a single-digit row count. |
| UNV-022 | Athena | Concurrency above 25, and working sets larger than the ONTAP cache | A dataset well beyond cache size and a higher concurrency sweep. The 2026-08-06 run was cache-resident. |
| UNV-023 | Hudi | Any operation on an FSx for ONTAP S3 AP | A Hudi-capable engine. Listed under BLK-002 but never tested. |
| UNV-025 | FSx for ONTAP | ListObjectsV2 latency above 5,000 objects | A larger object population. The 2026-08-05 measurement covered 10 to 5,000 objects. |
| UNV-026 | Bedrock | Whether the Managed Knowledge Base S3 connector accepts an S3 AP URI (the traditional Knowledge Base path is verified) | A Managed Knowledge Base run. |
| UNV-027 | Tooling | PyIceberg wheel on macOS Apple Silicon | A run on that platform. A wheel exists; this project has not exercised it. |
| ~~UNV-031~~ | FSx for ONTAP | ~~Whether an S3 access point can serve a SnapMirror destination while replication continues~~ | **Closed 2026-09-13: both routes work.** Mounting the DP destination through ONTAP gives a read-only access point that stays current — a later transfer was readable through it in 15 s, relationship still `snapmirrored`. A clone of the destination Snapshot gives a **writable** access point frozen at that Snapshot. The FSx API's refusal measured earlier was an FSx control-plane restriction only. [Evidence](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml), SM-VAL-013 |
| ~~UNV-032~~ | FSx for ONTAP | ~~Whether SM-VAL-009's ~30 min propagation applies to FlexClones, deciding if "clone then query" is minutes-scale~~ | **Closed 2026-09-13: it is not minutes-scale, but it is faster than 30 min.** FSx reported the clone at **1011 s** and the ONTAP-mounted DP volume at **2298 s**; the ONTAP operations themselves took seconds, and attachment 32 s. First-time setup is tens of minutes, dominated by propagation; steady-state freshness on the DP route is seconds. Two samples, one file system — not a calibrated range. [Evidence](../../verification-pack/s3ap-dp-volume-attachment/evidence/2026-09-13-in-vpc/evidence-record.yaml) |

## Needs a Snowflake session

Credentials are not held in this repository. These are runnable in a single sitting once signed in.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-004 | Snowflake | Horizon Catalog governance (row access policies, masking) enforced on external engines reading the Iceberg table | A Snowflake session and a second engine configured against the Horizon catalog. |

## Needs a Databricks workspace

The workspaces used in May 2026 were torn down. Note that BLK-001 blocks the Unity Catalog path regardless.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-009 | Databricks | Iceberg REST Catalog from a Databricks Spark cluster (`spark.sql.catalog.s3tables`) | A Databricks workspace with a Spark cluster. Inferred from the EMR mechanism; no run. |
| UNV-010 | Databricks | Executor-scale boto3 access from a customer-managed VPC | A customer-managed-VPC workspace. The Databricks-managed VPC case is recorded as failing (egress to FSx blocked); the customer-VPC case is untested. |
| UNV-011 | Databricks | 16 of the 18 cases in `verification-pack/databricks/test-cases.yaml` have no recorded run | A workspace matching each case's preconditions. |
| UNV-028 | Databricks | Whether a `FILE MANAGED` FileSpace may be an **external** volume | **Partly closed 2026-08-12.** Table creation for both `FILE MANAGED` and `FILE EXTERNAL` is verified. **Correction to the first pass:** it said a FileSpace need not be a dedicated volume, on the strength of `CREATE TABLE` succeeding. Re-tested the same day with the `INSERT` that actually exercises it: pointing the FileSpace at the volume holding the source files fails with `Cannot get file metadata under managed storage`. A dedicated volume is required in practice. The external-volume question itself is untested. [Evidence](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml) |
| UNV-029 | Databricks | `_object_metadata.tags` against an FSx for ONTAP S3 AP path (DBR 18.2+) — the object-tag bridge | **Run 2026-08-12 with the native-S3 control; still open, one step further along.** The control returns populated `tags` and `user_metadata`. Through the Access Point the read is refused before it reaches the tag code: UC's down-scoped session policy uses bucket-style ARNs while AWS authorises access-point requests against the access point ARN. Answering the original question now depends on a Databricks-side change, not on our environment. Cases `DBX-FILE-041a…041e`. [Evidence](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml) |
| ~~UNV-030~~ | Databricks | ~~Whether a table containing a `FILE` column can be shared via OpenSharing~~ | **Closed 2026-08-12: yes.** Both `FILE EXTERNAL` and `FILE MANAGED` tables were accepted into a share (`ENABLED`). Recipient-side reading remains untested. [Evidence](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record.yaml) |

## Needs another engine deployed

No ClickHouse instance is running.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-013 | ClickHouse | `s3()` table function reading Parquet directly from an FSx for ONTAP S3 AP | A ClickHouse instance with IAM credentials. |
| UNV-014 | ClickHouse | `iceberg()` table function plus Glue Catalog integration | ClickHouse 23.8+ and a Glue-catalogued Iceberg table. |
| UNV-015 | ClickHouse | S3Queue engine ingesting from a standard S3 bucket fed by DataSync | A ClickHouse instance. Direct S3Queue against the AP is blocked by BLK-003 (no event notifications). |

## Blocked by account tier or cost

Requires a paid tier or chargeable resource.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-007 | Snowflake | PrivateLink connectivity to an AP-backed stage | A Snowflake Business Critical account or higher, plus PrivateLink setup. |

## Blocked by elapsed time

Cannot be compressed.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-003 | Snowflake | COPY INTO 64-day load-history deduplication | A Snowflake session and 64 days of elapsed time. Cannot be shortened; the window is a Snowflake-side retention period. |

## Not verifiable

Depends on something unreleased.

| ID | Area | Unverified claim | What it would take |
|---|---|---|---|
| UNV-024 | FSx for ONTAP | Behaviour on ONTAP 9.18.1 and later | The release. Cannot be verified today. |

## Recently closed

Items that were on this list and have since been measured.

| Area | Claim | Result | Evidence |
|---|---|---|---|
| Athena | Iceberg read **and write** on an FSx for ONTAP S3 AP | Verified — full lifecycle including UPDATE, DELETE, time travel, OPTIMIZE, VACUUM and two concurrent commits | [2026-08-06](../../verification-pack/athena-iceberg/evidence/2026-08-06/evidence-record.yaml) |
| Athena | High-concurrency scans (10-50 analysts) | Verified to 25 concurrent; 25/25 succeeded, full scans degraded ~2x, queue time under 200 ms. Dataset was cache-resident | [2026-08-06](../../verification-pack/athena-concurrency/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake | Whether a synthesized S3 notification triggers a Snowpipe COPY | Verified — ingested ~0.5 s after publish | [2026-08-06](../../verification-pack/snowpipe-pattern-a/evidence/2026-08-06/snowflake-side-verification.yaml) |
| FSx for ONTAP | ListObjectsV2 latency versus native S3 | Re-measured at 1.3-1.4x for 10 to 5,000 objects; the earlier 30-80x figure did not reproduce and is withdrawn | [2026-08-05](../../verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml) |

## How to use this page

When a claim moves from unverified to measured: record the evidence under `verification-pack/<topic>/evidence/<date>/`, update the matrix row to cite it, move the row into **Recently closed** above, and adjust the total.

When a claim is withdrawn rather than verified, say so in the matrix and keep the reason. A withdrawn claim is a result.
