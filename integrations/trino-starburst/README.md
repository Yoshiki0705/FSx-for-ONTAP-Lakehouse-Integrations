# Trino / Starburst Integration

🌐 **English** | [日本語](docs/ja/README.md)

## Overview

Query FSx for ONTAP data via S3 Access Points using Trino — an open-source distributed SQL query engine. Trino uses its own S3 filesystem implementation that supports path-style access, making it compatible with FSx for ONTAP S3 AP aliases.

This integration targets **Trino 481** (`trinodb/trino:481`, pinned in `docker-compose.yaml`). The earlier Trino 438 configuration (file metastore, `hive.s3.*`) does not start on 481, because 481 removed the legacy S3 file system.

## Status: ✅ Read verified on Trino 481 (2026-05-26)

Evidence: [`verification-pack/trino/evidence/2026-05-26`](../../verification-pack/trino/evidence/2026-05-26/evidence-record.yaml) (Trino 481, Docker, Glue Catalog, native S3 with path-style access, ap-northeast-1).

- **Read**: `SHOW SCHEMAS`, `COUNT(*)` on 10K and 5M row Parquet, `GROUP BY` and a filter with predicate pushdown succeeded on FSx for ONTAP S3 Access Points.
- **Write-back (CTAS)**: Not tested on 481. On Trino 438 with a file-based metastore it failed because of the metastore, not because of S3 Access Points.
- **No session policy issues**: Direct IAM credentials, no intermediary governance layer
- **Not re-run since the configuration was updated for 481**: the evidence run used `fs.native-s3.enabled`, which 481 reports as replaced by `fs.s3.enabled` (the name used in this repository's `fsxn.properties`). With the new name the server starts and accepts credentials from the environment (checked with made-up credentials); queries against Glue and S3 Access Points with it have not been run.

**Benchmark (Trino 438, single-node Docker arm64, ap-northeast-1):** measured with the earlier file-metastore configuration. Only this README records it; the 2026-05-24 evidence record is a prediction made before any run. Treat these numbers as a historical reference, not as 481 results.

| Query | 10K rows | 5M rows (103 MB) |
|-------|----------|-------------------|
| COUNT(*) | 1,136 ms | 1,075 ms |
| GROUP BY + AVG | 860 ms | 1,462 ms |
| WHERE filter | — | 1,227 ms |

## Architecture

```
Trino 481 (Docker, single-node)
    │
    ├── Hive Connector ──→ AWS Glue Data Catalog (schemas and tables)
    │
    └── S3 file system (native, path-style access)
            │
            └── FSx S3 Access Point (internet-origin)
                    │
                    └── FSx for ONTAP Volume (Parquet files)
```

## Key Configuration

Trino's native S3 file system needs `s3.path-style-access=true` and an explicit `s3.endpoint` to resolve an S3 Access Point alias (the same pattern as DuckDB's `s3_url_style='path'`). The schemas and tables live in the Glue Data Catalog.

```properties
# config/etc/catalog/fsxn.properties
connector.name=hive
hive.metastore=glue
hive.metastore.glue.region=ap-northeast-1
fs.s3.enabled=true
s3.path-style-access=true
s3.endpoint=https://s3.ap-northeast-1.amazonaws.com
s3.region=ap-northeast-1
```

Credentials come from the AWS default credential chain. `docker-compose.yaml` passes `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` through from your shell, so temporary credentials work.

Properties that no longer work on 481:

| Property | Result on Trino 481 | Replacement |
|---|---|---|
| `hive.s3.*` (path-style access, endpoint, region, access keys) | Server refuses to start (`Configuration property 'hive.s3.endpoint' was not used`) | `s3.*` with `fs.s3.enabled=true` |
| `hive.metastore=file` with a `file:` location | `No factory for ...` when a schema is created | `hive.metastore=glue`. Adding `fs.hadoop.enabled=true` made it work in a local test, but the 481 release notes document that property as HDFS only |
| `fs.native-s3.enabled` | Works, with a "has been replaced" warning | `fs.s3.enabled` |

## Expected Behavior

Reading Parquet is verified on 481 (see Status). Writing Parquet with CTAS is not tested on 481; `03_write_back.sql` is that test. Delta and Iceberg writes are expected to fail under the same atomic rename constraint as on the other engines, but were not tried here. Authentication uses direct IAM credentials with no intermediary governance layer, so session policies are not an issue.

## S3 Tables through the Glue Iceberg REST endpoint

