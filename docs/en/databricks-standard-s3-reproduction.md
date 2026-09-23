🌐 **English** | [日本語](../ja/databricks-standard-s3-reproduction.md)

# Reproducing the standard-S3 × Databricks unstructured-AI PoC

> **Purpose**: a runbook to rebuild, from scratch, the environment behind the [Databricks unstructured-data AI on a standard S3 bucket PoC](./databricks-standard-s3-unstructured-poc.md). The AWS side is reproduced with CloudFormation; the Databricks side is a sequence of console/API steps.
> **Expected time**: 30–45 minutes (including the first Foundation Model warm-up).
> **Cost**: Serverless SQL usage (Small ≈ a few DBU) + Foundation Model inference (token-billed) + S3 storage (a few KB, effectively zero). Vector Search, if you try it, adds endpoint billing (see [cost doc §7](./databricks-verification-environment-cost.md)).
> **Naming note**: this runbook targets a standard general-purpose S3 bucket, not an FSx for ONTAP S3 Access Point (that path is blocked by BLK-001; see the [FILE type evaluation](./databricks-file-type-evaluation.md)).

---

## Prerequisites

- A Databricks workspace (**US region recommended**, e.g. us-west-2). Pay-per-token Foundation Models are offered in US regions; a Tokyo workspace has no default endpoint.
- Unity Catalog enabled, and permission to create a Serverless SQL Warehouse.
- An AWS account (**may be in a different region** from the workspace: this PoC placed the bucket in ap-northeast-1 and the workspace in us-west-2 and confirmed cross-region operation).
- AWS CLI and CloudFormation deploy permissions (including IAM role creation).

---

## 1. Deploy the AWS side (CloudFormation)

Template: `poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml`. It creates the standard S3 bucket and the IAM role Unity Catalog assumes.

`UnityCatalogRoleArn` and `UnityCatalogExternalId` are **the values the External Location wizard in step 2 displays**, so either open step 2 once to note them first, or create the role with placeholders and update it to the wizard's values. This PoC used the latter (match the trust policy to what the wizard shows).

```bash
aws cloudformation deploy \
  --template-file poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml \
  --stack-name databricks-stds3-poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketName=fsxn-databricks-stds3-poc-<account-id>-<region-short> \
    RoleName=databricks-uc-stds3-poc \
    UnityCatalogRoleArn=arn:aws:iam::<databricks-uc-account>:role/unity-catalog-prod-UCMasterRole-XXXXXXXXXXXXX \
    UnityCatalogExternalId=<databricks-account-uuid> \
    Environment=dev \
  --region ap-northeast-1
```

`CAPABILITY_NAMED_IAM` is required because the role has an explicit name. After deploy, note `RoleArnOut` and `BucketNameOut` from the outputs.

> **IAM note**: this role's policy **deliberately omits** `s3:GetBucketNotification`. That is why only File Events fails with 403 in the step-2 validation (below). Add `s3:GetBucketNotification` / `s3:PutBucketNotification` to the template policy only if you intend to use File Events.

---

## 2. Create the Unity Catalog External Location

`CREATE STORAGE CREDENTIAL` in DBSQL is a syntax error (`PARSE_SYNTAX_ERROR`; UC administration statements are not supported in DBSQL). Use the **Catalog Explorer UI wizard**.

1. Catalog Explorer → External Data → Credentials → Create credential. Enter the IAM role ARN (`RoleArnOut`).
2. Databricks displays the **trust policy it expects**. In this environment that was the **UC master role (`arn:aws:iam::<databricks-uc-account>:role/unity-catalog-prod-UCMasterRole-...`) + self-assume + `sts:ExternalId` = account UUID** (a specific role ARN, not `:root`). Match your step-1 template parameters to these displayed values.
3. Create the External Location: name `stds3_poc_location`, URL `s3://<bucket>/`, selecting the credential above.
4. The connection validation runs. **Read / List / Write / Delete / Path Exists / Assume Role / Self Assume Role / External ID Condition = all Success** confirms BLK-001 does not occur on a standard bucket.
5. **Only File Events provision Fails** (`no identity-based policy allows the s3:GetBucketNotification action`, 403). File Events is optional, so proceed with "Force create". Read/write and AI processing are unaffected.

> **Pitfall**: with browser automation, combobox overlay elements land off-viewport and add round trips. The wizard is more reliable operated manually.

---

## 3. Catalog, schema, External Volume, sample data

Start a Serverless SQL Warehouse (Small, 10-minute auto-stop) and run in the SQL editor.

```sql
CREATE SCHEMA IF NOT EXISTS workspace.stds3_poc;
CREATE EXTERNAL VOLUME workspace.stds3_poc.unstructured
  LOCATION 's3://<bucket>/unstructured/';
```

Samples are synthetic (no real data). Generate them locally and put them on S3 (an inspection-image PNG, a bar-chart PNG, an inspection-report PDF). The generation script is optional; this PoC used Python (Pillow + reportlab) for the three files.

```bash
aws s3 cp inspection-sample-01.png s3://<bucket>/unstructured/
aws s3 cp chart-sample-02.png      s3://<bucket>/unstructured/
aws s3 cp report-sample-01.pdf     s3://<bucket>/unstructured/
```

```sql
LIST '/Volumes/workspace/stds3_poc/unstructured/';  -- 3 files visible = OK
```

---

## 4. Reproducing the scenarios

