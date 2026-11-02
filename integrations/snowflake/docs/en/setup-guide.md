🌐 **English** | [日本語](../ja/setup-guide.md)

# Snowflake Setup Guide

## Overview

Configure FSx for NetApp ONTAP S3 Access Point as a Snowflake External Stage
to use as the storage layer for External Tables and Iceberg Tables.

## Prerequisites

- AWS account with FSx for NetApp ONTAP deployed
- **FSx for ONTAP S3 Access Point already created** (via `aws fsx create-and-attach-s3-access-point`)
- Snowflake account (Enterprise Edition or higher for Iceberg Tables)
- AWS CLI v2 configured
- ACCOUNTADMIN role access in Snowflake

## Important: FSx for ONTAP S3 Access Point Architecture

FSx for ONTAP S3 Access Points are **NOT** standard S3 Access Points. They are created
using the FSx API, not CloudFormation `AWS::S3::AccessPoint`:

```bash
aws fsx create-and-attach-s3-access-point \
  --name <ap-name> --type ONTAP \
  --ontap-configuration \
    'VolumeId=<fsvol-xxx>,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'
```

Key differences from standard S3:
- **Pre-signed URLs are NOT supported**
- **S3 Event Notifications are NOT supported** (use FPolicy instead)
- **Higher latency** than native S3 (tens of seconds for ListObjects)
- Maximum upload size: 50 GiB
- StorageClass is always `FSX_ONTAP`

## Setup Flow

```
Step 0: Create FSx for ONTAP S3 Access Point (aws fsx CLI)
    ↓
Step 1: Deploy CloudFormation (IAM Role only)
    ↓
Step 2: Create Snowflake Storage Integration
    ↓
Step 3: DESCRIBE INTEGRATION → get trust info
    ↓
Step 4: Update CloudFormation (trust policy)
    ↓
Step 5: Create External Stage
    ↓
Step 6: Create External Table / Iceberg Table
```

## Step 0: Create FSx for ONTAP S3 Access Point

```bash
# List existing access points
aws fsx describe-s3-access-point-attachments --region <YOUR_REGION>

# Create new access point (if needed)
aws fsx create-and-attach-s3-access-point \
  --name snowflake-ap --type ONTAP \
  --ontap-configuration \
    'VolumeId=<YOUR_VOLUME_ID>,FileSystemIdentity={Type=UNIX,UnixUser={Name=root}}'
```

Note the **Alias** from the output (e.g., `snowflake-ap-abc123-ext-s3alias`).

## Step 1: Deploy CloudFormation Stack

```bash
# Copy and configure parameters
cp params.example.json params.json
# Edit params.json: set S3AccessPointArn and S3AccessPointAlias

# Deploy
./deploy.sh --region <YOUR_REGION>
```

The template creates only an IAM Role with a two-phase trust policy.

## Step 2: Create Storage Integration

Run in Snowflake (SnowSQL or Worksheet):

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE STORAGE INTEGRATION fsxn_storage_integration
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '<IAMRoleArn from deploy output>'
  STORAGE_ALLOWED_LOCATIONS = (
    's3://<S3AccessPointAlias>/'
  );
```

## Step 3: Get Trust Policy Information

```sql
DESCRIBE INTEGRATION fsxn_storage_integration;
```

Note these values:
- `STORAGE_AWS_IAM_USER_ARN` → Snowflake's AWS Account ID (12-digit number in the ARN)
- `STORAGE_AWS_EXTERNAL_ID` → External ID for trust policy

## Step 4: Update CloudFormation (Trust Policy)

```bash
./scripts/update_trust_policy.sh \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

Or update params.json and re-run `./deploy.sh`.

## Step 5: Create External Stage

```sql
USE ROLE SYSADMIN;
USE DATABASE FSXN_LAKEHOUSE;
USE SCHEMA BRONZE;

CREATE OR REPLACE STAGE FSXN_BRONZE_STAGE
  STORAGE_INTEGRATION = fsxn_storage_integration
  URL = 's3://<S3AccessPointAlias>/';

-- Verify (note: LIST may take 30-60+ seconds due to FSx for ONTAP S3 AP latency)
LIST @FSXN_BRONZE_STAGE;
```

## Step 6: Create Tables

Run SQL scripts in order:
1. `03_file_format.sql` — File format definitions
2. `04_external_table.sql` — External Tables
3. `05_iceberg_table.sql` — Iceberg Tables (requires Enterprise Edition)
4. `06_snowpipe.sql` — Snowpipe setup (optional, requires FPolicy)
5. `07_data_sharing.sql` — Data sharing (optional)
6. `08_directory_table.sql` — Directory Table for unstructured data
7. `09_snowpark_image_udf.sql` — Snowpark UDFs

## Performance Considerations

| Operation | Expected Latency | Notes |
|-----------|-----------------|-------|
| CREATE STAGE | 30-60 seconds | Initial S3 AP connection establishment |
| LIST @stage | 30 seconds - 5+ minutes | Depends on file count |
| SELECT (External Table) | Seconds | After metadata is cached |
| Iceberg DML | Seconds | Write operations |

> **Tip**: FSx for ONTAP S3 AP has higher latency than native S3. For interactive queries,
> consider materializing frequently-accessed data into Snowflake native tables.

## Troubleshooting

### Issue: CREATE STAGE takes very long (minutes)

**Cause**: FSx for ONTAP S3 AP has high initial connection latency

**Resolution**: This is expected behavior. Set `STATEMENT_TIMEOUT_IN_SECONDS = 600`
for the session. Subsequent operations on the same stage may be faster.

### Issue: LIST @stage returns empty or times out

**Cause**: FSx for ONTAP S3 AP ListObjects is slow, especially with many files

**Resolution**:
1. Increase timeout: `ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 600;`
2. Use subdirectory paths to reduce file count
3. Verify data exists via NFS mount

### Issue: GET_PRESIGNED_URL returns error

**Cause**: FSx for ONTAP S3 Access Points do NOT support Pre-signed URLs

**Resolution**: This is a known limitation. Use alternative access patterns:
- Direct S3 API access via IAM role (for applications)
- NFS mount for direct file access

### Issue: "Failure using stage area" error

**Cause**: IAM Role trust policy not configured (Phase 2 incomplete)

**Resolution**: Run `scripts/update_trust_policy.sh` with values from DESCRIBE INTEGRATION

### Issue: Snowpipe not detecting files

**Cause**: FSx for ONTAP does not support S3 Event Notifications

**Resolution**: Use FPolicy event-driven pattern (see `06_snowpipe.sql` and
`shared/cloudformation/fpolicy-*.yaml`)
