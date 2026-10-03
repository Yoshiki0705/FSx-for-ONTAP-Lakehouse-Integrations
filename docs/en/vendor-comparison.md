# Platform Integration Reference

[日本語](../ja/vendor-comparison.md)

> Framing: This document is a neutral reference summarizing each platform's integration approach, support status, and trade-offs. It is not a ranking of superiority; the goal is to support right-tool-for-the-job selection based on use case.

## Project Concept

Amazon FSx for NetApp ONTAP (FSx for ONTAP) × S3 Access Points × Lakehouse/Data Lake Integrations

A pattern library enabling direct access from Lakehouse/Data Lake platforms to
FSx for ONTAP enterprise storage via S3 Access Points.
Leverages ONTAP deduplication, compression, Snapshot, and tiering while integrating
with modern analytics platforms.

```text
Lakehouse Platform ←→ S3 Access Point ←→ FSx for NetApp ONTAP
(External Table / Stage / Location)         (NFS/SMB/S3 unified storage)
```

---

## Managed Lakehouse Platforms

| Vendor | Integration Method | Use Case | Status |
|--------|-------------------|----------|--------|
| Databricks | Unity Catalog External Location / S3 External Table | Delta Lake on FSx for ONTAP, ML Feature Store | ⚠️ Blocked (session policy; UC table creation fails) |
| Snowflake | External Stage + `AWS_ACCESS_POINT_ARN` / External Table | Governed analytics, Cortex AI, Data Sharing, Managed Iceberg | ✅ Verified (May 2026). [Evidence](../../verification-pack/snowflake/evidence/2026-05-24/evidence-record.yaml) (ap-northeast-1) |

### Databricks

| Item | Detail |
|---|---|
| Auth | Cross-account IAM Role + External ID |
| Network | VPC network origin (recommended) |
| Formats | Delta Lake, Iceberg, Parquet, CSV, JSON, ORC |
| Unstructured | UC Volumes + `read_files()` + `ai_query()` (LLM on images/docs) + `ai_parse_document()` (OCR) |
| AI Capabilities | Mosaic AI (ML training, Feature Store, Model Registry), `ai_query` (LLM on files), `ai_parse_document` (OCR), Vector Search (RAG), MLflow experiment tracking |
| Governance | Unity Catalog (Table/Column Grants, Row Filters, Column Masks, UC Tags, Automatic Lineage (column-level), Audit Logs (system tables), Lakehouse Monitoring) |
| Data Sharing | Delta Sharing (open protocol, readable by Snowflake, Pandas, Spark, Power BI without a Databricks account) |
| ONTAP Value | FlexClone (dev/test), Snapshot (complements Delta Time Travel), FabricPool (cold data tiering) |
| Characteristics | Automatic data lineage (column-level), ML model governance (MLflow + Model Registry), Lakehouse Monitoring, Iceberg REST Catalog (external engine access to UC tables) |
| Limitation | UC session policy blocks table creation and subdirectory listing on FSx for ONTAP S3 Access Points directly. Recommended path: DataSync → S3 → UC (full governance, full AI, full lineage) |

### Snowflake

| Item | Detail |
|---|---|
| Auth | Storage Integration + IAM Role |
| Network | Internet network origin (PrivateLink optional) |
| Formats | Parquet, CSV, JSON, Avro, ORC, Iceberg |
| Unstructured | Directory Table + Pre-signed URLs + Cortex AI (PARSE_DOCUMENT for OCR, multimodal vision via staging) |
| AI Capabilities | 8/10 Cortex AI functions verified on FSx for ONTAP data (SUMMARIZE, TRANSLATE, SENTIMENT, COMPLETE, EXTRACT_ANSWER, PARSE_DOCUMENT, Cortex Search 198ms, Vision AI via staging). [Verification results](../../integrations/snowflake/README.md) |
| Governance | Object Tags, Row Access Policy, Column Masking, Data Sharing (all verified on External Table). [Evidence](../../verification-pack/snowflake/evidence/2026-05-24/evidence-record.yaml) |
| Advanced Patterns | Dynamic Table (confirmed, FULL refresh, min 60s TARGET_LAG), Managed Iceberg Table (confirmed, open format on user-owned S3). [Evidence](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml) |
| ONTAP Value | Snapshot (beyond Time Travel retention), FlexClone (test env), multi-protocol (NFS/SMB/S3 on same data) |
| Data Sharing | Governed distribution to partners/suppliers via Snowflake Data Sharing (External Table shareable) |
| Known Limitation | AUTO_REFRESH not available (no S3 Event Notifications); use Task + ALTER EXTERNAL TABLE REFRESH |

