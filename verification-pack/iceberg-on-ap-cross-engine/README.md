🌐 [日本語](README-ja.md) | **English**

# Cross-engine verification plan: Iceberg on an Access Point, read from Databricks and Snowflake

This is a plan, not a result. No case here has been run. Results go under `evidence/<date>/` when they exist.

## Question this plan answers

Can an Iceberg table whose data and metadata live on an FSx for ONTAP S3 Access Point, registered in the AWS Glue Data Catalog, be read from Databricks Unity Catalog and from Snowflake? And if a read fails, is the cause the catalog or the storage path?

The repository records show these pieces separately:

| Piece | Recorded state | Source |
|---|---|---|
| Athena creates and writes an Iceberg table on an Access Point alias, with Glue as catalog | Run 2026-08-06 | [athena-iceberg evidence](../athena-iceberg/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake reads files from an Access Point through a Storage Integration and External Stage | Run 2026-05 and 2026-08-06 | [snowflake evidence](../snowflake/evidence/2026-08-06/evidence-record.yaml) |
| Snowflake reads an S3 Tables Iceberg table through Glue Iceberg REST with `VENDED_CREDENTIALS` | Run 2026-06-05 | [compatibility matrix](../../docs/en/compatibility-matrix.md) |
| Unity Catalog registers an External Location on an Access Point alias but is denied on read | Run 2026-08-12 | [BLK-001](../../docs/en/blocker-tracker.md) |
| Glue HMS Federation to a Foreign Catalog over a table on an Access Point | **Not run** | [execution guide](../../integrations/iceberg-metadata-catalog/databricks/foreign-iceberg-execution-guide.md) |
| Snowflake Catalog Integration to Glue over a table on an Access Point | **Not run** | [compatibility matrix](../../docs/en/compatibility-matrix.md) |
| Directory Table on an Access Point stage | Statements exist in [unstructured-data-access](../../docs/en/unstructured-data-access.md); no run record found | — |

This plan fills the three "Not run" rows.

## Design: one table, one control, two engines

Every engine reads the same logical table twice. The only difference is where the files sit.

| Table | Location | Purpose |
|---|---|---|
| `xeng_ap.probe` | `s3://<AP_ALIAS>/xeng/probe/` (internet-origin Access Point) | Subject |
| `xeng_s3.probe` | `s3://<STANDARD_BUCKET>/xeng/probe/` | Control: same schema, same rows, standard S3 |

If the control fails, the setup is wrong and the subject result means nothing. Record the control result first in every track.

Schema: `id int, marker string, ts timestamp`. Insert 3 rows with distinct `marker` values (`row-a`, `row-b`, `row-c`), then a 4th row (`row-d`) later for the refresh cases.

Both tables are created by Athena, because that path is already recorded as working on an Access Point.

## Preconditions

| Item | Requirement |
|---|---|
| File system | ONTAP 9.17.1 or later. Query the REST API; the console does not show it |
| Access Point | Internet-origin. Snowflake and Athena cannot read a VPC-origin one. Databricks serverless is also outside your VPC |
| IAM | One role per engine, with `s3:GetObject`, `s3:ListBucket`, `s3:GetBucketLocation` on the **access point ARN** (alias-as-bucket ARN alone fails for Databricks, see BLK-001) |
| Glue | Standard Glue Data Catalog in the same Region, not `s3tablescatalog` |
| Lake Formation | Needed only for the Snowflake vended-credential case (SF-03). Register the Access Point location with `register-resource` (the 2026-05-24 record shows the API accepts it) |
| Databricks | A non-trial workspace in the same Region as the file system. Account UUID as the storage credential external ID. A service credential for Glue whose IAM role is self-assuming, with Lake Formation permissions that stay in place for the whole run (a brief loss makes Unity Catalog drop and recreate the foreign catalog's schemas, per the [Databricks Glue federation page](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue)). Standard-access-mode compute on DBR 13.3 LTS or later |
| Snowflake | A session with `ACCOUNTADMIN` or a role that can create integrations |
| Syntax | Re-read the current Databricks and Snowflake documentation for `CREATE CONNECTION` (Glue), `CREATE FOREIGN CATALOG`, `CREATE CATALOG INTEGRATION` and `CREATE EXTERNAL VOLUME` before running. Both vendors change these statements |

**Credentials.** Do not snapshot a sign-in page, and do not print a token or secret. Follow the rules in `AGENTS.md` (Browser Automation and Credentials).

## Setup S0: create the tables (Athena)

```sql
CREATE DATABASE xeng_ap;
CREATE DATABASE xeng_s3;

CREATE TABLE xeng_ap.probe (id int, marker string, ts timestamp)
LOCATION 's3://<AP_ALIAS>/xeng/probe/'
TBLPROPERTIES ('table_type'='ICEBERG');

CREATE TABLE xeng_s3.probe (id int, marker string, ts timestamp)
LOCATION 's3://<STANDARD_BUCKET>/xeng/probe/'
TBLPROPERTIES ('table_type'='ICEBERG');

INSERT INTO xeng_ap.probe VALUES (1,'row-a',current_timestamp),(2,'row-b',current_timestamp),(3,'row-c',current_timestamp);
INSERT INTO xeng_s3.probe VALUES (1,'row-a',current_timestamp),(2,'row-b',current_timestamp),(3,'row-c',current_timestamp);
```

Pass: `SELECT marker FROM xeng_ap.probe` and the same on `xeng_s3.probe` return `row-a`, `row-b`, `row-c`. Save the Glue `metadata_location` of both tables; it shows where each engine will have to read.

## Track D: Databricks Unity Catalog

Run D0 first. BLK-001 is dated 2026-08-12 and may have been fixed since.

| ID | Case | Steps | What to record |
|---|---|---|---|
| D0 | Recheck BLK-001 | Create storage credential, External Location and External Volume on the Access Point alias. Run `list_files` on the volume | Pass or the 403 text. If it now passes, D2 is likely to pass too |
| D1 | Control: Foreign Catalog over `xeng_s3` | Connection of type Hive Metastore, metastore type AWS Glue, with the service credential. External Location on `s3://<STANDARD_BUCKET>/xeng/`. Foreign catalog with `authorized_paths` and **a storage location set on the catalog itself** (Databricks documents this as mandatory for Iceberg reads; inheriting the metastore root is not enough). Then `SHOW SCHEMAS`, `SHOW TABLES`, `SELECT marker` | Row set. Must be `row-a..c` |
| D2 | Subject: Foreign Catalog over `xeng_ap` | Same as D1 with the Access Point alias as `authorized_paths`. Run the five statements one at a time | **The first statement that fails**: connection, External Location, foreign catalog, `SHOW TABLES`, `SELECT` metadata, or `SELECT` data. The error text verbatim |
| D3 | Refresh | Insert `row-d` from Athena. `SELECT COUNT(*)` without refresh, then `REFRESH FOREIGN TABLE`, then again | Counts at each step. Run on D1 and, if D2 reads, on D2 |
| D4 | Outside Unity Catalog | Spark cluster with an instance profile and the Glue catalog configured at cluster scope. Read `xeng_ap.probe` | Pass or fail. A pass shows the data is readable and only the Unity Catalog path is blocked. Governance does not apply on this path |

D2 reading which layer fails is the useful output. BLK-001 predicts the data read fails with a session-policy error; whether the catalog steps before it succeed is not recorded anywhere.

## Track S: Snowflake

| ID | Case | Steps | What to record |
|---|---|---|---|
| S1 | Control: Glue Catalog Integration over `xeng_s3` | `CREATE CATALOG INTEGRATION` (`ICEBERG_REST`, `AWS_GLUE`, `SigV4`, `VENDED_CREDENTIALS`), trust-policy update with the returned external ID, `SYSTEM$VERIFY_CATALOG_INTEGRATION`, `CREATE ICEBERG TABLE ... CATALOG_TABLE_NAME`, `SELECT` | Row set. Template: [snowflake-setup.sql](../../integrations/iceberg-metadata-catalog/snowflake/etl-standard-glue-path/snowflake-setup.sql) |
| S2 | Subject, External Volume mode | Catalog Integration with `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` (the default). `CREATE EXTERNAL VOLUME` with `STORAGE_BASE_URL = 's3://<AP_ALIAS>/xeng/'` **and `STORAGE_AWS_ACCESS_POINT_ARN`**, which the `CREATE EXTERNAL VOLUME` reference documents as required when the base URL is an access point alias. Iceberg data and metadata files must lie under the base URL. `SYSTEM$VERIFY_EXTERNAL_VOLUME`. Iceberg table with `EXTERNAL_VOLUME` and `CATALOG_TABLE_NAME = 'probe'`. `SELECT` | Result of the volume check (it tests write, and BLK-009 predicts a write to an Access Point fails checksum validation), then whether the read still works. Run `check_orphaned_unload_objects.py` afterwards |
| S3 | Subject, vended-credential mode | Register `s3://<AP_ALIAS>/xeng/` in Lake Formation. Grant the integration role `SELECT` on `xeng_ap.probe`. Same catalog integration as S1 pointed at `xeng_ap`. `SELECT` | Whether Lake Formation vends credentials for an Access Point location. The error text if not |
| S4 | Refresh | Insert `row-d` from Athena. `ALTER ICEBERG TABLE ... REFRESH`, or wait for `AUTO_REFRESH`. Count | Seconds until `row-d` is visible, per mode that read in S2 or S3 |

## Track U: unstructured files

Unstructured files are not catalog tables. They are reached by path. The catalog question for them is whether a table of file metadata can point at paths that each engine then opens.

| ID | Case | Steps | What to record |
|---|---|---|---|
| U1 | Snowflake Directory Table | Stage on the Access Point alias with `DIRECTORY = (ENABLE = TRUE)`. `ALTER STAGE ... REFRESH`. `SELECT * FROM DIRECTORY(@stage)` | Row count against the object count, and the refresh behaviour (the Access Point emits no event notifications, BLK-003) |
| U2 | Path from an Iceberg inventory table to `TO_FILE` | Insert 2 rows into `xeng_ap.files(path string, size bigint)` pointing at 2 objects under the Access Point. In Snowflake, join to the stage and call `TO_FILE` or `PARSE_DOCUMENT` | Whether the chain table → path → file works end to end |
| U3 | Databricks path from the same inventory | Read `xeng_s3.files` in D1, then `read_files` or `FILE EXTERNAL` on the Access Point path | Expected to follow D0. `FILE EXTERNAL` needs a Unity Catalog volume, so it is blocked while D0 fails |

## Reading the results

| Outcome | Interpretation |
|---|---|
| D1 and S1 pass, D2 fails at the data read, S2 or S3 passes | The limit is the Unity Catalog session policy on Access Point paths. Where the catalog sits does not matter |
| D2 fails before the data read (connection, External Location or foreign catalog) | A catalog-side limit exists in addition to BLK-001 |
| D2 passes | BLK-001 no longer holds for this path. Update the blocker tracker |
| S2 fails on the volume write check but the read passes | The read path works; use a separate read-only role and skip the verify procedure |
| S2 and S3 both fail, D4 passes | Catalog Integration over an Access Point is blocked at the storage layer for Snowflake, not at the catalog |
| D1 or S1 fails | The setup is wrong. Fix it and rerun; record nothing about the subject |

Only after these results can the repository say whether converting to S3 Tables or standard-S3 Iceberg, versus keeping the table on the Access Point, is needed per engine. Nothing in this plan tests S3 Tables, because the repository already records Databricks being unable to register its internal bucket (B-10).

## Prior art searched for this plan

Searched in the Snowflake and Databricks documentation, vendor guides and public blogs. No source reads an Iceberg table that lives on an FSx for ONTAP S3 Access Point from either engine through a catalog. What exists:

| Source | What it covers | Use in this plan |
|---|---|---|
| [Snowflake: Glue Iceberg REST catalog integration](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-glue) and [vended credentials](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials) | Standard S3 buckets. Table files must sit in one bucket per table. Snowflake does not check permissions until a table is created | Template for S1. Basis for the control |
| [Snowflake guide: Iceberg with Snowflake and AWS Glue](https://www.snowflake.com/en/developers/guides/data-lake-using-apache-iceberg-with-snowflake-and-aws-glue/) | Glue + Lake Formation credential vending on standard S3 | Step order for S1 and S3 |
| [Snowflake `CREATE EXTERNAL VOLUME`](https://docs.snowflake.com/en/sql-reference/sql/create-external-volume) | Access point alias supported through `STORAGE_AWS_ACCESS_POINT_ARN` | S2 parameter. Not exercised against FSx for ONTAP anywhere in the sources found |
| [Databricks: Hive metastore federation for AWS Glue](https://docs.databricks.com/aws/en/query-federation/hms-federation-glue) | Standard S3. Authorized paths, catalog storage location for Iceberg, service credential, Lake Formation permission continuity | Template for D1 |
| [AWS: Federate to Databricks Unity Catalog](https://aws.amazon.com/blogs/big-data/access-databricks-unity-catalog-data-using-catalog-federation-in-the-aws-glue-data-catalog/) | The reverse direction, standard S3 | Out of scope below |
| dev.to articles on the same topic for [Snowflake](https://dev.to/aws-builders/snowflake-and-fsx-for-ontap-s3-access-points-from-access-denied-to-working-external-tables-9k8) and [Databricks](https://dev.to/aws-builders/databricks-and-fsx-for-ontap-s3-access-points-a-layer-by-layer-validation-of-observed-boundaries-p4d) | Stage and External Location on an Access Point; the session-policy ARN mismatch | Same evidence as the blocker tracker |
| [AWS re:Post thread](https://repost.aws/pt/questions/QUmbYyURiVSzu4tdccXuLqvQ/hive-unknown-error-invalid-port-in-file-system-location) | Athena rejects an Iceberg table whose location is the access point **ARN** (`Invalid port in file system location`) | Use the alias, not the ARN, as the table location in S0 |

The Snowflake article above says an Iceberg table on an Access Point is "not suitable in place" because conditional writes are missing. That sentence concerns writes. This repository's 2026-08-06 Athena run wrote Iceberg in place, and this plan only reads, so the two do not conflict, but the article's wording is broader than its evidence.

Because no source covers the subject, the standard S3 control (D1, S1) follows the vendor documents above, and the subject cases (D2, S2, S3) are new measurements.

## Cost

Unit prices below come from the AWS Pricing API as recorded for this account's earlier runs (ap-northeast-1, retrieved 2026-10-26) and vendor pages. Re-check before running; prices drift.

| Item | Basis | Estimate for one 2 to 4 hour run |
|---|---|---|
| FSx for ONTAP file system | Reuse the existing file system (Single-AZ, 128 MBps, 1,024 GiB SSD, already running). A throwaway volume of a few GiB sits inside the provisioned capacity | No increment. The standing charge (about $0.37 per hour at $0.150 per GB-month and $0.906 per MBps-month) is already being paid |
| Access Point | Not checked against the Pricing API. Confirm before running | Unconfirmed; assume small |
| Athena | $5.00 per TB scanned, 10 MB minimum per query | Under $0.01 for roughly 50 queries |
| S3 standard bucket (control) | $0.025 per GB-month | Under $0.01 |
| Glue Data Catalog | First 1,000,000 metadata objects and 1,000,000 requests per month are free | $0 |
| Lake Formation | No separate charge for permissions | $0 |
| Snowflake | X-Small warehouse, 1 credit per hour, per-second billing with a 60-second minimum, auto-suspend | 2 to 4 credits at most. Dollar value follows the account's contract rate |
| Databricks | Serverless SQL warehouse, billed in DBUs. List price per DBU varies by product, tier and Region; I did not find a confirmed ap-northeast-1 rate | Warehouse size and DBU rate to be read from the workspace before the run. Set the auto-stop to 5 minutes. D4 adds a classic cluster, which also bills EC2 |
| Cross-engine data transfer | Table is a few KB | Negligible |

The AWS side adds almost nothing. The two vendor bills are the cost to confirm, and both depend on contract terms that this repository does not hold.

**Cost guard.** Keep each warehouse suspended between cases. Stop and tear down the same day. Do not leave the throwaway volume and Access Point in place; the file system's standing charge is unaffected either way, but orphaned Snowflake objects (S2) are the one leftover that costs nothing yet causes a failed later run.

## Out of scope

- The reverse direction in the AWS blog, where Glue federates **to** Unity Catalog and AWS engines read Unity Catalog tables. It concerns Unity Catalog-managed storage, not an Access Point. Run it separately if needed.
- Write paths. Databricks is read-only on Foreign Iceberg tables, and unloading to an Access Point is BLK-009.
- Performance. The table has single-digit rows.

## Failure modes to plan for

| Failure | Mitigation |
|---|---|
| Snowflake leaves an object on the Access Point after a failed write check (S2) | Run the orphan check; delete leftovers |
| 403 that looks like "unsupported" but is an ARN or external-ID mistake | Use the access point ARN in the IAM policy. Use the account UUID as the Databricks external ID. D1 catches the rest |
| Athena metadata written with a path form an engine cannot parse | Save `metadata_location` in S0 and compare with what each engine reports |
| Trial or restricted Databricks workspace | Use a non-trial workspace, as for BLK-001 |
| Auth expiry mid-run | Ask for `aws sso login` and wait |

## Evidence and teardown

- Copy `verification-pack/templates/evidence-record.yaml` to `evidence/<date>/evidence-record.yaml`. One record, one block per case ID. Put raw outputs in `evidence/<date>/raw/`.
- Replace account IDs, workspace URLs, the Access Point alias and names with placeholders before commit. Run the repository's gitleaks and PII checks.
- Teardown order: Snowflake integrations, volume and tables; Databricks catalog, connection, External Location, volume, credential; Lake Formation registration; Glue databases; Access Point (through the Amazon FSx API; a volume with an attached Access Point cannot be deleted from ONTAP); then the throwaway volume; standard bucket. Export `raw/` before deleting anything.
- Report per case: pass, fail with the first failing statement, or not run. Do not infer an untested case from its neighbour.
