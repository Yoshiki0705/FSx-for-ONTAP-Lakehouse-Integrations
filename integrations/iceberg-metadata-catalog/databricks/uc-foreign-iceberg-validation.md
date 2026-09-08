# UC Foreign Iceberg Validation Plan

🌐 [日本語](uc-foreign-iceberg-validation-ja.md) | English

## Purpose

Validate whether Unity Catalog Foreign Iceberg can access S3 Tables metadata via the AWS Glue Iceberg REST endpoint, providing governed metadata access without DataSync or format conversion.

## Background

- Databricks [Foreign Iceberg is GA](https://www.databricks.com/blog/unity-catalog-and-next-era-apache-icebergtm) (Jun 2026)
- AWS published [guidance on accessing S3 Iceberg tables from Databricks using Glue Iceberg REST](https://aws.amazon.com/blogs/big-data/access-amazon-s3-iceberg-tables-from-databricks-using-aws-glue-iceberg-rest-catalog-in-amazon-sagemaker-lakehouse)
- Databricks [catalog federation supports AWS Glue](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue)

## Known Limitations (from Databricks docs)

| Limitation | Impact | Source |
|---|---|---|
| Credential vending on Foreign Iceberg tables is not supported | External storage credentials must be configured separately | [docs](https://docs.databricks.com/aws/external-access/iceberg) |
| Foreign Iceberg tables are not automatically refreshed | `REFRESH FOREIGN TABLE` required to see latest snapshot | [docs](https://docs.databricks.com/aws/external-access/iceberg) |
| Read-only access | Cannot write to Foreign Iceberg tables from Databricks | [docs](https://docs.databricks.com/aws/iceberg/) |

## Validation Steps

### B-4: UC Foreign Iceberg via S3 Tables Direct REST

```sql
-- Step 1: Create service credential for S3 Tables access
CREATE SERVICE CREDENTIAL s3tables_cred
WITH (
  -- IAM role with s3tables:* permissions
);

-- Step 2: Create connection to S3 Tables REST endpoint
CREATE CONNECTION s3tables_rest TYPE iceberg_rest
OPTIONS (
  uri = 'https://s3tables.ap-northeast-1.amazonaws.com/iceberg',
  warehouse = 'arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog',
  credential_name = 's3tables_cred'
  -- SigV4 signing configuration TBD
);

-- Step 3: Create foreign catalog
CREATE FOREIGN CATALOG s3tables_metadata
USING CONNECTION s3tables_rest;

-- Step 4: Query
SELECT * FROM s3tables_metadata.metadata.unstructured_files LIMIT 10;
```

### B-5: UC Foreign Iceberg via Glue Iceberg REST

```sql
-- Step 1: Create service credential for Glue access
CREATE SERVICE CREDENTIAL glue_cred
WITH (
  -- IAM role with glue:* permissions
);

-- Step 2: Create connection to Glue Iceberg REST endpoint
CREATE CONNECTION glue_iceberg_rest TYPE iceberg_rest
OPTIONS (
  uri = 'https://glue.ap-northeast-1.amazonaws.com/iceberg',
  warehouse = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog',
  credential_name = 'glue_cred'
  -- SigV4 signing configuration TBD
);

-- Step 3: Create foreign catalog
CREATE FOREIGN CATALOG glue_metadata
USING CONNECTION glue_iceberg_rest;

-- Step 4: Query
SELECT * FROM glue_metadata.metadata.unstructured_files LIMIT 10;
```

### Alternative: Hive Metastore Federation with AWS Glue

```sql
-- If iceberg_rest connection type is not available for foreign catalogs,
-- try Hive Metastore federation (confirmed supported for AWS Glue)
CREATE CONNECTION glue_hms TYPE hive_metastore
OPTIONS (
  -- AWS Glue Hive Metastore connection
  -- See: https://docs.databricks.com/aws/en/query-federation/hms-federation-glue
);

CREATE FOREIGN CATALOG glue_hms_catalog
USING CONNECTION glue_hms
OPTIONS (authorized_paths = 's3://...');
```

## Success Criteria

| Criterion | Expected |
|---|---|
| Foreign catalog created | No errors |
| Namespaces visible | `metadata` namespace listed |
| Tables visible | `unstructured_files` table listed |
| SELECT query works | Returns rows with file metadata |
| Time travel works | `SELECT * ... FOR SYSTEM_TIME AS OF` returns historical data |
| REFRESH FOREIGN TABLE works | Latest snapshot visible after refresh |
| UC governance applies | UC grants control access to foreign table |
| UC lineage recorded | Query appears in UC lineage graph |

## Refresh Semantics Validation

```sql
-- 1. Query current state
SELECT COUNT(*) FROM glue_metadata.metadata.unstructured_files;

-- 2. Add new records via PyIceberg (from Lambda or local)
-- (append new file metadata)

-- 3. Query again WITHOUT refresh — expect stale count
SELECT COUNT(*) FROM glue_metadata.metadata.unstructured_files;

-- 4. Refresh
REFRESH FOREIGN TABLE glue_metadata.metadata.unstructured_files;

-- 5. Query again — expect updated count
SELECT COUNT(*) FROM glue_metadata.metadata.unstructured_files;
```

### Detailed Snapshot Freshness Test

```sql
-- Record snapshot_id before append
SELECT snapshot_id FROM glue_metadata.metadata.unstructured_files.history LIMIT 1;

-- After PyIceberg append from AWS side:
-- 1. Query Databricks — does it see the new snapshot?
SELECT snapshot_id FROM glue_metadata.metadata.unstructured_files.history LIMIT 1;
-- Expected: SAME as before (no auto-refresh)

-- 2. Run REFRESH
REFRESH FOREIGN TABLE glue_metadata.metadata.unstructured_files;

-- 3. Query again
SELECT snapshot_id FROM glue_metadata.metadata.unstructured_files.history LIMIT 1;
-- Expected: NEW snapshot_id (after refresh)

-- 4. Compare with Athena
-- Run same query in Athena — should always show latest snapshot
-- Document the delta between Athena (always fresh) and Databricks (refresh-dependent)
```

## Status

- B-4 (S3 Tables direct REST): Follow-up submitted to Databricks support (2026-06-01)
- B-5 (Glue Iceberg REST): Follow-up submitted to Databricks support (2026-06-01)
- Awaiting support guidance on connection type and credential configuration

## References

- [Databricks Foreign Iceberg docs](https://docs.databricks.com/aws/external-access/iceberg)
- [AWS Glue Iceberg REST → Databricks blog](https://aws.amazon.com/blogs/big-data/access-amazon-s3-iceberg-tables-from-databricks-using-aws-glue-iceberg-rest-catalog-in-amazon-sagemaker-lakehouse)
- [Databricks Catalog Federation](https://docs.databricks.com/aws/en/query-federation/catalog-federation)
- [AWS Glue → UC federation](https://docs.aws.amazon.com/lake-formation/latest/dg/catalog-federation-databricks.html)


---

## Validation Execution Results (2026-06-21)

### Environment

| Item | Value |
|------|-------|
| Workspace | `fsxn-lakehouse-verification` (ap-northeast-1) |
| Workspace URL | `https://<WORKSPACE_ID>.cloud.databricks.com` |
| Account ID | `<DATABRICKS_ACCOUNT_ID>` |
| SQL Warehouse | Serverless Starter Warehouse (Small) |
| S3 Tables bucket | `fsxn-metadata-catalog` (arn:aws:s3tables:ap-northeast-1:<ACCOUNT_ID>:bucket/fsxn-metadata-catalog) |
| S3 Tables table | `metadata.unstructured_files` |
| S3 Tables data bucket | `s3://<TABLE_BUCKET_ID>--table-s3` (internal, S3 Tables-managed) |
| IAM Role | `fsxn-databricks-executor-validation-role` (Glue + S3 Tables + S3 permissions) |

### Pre-existing Resources

| Resource | Type | Status |
|----------|------|--------|
| `glue_s3tables_conn` | CONNECTION (GLUE) | ✅ Exists |
| `s3tables_storage_credential` | STORAGE CREDENTIAL | ✅ Exists |
| `fsxn_s3ap_credential` | STORAGE CREDENTIAL | ✅ Exists |

### Test Results

#### Test 1: `CREATE CONNECTION TYPE iceberg_rest`

```sql
CREATE CONNECTION IF NOT EXISTS glue_iceberg_rest
TYPE iceberg_rest
OPTIONS (
  uri = 'https://glue.ap-northeast-1.amazonaws.com/iceberg',
  warehouse = '<ACCOUNT_ID>:s3tablescatalog/fsxn-metadata-catalog',
  credential_name = 'glue_s3tables_conn'
);
```

**Result**: ❌ FAILED

**Error**: `[CONNECTION_TYPE_NOT_SUPPORTED] Cannot create connection of type 'iceberg_rest'. Supported connection types: 1PASSWORD_EVENT_LOGS, SALESFORCE, AKAMAI_WAF_LOGS, EPIC_CLARITY, GLUE, X_ADS, MARKETO, APPLE_SEARCH_ADS, FRONT, AZURE_MONITOR_LOGS, META_MARKETING, GA4_RAW_DATA, WORKDAY_ACTIVITY_LOGGING, ONELAKE, AKAMAI, GOOGLE_WORKSPACE, PROOFPOINT_SIEM, WORKDAY_HCM, BIGQUERY, VEEVA, HTTP, QUICKBOOKS, ZOHO_BOOKS, SQUARE, OUTLOOK, PENDO, ZOOM_LOGS, CERIDIAN_DAYFORCE, COMMUNITY, GURU, APPLE_APP_STORE, AMPLITUDE, JIRA, GENESYS, GOOGLE_ADS, SALESFORCE_DATA_CLOUD_FILE_SHARING, POSTGRESQL, DYNAMICS365, ADOBE_CAMPAIGNS, SALESFORCE_MARKETING_CLOUD, ZENDESK_SUPPORT, ADP_WORKFORCE...`

**Root Cause**: `iceberg_rest` connection type is not available in this workspace (ap-northeast-1). This appears to be a regional feature availability limitation or a preview feature not yet enabled.

---

#### Test 2: `CREATE EXTERNAL LOCATION` for S3 Tables data bucket

```sql
CREATE EXTERNAL LOCATION IF NOT EXISTS s3tables_data_location
URL 's3://<TABLE_BUCKET_ID>--table-s3'
WITH (STORAGE CREDENTIAL s3tables_storage_credential);
```

**Result**: ❌ FAILED

**Error**: `[INVALID_STATE.UC_CLOUD_STORAGE_ACCESS_FAILURE] Failed to access cloud storage: [AWSBadRequestException] () exceptionTraceId=0ff546b2-e705-425b-8588-196f3edab325`

**Root Cause**: S3 Tables managed data buckets (`xxxx--table-s3` format) are AWS-internal buckets that cannot be accessed via standard S3 API operations (`s3:ListBucket`, `s3:GetObject`). They are only accessible via the S3 Tables API (`s3tables:GetTableData`). Unity Catalog performs S3 API validation during External Location creation, which fails against S3 Tables managed buckets.

---

#### Test 3: `CREATE FOREIGN CATALOG` via Glue HMS connection

```sql
CREATE FOREIGN CATALOG IF NOT EXISTS glue_s3tables_catalog
USING CONNECTION glue_s3tables_conn
OPTIONS (
  authorized_paths = 's3://<TABLE_BUCKET_ID>--table-s3'
);
```

**Result**: ❌ FAILED

**Error**: `[EXTERNAL_LOCATION_DOES_NOT_EXIST] parent external location for path 's3://<TABLE_BUCKET_ID>--table-s3/' does not exist.`

**Root Cause**: Foreign Catalog creation requires a parent External Location to exist for the `authorized_paths`. Since Test 2 failed (External Location cannot be created for S3 Tables managed buckets), this test also fails.

---

### Summary of Findings

| Path | Result | Blocker |
|------|--------|---------|
| B-4: `iceberg_rest` → Foreign Catalog | ❌ Blocked | `iceberg_rest` connection type not available in ap-northeast-1 workspace |
| B-5: Glue Iceberg REST → Foreign Catalog | ❌ Blocked | Same as B-4 (requires `iceberg_rest` type) |
| Alternative: Glue HMS → Foreign Catalog | ❌ Blocked | S3 Tables managed bucket cannot be registered as UC External Location |

### Platform Constraints Identified

1. **`iceberg_rest` connection type**: Not available in this workspace. The supported connection types list does NOT include `iceberg_rest`. This may be:
   - A regional limitation (ap-northeast-1 not yet supported)
   - A preview feature requiring explicit opt-in
   - A workspace configuration requirement

2. **S3 Tables managed buckets vs UC External Location**: UC External Location validates bucket access via standard S3 API during creation. S3 Tables managed buckets (format: `xxxx--table-s3`) are AWS-internal and do not respond to standard S3 API calls. This creates an incompatibility between UC External Location and S3 Tables data storage.

3. **Circular dependency**: Foreign Catalog (Glue HMS type) requires `authorized_paths` → which requires External Location → which requires S3 API-accessible bucket → S3 Tables managed buckets are not S3 API-accessible.

### Required Actions (open questions for Databricks)

1. Confirm when `iceberg_rest` connection type will be available for ap-northeast-1 workspaces
2. Confirm whether UC External Location will support S3 Tables managed buckets (via S3 Tables API instead of standard S3 API)
3. Clarify the recommended path for accessing S3 Tables data from Databricks Unity Catalog

### Workaround (if needed before platform support)

If UC Foreign Iceberg remains blocked, the validated alternative is:
- **Athena** can query S3 Tables directly (via Glue catalog integration) — confirmed working
- **DataSync → S3 → UC Delta** remains the only validated Databricks path
- **PyIceberg on Databricks compute** (driver-only, no UC governance) could read S3 Tables via the Glue Iceberg REST endpoint directly — not validated yet

### Evidence Files

- Screenshots: `tmp/.playwright-mcp/page-2026-06-21T01-27-35-446Z.png` (iceberg_rest error), `tmp/.playwright-mcp/page-2026-06-21T01-36-39-118Z.png` (External Location error)
- Workspace: `https://<WORKSPACE_ID>.cloud.databricks.com`
- Query: `New Query 2026-06-21 10:14:58` (saved in workspace)