---

## Open Table Formats & Distributed SQL

| Format/Engine | Read from FSx for ONTAP S3 Access Points | Write to it | Write to S3 (via sync) | Status |
|--------------|:---:|:---:|:---:|--------|
| Apache Iceberg | ⚠️ Experimental (pre-existing tables) | Not Supported (NullPointerException) | EMR Spark → S3 | Part 7 verified |
| Delta Lake (OSS) | ✅ Read Verified (delta-rs) | Not Supported (501 Not Implemented) | DataSync → S3 → UC | Part 7 verified |
| Apache Hudi | ⚠️ Not tested | Not Supported (no atomic rename) | Standard S3 path | Part 7 verified |
| Trino / Starburst | ✅ Read Verified (5M rows, 1.5s) | Not supported (same limitations) | N/A | Part 0 verified |
| Dremio | Planned | Planned | N/A | NetApp/Dremio joint solution (not independently validated) |

Key finding (Part 7): all three transactional table formats (Delta, Iceberg, Hudi) fail to write on FSx for ONTAP S3 Access Points because of S3 API limitations: no conditional writes (`If-None-Match` returns 501) and no atomic rename. Reading pre-existing tables is theoretically possible, but only Delta read has been verified. Evidence: [Delta](../../verification-pack/delta-lake-oss-read/evidence/2026-05-23/evidence-record.yaml), [Iceberg](../../verification-pack/iceberg/evidence/2026-05-24/evidence-record.yaml), [Hudi](../../verification-pack/hudi/evidence/2026-05-24/evidence-record.yaml) (ap-northeast-1).

### Apache Iceberg

| Item | Detail |
|---|---|
| Read | Pre-existing Iceberg tables (metadata in Glue Catalog, data files on FSx for ONTAP S3 Access Points) are theoretically readable via GetObject. Not fully validated |
| Write | Not supported. S3FileIO cannot handle the AP alias for metadata write/verify (NullPointerException during commit). Conditional writes not supported |
| Working alternative | EMR Spark writes Iceberg to standard S3 → register in Glue Catalog → query from Athena/Redshift/Snowflake/Databricks. FSx for ONTAP S3 Access Points is the read-only source data |
| Snowflake path | FSx for ONTAP S3 Access Points → External Stage → COPY INTO → Snowflake Managed Iceberg Table (open format on user-owned S3, confirmed May 2026) |
| Catalog options | Glue Catalog (AWS-native), Snowflake Managed Iceberg (Snowflake-native), Databricks UC Iceberg REST Catalog (Databricks-native) |

### Delta Lake (OSS)

| Item | Detail |
|---|---|
| Read | Verified with delta-rs (Rust). Spark Delta reader also works for pre-existing tables. [Evidence](../../verification-pack/delta-lake-oss-read/evidence/2026-05-23/evidence-record.yaml) (ap-northeast-1, 2026-05-23) |
| Write | Not supported. Delta commit protocol requires an `If-None-Match` conditional write for `_delta_log/`, and FSx for ONTAP S3 Access Points returns 501 Not Implemented |
| Working alternative | DataSync → S3 → Delta Table (Databricks UC or OSS Spark). FSx for ONTAP S3 Access Points as read-only source |
| Databricks path | DataSync → S3 → UC Managed Delta Table (full governance, lineage, Time Travel) |

### Apache Hudi

