# Reading FSx for ONTAP files from Snowflake and writing Iceberg tables

**English** | [日本語](../ja/snowflake-iceberg-setup.md)

> Verified end to end on 2026-08-06 ([evidence](../../verification-pack/snowflake/evidence/2026-08-06/evidence-record.yaml)).
> Every command here was run against a real account and a real FSx for ONTAP file system.

## What you get

Files already sitting on an FSx for ONTAP volume become queryable from Snowflake
without copying them anywhere. Governed tables are written to a standard S3
bucket. Nothing needs to move first.

```
FSx for ONTAP volume            S3 Access Point         Snowflake
┌──────────────────┐            ┌─────────────┐         ┌────────────────────┐
│ NFS / SMB write  │            │             │  read   │ External Stage     │
│ from existing    │───────────►│  read-only  │────────►│ SELECT, COPY INTO  │
│ applications     │            │  S3 API     │         │                    │
└──────────────────┘            └─────────────┘         └─────────┬──────────┘
                                                                  │ write
                                                        ┌─────────▼──────────┐
                                                        │ Managed Iceberg    │
                                                        │ Table on standard  │
                                                        │ S3 (External Vol.) │
                                                        └────────────────────┘
```

The split is deliberate. Reads go through the Access Point; writes go to standard
S3. Writing Iceberg or Delta **to** an Access Point does not work today and fails
in a way that leaves objects behind — see [Why writes go elsewhere](#why-writes-go-elsewhere).

## Before you start

| You need | How to check | If missing |
|---|---|---|
| An FSx for ONTAP file system, ONTAP 9.17.1 or later | S3 Access Points need it. The console does not show the ONTAP version; query the ONTAP REST API | Upgrade, or use a newer file system |
| An SVM with **no** native ONTAP S3 object-store server | `vserver object-store-server show` | Use a different SVM. The two cannot coexist on one SVM |
| A Snowflake account you can run `CREATE STORAGE INTEGRATION` in | `SELECT CURRENT_ROLE()` returns ACCOUNTADMIN, or your role has the privilege | Ask whoever administers the account |
| AWS CLI v2, permission to create IAM roles and S3 buckets | `aws sts get-caller-identity` | — |

Region matters less than you might expect: the Access Point and the Snowflake
account do not have to be in the same region, but cross-region reads add latency
and data transfer cost. Same region is the sensible default.

## Step 1 — create the S3 Access Point

Access Points are not created by the CloudFormation templates in this repository,
because they belong to the file system rather than to any one integration.

```bash
aws fsx create-and-attach-s3-access-point \
  --name my-lakehouse-ap \
  --type FSX \
  --fsx-configuration 'VolumeId=fsvol-EXAMPLE,FileSystemIdentity={Type=UNIX,UnixConfiguration={Uid=0,Gid=0}}'
```

Two choices to make here:

**Network origin.** Leave `VpcConfiguration` out. An internet-origin Access Point
is what Snowflake needs — it reaches your data over its own network, not from
inside your VPC. A VPC-scoped Access Point cannot be read by Snowflake.

**File system identity.** `Uid=0,Gid=0` is root, which reads everything. Fine for
a first run. For anything beyond that, create a dedicated UNIX user that can read
only the directories you intend to expose, and use its uid. The Access Point
enforces **both** the IAM policy and this file system identity's permissions, so
the identity is a real control, not a formality.

Note the alias from the output — it looks like
`my-lakehouse-ap-<random>-ext-s3alias` and is what Snowflake addresses as a
bucket name.

## Step 2 — the IAM role Snowflake reads through

```bash
cp cfn-params/snowflake-phase1.example.json cfn-params/snowflake.json
# edit: S3AccessPointArn and S3AccessPointAlias from step 1
aws cloudformation deploy \
  --template-file integrations/snowflake/template.yaml \
  --stack-name fsxn-snowflake \
  --parameter-overrides file://cfn-params/snowflake.json \
  --capabilities CAPABILITY_NAMED_IAM
```

Then in Snowflake, using the `IAMRoleArn` output:

```sql
CREATE STORAGE INTEGRATION fsxn_s3ap
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<IAMRoleArn from the stack output>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('s3://<your-ap-alias>/');

DESC STORAGE INTEGRATION fsxn_s3ap;
```

Copy `STORAGE_AWS_IAM_USER_ARN` and `STORAGE_AWS_EXTERNAL_ID` from the result and
finish the trust policy:

```bash
./integrations/snowflake/scripts/update_trust_policy.sh \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

This two-pass shape is unavoidable: Snowflake will not tell you which principal
it uses until the integration exists, and the role cannot trust a principal it
does not know. Every integration in this repository that talks to Snowflake works
this way.

## Step 3 — the stage, and the parameter that decides everything

```sql
CREATE OR REPLACE STAGE my_stage
  URL = 's3://<your-ap-alias>/path/'
  STORAGE_INTEGRATION = fsxn_s3ap
  AWS_ACCESS_POINT_ARN = 'arn:aws:s3:<region>:<account>:accesspoint/<ap-name>';
```

`AWS_ACCESS_POINT_ARN` is the whole ballgame. Without it:

| Operation | Without the parameter | With it |
|---|---|---|
| `LIST @my_stage` | works | works |
| `SELECT FROM @my_stage` | **AccessDenied** | works |
| `COPY INTO` from the stage | **AccessDenied** | works |

`LIST` succeeding while every read fails is a genuinely confusing failure, because
the stage looks correctly configured. The cause is that Snowflake's session policy
restricts object-level operations to standard bucket ARNs unless you name the
access point ARN explicitly.

If you see `AccessDenied` on `SELECT` and `LIST` works, check this parameter first.

## Step 4 — read your files

```sql
LIST @my_stage;

-- Parquet and CSV
SELECT $1, $2 FROM @my_stage/data.csv;

-- JSON, Avro, ORC need a named file format; an inline FILE_FORMAT is not
-- accepted in this position
CREATE OR REPLACE FILE FORMAT ff_json TYPE = JSON;
SELECT $1:event_id::string
FROM @my_stage/events.json (FILE_FORMAT => ff_json);
```

Verified formats: Parquet, CSV, JSON, Avro, ORC. Also verified: External Tables,
Directory Tables, governance tags, `BUILD_SCOPED_FILE_URL`, and Snowpark
`SnowflakeFile.open` for files that SQL cannot parse.

## Step 5 — write Iceberg tables

```bash
./integrations/snowflake/scripts/setup_external_volume.sh \
  --bucket acme-lakehouse-iceberg-apne1
```

The script deploys the IAM role, prints the `CREATE EXTERNAL VOLUME` statement to
paste into Snowflake, and then takes back the two values `DESC EXTERNAL VOLUME`
returns:

```bash
./integrations/snowflake/scripts/setup_external_volume.sh --phase3 \
  --snowflake-arn "<STORAGE_AWS_IAM_USER_ARN>" \
  --external-id "<STORAGE_AWS_EXTERNAL_ID>"
```

Confirm before building on it:

```sql
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('fsxn_lakehouse_iceberg_vol');
```

A healthy result is `"success": true` with `writeResult`, `readResult`,
`listResult` and `deleteResult` all `PASSED`. Then:

```sql
CREATE OR REPLACE ICEBERG TABLE my_table (id STRING, value FLOAT)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'fsxn_lakehouse_iceberg_vol'
  BASE_LOCATION = 'my_table/';

COPY INTO my_table
FROM (SELECT $1:id::string, $1:value::float FROM @my_stage/events.json)
FILE_FORMAT = (TYPE = JSON);
```

The result is a real Iceberg table — metadata JSON, manifest Avro, data Parquet —
readable by other Iceberg-aware engines.

## Why writes go elsewhere

Two separate problems, both measured:

**Unloading to an Access Point leaves objects behind.** `COPY INTO @stage` is not
refused. The object is written, is intact, and then the statement fails with
`Remote upload failed checksum validation` because FSx for ONTAP reports
server-side encryption as `aws:fsx`, which is neither `AWS_SSE_S3` nor
`AWS_SSE_KMS`. You are told the write failed; a complete object remains.
Tracked as [BLK-009](./blocker-tracker.md).

**Delta writes fail at the commit, after the data lands.** The Access Point does
not implement conditional writes (`If-None-Match` returns 501), so the commit into
`_delta_log` fails while the Parquet files stay. Each retry adds another orphan.
Tracked as [BLK-002](./blocker-tracker.md).

Iceberg via Athena is the exception, because the Glue Data Catalog holds the
metadata pointer and the commit never needs a conditional write on S3.

If you or anyone before you tried writing to an Access Point, sweep for leftovers:

```bash
./shared/scripts/check_orphaned_unload_objects.py --access-point <your-ap-alias>
```

It reports prefixes holding engine output with no completion marker, which is what
an interrupted write looks like from the storage side. Look before using `--delete`.

## When this pattern fits, and when it does not

| Situation | Fit | Why |
|---|---|---|
| Files land on NAS from existing applications and you want SQL on them | Good | This is the case the pattern is for. No pipeline to build or operate |
| Multiple protocols on the same data — NFS write, S3 read | Good | The volume is one copy; the Access Point is a view of it |
| You need the freshest possible data | Good | Reads hit the volume; there is no sync lag to reason about |
| Large scans on a well-shaped dataset | Reasonable | Throughput is bounded by the file system's provisioned throughput, which you size |
| Transactional table writes onto the same storage | Poor | Delta cannot commit; unload leaves objects behind. Write to standard S3 |
| Millions of tiny files | Poor | Per-object overhead dominates. Compact first, or land Parquet |
| Nothing on NAS to begin with | Poor | If data is already in S3, the Access Point adds a hop and no benefit |

The honest summary: this removes a copy step for data that already lives on
ONTAP. If your data does not, the simpler architecture is standard S3.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `LIST` works, `SELECT` returns AccessDenied | `AWS_ACCESS_POINT_ARN` missing from the stage | Add it. See step 3 |
| `AccessDenied` on everything, right after setup | Trust policy still on the phase-1 placeholder | Run `update_trust_policy.sh` |
| `AccessDenied` after pasting the external id | The id ends with `=` and was truncated | Re-copy the whole value |
| `SYSTEM$VERIFY_EXTERNAL_VOLUME` fails on `listResult` only | The IAM policy prefix and `STORAGE_BASE_URL` disagree | Make them match |
| Access Point creation fails mentioning an object storage server | The SVM already runs native ONTAP S3 | Use a different SVM |
| `COPY INTO @stage` fails on checksum validation | Expected — [BLK-009](./blocker-tracker.md) | Do not unload to an Access Point |
| Snowpipe never fires | The Access Point emits no S3 Event Notifications ([BLK-003](./blocker-tracker.md)) | Use a Snowflake Task running `COPY INTO` |

## Tearing it down

```sql
DROP EXTERNAL VOLUME IF EXISTS fsxn_lakehouse_iceberg_vol;   -- before the bucket
DROP STAGE IF EXISTS my_stage;
DROP STORAGE INTEGRATION IF EXISTS fsxn_s3ap;
```

```bash
aws cloudformation delete-stack --stack-name fsxn-lakehouse-sf-external-volume
aws cloudformation delete-stack --stack-name fsxn-snowflake
aws fsx detach-and-delete-s3-access-point --name my-lakehouse-ap
```

Drop the external volume before deleting the bucket, or Snowflake keeps an object
pointing at storage that no longer exists. The bucket has `DeletionPolicy: Retain`
so stack deletion will not take your tables with it; empty and delete it
deliberately when you mean to.

## Related

| Document | What it covers |
|---|---|
| [Compatibility matrix](./compatibility-matrix.md) | Every engine and format, with verification status |
| [Blocker tracker](./blocker-tracker.md) | What does not work, and why |
| [Unverified inventory](./unverified-inventory.md) | What is untested, and what it would take |
| [Snowflake integration](../../integrations/snowflake/README.md) | SQL, Lambda, and test details |