> **Model names measured**: in this environment the usable pay-per-token models were `databricks-meta-llama-3-3-70b-instruct` (text), `databricks-llama-4-maverick` (multimodal), and `databricks-gte-large-en` (embedding). `databricks-claude-3-7-sonnet` **does not exist**. If you get `RESOURCE_DOES_NOT_EXIST`, suspect the model name first (do not jump to a region constraint).

### 4.1 Scenario 2: PDF OCR with `ai_parse_document()`

```sql
SELECT ai_parse_document(content)
FROM READ_FILES('/Volumes/workspace/stds3_poc/unstructured/report-sample-01.pdf', format => 'binaryFile');
```

Success when `elements[0].type = title`, `content = "Synthetic Equipment Inspection Report"`.

### 4.2 Scenario 3: FILE type + AI functions

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.docs AS
  SELECT path, file FROM list_files('/Volumes/workspace/stds3_poc/unstructured/') WHERE path LIKE '%.pdf';
DESCRIBE TABLE workspace.stds3_poc.docs;                     -- file column type = file external
SELECT path, ai_parse_document(file) FROM workspace.stds3_poc.docs;  -- OCR the FILE column directly
```

The `file` column type is **`file external`**, and passing it straight to `ai_parse_document(file)` OCRs successfully. `FILE EXTERNAL` is blocked by BLK-001 on an S3 Access Point but holds on a standard bucket — the core of this PoC's contrast.

### 4.3 Scenario 1: LLM Vision on images with `ai_query()`

Hand-building the messages struct with `named_struct` in SQL breaks easily under Monaco's auto-close. A **Python notebook + `mlflow.deployments`** is reliable.

```python
from mlflow.deployments import get_deploy_client
import base64
client = get_deploy_client("databricks")
img = base64.b64encode(open("/Volumes/workspace/stds3_poc/unstructured/inspection-sample-01.png","rb").read()).decode()
resp = client.predict(endpoint="databricks-llama-4-maverick", inputs={"messages":[{"role":"user","content":[{"type":"text","text":"Describe this image."},{"type":"image_url","image_url":{"url":f"data:image/png;base64,{img}"}}]}]})
print(resp)
```

Success when the synthetic image (a blue square, an orange circle, a black bar at the bottom) is described correctly.

### 4.4 Scenario 4: AI Functions across the board

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.doc_chunks
  TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
  SELECT explode(...) ...;  -- split ai_parse_document output into title/text/table chunks
SELECT ai_classify(chunk, array('inspection_report','financial','marketing','legal')) FROM workspace.stds3_poc.doc_chunks;  -- inspection_report
SELECT ai_gen('Summarize in 8 words or fewer: ' || chunk) FROM workspace.stds3_poc.doc_chunks;
SELECT ai_analyze_sentiment(chunk) FROM workspace.stds3_poc.doc_chunks;  -- neutral
```

### 4.5 Scenario 6: Natural-language querying with Genie

```sql
CREATE OR REPLACE TABLE workspace.stds3_poc.inspection_findings
  (item STRING, status STRING, score DOUBLE) COMMENT 'Inspection results table';
INSERT INTO workspace.stds3_poc.inspection_findings VALUES
  ('Weld seam','Review',0.71), ('Coating','OK',0.95), ('Pressure valve','OK',0.98);
```

Create a Genie space and connect `inspection_findings`. Asking "Which inspection item has the lowest score?" should return **Weld seam (0.71, Review)** (NL → SQL auto-generation → execution → NL answer).

### 4.6 Scenario 5: Mosaic AI Vector Search (environment-dependent, not completed)

Endpoint creation and the Delta Sync Index creation request are Verified. In this environment the index stayed `PROVISIONING_ENDPOINT` for about 16 minutes and never reached ONLINE (`databricks-gte-large-en` high latency plus trial/shared-environment provisioning delay; details in [cost doc §7](./databricks-verification-environment-cost.md)). If you try it, mind the billing (**endpoint billing persists for 24 hours after the last index is deleted**). For critical operations like teardown, avoid indented Python (`try/except`) and use flat single-line statements (a Monaco auto-indent guard).

---

## 5. Teardown

Contains irreversible operations. Confirm the targets before running.

```bash
# AWS: empty the bucket, then delete the CFn stack (the bucket is DeletionPolicy: Retain, so delete it separately)
aws s3 rm s3://<bucket>/ --recursive
aws s3api delete-bucket --bucket <bucket> --region ap-northeast-1
aws cloudformation delete-stack --stack-name databricks-stds3-poc --region ap-northeast-1
```

On the Databricks side, delete in reverse dependency order: tables (`docs` / `doc_chunks` / `inspection_findings`) → External Volume → schema `stds3_poc` → External Location `stds3_poc_location` → the auto-generated Storage Credential. Delete the Genie space and the notebook too. The SQL Warehouse, if shared, only needs stopping (10-minute auto-stop). If you created Vector Search, delete the index then the endpoint, and mind the 24-hour billing tail.

---

## References

- [Databricks unstructured-data AI on a standard S3 bucket — PoC](./databricks-standard-s3-unstructured-poc.md) — the verification write-up itself (6 scenarios, IAM/auth, CloudTrail corroboration, Snowflake Cortex contrast)
- [FILE type (Beta) evaluation](./databricks-file-type-evaluation.md) — behaviour on an S3 Access Point and the recommendation to stage to standard S3
- [Verification environment and cost](./databricks-verification-environment-cost.md) — pay-per-token US-only, Vector Search billing tail, teardown checklist
- CloudFormation template: `poc-templates/08-databricks-standard-s3/standard-s3-uc-access.yaml`
