# AWS Athena Integration

🌐 **English** | [日本語](docs/ja/README.md)

## Overview

Query data on Amazon FSx for NetApp ONTAP (FSx for ONTAP) directly from Amazon Athena using
Glue Data Catalog and S3 Access Points. Serverless, pay-per-query analytics.

## Architecture

```
Athena (Serverless SQL)
    │
    └── Glue Data Catalog
            │
            ├── Glue Crawler (schema discovery)
            │
            └── S3 Access Point (internet origin) ──→ FSx for ONTAP Volume
                                                        ├── transactions/ (Parquet, partitioned)
                                                        ├── customers/ (CSV)
                                                        ├── events/ (JSON)
                                                        └── gold/ (CTAS output)
```

## Important: Network Origin

Athena requires S3 Access Points with **internet network origin**.
VPC-only access points will NOT work with Athena.

Reference: [AWS Tutorial - Query files with Athena](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

### If your SVM is joined to Active Directory

The read-path verification here ran against an AD-joined SVM with its domain
controller reachable. For a **WINDOWS**-type access point, data operations
(ListObjectsV2/GetObject) through the access point need the SVM to reach its
domain controller; if the controller is unreachable, those operations fail even
though `HeadBucket` can still succeed. A **UNIX**-type access point on an
AD-non-joined SVM avoids this dependency. Behavior when the controller is
unreachable is not measured here — pick the user type (`S3AccessPointName`
mapping) that matches how your files are owned, and keep the controller reachable
for WINDOWS. See the AD-integration notes in the evidence pack.

## Status: ✅ Security Verified (2026-05-23)

Benchmark: 54.8 MB/s peak throughput, 5M rows queried in 2.2s (103 MB Parquet, 128 MB/s provisioned).
9/9 negative security tests PASS. CloudTrail audit confirmed.

## Quick Start

```bash
# 1. Copy params and fill values
cp params.example.json params.json
# Edit params.json with your FSx for ONTAP details

# 2. Generate sample data
pip install pandas pyarrow
python scripts/generate_sample_data.py

# 3. Upload to FSx for ONTAP via NFS
./scripts/upload_sample_data.sh

# 4. Deploy infrastructure
./deploy.sh

# 5. Validate connectivity
python scripts/validate_connectivity.py

# 6. Execute queries and collect metrics
python scripts/execute_queries.py
```

### Iceberg on the Access Point

Iceberg read **and write** work here, unlike Delta Lake. The Glue Data Catalog
holds the metadata pointer, so a commit never needs the conditional write that
an FSx for ONTAP S3 Access Point does not implement. Verified 2026-08-06
([evidence](../../verification-pack/athena-iceberg/evidence/2026-08-06/evidence-record.yaml)).

```bash
# see the statements first
python scripts/iceberg_quickstart.py \
  --access-point-alias <your-ap-alias> \
  --athena-output s3://<your-athena-results>/ --dry-run

# then run them: CREATE, INSERT, UPDATE, DELETE, time travel, OPTIMIZE, VACUUM
python scripts/iceberg_quickstart.py \
  --access-point-alias <your-ap-alias> \
  --athena-output s3://<your-athena-results>/
```

## Directory Structure

```
integrations/athena/
├── README.md                          ← This file
├── template.yaml                      ← CloudFormation (Glue + Athena + IAM)
├── deploy.sh                          ← Deployment automation
├── params.example.json                ← Parameter template
├── sql/
│   ├── 01_basic_queries.sql           ← SELECT, GROUP BY, JOIN queries
│   ├── 02_partition_pruning.sql       ← Partition pruning verification
│   └── 03_ctas_writeback.sql          ← CTAS write-back to FSx for ONTAP
├── scripts/
│   ├── generate_sample_data.py        ← Sample data generator
│   ├── upload_sample_data.sh          ← NFS upload script
│   ├── validate_connectivity.py       ← Connectivity validation
│   ├── execute_queries.py             ← Query execution + metrics
│   ├── run_crawler.py                 ← Crawler execution + verification
│   └── cleanup.sh                     ← Resource cleanup
├── tests/
│   └── results/                       ← Query metrics output
└── docs/
    ├── verification-report-en.md      ← (planned)
    └── verification-report-ja.md      ← (planned)
```

## Unstructured Data Support

| Format | Support | Access Method | Use Case |
|--------|:---:|--------------|----------|
| Images (JPEG, PNG, TIFF) | ❌ | N/A (SQL engine for structured data) | — |
| Video (MP4, MOV) | ❌ | N/A | — |
| Documents (PDF, DOCX) | ❌ | N/A | — |
| Audio (WAV, MP3) | ❌ | N/A | — |
| Binary / Archives | ❌ | N/A | — |

Athena is a SQL query engine optimized for structured data formats (Parquet, CSV, JSON, ORC). It cannot directly query unstructured data (images, video, audio). However, you can create metadata tables to manage file paths and integrate with other services for processing.

**Patterns for unstructured data workflows:**
1. **Metadata table** — Use Glue Crawler to catalog file paths, sizes, and timestamps on S3 AP
2. **Athena + Lambda UDF** — Pass file paths from query results to Lambda for processing
3. **Pipeline integration** — Use Athena to identify files, then process with Lambda/Bedrock

```sql
-- Query file metadata (registered via Glue Crawler)
SELECT key, size, last_modified
FROM fsxn_file_catalog
WHERE key LIKE '%.pdf'
ORDER BY last_modified DESC;
```

**Recommended alternative for unstructured data on FSx for ONTAP:**
- Use **AWS Lambda** for serverless file processing ([AWS tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html))
- Use **Amazon Bedrock** for RAG over documents ([AWS tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html))
- Use **Snowflake** (Directory Table + GET_PRESIGNED_URL) for file catalog and secure URL generation

## If you already run an analytics engine

The reusable part here is the access path: an S3 Access Point lets a query engine
read the ONTAP volume in place, without copying the data into a separate S3
bucket. Athena is one engine on top of it; this repository has sibling
integrations for others (`integrations/glue`, `integrations/emr-spark`,
`integrations/trino-starburst`, `integrations/redshift-spectrum`,
`integrations/snowflake`, `integrations/databricks`, and more). Which engine fits
depends on what you already operate, and each has a trade-off:

- **Athena (this integration)**: serverless, no cluster to run, pay per query.
  Requires an internet-origin access point and a Glue table over the data.
- **Your existing engine (EMR/Spark, Trino, Redshift Spectrum, a managed
  lakehouse)**: point its external-table location at the same access point alias
  and keep your current catalog. Trade-off: the access point has the same network
  and user-type constraints regardless of engine, and conditional/transactional
  writes that FSx for ONTAP S3 Access Points do not implement (for example Delta
  Lake commits) still will not work. Iceberg, whose commit goes through the Glue
  catalog, does work (see above).

In every case the access point does not copy data; the file stays on the ONTAP
volume and is still reachable over NFS/SMB. Choose the engine by what you operate,
not by which is "better", because the storage access path underneath is the same.

## Reference Implementation

This integration leverages patterns from:
- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
  - UC1 (legal-compliance): Athena × S3 AP E2E verified
  - UC3 (manufacturing-analytics): Athena query patterns
  - `shared/cfn/fpolicy-routing.yaml`: Event-driven Crawler trigger
  - `docs/event-driven/`: FPolicy configuration reference