| Item | Detail |
|---|---|
| Read | Not tested (theoretically possible for pre-existing tables via GetObject) |
| Write | Not supported. Hudi timeline commit requires atomic rename (`.inflight` → `.commit`), and S3 has no rename operation |
| Working alternative | Standard S3 bucket for the Hudi write path. FSx for ONTAP S3 Access Points as read-only source |

### Trino / Starburst

| Item | Detail |
|---|---|
| Read | Verified. Trino 481 + Glue Catalog + `hive.s3.path-style-access=true` + explicit `hive.s3.endpoint`. 5M rows in 1.5s. [Evidence](../../verification-pack/trino/evidence/2026-05-26/evidence-record.yaml) (ap-northeast-1, 2026-05-26) |
| Write | Not tested (same S3 Access Points limitations apply for transactional writes) |
| Configuration | Requires `hive.s3.path-style-access=true` and explicit `hive.s3.endpoint` to resolve S3 Access Points aliases. Same pattern as DuckDB |
| Catalog | Glue Catalog (shared with Athena, Redshift, EMR) |

### Dremio

| Item | Detail |
|---|---|
| Auth | IAM Role / Access Key |
| Catalog | Nessie (Git-like catalog) / Arctic |
| Status | NetApp/Dremio joint solution exists. Independent validation in this repo not yet performed |
| NetApp Partnership | Dremio and NetApp announced a joint Hybrid Iceberg Lakehouse solution at NetApp INSIGHT 2024 (Sep 2024). Full deployment guide available at [docs.netapp.com](https://docs.netapp.com/us-en/netapp-solutions/data-analytics/dremio-lakehouse-introduction.html) covering ONTAP S3, NAS, and StorageGRID sources |
| FSx for ONTAP integration | NetApp blog (Jan 2025) documents Dremio Cloud + FSx for ONTAP S3 Access Points as a joint solution for AI-ready analytics on NAS data ([netapp.com](https://www.netapp.com/blog/ai-insights-ontap-s3-access-points-dremio/)) |
| Key capabilities | Iceberg-native query engine, reflections (materialized acceleration), semantic layer, data-as-code (Nessie Git-like versioning) |
| Iceberg interoperability | Dremio writes Iceberg tables that are readable by Snowflake (External Iceberg Table), Databricks (UC Iceberg), Athena (Glue Catalog), EMR, Trino |
| Why not yet validated in this repo | Requires Dremio Cloud or a self-managed Dremio instance. The NetApp/Dremio joint solution documentation provides the reference architecture. This repo may add independent validation in a future phase |

---

## Cloud-Native Analytics (AWS)

| Service | Integration Method | Use Case | Status |
|---------|-------------------|----------|--------|
| AWS Athena | Direct S3 AP query via Glue Catalog | Serverless SQL | ✅ Security Verified |
| AWS Glue | S3 AP Crawler / ETL Job | Data catalog + ETL + write-back | ✅ Functional Verified |
| AWS Lake Formation | Governance on Glue Catalog tables | Fine-grained access (table/column/row/tag) | ✅ Verified (column, row filter, LF-Tag) |
| Amazon Redshift Spectrum | External Schema on Glue Catalog | DWH + Data Lake federated query | ✅ Functional Verified |
| Amazon EMR Serverless | EMRFS (`s3://`) direct access | Spark ETL + write-back | ✅ Functional Verified |
| Amazon Bedrock KB | S3 AP as data source | RAG / document retrieval | ✅ AWS-documented path |
| DuckDB Lambda | httpfs extension + path-style | Lightweight serverless analytics | ✅ Functional Verified |

### AWS Athena

| Item | Detail |
|---|---|
| Auth | IAM Role (service role) |
| Network | Internet network origin required |
| Integration | Serverless, pay-per-query ($5/TB scanned), Glue Catalog integration |
| AI Integration | Athena + Bedrock KB (RAG on same FSx for ONTAP data), Athena + SageMaker (ML inference UDF) |
| Governance | Lake Formation (table/column/row/tag). Same permissions apply to Athena and Redshift Spectrum |
| Write-back | CTAS writes Parquet back to FSx for ONTAP S3 Access Points (verified, 3.7s) |
| Characteristics | Zero infrastructure, shared Glue Catalog with all AWS engines, Lake Formation governance automatic |
| Benchmark | 54.8 MB/s peak (5M rows in 2.2s). [Evidence](../../verification-pack/athena-parquet-read/evidence/2026-05-22/benchmark-result.yaml) (ap-northeast-1, 2026-05-23) |
| Reference | [AWS Tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html) |

### AWS Glue

| Item | Detail |
|---|---|
| Auth | Glue service role |
| Network | Internet network origin required |
| Features | Crawler (schema discovery), ETL Job (PySpark/Python Shell/Ray), Data Quality |
| AI Integration | Glue + Bedrock (AI-powered transforms), Glue Data Quality (automated validation) |
| Governance | Glue Data Catalog is the foundation for Lake Formation. All permissions defined here |
| Write-back | ETL write-back to FSx for ONTAP S3 Access Points (verified, 64s for 10K row medallion pipeline). [Evidence](../../verification-pack/glue-etl/evidence/2026-05-23/evidence-record.yaml) (ap-northeast-1, 2026-05-23) |
| Characteristics | Schema discovery (Crawler), visual ETL (Studio), serverless Spark, Data Quality rules |
| Reference | [AWS Tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |

### AWS Lake Formation

| Item | Detail |
|---|---|
| Auth | Lake Formation admin + per-principal grants |
| Network | N/A (governance layer, not a query engine) |
| Features | Table/column-level grants, Row Filters (Data Cells Filter), LF-Tags (tag-based access control), cross-account sharing |
| AI Integration | Governs data accessed by Bedrock KB, SageMaker, EMR ML workloads |
| Governance | Fine-grained (column/row/tag), multi-engine (Athena + Redshift + EMR + Glue all share the same permissions), zero data movement |
| Characteristics | Single governance definition applies to all AWS analytics engines simultaneously. No per-engine configuration needed. Cross-account table sharing without data copy |
| Verified capabilities (May 2026) | Column-level permission (deny specific columns), Row Filter (Data Cells Filter with expression), LF-Tag (sensitivity classification + tag-based grants). [Evidence](../../verification-pack/lake-formation/evidence/2026-05-26/fine-grained-evidence.yaml) (ap-northeast-1) |

### Amazon Redshift Spectrum

| Item | Detail |
|---|---|
| Auth | Redshift IAM Role with S3 Access Points permissions |
| Network | Internet network origin required |
| Features | DWH + Data Lake federated query, materialized views, stored procedures |
| AI Integration | Redshift ML (CREATE MODEL), federated query to SageMaker endpoints |
| Governance | Lake Formation (same permissions as Athena; configure once, apply everywhere) |
| Write-back | Not possible (query results stay in Redshift; use EMR for write-back) |
| Characteristics | JOIN NAS data with local DWH tables, materialized views on external data, same Glue Catalog as Athena |
| Benchmark | 5M rows in 4.3s (Serverless 8 RPU). [Evidence](../../verification-pack/redshift-spectrum/evidence/2026-05-23/evidence-record.yaml) (ap-northeast-1, 2026-05-23) |
| Reference | [AWS re:Post](https://repost.aws/articles/AR7E4oxFvtR5GgajAQT7X1xQ) |

### Amazon EMR Serverless (Spark)

| Item | Detail |
|---|---|
| Auth | Execution role (IAM) |
| Network | Internet network origin (EMRFS handles S3 Access Points natively) |
| Features | Full Spark SQL, UDFs, window functions, MLlib, distributed processing |
| AI Integration | Spark MLlib, SageMaker Spark connector, Iceberg table creation on S3 |
| Governance | IAM-based (pair with Lake Formation for governed reads on output) |
| Write-back | Flat Parquet to FSx for ONTAP S3 Access Points (verified, 16s total ETL) |
| Characteristics | No session policy issues (direct IAM), full Spark power, write-back to FSx, Iceberg table creation on S3 |
| Benchmark | 10K rows read+transform+write in 16s, $0.05/job. [Evidence](../../verification-pack/emr-spark/evidence/2026-05-23/evidence-record.yaml) (ap-northeast-1, 2026-05-23) |
| Note | Use `s3://` (EMRFS); `s3a://` cannot parse the AP alias |

### Amazon Bedrock Knowledge Bases

| Item | Detail |
|---|---|
| Auth | Bedrock service role with S3 Access Points permissions |
| Network | Internet network origin |
| Features | RAG document ingestion, vector embeddings, permission-aware retrieval |
| AI Integration | Ingest documents from FSx for ONTAP S3 Access Points, create embeddings, semantic search with guardrails |
| Governance | Bedrock guardrails (topic filtering, PII detection, hallucination reduction), IAM model access policies |
| Characteristics | Zero-copy RAG (reads directly from FSx for ONTAP S3 Access Points without COPY INTO), permission-aware retrieval, Bedrock agents for multi-step reasoning |
| Reference | [AWS Tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |

### DuckDB Lambda

| Item | Detail |
|---|---|
| Auth | Lambda execution role (IAM) |
| Network | Internet network origin (no VPC needed) |
| Features | In-process SQL, sub-second warm queries, arm64 (Graviton2) |
| AI Integration | Minimal (SQL-only; pair with Bedrock for AI) |
| Governance | IAM + S3 Access Points policy only (no table-level governance) |
| Write-back | COPY TO Parquet (verified, 304ms) |
| Characteristics | Low-cost path ($0.00001/query), zero idle cost, sub-second warm latency (452ms) |
| Benchmark | 10K rows in 452ms (warm), 5M rows in 779ms. [Evidence](../../verification-pack/duckdb-local/evidence/2026-05-23/evidence-record.yaml) (ap-northeast-1, 2026-05-23) |

### Characteristics of the AWS-native path

These are the properties measured for the AWS-native engines in this repository. They are
stated as characteristics, not as a ranking: several of them are consequences of the
architecture rather than choices, and each has a corresponding trade-off listed in the
engine sections above.

| Characteristic | Detail |
|-----------|--------|
| Direct IAM, no intermediary session policy | AWS services authorise with the caller's own IAM context, so the down-scoped session policy that blocks the S3 Access Points ARN form on managed-platform paths does not apply. Trade-off: no table-level governance unless Lake Formation is added |
| Shared Glue Catalog | Athena, Redshift Spectrum, EMR, Glue all share the same catalog. Register once, query from any engine |
| Lake Formation multi-engine | One governance definition applies to all engines simultaneously. No per-platform configuration |
| Zero-copy RAG | Bedrock KB reads directly from FSx for ONTAP S3 Access Points. No COPY INTO, no staging, no data movement for RAG |
| Serverless-first | Athena, Glue, EMR Serverless and Lambda have no idle cost. Trade-off: per-query pricing makes sustained heavy usage harder to predict than a reserved cluster |
| Write-back verified | EMR, Athena CTAS and DuckDB write flat Parquet back to an FSx for ONTAP S3 Access Points. On the Snowflake and Databricks paths the write goes through a standard S3 stage instead (see their sections for the mechanism) |
| Iceberg on S3 | EMR Spark creates Iceberg tables on standard S3 → registered in Glue Catalog → queryable by Athena/Redshift/Snowflake/Databricks |

### Google BigQuery Omni

| Item | Detail |
|---|---|
| Auth | S3 Connection (IAM Role) |
| Network | Internet network origin |
| Features | Cross-cloud analytics, BigLake tables |
| Unstructured | Object Table for image/video metadata |

### Microsoft Fabric / Synapse

| Item | Detail |
|---|---|
| Auth | S3 Shortcut (Access Key / IAM Role) |
| Network | Internet network origin |
| Features | OneLake integration, Power BI connectivity |
| Unstructured | File access via OneLake Shortcut |

---

## Emerging & Specialized Platforms

| Vendor | Integration Method | Use Case | Status |
|--------|-------------------|----------|--------|
| Firebolt | S3 External Table | High-speed OLAP | Research |
| ClickHouse | S3 Table Function | Real-time analytics | Research |
| DuckDB | S3 httpfs Extension | Edge/Lambda analytics | ✅ Functional Verified |
| Apache Spark (Self-managed) | S3A FileSystem | Custom Spark cluster | Research |
| Presto / PrestoDB | Hive Connector + S3 | Distributed query | Research |

### DuckDB

| Item | Detail |
|---|---|
| Auth | Access Key / IAM Role (Lambda execution role) |
| Network | VPC network origin possible |
| Features | In-process analytics, runs inside Lambda, lightweight |
| Unstructured | Parquet/CSV only (no binary support) |
| Use Case | Lightweight analytics in Lambda, edge computing |

### ClickHouse

| Item | Detail |
|---|---|
| Auth | Access Key |
| Network | Internet network origin |
| Features | Columnar, real-time analytics, high-speed aggregation |
| Unstructured | Not supported (structured data only) |

### Firebolt

| Item | Detail |
|---|---|
| Auth | IAM Role |
| Network | Internet network origin |
| Features | High-speed OLAP, sub-second queries |
| Unstructured | Not supported |

---

## Unstructured Data Support Matrix

| Platform | Images | Video | Audio | Documents | Method |
|----------|--------|-------|-------|-----------|--------|
| SageMaker | ✅ | ✅ | ✅ | ✅ | Direct S3 AP read |
| Bedrock | ✅ | Not supported | Not supported | ✅ | Knowledge Base (RAG) |
| Rekognition | ✅ | ✅ | Not supported | Not supported | Direct S3 AP read |
| Transcribe | Not supported | Not supported | ✅ | Not supported | Direct S3 AP read |
| Textract | ✅ | Not supported | Not supported | ✅ | Direct S3 AP read |
| Lambda | ✅ | ✅ | ✅ | ✅ | S3 AP read/write |
| Databricks | ✅ | ✅ | ✅ | ✅ | binaryFile format |
| Snowflake | ✅ | ✅ | ✅ | ✅ | Directory Table + Pre-signed URLs |
| EMR Spark | ✅ | ✅ | ✅ | ✅ | binaryFile / custom |
| Athena | Not supported | Not supported | Not supported | Not supported | Structured data only |
| BigQuery Omni | ✅ | ✅ | Not supported | Not supported | Object Table |

Legend: ✅ = direct processing / metadata only / not supported.

---

## Network Origin Requirements

| Network Origin | Supported Platforms |
|---------------|-------------------|
| VPC origin | Databricks, EMR, Lambda, DuckDB (in Lambda) |
| Internet origin | Athena, Glue, Redshift Spectrum, Snowflake, BigQuery Omni, Fabric |

VPC origin allows access only from within the same VPC (more secure). Internet origin is protected by IAM auth (broader service compatibility).

---

## Selection Guide

### Structured Data Analytics

```text
High-frequency queries + governance → Databricks (Unity Catalog) — requires DataSync → S3
AI on NAS data (summarize, RAG, sentiment) → Snowflake (External Table + Cortex AI)
Data sharing + SQL-centric + governance → Snowflake (External Table + Tags + Data Sharing)
Serverless + low cost → Athena
ETL pipelines → Glue
DWH integration → Redshift Spectrum
Open format interoperability → Snowflake Managed Iceberg Table (readable by all engines)
```

### Unstructured Data Processing

```text
AI/ML training → SageMaker + S3 AP
RAG pipelines → Bedrock + S3 AP
Image/video analysis → Rekognition + Lambda + S3 AP
Document processing → Textract + Lambda + S3 AP
Media transcoding → MediaConvert + S3 AP
```

### Vendor Neutrality Priority

```text
Table format → Apache Iceberg
Catalog → REST Catalog or Glue Catalog
Engine → Trino / Spark / Dremio
```