`config/etc/catalog/s3tables_glue_rest.properties` defines a second catalog for S3 Tables. It loads on 481 but sends unsigned requests, so Glue answers `Missing Authentication Token`. Trino signs requests only when `iceberg.rest-catalog.security=SIGV4` is set, and that setting is commented out in the file because 481 then refuses to start unless `s3.aws-access-key` and `s3.aws-secret-key` are also set, and neither property accepts a session token. The file's comments give the steps. A control run on 481 with made-up credentials showed signed requests (`The security token included in the request is invalid`); a run with valid credentials has not been done.

## Unstructured Data Support

| Format | Support | Access Method | Use Case |
|--------|:---:|--------------|----------|
| Images (JPEG, PNG, TIFF) | ❌ | N/A (SQL engine for structured data) | — |
| Video (MP4, MOV) | ❌ | N/A | — |
| Documents (PDF, DOCX) | ❌ | N/A | — |
| Audio (WAV, MP3) | ❌ | N/A | — |
| Binary / Archives | ❌ | N/A | — |

Trino is a distributed SQL query engine for structured data. It cannot directly query unstructured data. However, you can create metadata tables and use federated queries across multiple data sources.

**Patterns:**
1. **Metadata table** — Register file paths, sizes, and types as Hive tables for querying
2. **Multi-source federation** — JOIN FSx for ONTAP S3 AP file catalogs with other data sources (RDS, PostgreSQL)
3. **Hive Connector** — Read Parquet metadata directly from S3 AP with path-style access

```sql
-- Query file catalog
SELECT file_path, file_type, file_size, last_modified
FROM fsxn.default.file_catalog
WHERE file_type = 'image/jpeg'
  AND file_size > 1000000;

-- Federated JOIN with other data sources
SELECT f.file_path, m.model_name, m.accuracy
FROM fsxn.default.file_catalog f
JOIN ml_catalog.default.model_results m ON f.file_path = m.input_path;
```

## Quick Start

Prerequisites: Docker, AWS credentials exported in your shell, and permission to use the Glue Data Catalog. For SSO: `eval "$(aws configure export-credentials --format env)"`.

```bash
# 1. Start Trino (Docker). The server starts without credentials, but queries need them.
docker compose up -d

# 2. Connect with Trino CLI
docker exec -it trino trino --catalog fsxn --schema default

# 3. Run queries against a table registered in Glue
trino> SELECT COUNT(*) FROM sensor_data;
trino> SELECT status, AVG(temperature) FROM sensor_data GROUP BY status;
```

`scripts/run_verification.sh <alias>` runs the whole flow. It creates the Glue database `sensor_data` and its table `readings`, and `scripts/cleanup.sh` does not remove them; the commands to delete them are in the script header.

## Directory Structure

```
integrations/trino-starburst/
├── README.md                          ← This file
├── docker-compose.yaml                ← Trino single-node + config
├── config/
│   ├── etc/
│   │   ├── config.properties          ← Trino server config
│   │   ├── jvm.config                 ← JVM settings
│   │   ├── node.properties            ← Node identity
│   │   └── catalog/
│   │       ├── fsxn.properties        ← Hive connector: Glue metastore + native S3
│   │       └── s3tables_glue_rest.properties  ← Iceberg REST catalog (SigV4 off by default)
├── sql/
│   ├── 01_create_schema.sql           ← Schema + table DDL
│   ├── 02_read_queries.sql            ← SELECT, GROUP BY, aggregation
│   └── 03_write_back.sql             ← CTAS write-back test
├── scripts/
│   ├── run_verification.sh            ← End-to-end verification
│   └── cleanup.sh                     ← Stop and remove containers
└── params.example.json                ← Parameter template
```

## Comparison with Other Engines

| Feature | Trino | DuckDB | Athena | EMR Spark |
|---------|-------|--------|--------|-----------|
| Deployment | Docker / EC2 / K8s | In-process / Lambda | Serverless | EMR Serverless |
| S3 AP support | Native S3, path-style + endpoint | path-style + endpoint | Native (EMRFS) | Native (EMRFS) |
| Session policy risk | None (direct IAM) | None (direct IAM) | None (AWS-native) | None (AWS-native) |
| Write-back | Not tested on 481 | COPY TO | CTAS | Spark write |
| Cost model | Compute (EC2/container) | Per-invocation (Lambda) | Per-scan | Per-job |
| Best for | Federated SQL, multi-source | Lightweight ad-hoc | Serverless SQL | Large-scale ETL |
