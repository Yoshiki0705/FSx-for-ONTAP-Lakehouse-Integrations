# Trino + AWS Glue Iceberg REST Validation Plan

🌐 [日本語](trino-glue-rest-validation-ja.md) | English

## Purpose

Validate Trino access to S3 Tables metadata via the AWS Glue Iceberg REST endpoint. Trino is a strong validation target because it natively supports Iceberg REST catalogs and AWS has published integration guidance.

## Background

- Trino's [Iceberg connector](https://trino.io/docs/current/connector/iceberg.html) supports REST, Glue, Hive Metastore, JDBC, Nessie, and Snowflake catalog types
- AWS Glue Iceberg REST endpoint provides [Iceberg REST API](https://docs.aws.amazon.com/glue/latest/dg/connect-glu-iceberg-rest.html) for any compliant client
- AWS has published guidance on querying S3 Tables from Trino via Iceberg REST
- Lake Formation governance applies through the Glue REST credential vending path

## Validation Results (2026-06-01)

### OSS Trino 481 (Docker, single-node)

| Step | Result | Notes |
|---|---|---|
| Trino startup with Iceberg REST catalog | ✅ | `SERVER STARTED`, catalog recognized |
| `SHOW SCHEMAS FROM s3tables_glue_rest` | ❌ | `Missing Authentication Token` |
| Root cause | — | Trino uses `NoopAuthManager` for REST catalog; SigV4 signing not applied to HTTP requests |

**Conclusion**: OSS Trino 481's Iceberg REST connector does not natively support AWS SigV4 authentication for REST catalog requests. The Glue Iceberg REST endpoint requires SigV4 (`rest.sigv4-enabled=true` in `/v1/config`), but Trino's REST client sends unauthenticated requests.

> **Correction note (2026-11-03)**: this conclusion is not settled. The 2026-06-01 run did not set `iceberg.rest-catalog.security=SIGV4`, and the default is `NONE`, so `Missing Authentication Token` is the expected answer to an unsigned request. A control run on Trino 481 (Docker) with `security=SIGV4` and `signing-name=glue` and fake credentials returned `The security token included in the request is invalid`, which means the request was signed and was refused only because of its credentials. Not confirmed: a successful `SHOW SCHEMAS` with valid credentials. In 481, `SIGV4` also needs static `s3.aws-access-key` and `s3.aws-secret-key`, and these do not accept a session token, so temporary credentials (for example from IAM Identity Center) do not sign. Until a run with valid credentials is recorded, read "not supported" in this document as "not confirmed". Tracked in #175.

### Implications by Deployment

| Deployment | Expected to work | Reason |
|---|---|---|
| **EMR Trino** | ✅ Yes | EMR patches Trino with AWS SDK SigV4 handling |
| **Starburst Enterprise** | ✅ Yes | Built-in AWS integration and SigV4 support |
| **OSS Trino (Docker/EC2)** | ❌ Not currently | No SigV4 signing for REST catalog requests |
| **OSS Trino + custom AuthManager** | Possible | Would require custom plugin development |

### Glue Iceberg REST API (verified independently)

The underlying API is fully functional when called with proper SigV4 authentication (verified via PyIceberg/botocore):

| API call | Result | Latency |
|---|---|---|
| List Namespaces | ✅ `[["metadata"]]` | 229ms |
| List Tables | ✅ `["unstructured_files"]` | 308ms |
| Load Table | ✅ 54 snapshots, 23 columns | 381ms |
| `/credentials` endpoint | ❌ `UnknownOperationException` | — |

## Configuration

### Critical Finding: Glue REST Does NOT Support Credential Vending

**Verified 2026-06-01**: The AWS Glue Iceberg REST endpoint does NOT implement the Iceberg REST `/credentials` endpoint (returns `UnknownOperationException`). The `X-Iceberg-Access-Delegation: vended-credentials` header in `loadTable` also does not return storage credentials.

This means:
- **Trino**: Must use its own IAM credentials (SigV4) for both metadata AND data access. Set `vended-credentials-enabled=false`.
- **Snowflake**: `VENDED_CREDENTIALS` mode expects the catalog to vend credentials, but Glue REST cannot. This is the root cause of the "Failed to retrieve credentials from the Catalog" error.
- **Glue REST `/v1/config`** returns `rest.sigv4-enabled=true`, confirming SigV4 is the intended auth mechanism.

### Trino Catalog Properties (Glue Iceberg REST — Corrected)

```properties
# catalog/s3tables.properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=https://glue.ap-northeast-1.amazonaws.com/iceberg
iceberg.rest-catalog.warehouse=catalogs/<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog
iceberg.rest-catalog.vended-credentials-enabled=false
iceberg.rest-catalog.signing-region=ap-northeast-1
iceberg.rest-catalog.signing-name=glue
# Trino uses its own AWS credentials for S3 data access
fs.native-s3.enabled=true
s3.region=ap-northeast-1
```

> **Note**: The `warehouse` parameter must include the `catalogs/` prefix. Without it, the API returns HTTP 400 "Prefix must follow the 'catalogs/{catalogId}' format."

### Alternative: S3 Tables Direct REST

```properties
# catalog/s3tables-direct.properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=https://s3tables.ap-northeast-1.amazonaws.com/iceberg
iceberg.rest-catalog.warehouse=arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog
# SigV4 signing for s3tables service
```

## Validation Steps

| # | Step | Expected result |
|---|------|----------------|
| 1 | Configure Trino Iceberg catalog with Glue REST | Catalog loads without error |
| 2 | `SHOW SCHEMAS FROM s3tables` | Lists `metadata` namespace |
| 3 | `SHOW TABLES FROM s3tables.metadata` | Lists `unstructured_files` |
| 4 | `SELECT * FROM s3tables.metadata.unstructured_files LIMIT 10` | Returns file metadata rows |
| 5 | `SELECT * FROM s3tables.metadata.unstructured_files FOR VERSION AS OF <snapshot_id>` | Time travel works |
| 6 | Latest-record view query (ROW_NUMBER window) | Deduplication works |
| 7 | `SELECT * FROM s3tables.metadata."unstructured_files$history"` | Metadata tables accessible |
| 8 | Lake Formation permission enforcement | Unauthorized query blocked |

## Deployment Options

| Option | Best for | Notes |
|---|---|---|
| EMR with Trino | AWS-native, managed | EMR 7.x includes Trino with Iceberg |
| Starburst Enterprise | Enterprise features, support | Commercial Trino distribution |
| Trino on ECS/EKS | Custom deployment | Self-managed |
| Trino on EC2 | Development/testing | Simplest setup |

## Key Validation Points

- **Case sensitivity**: S3 Tables requires lowercase names. Verify Trino handles this correctly.
- **SigV4 authentication**: Trino must sign requests with AWS credentials for both Glue REST and S3 data access.
- **Lake Formation**: If using Glue REST path, Lake Formation grants should be enforced. Verify unauthorized access is blocked.
- **Snapshot freshness**: Trino should always see the latest committed snapshot (no refresh needed, unlike Databricks Foreign Iceberg).
- **Write capability**: Verify whether Trino can append to the Iceberg table via Glue REST (if write access is needed for backfill).

## Trino's Iceberg REST Access Characteristics (Comparison with Other Engines)

| Aspect | Trino | Databricks | Snowflake |
|---|---|---|---|
| Direct Iceberg REST access | ✅ Native | ❌ UC blocks | 🔄 Credential vending issue |
| Auto-refresh | ✅ Always latest | ❌ REFRESH required | TBD |
| Write via REST | Likely ✅ | ❌ Read-only (Foreign) | TBD |
| Lake Formation | Via Glue REST | TBD (Foreign Catalog) | TBD (vended credentials) |
| Setup complexity | Medium (catalog config) | High (UC constraints) | Medium (integration config) |

## References

- [Trino Iceberg connector](https://trino.io/docs/current/connector/iceberg.html)
- [AWS Glue Iceberg REST endpoint](https://docs.aws.amazon.com/glue/latest/dg/connect-glu-iceberg-rest.html)
- [EMR Trino + Iceberg](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-iceberg-use-trino-cluster.html)
- [Iceberg REST catalog specification](https://iceberg.apache.org/concepts/catalog/)
