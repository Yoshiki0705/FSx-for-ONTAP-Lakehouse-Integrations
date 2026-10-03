# Engine Selection Guide

**English** | [日本語](../ja/engine-selection-guide.md)

> Choose the right analytics engine for your FSx for ONTAP S3 Access Point use case based on cost, governance needs, and AI readiness.

---

## Quick Decision Table

| Primary Question | Recommended Engine | Access Pattern | Governance | AI Readiness | PoC Cost (1 day) |
|---|---|---|---|---|---|
| "Cheapest way to query NAS data" | DuckDB Lambda | Zero-copy | None (IAM only) | Discovery / profiling | ~$0.01 |
| "Serverless SQL, no infrastructure" | Athena | Zero-copy | Glue + Lake Formation | Discovery → curated dataset | ~$0.05 |
| "Need Spark ETL with write-back" | EMR Serverless | Zero-copy (read) + write to FSx for ONTAP | IAM | Curated Parquet / Iceberg creation | ~$0.50 |
| "Need DWH JOINs + enterprise governance" | Redshift Spectrum + Lake Formation | Zero-copy | Lake Formation (column/row/tag) | Governed analytics | ~$1.50 |
| "Need AI on NAS data (summarize, RAG, sentiment)" | Snowflake External Table + Cortex | Zero-copy | Snowflake RBAC + Tags | AI-ready (Cortex AI immediate) | ~$5 |
| "Already use Databricks, need full UC + ML" | DataSync → S3 → UC | With S3 sync | Unity Catalog (full) | Full ML/AI (Mosaic AI, Feature Store) | ~$10 |
| "Can we use Delta/Iceberg on FSx for ONTAP?" | No — read from FSx for ONTAP, write to S3 | Read: zero-copy, Write: S3 | Depends on engine | Depends on engine | ~$0.50 |

---

## When FSx for ONTAP + S3 AP Applies (vs S3-only)

| Consideration | S3 only | FSx for ONTAP + S3 AP |
|---|---|---|
| Existing NFS/SMB workloads | Must migrate or maintain dual paths | No change — existing apps continue on NFS/SMB |
| Storage efficiency | No dedup/compression | ONTAP dedup + compression (1.5–2x typical) |
| Point-in-time recovery | S3 Versioning (per-object, costly at scale) | ONTAP Snapshot (volume-level, instant, space-efficient) |
| Dev/test data provisioning | Full copy required | FlexClone (instant zero-copy clone) |
| Multi-protocol access | S3 only | NFS + SMB + S3 on same data simultaneously |
| Application changes needed | Yes (rewrite to S3 SDK) | No (NFS/SMB unchanged, S3 AP is additive) |

---

## Architecture Patterns by Engine

### Pattern A: Read-Only Analytics (Athena, DuckDB, Redshift Spectrum)

```
Analytics Engine → (S3 API) → S3 Access Point → FSx for ONTAP Volume
```

- Register as External Table / External Stage
- Query Parquet, CSV, JSON, ORC files directly
- No write-back to FSx for ONTAP required

### Pattern B: Read-Write ETL (EMR Spark, Glue)

```
FSx for ONTAP → S3 AP → EMR/Glue (transform) → S3 AP → FSx for ONTAP (curated)
```

- Raw → Bronze → Silver → Gold (Medallion)
- Write-back works for Parquet/CSV (not Delta/Iceberg format)

### Pattern C: External Platform with S3 AP ARN (Snowflake)

```
Snowflake → External Stage (AWS_ACCESS_POINT_ARN) → S3 AP → FSx for ONTAP
```

- Requires explicit AP ARN in stage configuration
- Full SELECT + External Table support verified

### Pattern D: Sync-Based (Databricks)

```
FSx for ONTAP → DataSync → S3 → Unity Catalog (Delta tables)
```

- Used when the platform cannot directly consume S3 AP ARN
- Adds latency (sync interval) but enables full platform features

### Pattern E: OpenSharing (Zero-Copy Governed Access) — Under Analysis

```
FSx for ONTAP → OpenSharing Server → Catalog → Lakehouse Compute
```

- Presigned-URL sharing model may bypass S3 AP ARN limitations
- See [OpenSharing Integration Analysis](opensharing-integration-analysis.md)

---

## Open Table Format Considerations

FSx for ONTAP S3 Access Points do **not** support conditional writes (`If-None-Match`). This means:

| Format | Read | Write |
|---|---|---|
| Delta Lake | Works | Returns HTTP 501 |
| Apache Iceberg | Read of pre-existing tables expected to work | Fails (S3FileIO cannot handle AP alias for metadata) |
| Apache Hudi | Expected to work | Expected to have similar write limitations |

**Recommended approach**: Read source data from FSx for ONTAP via S3 AP, write managed tables to native S3.

### Multi-Platform Bridge via Iceberg

For environments using both Snowflake and Databricks, open Iceberg format enables cross-platform sharing:

```
FSx for ONTAP (source) → S3 AP / DataSync → S3 → Snowflake Managed Iceberg Table
                                                          ↓
                                                Same Iceberg on S3
                                                          ↓
                                    Databricks UC / Athena / EMR (read Iceberg)
```

No vendor lock-in. Data ownership retained. Each platform applies its own governance layer.

---

## Cost Comparison Summary

| Engine | Monthly cost (idle) | Per-query cost | Best for |
|---|---|---|---|
| DuckDB Lambda | $0 | ~$0.00001 | Ad-hoc exploration, profiling |
| Athena | $0 | $5/TB scanned | Serverless SQL, infrequent queries |
| EMR Serverless | $0 | ~$0.05/job (small) | ETL, Spark workloads |
| Redshift Spectrum | Cluster cost | $5/TB scanned | Enterprise DWH with governance |
| Snowflake | Credit-based | ~$2/credit | Multi-cloud, AI/Cortex |
| Databricks (via DataSync) | Cluster/Serverless | DBU-based | Full ML/AI platform |

For detailed cost modeling, see [Cost Estimation](../adoption-guide/cost-estimation.md).

---

## Related Resources

- [Compatibility Matrix](compatibility-matrix.md) — Detailed platform support status
- [Architecture](architecture.md) — Full system architecture
- [Industry Solution Catalog](industry-solution-catalog.md) — 26 industries with recommended patterns
- [PoC Execution Guide](../implementation-guide/poc-execution-guide.md) — Step-by-step deployment
