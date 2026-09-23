🌐 **English** | [日本語](../ja/databricks-standard-s3-unstructured-poc.md)

# Databricks Unstructured-Data AI on a Standard S3 Bucket — PoC

> **Status**: Verified in this environment (2026-09-23). Five of six scenarios are **Verified** here; one (Vector Search) is Verified up to endpoint creation, with index ONLINE not reached due to environment-dependent provisioning delay (see [Verification Status](#verification-status)). Screenshots are published with account ID / workspace URL / email masked.
> **Evidence tier** per claim: **Public** (verifiable from public sources) / **Verified** (measured in this environment) / **Project-context** (internal assumption) / **Hypothesis**.
> **Test environment**: Databricks workspace (US region, us-west-2), Serverless SQL Warehouse (Small, DBSQL channel Current), standard S3 general purpose bucket (ap-northeast-1, no FSx for ONTAP S3 Access Point involved). Synthetic samples only (no real or customer data).
> **Framing**: right-tool-for-the-job, not vendor-versus. Trade-offs stated symmetrically, including for the approach this repository recommends.
> **How this page relates to the other**: the [FILE type (Beta) evaluation](./databricks-file-type-evaluation.md) covers behaviour on an FSx for ONTAP **S3 Access Point**, where the recommended interim path was "stage to a standard S3 bucket, then govern the copy." This page fills in, live, **what you can actually do on that standard S3 bucket**. It is about the standard staging bucket, not the S3 Access Point.

---

## Executive Summary

- **Subject and result**: given data on a **standard S3 general purpose bucket**, Databricks unstructured-data AI was confirmed to work live. `ai_query` LLM Vision, `ai_parse_document` OCR, FILE type, AI Functions (`ai_classify` / `ai_gen` / `ai_analyze_sentiment`), and Genie natural-language querying all held over data on standard S3. Vector Search held up to endpoint creation; the index did not reach ONLINE within the session (see [Verification Status](#verification-status)).
- **Why a standard bucket works**: on an FSx for ONTAP S3 Access Point, unstructured-data AI is blocked by [BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads) because the down-scoped session policy Unity Catalog vends is written in **bucket-form ARNs** while AWS authorises access-point requests against the **access point ARN**. On a standard S3 bucket both the request and the session policy use the same bucket-form ARN, so the mismatch does not arise. The UC External Location validation here returned Success for Read / List / Write / Delete, confirming this by measurement (see [IAM / authentication and authorization behaviour](#2-iam--authentication-and-authorization-behaviour-on-standard-s3)).
- **From an IAM / auth standpoint**: on a standard bucket all core operations (read/write, AssumeRole, External ID condition) passed. Only File Events (S3 bucket notifications) failed, for lack of the `s3:GetBucketNotification` permission — an optional feature that does not block core function. A presigned URL is a client-side SigV4 calculation and works on a standard bucket as an ordinary `GetObject`.
- **Contrast with Snowflake**: the same "NAS → standard S3 → governed AI" is achievable with Snowflake Cortex. Databricks AI Functions map to Cortex AISQL, Vector Search to Cortex Search, and Genie to Cortex Analyst (see [contrast](#5-contrast-with-snowflake-cortex)). Not which is better, but which fits your existing platform and use.
- **Recommended shape**: the core of unstructured-data usage (Vision, OCR, FILE type, AI Functions, NL querying) holds on a standard S3 bucket with UC today. It is the practical route when you want governance and AI on Databricks.

---

## 1. Architecture (why a standard S3 bucket is the target)

**Evidence tier: Public / Project-context.**

The live PoC target is a **standard S3 general purpose bucket** with synthetic samples uploaded directly. The realistic route from FSx for ONTAP is the left side of the diagram; moving real data is out of scope for this PoC (deferred to the [DataSync to S3 guide](./datasync-to-s3-guide.md)).

```
FSx for ONTAP volume (NFS / SMB / S3 Access Point multiprotocol)
     │
     │  AWS DataSync (the only verified sync mechanism; SnapMirror S3 is not available on FSx for ONTAP)
     ▼
Standard S3 general purpose bucket  ◀── the live PoC target (synthetic samples uploaded directly)
     │
     │  UC Storage Credential (IAM role) → External Location → External Volume
     ▼
Databricks Unity Catalog
     ├── ai_query() (LLM Vision / chat)
     ├── ai_parse_document() (OCR / layout extraction)
     ├── AI Functions (ai_classify / ai_gen / ai_analyze_sentiment)
     ├── FILE type (FILE EXTERNAL) + AI functions
     ├── Mosaic AI Vector Search (embedding → semantic search / RAG)
     └── Genie (natural-language querying over an extracted metadata table)
```

> **Naming note**: the left edge is "Amazon FSx for NetApp ONTAP" (thereafter FSx for ONTAP). The standard S3 bucket is an Amazon S3 general purpose bucket and is a different thing from an FSx for ONTAP S3 Access Point. To avoid conflating them, "standard S3" on this page always means an Amazon S3 general purpose bucket.

---

## 2. IAM / authentication and authorization behaviour on standard S3

**Evidence tier: Public / Verified (marked per item).**

This is the core from an IAM / auth standpoint — how IAM roles / policies, presigned URLs, and S3 bucket authentication behave on a standard bucket versus an S3 Access Point.

### 2.1 The authorization chain when Databricks reads standard S3

```
Unity Catalog
  └─ Storage Credential (IAM role ARN + External ID)
       └─ on AssumeRole, Databricks generates a down-scoped session policy
            └─ External Location (maps s3://<standard-bucket>/path to the credential)
                 ├─ External Volume (unstructured files: images / PDF / audio / video)
                 └─ External Table (tabular data)
```

The IAM role's trust policy allows AssumeRole from the Databricks Unity Catalog account (with an `sts:ExternalId` condition, plus a self-assume so the role can assume itself), and its permission policy grants `s3:GetObject` / `s3:ListBucket` on the target bucket. On each AssumeRole, Databricks layers a session policy that narrows what the session can do to the target path.

> **Verified (IAM trust relationship)**: when creating the External Location manually, Databricks shows the trust policy it expects. Here it was **the UC master role (`arn:aws:iam::<databricks-uc-account>:role/unity-catalog-prod-UCMasterRole-...`) + self-assume + `sts:ExternalId` = the Databricks account UUID** (a specific role ARN, not `:root`). Matching the trust policy to that shape makes validation pass.

### 2.2 Why BLK-001 does not occur on a standard bucket

| | Standard S3 general purpose bucket | FSx for ONTAP S3 Access Point |
|---|---|---|
| ARN the request is authorized against | Bucket-form `arn:aws:s3:::<bucket>` | Access point ARN `arn:aws:s3:<region>:<account>:accesspoint/<name>` |
| ARN form of the session policy UC vends | Bucket-form | Bucket-form (**same**) |
| Do they match | ✅ Match → read succeeds | ❌ Mismatch → `s3:ListBucket` denied (BLK-001) |

On a standard bucket, the request's evaluation target and the session policy's wording are both bucket-form ARNs, so the intersection is not empty. This is the technical basis for "stage to standard S3 and governed AI under UC holds" ([BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads)).

> **Verified (External Location connection check)**: on creating the UC External Location for the standard bucket, the Databricks connection check returned **Success for Read / List / Write / Delete / Path Exists / Assume Role / Self Assume Role / External ID Condition**. The `s3:ListBucket` denial that occurs on an S3 Access Point (BLK-001) did not happen.

![UC External Location overview (verified Storage Credential over the standard bucket; URL / email masked)](../images/databricks-standard-s3-poc/01b-external-location-overview.png)

> **Security note**: the session policy intersects with the IAM role's own policy. Even if the role has broad permissions, the session policy narrows to the target path, so nothing outside the prefix the External Location points at is reachable. Least privilege is enforced through the External Location scope design.

### 2.3 File Events (S3 bucket notifications) and least privilege

**Evidence tier: Verified** (the External Location validation in this environment).

In the External Location connection check, while every core operation returned Success, **only File Events (S3 bucket notifications) provisioning failed**. The cause was that the assumed session lacked `s3:GetBucketNotification` (`no identity-based policy allows the s3:GetBucketNotification action`, HTTP 403).

- File Events is an **optional feature** (improves ingestion performance, reduces storage-listing cost); reads, writes and AI processing hold without it. You can proceed with "Force create".
- **IAM implication**: to use UC File Events, the IAM role needs `s3:GetBucketNotification` (and `PutBucketNotification`, etc.). A read/write-centric least-privilege policy will fail File Events but does not block core function. Whether you use File Events changes the IAM permissions you need — a design decision point.

### 2.4 Where presigned URLs fit

**Evidence tier: Public** (based on the public SigV4 presign specification and the §2.5 observation from this verification).

A presigned URL is a **client-side SigV4 signature calculation**; no request reaches AWS at URL-generation time. Using the generated URL is an ordinary `GetObject`. On a standard bucket `GetObject` is of course supported, so presigned URLs work too.

Even where the FSx for ONTAP S3 Access Point compatibility table lists `Presign` as "Not supported", that reads as "do not rely on it in production," not "it fails" (for the same reason, it is structurally impossible to block presign without breaking `GetObject`). On a standard bucket that caveat is unnecessary. Details are recorded in [FILE type evaluation §4.2](./databricks-file-type-evaluation.md#presigned-urls-work-and-that-is-expected).

### 2.5 API-level corroboration with CloudTrail

**Evidence tier: Verified** (CloudTrail data-event logs from this verification, 2026-09-23).

The File Events failure in 2.3 and the presigned-URL positioning in 2.4 were corroborated at the API level, not only by the External Location wizard screen. Log files from a Trail that records data events were parsed, extracting records matching the target bucket and the UC role (`databricks-uc-stds3-poc`); account ID, session ID, and bucket name are masked.

**Evidence of the File Events 403**: from the UC session (`arn:aws:sts::<account-id>:assumed-role/databricks-uc-stds3-poc/<session>`), `GetBucketNotification` was **`AccessDenied` on all 13 calls** and `HeadBucket` **`AccessDenied` on all 4 calls**. The reason is the absence of an identity-based policy allowing `s3:GetBucketNotification` (HTTP 403). This pins down, at the API level, that the "File Events Failed" of 2.3 is caused by that 403. Meanwhile, data-plane operations from the same session (`GetObject` / `HeadObject` / `ListObjects` / `PutObject`) were **not denied**.

**The data-plane principal (AssumeRole, not presign)**: every recorded `GetObject` was `userIdentity.type = AssumedRole` under the UC role. A presigned-URL GET would appear as query-string SigV4 under a different principal, and no such trace exists. That is, UC on standard S3 reads **directly with the assumed-role credential (server-side SigV4)**, and this PoC path used no presigned URL. This differs from an approach where a sharing server vends a SigV4 presigned URL that the client then reads (for example, Delta Sharing credential vending).

**The credential-validation round trip**: at External Location creation, UC ran `PutObject` → `HeadObject` → `GetObject` (later removed with `DeleteObject`) against a validation object. The "Read / List / Write / Delete / Path Exists all Success" of 2.2 matches this sequence of data-plane operations being recorded with no errorCode.

| CloudTrail event | Count | errorCode | Meaning |
|---|---:|---|---|
| `GetBucketNotification` | 13 | `AccessDenied` | File Events provision 403 (2.3) |
| `HeadBucket` | 4 | `AccessDenied` | bucket-level notification probe 403 |
| `GetObject` | 5 | none | data read succeeds (all AssumedRole) |
| `PutObject` | 1 | none | credential-validation write |
| `ListObjects` | 23 | none | listing succeeds |

> **Note (what data events record)**: S3 object-level events (such as `GetObject`) are "data events" and do not appear in CloudTrail management-event history (`lookup-events`). The above was obtained by parsing the log files of a Trail that records data events directly. `GetBucketNotification`, a management event, also appears in the history side.

---

## 3. Verification scenarios

Each scenario shows, live, what Databricks unstructured-data AI can do given data on a standard S3 bucket. Synthetic samples (an inspection image PNG, a bar-chart PNG, an inspection-report PDF) were placed under `unstructured/` on the standard bucket, registered as a UC External Volume, and each AI feature applied.

> **Model names measured (Public / Verified)**: in this environment (us-west-2), the pay-per-token models usable were `databricks-meta-llama-3-3-70b-instruct` (text), `databricks-llama-4-maverick` (multimodal), and `databricks-gte-large-en` (embedding). `databricks-claude-3-7-sonnet` did not exist and errored. Pay-per-token Foundation Models are offered in US regions; a Tokyo (ap-northeast-1) workspace has no default endpoint (see [Environment and cost](#environment-and-cost)).

### 3.1 Scenario 1: LLM Vision on images with `ai_query()` (Cortex AISQL equivalent)

**Evidence tier: Verified**.

An image on the standard S3 bucket was read from the UC External Volume, base64-encoded into a data URI, and passed to `ai_query` (`databricks-llama-4-maverick`, multimodal). For the synthetic image (blue square, orange circle, black bar at the bottom) the model correctly described "a blue square and an orange circle against a white background, with a black bar at the bottom." Because hand-building the messages struct in SQL was brittle, this ran in a Python notebook via the `mlflow.deployments` client.

![ai_query image Vision result (Llama 4 Maverick correctly describes shapes and colors)](../images/databricks-standard-s3-poc/02-ai-query-vision-result.png)

### 3.2 Scenario 2: PDF OCR with `ai_parse_document()` (Cortex AISQL equivalent)

**Evidence tier: Verified** (10.3s).

`ai_parse_document()` applied to the PDF on the standard S3 bucket extracted the `title` ("Synthetic Equipment Inspection Report") with bbox `[197,206,1141,264]`, confidence `1`, and `page_id 0`. Paragraph and table elements were also extracted.

![ai_parse_document PDF OCR result (title, bbox, confidence extracted)](../images/databricks-standard-s3-poc/03-ai-parse-document-result.png)

### 3.3 Scenario 3: FILE type + AI functions

**Evidence tier: Verified** (`ai_parse_document(file)` 8.3s).

`list_files` enumerated the files on the standard bucket, and a CTAS created a table with a `FILE EXTERNAL` column. `DESCRIBE TABLE` reported the `file` column type as **`file external`**. That `FILE EXTERNAL` column was passed straight to `ai_parse_document(file)` and OCR succeeded. **`FILE EXTERNAL` is blocked by BLK-001 on an S3 Access Point, but holds on a UC External Volume over a standard bucket** — the core of this PoC's contrast. FILE type beta constraints (Delta only, DBR 18 LTS+, no automatic GC) are in [FILE type evaluation §1](./databricks-file-type-evaluation.md#beta-constraints-to-plan-around).

![DESCRIBE TABLE shows the file column as file external type](../images/databricks-standard-s3-poc/04-file-external-describe.png)

![Passing the FILE EXTERNAL column to ai_parse_document succeeds](../images/databricks-standard-s3-poc/05-file-type-ai-parse.png)

### 3.4 Scenario 4: AI Functions across the board (Cortex AISQL equivalent)

**Evidence tier: Verified**.

Against a metadata table holding the text extracted by `ai_parse_document`, AI Functions were applied.

| Function | Input | Result |
|---|---|---|
| `ai_classify(chunk, array('inspection_report','financial','marketing','legal'))` | extracted text | **inspection_report** (15.0s, includes first warehouse start) |
| `ai_gen('Summarize in 8 words or fewer: ' \|\| chunk)` | extracted text | "Synthetic document for OCR testing purposes." (2.7s) |
| `ai_analyze_sentiment(chunk)` | extracted text | **neutral** |

With Vision (`ai_query`) and OCR (`ai_parse_document`), the main Cortex-AISQL-equivalent functions (classify, generate, summarize, sentiment, OCR, Vision) all worked over standard S3 data.

![ai_classify result (inspection_report)](../images/databricks-standard-s3-poc/07-ai-classify.png)

![ai_gen (summary generation) and ai_analyze_sentiment (sentiment) results](../images/databricks-standard-s3-poc/06-ai-functions-gen-sentiment.png)

### 3.5 Scenario 5: RAG with Mosaic AI Vector Search (Cortex Search equivalent)

**Evidence tier: Verified (up to endpoint creation) / environment-dependent incomplete (index ONLINE).**

A Delta table of chunked extracted text (with Change Data Feed enabled) was built, and a Vector Search endpoint (STANDARD) was created (`{'state': 'ONLINE'}` confirmed). A Delta Sync Index (embedding model `databricks-gte-large-en`, TRIGGERED) was then requested, but the **index stayed at `PROVISIONING_ENDPOINT` for about 16 minutes without reaching ONLINE**, continuing to report `Delta sync index creation is pending endpoint provisioning.` First-provisioning delay in trial / shared environments is reported repeatedly in the Databricks community (20 minutes to several hours, occasionally failing) and is environment-dependent. To stop billing, the index then the endpoint were deleted, and absence was confirmed in the listing (`endpoints now: []`).

> **Cost note**: a Vector Search endpoint has a different billing structure from the other three scenarios — it is always-on. Per Databricks documentation, the endpoint is **billed after an index is created, and billing stops 24 hours after the last index is deleted**. So endpoint billing can linger up to 24 hours after teardown. Also, `databricks-gte-large-en` is a high-latency pay-per-token embedding, one reason the first sync is slow.

### 3.6 Scenario 6: Natural-language querying with Genie (Cortex Analyst equivalent)

**Evidence tier: Verified**.

The inspection table extracted by `ai_parse_document` was made into a structured table (`item` / `status` / `score`, with a table comment), connected to a Genie Agent, and queried in natural language.

- **Question**: "Which inspection item has the lowest score?"
- **Genie's answer** (NL → SQL auto-generated → executed → NL answer): "The inspection item with the lowest score is **Weld seam** with a score of **0.71**. This item has a status of 'Review', indicating it requires further attention." → correct.

The sequence "structure the unstructured data with `ai_parse_document` → query that table in natural language with Genie" held. This is symmetric with Snowflake's "`PARSE_DOCUMENT` → Cortex Analyst." Genie runs on the SQL warehouse and incurs no always-on charge.

![Genie natural-language query (correctly answers the lowest-scoring inspection item)](../images/databricks-standard-s3-poc/08-genie-nl-query.png)

---

## 4. Supported data formats

**Evidence tier: Public / Verified (marked per item).**

| Format | Ingestion on standard S3 | Applicable AI | Live in this environment |
|---|---|---|---|
| Image (JPEG / PNG / TIFF) | `read_files` / External Volume / `BINARYFILE` | `ai_query` (Vision), Vector Search (multimodal embedding) | ✅ Vision run live (PNG) |
| PDF | `read_files` / FILE type | `ai_parse_document` (OCR / layout), then AI Functions / Vector Search | ✅ OCR + AI Functions run live |
| Audio (WAV / MP3) | `BINARYFILE` / External Volume | transcription UDF / external ASR | mentioned as a supported format (not run) |
| Video (MP4 / MOV) | `BINARYFILE` / External Volume | frame extraction → Vision | mentioned as a supported format (not run) |

> **Note**: audio and video are covered only as "supported as an ingestion format"; the live AI runs focused on image and PDF (synthetic or clearly licensed public samples only; no real or customer data).

---

## 5. Contrast with Snowflake Cortex

**Evidence tier: Public** (from Databricks / Snowflake official documentation). Trade-offs stated symmetrically.

The same requirement — governed AI over unstructured data on a standard S3 bucket — is also met by Snowflake Cortex. Choose by use, not by superiority. This connects to the concept mapping in the existing [Databricks integration README](../../integrations/databricks/README.md) and [Snowflake integration README](../../integrations/snowflake/README.md).

### 5.1 Feature mapping

Snowflake Cortex is an umbrella over several features, and the Databricks counterparts split per feature. "Genie is the Cortex equivalent" is inaccurate; precisely, **Genie is the Cortex Analyst equivalent**.

| Purpose | Databricks | Snowflake Cortex | Live in this PoC |
|---|---|---|---|
| Text AI (classify / generate / summarize / sentiment) | AI Functions (`ai_classify` / `ai_gen` / `ai_analyze_sentiment`) | Cortex AISQL (`CLASSIFY` / `COMPLETE` / `SUMMARIZE` / `SENTIMENT`) | ✅ Databricks side Verified |
| Image Vision | `ai_query` (multimodal model) | Cortex `AI_COMPLETE` (multimodal) | ✅ Databricks side Verified |
| Document OCR | `ai_parse_document` | `PARSE_DOCUMENT` | ✅ Databricks side Verified |
| Semantic search / RAG | Mosaic AI Vector Search | Cortex Search | Verified up to endpoint creation |
| Natural-language querying (NL→SQL) | Genie | Cortex Analyst | ✅ Databricks side Verified |
| Unstructured file catalog | UC External Volume / FILE type | Directory Table | ✅ Databricks side Verified |
| Agents | Agent Bricks / Mosaic AI Agent | Cortex Agents | mentioned only (always-on cost) |
| IAM reference | Storage Credential | Storage Integration | ✅ Databricks side Verified |
| Cloud path mapping | External Location | External Stage | ✅ Databricks side Verified |

### 5.2 How to choose (right-tool-for-the-job)

- **Organization already on Databricks**: register the standard S3 bucket as a UC External Location and put unstructured-data AI on it directly with `ai_query` / `ai_parse_document` / AI Functions / FILE type / Genie. This PoC confirmed the sequence works live.
- **Organization already on Snowflake**: the equivalent is available with External Table + Cortex, or COPY INTO an internal table ([Snowflake integration README](../../integrations/snowflake/README.md)).
- **Organization using both**: hold the standard S3 bucket in an open format (Delta / Iceberg) so both engines can read it. Do not duplicate storage; use each engine for what it fits.
- Trade-offs symmetrically: Databricks has the Vector Search endpoint's always-on cost and 24-hour billing rule, and the US-region constraint on pay-per-token. Snowflake has the constraint that `TO_FILE` for Vision cannot resolve over an S3 Access Point external stage (needs a copy-to-internal-stage workaround). Neither runs every feature unconditionally on the spot.

---

## Verification Status

**Test environment**: Databricks (us-west-2), Serverless SQL Warehouse (Small), standard S3 general purpose bucket (ap-northeast-1), synthetic samples only. Run 2026-09-23.

### Verified in this environment

| Claim | Result |
|---|---|
| Reads/writes through a UC External Location hold on a standard S3 bucket and do not hit BLK-001 | Read / List / Write / Delete / Assume / Self-Assume / External ID Condition all Success |
| `ai_query` can apply Vision to images on standard S3 | Llama 4 Maverick correctly described shapes and colors |
| `ai_parse_document` can OCR PDFs on standard S3 | title, bbox, confidence extracted (10.3s) |
| `FILE EXTERNAL` holds on a UC External Volume over standard S3 | `DESCRIBE` reports `file external`; `ai_parse_document(file)` succeeded (8.3s) |
| AI Functions work over standard S3 data | `ai_classify`→inspection_report, `ai_gen`→summary, `ai_analyze_sentiment`→neutral |
| Genie answers over an extracted metadata table via NL→SQL | "lowest score?" → "Weld seam 0.71" correct |

### Environment-dependent incomplete / out of scope

| Item | State and reason |
|---|---|
| Vector Search index reaching ONLINE | Endpoint creation Success (ONLINE). Index stayed at `PROVISIONING_ENDPOINT` for ~16 min without completing. Trial / shared-environment first-provisioning delay (reported repeatedly in the Databricks community). Torn down |
| File Events (S3 bucket notifications) provisioning | Failed (lacked `s3:GetBucketNotification`). Optional feature; does not block core function ([§2.3](#23-file-events-s3-bucket-notifications-and-least-privilege)) |
| FSx for ONTAP → DataSync → standard S3 real data transfer | Shown as architecture; actual transfer is out of scope for this PoC ([DataSync guide](./datasync-to-s3-guide.md)) |
| Live AI runs on audio / video | Live runs focus on image and PDF; audio and video stay as format mentions |
| AI Functions on a Tokyo (ap-northeast-1) workspace | Pay-per-token Foundation Models are offered in US regions; a Tokyo workspace has no default endpoint |

---

## Environment and cost

**Evidence tier: Public / Verified / Project-context.**

This PoC ran on a Databricks trial workspace (us-west-2). The environment / cost points learned by running it:

- **Pay-per-token Foundation Models are offered in US regions**. A Tokyo (ap-northeast-1) workspace has no default Serving endpoint, so `ai_query` / `ai_parse_document` cannot be called as-is. To use AI Functions live, choose a US-region workspace.
- **Serverless SQL Warehouse (Small, 10-minute auto-stop)** ran the AI Functions and OCR/Vision. Metered, small.
- **Vector Search is an always-on endpoint charge** + **billing stops 24 hours after the last index is deleted** (Databricks behaviour). Endpoint billing can linger up to 24 hours after teardown. The embedding model `databricks-gte-large-en` is high-latency pay-per-token.
- Workspace-type / region / storage-mode constraints and the dominant cost (managed-VPC NAT Gateway; teardown that does not end with a stack deletion) are recorded in [Databricks verification environment cost](./databricks-verification-environment-cost.md).

---

## FAQ

**Q1. Why a standard S3 bucket rather than an S3 Access Point?**

On an FSx for ONTAP S3 Access Point, unstructured-data AI is blocked by UC credential vending (BLK-001). On a standard S3 bucket the ARN forms of the session policy and the request match, so it holds (measured here: Read/List/Write/Delete all Success). This PoC fills in "what you can do on standard S3"; the S3 Access Point evaluation is covered by the [FILE type evaluation](./databricks-file-type-evaluation.md).

**Q2. How does FSx for ONTAP data get to standard S3?**

AWS DataSync is the only verified sync mechanism (SnapMirror S3 is not available on FSx for ONTAP). This PoC does not transfer real data and only shows the route as [architecture](#1-architecture-why-a-standard-s3-bucket-is-the-target). Procedure in the [DataSync to S3 guide](./datasync-to-s3-guide.md).

**Q3. Is Genie the Cortex equivalent?**

No. Snowflake Cortex is an umbrella over several features, and the Databricks counterparts split per feature. **Genie is the Cortex Analyst equivalent** (natural language → SQL). The Cortex AISQL functions for text/Vision/OCR map to Databricks AI Functions (`ai_query` / `ai_parse_document` / `ai_classify`, etc.), and Cortex Search maps to Mosaic AI Vector Search (see [feature mapping](#51-feature-mapping)).

**Q4. Should I choose Snowflake or Databricks?**

It depends on use — your existing platform, the AI features you need, and the cost structure. See [How to choose](#52-how-to-choose-right-tool-for-the-job). If you use both, hold the data on standard S3 in an open format and use each engine for what it fits.

---

## References

**Databricks (Public)**
- [Work with unstructured data](https://docs.databricks.com/aws/en/unstructured/) · [AI Functions](https://docs.databricks.com/aws/en/large-language-models/ai-functions) · [Query vision models](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-vision-models)
- [FILE type reference](https://docs.databricks.com/aws/en/sql/language-manual/data-types/file-type) · [Ingest files as the FILE type](https://docs.databricks.com/aws/en/ingestion/file)
- [Create vector search endpoints and indexes](https://docs.databricks.com/aws/en/generative-ai/create-query-vector-search) · [Connect agents to unstructured data](https://docs.databricks.com/aws/en/agents/custom-agents/unstructured-retrieval-tools)

**This repository**
- [FILE type (Beta) evaluation](./databricks-file-type-evaluation.md) — behaviour on an S3 Access Point and the recommendation to stage to standard S3 (the counterpart to this page)
- [Blocker tracker](./blocker-tracker.md) — BLK-001 (UC credential vending and the S3 Access Point ARN form)
- [Databricks verification environment cost](./databricks-verification-environment-cost.md) · [DataSync to S3 guide](./datasync-to-s3-guide.md)
- [Databricks integration README](../../integrations/databricks/README.md) · [Snowflake integration README](../../integrations/snowflake/README.md)
