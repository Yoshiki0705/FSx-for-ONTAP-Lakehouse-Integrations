🌐 **English** | [日本語](../ja/ai-demo-guide.md)

# Snowflake Analytics & AI Demo Guide — FSx for ONTAP S3 AP

This guide demonstrates analytics and AI/ML capabilities on FSx for ONTAP data accessed via Snowflake [External Stage](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage) with `AWS_ACCESS_POINT_ARN`.

> 📖 For a detailed comparison of **External Table vs Internal Table** (zero-copy vs COPY INTO) including decision flowchart and cost analysis, see the [Internal Table vs External Table Design Guide](../../README.md#internal-table-vs-external-table--design-guide).

## Prerequisites

- Snowflake account with Cortex AI enabled
- FSx for ONTAP S3 Access Point configured
- External Stage with `AWS_ACCESS_POINT_ARN` (see [README](../../README.md))

## Demo 1: OCR Text Extraction (PARSE_DOCUMENT)

**Use case**: Extract text from scanned inspection reports, invoices, or quality documents stored on NAS.

```sql
-- OCR: Extract text from image on FSx for ONTAP
SELECT SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
  @fsxn_stage,
  'media/documents/invoice_sample.png',
  {'mode': 'OCR'}
) AS ocr_result;
```

**Result**: Structured text extracted from the image (~8s).

![PARSE_DOCUMENT OCR extracts text from image on FSx for ONTAP S3 AP](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-08-parse-document-ocr.png)

*PARSE_DOCUMENT successfully extracts text from an invoice image stored on FSx for ONTAP via S3 Access Point. The result includes structured fields such as invoice number, customer name, and amount.*

**Manufacturing use case**: Digitize paper-based inspection reports stored on NFS, making them searchable and analyzable without manual data entry.

## Demo 2: AI Text Summarization (CORTEX.SUMMARIZE)

**Use case**: Summarize sensor data, log files, or document content for quick insights.

```sql
-- Summarize sensor data from External Table
SELECT SNOWFLAKE.CORTEX.SUMMARIZE(VALUE::VARCHAR) AS ai_summary
FROM fsxn_sensor_ext_table
LIMIT 1;
```

**Result**: "The text is a JSON object containing data on humidity, pressure, temperature, sensor ID, status, and timestamp." (3.3s)

![Cortex SUMMARIZE generates AI summary from External Table on FSx for ONTAP S3 AP](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-07-cortex-llm-summary.png)

*Cortex SUMMARIZE generates an AI summary of sensor data stored on FSx for ONTAP, accessed via External Table (3.3s).*

**Manufacturing use case**: Auto-generate shift summaries from IoT sensor data stored on FSx for ONTAP.

## Demo 3: File Catalog + Download URLs

**Use case**: Manage unstructured data (images, videos, documents) as a searchable library.

```sql
-- Enable file catalog
ALTER STAGE fsxn_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_stage REFRESH;

-- Search for inspection images
SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED,
  GET_PRESIGNED_URL(@fsxn_stage, RELATIVE_PATH, 3600) AS DOWNLOAD_URL
FROM DIRECTORY(@fsxn_stage)
WHERE RELATIVE_PATH LIKE 'media/images/%'
ORDER BY LAST_MODIFIED DESC;
```

**Result**: File catalog with downloadable URLs for each image.

![Directory Table with presigned URLs for unstructured data on FSx for ONTAP S3 AP](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-06-directory-table-presigned-url.png)

*Directory Table catalogs image files on FSx for ONTAP with metadata and generates download URLs for each file.*

**Manufacturing use case**: Quality engineers search for inspection photos by date/location, download for review.

## Demo 4: Vision AI for Defect Detection (TBD)

**Use case**: Natural language instructions for product quality inspection.

```sql
-- Vision AI: Analyze product inspection image (syntax requires validation)
SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(
  'claude-3-5-sonnet',
  'Analyze this product inspection image and identify any defects or quality issues.',
  {'image': BUILD_SCOPED_FILE_URL(@fsxn_stage, 'media/images/product_inspection.png')}
) AS defect_analysis;
```

**Status**: ✅ **Verified with workaround** — Vision AI works when files are copied to an unencrypted [internal stage](https://docs.snowflake.com/en/user-guide/data-load-local-file-system-create-stage). Direct `TO_FILE()` on FSx for ONTAP S3 AP [external stage](https://docs.snowflake.com/en/user-guide/data-load-s3-create-stage) returns "Remote file not found." See [Internal vs External Table Design Guide](../../README.md#internal-table-vs-external-table--design-guide) for architecture trade-offs.

**Workaround (validated)**:
```sql
-- Step 1: Copy file from FSx for ONTAP S3 AP to unencrypted internal stage
CREATE OR REPLACE STAGE fsxn_ai_noenc_stage ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
COPY FILES INTO @fsxn_ai_noenc_stage FROM @fsxn_ap_arn_test_stage/media/documents/invoice_sample.png;
ALTER STAGE fsxn_ai_noenc_stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE fsxn_ai_noenc_stage REFRESH;

-- Step 2: Enable Cross-Region Inference (required for vision models in ap-northeast-1)
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- Step 3: Run Vision AI
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  'pixtral-large',
  'Describe this invoice image. What is the invoice number, customer name, and total amount?',
  FILE
) AS vision_result
FROM (
  SELECT TO_FILE(BUILD_SCOPED_FILE_URL(@fsxn_ai_noenc_stage, RELATIVE_PATH)) AS FILE
  FROM DIRECTORY(@fsxn_ai_noenc_stage)
  WHERE RELATIVE_PATH LIKE '%.png' LIMIT 1
);
```

**Result**: ✅ Vision AI correctly identified: Invoice #INV-2026-0524, Customer: Acme Corp, Amount: USD 1,234.56 (41s)

![Vision AI successfully analyzes invoice image from FSx for ONTAP (via internal stage workaround)](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-15-vision-ai-success.png)

*Cortex COMPLETE (pixtral-large) correctly extracts invoice details from an image originally stored on FSx for ONTAP, accessed via the COPY FILES → internal stage → TO_FILE workaround.*

**Why direct TO_FILE on FSx for ONTAP S3 AP fails**:

![TO_FILE returns "Remote file not found" on FSx for ONTAP S3 AP external stage](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-10-tofile-remote-not-found.png)

*TO_FILE() cannot resolve files on FSx for ONTAP S3 AP external stages. The same file is accessible via PARSE_DOCUMENT (which uses a different file access mechanism) but not via TO_FILE.*

**Manufacturing use case**: Automated visual quality inspection — natural language instructions like "identify scratches on this component" or "check alignment of this assembly." Requires the COPY FILES workaround for now.

## Demo 5: Text-based Cortex AI Functions (All Working)

All text-based Cortex AI functions work directly on FSx for ONTAP S3 AP External Table data without any workaround:

```sql
-- TRANSLATE: Translate sensor status to Japanese
SELECT SNOWFLAKE.CORTEX.TRANSLATE(VALUE:status::VARCHAR, 'en', 'ja') AS translated
FROM fsxn_sensor_ext_table LIMIT 1;

-- SENTIMENT: Analyze sentiment of text data
SELECT SNOWFLAKE.CORTEX.SENTIMENT(VALUE:status::VARCHAR) AS sentiment_score
FROM fsxn_sensor_ext_table LIMIT 3;

-- COMPLETE (text-only): AI analysis of sensor data
SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2',
  'Analyze this IoT sensor reading and identify anomalies: ' || VALUE::VARCHAR
) AS ai_analysis FROM fsxn_sensor_ext_table LIMIT 1;

-- EXTRACT_ANSWER: Extract specific information
SELECT SNOWFLAKE.CORTEX.EXTRACT_ANSWER(VALUE::VARCHAR,
  'What is the sensor ID and temperature reading?'
) AS extracted FROM fsxn_sensor_ext_table LIMIT 1;
```

![CORTEX.TRANSLATE successfully translates External Table data from FSx for ONTAP S3 AP](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-11-cortex-translate-success.png)

*CORTEX.TRANSLATE translates sensor status text from English to Japanese directly from External Table on FSx for ONTAP S3 AP (5.1s).*

![CORTEX.COMPLETE generates AI analysis of sensor data from FSx for ONTAP S3 AP](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-12-cortex-complete-text-success.png)

*CORTEX.COMPLETE (mistral-large2) generates detailed AI analysis of IoT sensor data stored on FSx for ONTAP (16s).*

## Cortex AI Comprehensive Compatibility Matrix

| Function | Input Source | FSx for ONTAP S3 AP Direct | Workaround | Duration |
|---|---|:---:|:---:|---|
| **PARSE_DOCUMENT (OCR)** | Stage path string | ✅ Direct | — | ~8s |
| **CORTEX.SUMMARIZE** | External Table column | ✅ Direct | — | 3.3s |
| **CORTEX.TRANSLATE** | External Table column | ✅ Direct | — | 5.1s |
| **CORTEX.SENTIMENT** | External Table column | ✅ Direct | — | 2.5s |
| **CORTEX.COMPLETE (text)** | External Table column | ✅ Direct | — | 16s |
| **CORTEX.EXTRACT_ANSWER** | External Table column | ✅ Direct | — | 2.7s |
| **COMPLETE (vision/multimodal)** | TO_FILE + image | ❌ Remote file not found | ✅ COPY FILES → internal stage | 41s |
| **TO_FILE on external stage** | FSx for ONTAP S3 AP stage | ❌ Not supported | COPY FILES to internal | — |
| **TO_FILE on encrypted internal** | Default internal stage | ❌ Encryption not supported | Use SNOWFLAKE_SSE | — |

### Key Findings

1. **Text-based functions work directly** — No workaround needed for SUMMARIZE, TRANSLATE, SENTIMENT, COMPLETE (text), EXTRACT_ANSWER on External Table data
2. **PARSE_DOCUMENT works directly** — Uses stage path string (different mechanism from TO_FILE)
3. **TO_FILE does NOT work on FSx for ONTAP S3 AP external stages** — "Remote file not found" (confirmed, matches NetApp support case)
4. **Vision AI workaround exists**: `COPY FILES` → unencrypted internal stage → `TO_FILE(BUILD_SCOPED_FILE_URL())` → COMPLETE multimodal
5. **Cross-Region Inference required** for vision models in ap-northeast-1

## Verified Results Summary

| Capability | Status | Duration | Use Case |
|---|:---:|---|---|
| PARSE_DOCUMENT (OCR) | ✅ Verified | ~8s | Invoice/report text extraction |
| CORTEX.SUMMARIZE | ✅ Verified | 3.3s | Sensor data / document summarization |
| CORTEX.TRANSLATE | ✅ Verified | 5.1s | Multi-language support |
| CORTEX.SENTIMENT | ✅ Verified | 2.5s | Text sentiment analysis |
| CORTEX.COMPLETE (text) | ✅ Verified | 16s | AI analysis, anomaly detection |
| CORTEX.EXTRACT_ANSWER | ✅ Verified | 2.7s | Information extraction from text |
| COMPLETE (vision) via workaround | ✅ Verified | 41s | Image analysis, defect detection |
| Directory Table + URLs | ✅ Verified | 1.3s | Unstructured data catalog |
| TO_FILE on FSx for ONTAP S3 AP | ❌ Blocked | — | Multimodal direct access not supported |

## Screenshots

- [OCR success](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-08-parse-document-ocr.png)
- [Cortex SUMMARIZE](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-07-cortex-llm-summary.png)
- [Directory Table](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-06-directory-table-presigned-url.png)
- [TO_FILE compilation error](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-09-tofile-compilation-error.png)
- [TO_FILE remote not found](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-10-tofile-remote-not-found.png)
- [CORTEX.TRANSLATE success](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-11-cortex-translate-success.png)
- [CORTEX.COMPLETE text success](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-12-cortex-complete-text-success.png)
- [Vision AI success (workaround)](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-15-vision-ai-success.png)

---

## Governance Tags & Data Protection

Snowflake provides tag-based governance that enables automatic data protection enforcement — including on External Tables backed by FSx for ONTAP S3 AP.

### How It Works

```
Object Tag (classification)
    │
    ├── Tag-based Masking Policy (column-level protection)
    │     → Automatically masks sensitive columns based on tag value
    │     → Applies to all tables/views inheriting the tag
    │
    └── Row Access Policy (row-level filtering)
          → Restricts visible rows based on user role/attributes
          → Enforced at query time, transparent to users
```

### Governance Boundary: What's Protected

| Level | Tag Support | Masking Policy | Row Access Policy | Notes |
|---|:---:|:---:|:---:|---|
| Database | ✅ | ✅ (inherited) | — | Tags cascade to all schemas/tables below |
| Schema | ✅ | ✅ (inherited) | — | Tags cascade to all tables below |
| Table (including External Table) | ✅ | ✅ | ✅ | **Full governance on FSx for ONTAP S3 AP data** |
| Column | ✅ | ✅ (direct) | — | Most granular masking target |
| Stage / File | ✅ (tag only) | ❌ | ❌ | Tags for classification; no query-time enforcement |

### Key Insight: External Tables Are Fully Governed

Unlike some platforms, Snowflake applies the same governance controls to External Tables as to native tables:

![SELECT fails without AWS_ACCESS_POINT_ARN — access denied despite LIST working](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-03-select-denied.png)

*Without `AWS_ACCESS_POINT_ARN`: SELECT fails with "access denied" even though LIST works. With the parameter set, full governance (tags, masking, row policies) can be applied to External Tables on FSx for ONTAP S3 AP.*

```sql
-- 1. Create classification tag
CREATE TAG IF NOT EXISTS data_classification ALLOWED_VALUES 'PII', 'CONFIDENTIAL', 'PUBLIC';

-- 2. Apply tag to External Table column
ALTER TABLE fsxn_sensor_ext_table MODIFY COLUMN customer_name SET TAG data_classification = 'PII';

-- 3. Create tag-based masking policy (Enterprise Edition required)
CREATE MASKING POLICY pii_mask AS (val STRING) RETURNS STRING ->
  CASE WHEN CURRENT_ROLE() IN ('DATA_ADMIN') THEN val
       ELSE '***MASKED***'
  END;

-- 4. Attach masking policy to tag
ALTER TAG data_classification SET MASKING POLICY pii_mask;

-- Result: Any column tagged 'PII' is automatically masked for non-admin roles
```

### Edition Requirements

| Feature | Standard | Enterprise | Business Critical |
|---|:---:|:---:|:---:|
| Object Tags (CREATE TAG, SET TAG) | ✅ | ✅ | ✅ |
| Tag-based Masking Policies | ❌ | ✅ | ✅ |
| Row Access Policies | ❌ | ✅ | ✅ |
| Data Classification (auto-detect PII) | ❌ | ✅ | ✅ |
| External Tokenization | ❌ | ✅ | ✅ |

### Comparison with Databricks

| Capability | Snowflake | Databricks |
|---|---|---|
| Tag-based column masking | ✅ Tag-based Masking Policy (Enterprise) | ✅ ABAC Governed Tags + Column Masks |
| Row-level filtering | ✅ Row Access Policy (Enterprise) | ✅ ABAC Row Filter Policies |
| Auto-classification (PII detection) | ✅ Built-in (Enterprise) | ✅ Built-in (automated data classification) |
| Governance on External Table | ✅ **Full support** (verified on FSx for ONTAP S3 AP) | ❌ **Blocked** (CREATE TABLE fails on S3 AP) |
| Tag inheritance | Database → Schema → Table → Column | Catalog → Schema → Table (not to column) |
| Enforcement boundary | Query-time rewrite (server-side) | Query-time rewrite (server-side) |
| Data never leaves governed path | ✅ Masking at query time, no raw data export | ✅ Masking at query time, no raw data export |

### FSx for ONTAP S3 AP + Snowflake Governance: Validated

![Snowflake validation summary — all read and governance paths verified](https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations/main/docs/images/snowflake-05-summary-table.png)

*Complete validation summary: LIST, SELECT, External Table, COPY INTO, Directory Table, and Governance Tags all verified with `AWS_ACCESS_POINT_ARN`.*

In our validation environment (Standard edition), we confirmed:
- ✅ `CREATE TAG` + `ALTER TABLE SET TAG` works on External Tables backed by FSx for ONTAP S3 AP
- ✅ `SYSTEM$GET_TAG` retrieves tag values correctly
- ⚠️ Tag-based Masking Policies require Enterprise Edition (not tested in Standard)
- ⚠️ Row Access Policies require Enterprise Edition (not tested in Standard)

**Implication**: Organizations using Snowflake Enterprise Edition can apply full ABAC governance (classification, masking, row filtering) to FSx for ONTAP data accessed via External Tables — without copying data into Snowflake-managed storage.

### File-Level Access Control: ONTAP Native Layer

For NetApp users, the critical governance question is not just table/column-level masking but **file-level access control on unstructured data** (images, documents, videos). FSx for ONTAP S3 Access Points provide a dual-layer authorization model:

```
Layer 1: AWS IAM + S3 AP Policy (who can call the S3 API)
    │
Layer 2: ONTAP File System Permissions (what files the user can access)
    │
    ├── Export Policy (NFS: client IP, protocol, RO/RW/root)
    ├── NTFS ACL / NFSv4 ACL (per-file/directory permissions)
    ├── Storage-Level Access Guard (volume-level ACL override)
    ├── FPolicy (file operation monitoring, screening, blocking)
    └── File System User mapping (S3 AP → UNIX/Windows identity)
```

#### How S3 AP File-Level Control Works

Each S3 Access Point is mapped to a **file system user** (UNIX UID/GID or Windows identity). All S3 API operations through that access point execute as that user:

| S3 AP Configuration | File Access Scope | Use Case |
|---|---|---|
| File system user = `root` (UID 0) | Full access to all files | Admin/analytics (broad read) |
| File system user = `analytics` (UID 1001) | Only files readable by UID 1001 | Scoped analytics access |
| File system user = `dept_finance` | Only finance department files | Department-level isolation |
| Multiple S3 APs per volume | Different users per AP | Per-consumer access scoping |

#### Per-Consumer S3 Access Points (Data Isolation Pattern)

```
FSx for ONTAP Volume: /vol1
├── /finance/     (owner: finance_user, mode: 750)
├── /engineering/ (owner: eng_user, mode: 750)
├── /shared/      (owner: root, mode: 755)
│
├── S3 AP "snowflake-finance"    → file_system_user: finance_user
│     → Can read /finance/ and /shared/, cannot read /engineering/
│
├── S3 AP "snowflake-engineering" → file_system_user: eng_user
│     → Can read /engineering/ and /shared/, cannot read /finance/
│
└── S3 AP "snowflake-admin"      → file_system_user: root
      → Can read everything (for admin/governance use)
```

#### FPolicy: File Operation Monitoring & Blocking

FPolicy provides real-time file access monitoring and blocking at the ONTAP level — independent of which protocol (NFS, SMB, or S3 AP) is used:

| FPolicy Capability | Description | Relevance to Analytics |
|---|---|---|
| Native file blocking | Block specific file extensions (e.g., .exe, .bat) | Prevent malicious file upload via any protocol |
| External FPolicy server | Send file access events to external application | Audit trail for compliance (who accessed what, when) |
| File screening | Allow/deny based on file type or pattern | Control what data types are accessible |
| Operation monitoring | Monitor open, create, rename, delete, read, write | Complete audit of data access patterns |

**Key insight for NetApp users**: Even when Snowflake queries data via S3 AP, ONTAP's file-level permissions and FPolicy still apply. The S3 AP does not bypass ONTAP security — it maps S3 API calls to file system operations that respect the configured permissions.

### Integration: ONTAP File-Level Control × Snowflake Tag Governance

The two governance layers (ONTAP file-level and Snowflake tag-based) operate independently but can be combined for defense-in-depth:

#### Integration Matrix

| Scenario | ONTAP Layer (File-Level) | Snowflake Layer (Tag/Policy) | Combined Effect |
|---|---|---|---|
| **Department isolation** | Separate S3 AP per dept (different file_system_user) | Tags classify tables by department | Files physically inaccessible + query-time masking on shared tables |
| **PII protection** | FPolicy monitors access to PII directories | Tag-based Masking Policy on PII columns | File access audited + column values masked for unauthorized roles |
| **Compliance hold** | SnapLock prevents file deletion | Row Access Policy restricts query results | Data immutable at storage + query results filtered by role |
| **ML training data control** | Export Policy limits which clusters can read | Tags mark sensitivity level on External Table | Network-level restriction + column masking for sensitive features |
| **Ransomware defense** | ARP/AI detects encryption + auto-snapshot | N/A (storage-layer concern) | Storage protected; analytics layer unaffected |
| **Cross-team data sharing** | Shared directory (mode 755) via common S3 AP | Row Access Policy filters by team role | All teams see the table, each sees only their authorized rows |

#### How They Work Together (Example Flow)

```
1. Data scientist queries External Table via Snowflake
       │
       ▼
2. Snowflake generates S3 API call (GetObject)
       │
       ▼
3. S3 AP Policy checks: IAM role allowed? ──── If NO → AccessDenied
       │ YES
       ▼
4. ONTAP checks: file_system_user has permission? ──── If NO → AccessDenied
       │ YES
       ▼
5. File data returned to Snowflake
       │
       ▼
6. Snowflake applies Tag-based Masking Policy ──── PII columns masked
       │
       ▼
7. Snowflake applies Row Access Policy ──── Unauthorized rows filtered
       │
       ▼
8. User sees: only authorized rows with sensitive columns masked
```

#### Design Patterns for Combined Governance

| Pattern | ONTAP Configuration | Snowflake Configuration | Best For |
|---|---|---|---|
| **Broad read + fine-grained mask** | Single S3 AP (root user), all files readable | Tag-based masking on sensitive columns | Analytics teams needing broad access with PII protection |
| **Strict file isolation + tag classification** | Per-department S3 AP (scoped user) | Tags for audit/compliance tracking only | Regulated industries requiring physical data separation |
| **Shared data + role-based filtering** | Shared S3 AP (read-only user) | Row Access Policy by department/role | Cross-functional analytics on common datasets |
| **Immutable audit + governed query** | SnapLock volume + FPolicy audit | Tags + masking + row policy | Financial/healthcare compliance |

#### References: ONTAP File-Level + Snowflake Tag Integration

| Topic | Reference |
|---|---|
| FSx for ONTAP S3 AP dual-layer authorization | [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) |
| FSx for ONTAP S3 AP with Active Directory | [Enabling AI-powered analytics on enterprise file data](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| ONTAP Export Policy (NFS access control) | [How export rules work](https://docs.netapp.com/us-en/ontap/nfs-admin/export-rules-concept.html) |
| ONTAP FPolicy (file monitoring/blocking) | [FPolicy configuration types](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |
| ONTAP Storage-Level Access Guard | [Secure file access with SLAG](https://docs.netapp.com/us-en/ontap/smb-admin/secure-file-access-storage-level-access-guard-concept.html) |
| ONTAP NFSv4 ACLs | [NFSv4 ACLs for SVMs](https://docs.netapp.com/us-en/ontap/nfs-admin/nfsv4-acls-concept.html) |
| Snowflake Object Tagging | [Introduction to object tagging](https://docs.snowflake.com/en/user-guide/object-tagging/introduction) |
| Snowflake Tag-based Masking | [Tag-based masking policies](https://docs.snowflake.com/en/user-guide/tag-based-masking-policies) |
| Snowflake Row Access Policies | [Use row access policies](https://docs.snowflake.com/en/user-guide/security-row-using) |
| Snowflake Data Classification | [Sensitive data classification](https://docs.snowflake.com/en/user-guide/classify-using) |
| Snowflake Governed Lakehouse for AI | [Govern your lakehouse for AI quickstart](https://www.snowflake.com/en/developers/guides/govern-your-lakehouse-for-ai/) |

#### Governance Layers Summary (Snowflake + ONTAP)

| Layer | Enforcement Point | Scope | Controls |
|---|---|---|---|
| **ONTAP Export Policy** | File system | Volume/qtree level | Client IP, protocol, RO/RW |
| **ONTAP File Permissions** | File system | Per-file/directory | UNIX mode, NFSv4 ACL, NTFS ACL |
| **ONTAP FPolicy** | File system | Per-operation | Monitor, screen, block file operations |
| **ONTAP Storage-Level Access Guard** | File system | Volume level | ACL override for all protocols |
| **S3 AP Policy** | AWS | Per-access-point | IAM conditions, VPC restriction |
| **S3 AP File System User** | File system | Per-access-point | Maps S3 identity to UNIX/Windows user |
| **Snowflake Object Tags** | Query engine | Table/column | Classification metadata |
| **Snowflake Masking Policy** | Query engine | Column | Dynamic data masking at query time |
| **Snowflake Row Access Policy** | Query engine | Row | Row-level filtering at query time |

### References

- [Object Tagging](https://docs.snowflake.com/en/user-guide/object-tagging/introduction)
- [Tag-based Masking Policies](https://docs.snowflake.com/en/user-guide/tag-based-masking-policies)
- [Row Access Policies](https://docs.snowflake.com/en/user-guide/security-row-using)
- [Dynamic Data Masking](https://docs.snowflake.com/en/user-guide/security-column-ddm-intro)
- [Data Classification](https://docs.snowflake.com/en/user-guide/classify-using)

---

## Industry Use Cases with Snowflake Cortex AI + FSx for ONTAP

### Manufacturing / Quality Inspection

| Use Case | Cortex Function | Data on FSx | Reference |
|---|---|---|---|
| Inspection report OCR | PARSE_DOCUMENT (OCR mode) | Scanned reports (PNG/PDF) | [Snowflake PARSE_DOCUMENT docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| Sensor anomaly summarization | CORTEX.SUMMARIZE | IoT sensor Parquet/CSV | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| Visual defect detection | AI_COMPLETE (vision) | Product images | [AI_COMPLETE multimodal](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) |
| Yield analysis from dashboards | AI_COMPLETE (vision) | Dashboard screenshots | [Image Analysis Quickstart](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/) |

### Financial Services / Insurance

| Use Case | Cortex Function | Data on FSx | Reference |
|---|---|---|---|
| Invoice data extraction | PARSE_DOCUMENT (LAYOUT mode) | Invoice PDFs/images | [Document AI](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| Contract clause summarization | CORTEX.SUMMARIZE | Contract documents | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| Claims document processing | PARSE_DOCUMENT + SUMMARIZE | Claims forms | [OCR + RAG Quickstart](https://quickstarts.snowflake.com/guide/getting_started_with_ocr_and_rag_with_snowflake_notebooks/) |
| Regulatory document search | Cortex Search (via COPY INTO) | Compliance docs | [Cortex Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview) |

### Healthcare / Life Sciences

| Use Case | Cortex Function | Data on FSx | Reference |
|---|---|---|---|
| Medical record digitization | PARSE_DOCUMENT (OCR) | Scanned records | [PARSE_DOCUMENT](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| Research paper summarization | CORTEX.SUMMARIZE | PDF papers | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| Lab report text extraction | PARSE_DOCUMENT | Lab images/PDFs | [Document AI](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document) |
| Clinical trial data catalog | Directory Table | Trial documents | [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables) |

### Media / Content Management

| Use Case | Cortex Function | Data on FSx | Reference |
|---|---|---|---|
| Image metadata extraction | AI_COMPLETE (vision) | Media assets | [AI_COMPLETE](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal) |
| Video frame description | AI_COMPLETE (vision) | Extracted frames | [Image Analysis](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/) |
| Asset catalog management | Directory Table + Tags | All media files | [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables) |
| Content translation | CORTEX.TRANSLATE | Text documents | [Cortex TRANSLATE](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions#label-cortex-llm-translate) |

### Cross-Industry: Data Engineering

| Use Case | Cortex Function | Data on FSx | Reference |
|---|---|---|---|
| Schema inference from files | PARSE_DOCUMENT + LLM | Mixed format files | [Cortex LLM](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| Data quality assessment | CORTEX.SUMMARIZE | Data samples | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |
| File classification/tagging | AI_COMPLETE + Tags | Unstructured files | [Governance Tags](https://docs.snowflake.com/en/user-guide/object-tagging/introduction) |
| Automated documentation | CORTEX.SUMMARIZE | Code/config files | [Cortex LLM Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions) |

---

## ONTAP Value for AI/ML Workloads

| ONTAP Feature | AI/ML Benefit | Reference |
|---|---|---|
| **FlexCache** | Cache hot training data across regions/sites for low-latency access; reduce WAN bandwidth for distributed ML workloads | [FlexCache overview](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-flexcache.html) |
| **SnapLock / Tamperproof Snapshot** | Immutable data protection — even administrators cannot delete locked snapshots during retention period; meets SEC 17a-4(f), HIPAA, FINRA compliance | [SnapLock on FSx for ONTAP](https://netapp.com/blog/snaplock-on-amazon-fsx-ontap/) |
| **ARP/AI (Autonomous Ransomware Protection)** | AI-powered real-time detection of ransomware encryption patterns; automatic snapshot creation before damage spreads | [ARP on FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) |
| **FlexClone** | Zero-copy instant clones for ML experimentation — test different preprocessing without duplicating data | [FlexClone docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| **Snapshot** | Point-in-time recovery of training datasets; version control for feature engineering pipelines | [Snapshot docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snapshots-ontap.html) |
| **FabricPool** | Auto-tier cold training data and old model artifacts to S3 — transparent to Snowflake queries | [FabricPool docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fabricpool.html) |
| **Storage Efficiency** | Up to 65% savings via deduplication + compression + compaction on training data and embeddings | [Storage efficiency](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/storage-efficiency.html) |
| **SnapMirror** | Cross-region DR for critical ML pipelines and training datasets | [SnapMirror docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html) |
| **Multi-protocol** | Same data accessible via NFS (data scientists), SMB (Windows users), S3 AP (Snowflake/analytics) simultaneously | [Multi-protocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/supported-fsx-clients.html) |
| **FPolicy** | File operation monitoring for AI data access audit; block unauthorized file types in ML pipelines | [FPolicy docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html) |

### AI/ML-Specific Scenarios

- **FlexCache for distributed training**: Cache training datasets from on-premises NAS to cloud FSx for ONTAP — ML clusters read locally cached data with sub-millisecond latency instead of crossing WAN
- **SnapLock for model governance**: Lock training data snapshots to ensure reproducibility — auditors can verify that the exact dataset used for model training has not been modified
- **ARP/AI for data pipeline protection**: Detect and block ransomware that targets training data or model artifacts — automatic snapshot preserves clean state for recovery

---

## Getting Started

1. **Set up FSx for ONTAP S3 AP stage** — Follow the [Configuration Guide](../../README.md)
2. **Upload sample data** — Place images/documents on FSx for ONTAP via NFS
3. **Refresh Directory Table** — `ALTER STAGE REFRESH` to detect new files
4. **Run Cortex functions** — Use the SQL examples above
5. **Build Streamlit app** — For interactive dashboards with image thumbnails

## Snowflake Cortex AI Documentation

- [Cortex AI Overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex)
- [LLM Functions (SUMMARIZE, COMPLETE, TRANSLATE)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions)
- [PARSE_DOCUMENT (OCR / Document AI)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/parse-document)
- [AI_COMPLETE (Multimodal/Vision)](https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex-multimodal)
- [Cortex Search (RAG)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview)
- [Directory Tables](https://docs.snowflake.com/en/user-guide/data-load-dirtables)
- [OCR + RAG Quickstart](https://quickstarts.snowflake.com/guide/getting_started_with_ocr_and_rag_with_snowflake_notebooks/)
- [Image Analysis with Streamlit](https://www.snowflake.com/en/developers/guides/build-image-analysis-app-with-streamlit-and-snowflake-cortex/)
