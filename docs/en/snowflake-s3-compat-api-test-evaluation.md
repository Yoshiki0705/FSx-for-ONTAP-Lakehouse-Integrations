🌐 **English** | [日本語](../ja/snowflake-s3-compat-api-test-evaluation.md)

# Snowflake S3-compatible Storage API Test Suite Evaluation: ONTAP S3 and NAS bucket

> **Status**: Initial evaluation (2026-09-26). Snowflake-side registration requirements are from official documentation (**Public**). Test suite results were observed in this environment (**Observed**). Internal causes of the failures are **Hypothesis**.
> **Evidence tier** per claim: **Public** (verifiable from public sources) / **Observed** (seen in this environment's test run) / **Hypothesis**.
> **Test environment**: Snowflake public test suite [`snowflake-s3compat-api-test-suite`](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite) (aws-java-sdk-s3 1.12.62, Java 11). The target is a native ONTAP S3 object-store server endpoint (custom DNS name + direct credentials), which is path (B) in §1 and is distinct from FSx for ONTAP S3 Access Points (path (A) in §1) — the endpoint type was confirmed by AWS CLI (**Observed**). Two buckets on that same endpoint were tested: a regular bucket and a bucket on an NFS/SMB multiprotocol volume.
> **Framing**: right-tool-for-the-job, not vendor-versus. Trade-offs of each storage shape are stated symmetrically.

---

## Executive Summary

- **There are two registration mechanisms, and they are different.** Snowflake reads FSx for ONTAP data through either (A) a **Storage Integration path** that treats S3 Access Points as ordinary Amazon S3 buckets, or (B) an **S3-compatible external stage path** that registers an arbitrary S3-compatible endpoint. This document covers (B). Path (A) is covered in the [Snowflake setup guide](./snowflake-iceberg-setup.md).
- **Path (B) has an application flow at its entrance.** S3-compatible endpoints are not auto-enabled for all accounts. Only Cloudflare R2 is enabled by default; other endpoints are enabled through a request to Snowflake Support. As a precondition, you are asked to verify your endpoint with the public test suite (**Public**).
- **Vendor listing is not a connectivity guarantee.** The Snowflake vendor list is a list of vendors that *indicated they tested at least some of their products*, not one Snowflake validated — the KB states this explicitly (**Public**). Whether a vendor is listed is separate from whether you can pass the application flow in your own environment.
- **The ONTAP S3 regular bucket is effectively a full pass** (**Observed**). Two of nine tests failed, both of a kind the test suite's Troubleshooting explicitly tolerates (a negative-test error-code difference, and a one-object paging count difference).
- **The NFS/SMB multiprotocol bucket shows several divergences** (**Observed**). Three failures and one error out of nine. getBucketLocation is the same tolerated case as the regular bucket, but the other three (object-metadata ETag mismatch, internal error on PutObject with user metadata, post-test cleanup failure) are different in kind.
- **The internal cause of the NAS bucket's three items does not rise above inference** (**Hypothesis**). The observed fact is only that three tests failed; the ETag and user-metadata generation/persistence logic is not public and is unconfirmed from this environment. The essence, though, is not a directory-marker problem alone but that **treating a NAS Bucket as S3-compatible object storage itself still has difficult areas** (§5.4). On the fix side, fixing only the HeadObject 404 leaves ETag, user metadata and cleanup outstanding (§6).

---

## 1. Distinguishing the two registration mechanisms

**Evidence tier: Public** — from [Work with Amazon S3-compatible storage](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) and [this repository's Snowflake setup guide](./snowflake-iceberg-setup.md).

Snowflake reads data on FSx for ONTAP through two paths with different registration mechanisms. Conflating them makes it unreadable why one needs an application and the other does not.

| | (A) Storage Integration path | (B) S3-compatible external stage path |
|---|---|---|
| Classification from Snowflake's view | Amazon S3 | Third-party S3-compatible storage |
| Connection target | FSx for ONTAP S3 Access Points alias | Any S3-compatible endpoint (host name) |
| Stage definition | `STORAGE_INTEGRATION` + `AWS_ACCESS_POINT_ARN` | `ENDPOINT='...'` + `URL='s3compat://...'` + direct credentials |
| Prior application | Not required (only IAM role trust) | **Required** — Support request + public test suite verification |
| Verification status in this repository | E2E verified ([setup guide](./snowflake-iceberg-setup.md), 2026-08 series) | This document (test suite run observation) |

Path (A) has the Access Point alias treated as an ordinary S3 bucket, so it connects without the S3-compatible application flow. Path (B) registers an S3-compatible endpoint host name directly, so it goes through the application flow described below.

---

## 2. The enablement flow for S3-compatible endpoints

**Evidence tier: Public** — from [Requirements for S3-compatible storage (docs.snowflake.com)](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) and [How to enable Amazon S3-compatible storage endpoint (Snowflake Community KB)](https://community.snowflake.com/s/article/How-to-enable-Amazon-S3-compatible-storage-endpoint-for-your-Snowflake-account).

Requirements and steps:

- **Not auto-enabled.** Some major vendors such as R2 may already be allowlisted on the system side; others are enabled by contacting Snowflake Support. docs.snowflake.com states that Cloudflare's `r2.cloudflarestorage.com` is enabled by default and other endpoints require contacting Support, while the Community KB states "Some widely-used storage vendor endpoints (e.g., Cloudflare R2, MinIO, DigitalOcean Spaces) may already be allowlisted at the system level."
- Information to include with the request: (a) Snowflake account name and cloud region, (b) the endpoint URL, (c) the vendor that provides the endpoint. These three items are listed on the **same docs.snowflake.com page**.
- As a precondition, **verifying your own endpoint with the public test suite** is expected ("verify the endpoints by using our public test suite", docs.snowflake.com).
- **Vendor Support requirement**: beyond passing the tests, it is listed as a precondition that the storage vendor supports the endpoint as "a Snowflake S3-compatible tested service" (a docs.snowflake.com requirement, and the Community KB's "Vendor Support: Supported by your storage provider as a Snowflake S3-compatible tested service"). That is, using a NAS bucket as S3-compatible requires not only compatibility fixes but also **the storage vendor's statement of support**.
- Endpoint-side requirements (docs.snowflake.com / Community KB): highly compliant with the S3 API, **virtual-hosted-style requests (path-style not allowed)**, **HTTPS with a CA-issued valid TLS certificate (self-signed not allowed)**, **direct credentials**, no port number in the endpoint, and reachable from the public cloud where your Snowflake account is hosted. The TLS certificate and virtual-hosted-style requirements are **items to confirm at application time** for a NAS bucket / endpoint configuration.

Stage definition shape (KB sample, values illustrative):

```sql
CREATE STAGE my_s3compat_stage
  URL = 's3compat://my_bucket/files/'
  ENDPOINT = 'mystorage.com'
  CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...');
```

If you add a directory table, `AUTO_REFRESH = FALSE` is required and metadata is refreshed manually.

### What a vendor listing means

**docs.snowflake.com**'s "Vendor support for S3-compatible storage" list includes several storage vendors. But the **same page's body** states explicitly: the list is provided for convenience only, Snowflake does not test external products to validate compatibility, and cannot fix issues in third-party products. So a listing indicates that "a vendor told Snowflake it had tested at least some of its products and found them to work," and is **neither a connectivity guarantee nor grounds to skip the application flow**. At actual registration time you run the test suite against your own endpoint and submit the results with the request. Note that the Vendor Support requirement in the previous section is separate from this listing — it asks that the vendor state the endpoint is supported.

---

## 3. APIs the test suite covers

**Evidence tier: Public** — from the [test suite README](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite).

The tests cover nine S3 APIs:

| # | API | Note |
|:---:|---|---|
| 1 | `getBucketLocation` | Region retrieval for SigV4. See the tolerated case in §4.1 |
| 2 | `getObject` | Includes content-range reads (`Content-Range: bytes 10-19/100` format) |
| 3 | `getObjectMetadata` | ETag and `x-amz-bucket-region` header |
| 4 | `putObject` | Includes an up-to-5 GB upload and a PUT with user metadata |
| 5 | `listObjectsV2` | Includes paging over 1000 objects (`PAGE_LISTING_TOTAL_SIZE`) |
| 6 | `deleteObject` | Single delete |
| 7 | `deleteObjects` | Batch delete |
| 8 | `copyObject` | Server-side copy |
| 9 | `generatePresignedUrl` | Presigned URL generation |

The README says to consult Snowflake's public documentation once all APIs pass, consistent with passing the tests being a precondition of the application. Because putObject includes a 5 GB upload, a full run takes several minutes.

---

## 4. Test results

Two buckets were tested: an ONTAP S3 regular bucket, and a bucket on an NFS/SMB multiprotocol volume. The pass/fail below is observed from this environment's test run (**Observed**).

### 4.1 ONTAP S3 regular bucket

**Evidence tier: Observed.** 2 failures, 0 errors out of 9.

| Test | Result | Verdict |
|---|---|---|
| `getBucketLocation` | expected `<400>`, got `<404>` | **Tolerated**. Matches the Troubleshooting note below |
| `listObjectsV2` (paging) | expected `<1005>`, got `<1006>` | One-object difference. Likely the prefix itself counted |
| Other 7 tests | Pass | — |
| Cleanup | Succeeded | — |

Both are of a kind the test suite README explicitly tolerates.

- **Negative-test error-code difference**: the README Troubleshooting states that in negative cases where AWS S3 returns 404/403, an implementation returning a different code such as 400 is fine as long as the codes and messages are reasonable. `getBucketLocation`'s `<400>` vs `<404>` falls here. The README also notes that, because the SigV4 region is obtained from the `x-amz-bucket-region` header of `getObjectMetadata`, a `getBucketLocation` failure can be ignored if the service ignores bucket location.
- **One-object paging difference**: the listed prefix itself appears to be counted as one object, returning one more than expected (**Hypothesis**). It is an off-by-one at the count boundary, not dropped or over-counted data.

### 4.2 NFS/SMB multiprotocol bucket

**Evidence tier: Observed.** 3 failures, 1 error out of 9. Post-test cleanup also failed.

| Test | Result | Kind |
|---|---|---|
| `getBucketLocation` | expected `<400>`, got `<404>` | Failure (same tolerated case as §4.1) |
| `getObjectMetadata` | ETag/MD5 mismatch | Failure |
| `copyObject` | ETag/MD5 mismatch | Failure |
| `putObject` (with user metadata) | `InternalError` / Status 403 "We encountered an internal error" | **Error** |
| tearDown cleanup | "Directory is not empty" / `InvalidObjectState` 403 | Stack trace in log (not in totals) |

Excluding getBucketLocation, the three items do not occur on the ONTAP S3 regular bucket. The next section examines their causes.

---

## 5. Observed facts vs inference for the NAS bucket failures

**Evidence tier: observation is Observed, internal cause is Hypothesis.** What is observed is only that "these three tests failed on the NAS bucket." The bucket-implementation details of ONTAP S3, NAS Bucket and FSx for ONTAP S3 Access Points are not public and could not be confirmed from this environment either (per §6, the ONTAP management plane is not reachable from outside). The internal causes below do not rise above inference.

### 5.1 ETag/MD5 mismatch (getObjectMetadata, copyObject)

Under the S3 contract, the ETag of a non-multipart, non-encrypted object equals the MD5 of the object content. The test expects the ETag of the PUT object to match a known MD5, and it mismatched only on the NAS bucket. That ETag generation differs across ONTAP S3, NAS Bucket and S3 Access Points is plausible, but a specific mechanism such as "a non-MD5 hash" or "re-derived on copyObject" cannot be stated from public information. The accurate statement is: **there may be an internal-implementation difference around ETag, but at present this does not rise above inference.**

> **Adjacent Public information (about a different path)**: AWS states for FSx for ONTAP S3 Access Points that "[the ETag is not an MD5 digest of the object data](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)." This test hit not the S3 Access Points but a native ONTAP S3 object-store server, whose ETag behaviour follows ONTAP's own spec and is unconfirmed here; but at least on the S3 Access Points path, ETag≠MD5 is documented as by design.

### 5.2 Internal error on PutObject with user metadata

`testPutObjectWithUserMetadata` is a PutObject with `x-amz-meta-*`. It passes on the ONTAP S3 regular bucket and errors only on the NAS bucket. Mapping to extended attributes (xattr) is a natural assumption in Linux terms, but how ONTAP actually represents this is unconfirmed. This is kept to: **there may be an implementation difference or constraint in the user-metadata persistence path.**

### 5.3 "Directory is not empty" at cleanup

The tearDown `deleteObject` appears to have tried to delete a pseudo-directory (prefix) and been refused because the NAS backing entity is a non-empty directory. Of the three, this is the more readily explained behaviour, but the internal cause is still inference.

### 5.4 A more essential framing of the three

These three are better not reduced to a directory-marker (HeadObject 404) problem. Placed per path, the results look like this:

| Path | Position |
|---|---|
| ONTAP S3 (regular bucket) | Effectively a full pass as S3-compatible (only the two tolerated items) |
| NAS Bucket | Partially compatible; viewed as object storage, differences remain (ETag, user metadata, cleanup) |
| FSx for ONTAP S3 Access Points | A path where an `amazon-fsx-fsvol-*` NAS bucket is created behind it. AWS-native integration is available, but whether the AWS front end absorbs the NAS bucket's quirks is not yet evaluated (§7) |

So it is not a simple directory-marker problem. Across Databricks, Snowflake and AI use cases, the essence is closer to: **treating a NAS Bucket as S3-compatible object storage itself still has difficult areas.** Confirmation requires the internal implementation or a vendor confirmation.

---

## 6. Feedback points for the storage development side

**Evidence tier: a framing based on Observed.** Points to raise with the side that improves the NAS bucket's S3-compatible behaviour (the storage development / product side).

**A single fix cannot be said to make S3-compatible compatibility sufficient.** The NAS bucket failures extend beyond the directory marker (the HeadObject 404 area) to the ETag family, the user-metadata family and the cleanup family. Therefore, **fixing only the HeadObject 404 problem cannot, at present, be said to make S3-compatible compatibility sufficient.** When discussing fix priority, do so on the premise that these three families (ETag / user metadata / cleanup) remain. This "the HeadObject 404 alone may not be enough" was a concern the verifier had raised beforehand, which this run's logs corroborate.

The getBucketLocation 400/404 difference is within the range the README explicitly tolerates and is excluded from this point. The ONTAP S3 regular bucket is effectively a full pass to begin with.

---

## 7. Next-phase items (S3 Access Points evaluation plan)

**Evidence tier: Not yet run.** The same test suite will be run via S3 Access Points and the results appended. The following are the points to confirm.

- FSx for ONTAP S3 Access Points have an `amazon-fsx-fsvol-*` NAS bucket created behind them (confirmed at Access Point deletion). So the main question is not the binary "close to ONTAP S3 or close to AWS S3," but **whether the NAS bucket's quirks (ETag, user metadata) are absorbed at the AWS front end, or fail at the same place as the NAS bucket**.
- **Test prerequisites must be distinguished from compatibility failures.** See the table in §7.1.
- **Some of the AI / Cortex differences are already known.** That some Cortex SQL is unavailable via S3 Access Points, that Cortex is US-region-centric with some Cortex / AI functions US-region only (depending on the function), and that as of 9/1 AI Images was not supported in the Tokyo region, have already been shared. Line up this known difference separately from basic S3 API compatibility.
- Aligning this also makes it easier to compare with the **Unity Catalog / AI Functions / FILE type** already verified on the Databricks side (lined up under the same lens as the [Databricks FILE type evaluation](./databricks-file-type-evaluation.md)).

S3 Access Points are, per §1 (A), a path Snowflake treats as Amazon S3, so the test pass/fail does not by itself decide connectivity. This section states no further hypothesis until results exist.

### 7.1 S3 Access Points constraints and their impact on the test suite

**Primary source**: [Access point compatibility — FSx for ONTAP (docs.aws.amazon.com)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), **confirmed 2026-09-26**. Compatibility failures and failures from unmet test prerequisites are treated separately.

| S3 AP constraint (AWS primary source) | Impact on the test suite | tier |
|---|---|---|
| **Object Versioning not supported** | The README requires versioning enabled on `BUCKET_NAME_1` → the prerequisite cannot be met. Failures arising from this are not compatibility gaps | Public (README + AWS doc) |
| **ETag is not an MD5 of the object data** | The getObjectMetadata / copyObject ETag=MD5 assertions are expected to fail on S3 AP too. By design, not a defect | Public (AWS doc); not measured on S3 AP |
| **CopyObject / UploadPartCopy same-Region, same access point only** | Whether the copyObject test stays within the same AP or attempts cross-AP is **unconfirmed against the test code** | Unconfirmed |
| **conditional writes not supported** | Whether the 9 tests use conditional writes such as `If-None-Match` is **unconfirmed against the test code** | Unconfirmed |
| `REGION_2` / `NOT_ACCESSIBLE_BUCKET` / prefix with over 1000 objects | Whether these can be arranged in the test harness | Unconfirmed (not verified in an S3 AP environment) |

**Presign (bears directly on the generatePresignedUrl test)**: the docs.aws.amazon.com table shows **`Presign — Supported` as of 2026-09-26**. The docs.amazonaws.cn S3 User Guide ([access-points-service-api-support](https://docs.amazonaws.cn/en_us/AmazonS3/latest/userguide/access-points-service-api-support.html)) also shows **Supported** in the FSx for ONTAP column. It was previously listed as `Not supported`. Presign is a client-side signature computation, and what actually runs is a supported GetObject. That history is in [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns docs/s3ap-compatibility-notes.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/s3ap-compatibility-notes.md). If the current listing holds, the generatePresignedUrl test is expected to pass on S3 AP too, but this was not measured on S3 AP.

---

## FAQ

**Q1. Can FSx for ONTAP be registered as Snowflake S3-compatible storage?**

The procedure itself is defined in the KB (Support request + public test suite verification). But this document covers only up to the test suite run; the end-to-end from application to established connection is out of scope here. Note that via S3 Access Points (path (A) in §1) you can connect as Amazon S3 without this application flow, and that path is E2E verified in the [setup guide](./snowflake-iceberg-setup.md).

**Q2. Are the two failures on the ONTAP S3 regular bucket a problem?**

Both are of a kind the test suite README explicitly tolerates. The getBucketLocation error-code difference is a negative-test implementation difference, and the one-object paging difference is a suspected prefix-count difference, not dropped data. The README also states the getBucketLocation failure can be ignored because the SigV4 region is obtained from a different header.

**Q3. How should the NAS bucket failures be interpreted?**

getBucketLocation is the same tolerated case as the ONTAP S3 regular bucket. The remaining three (ETag mismatch, internal error on PutObject with user metadata, cleanup failure) are observed facts whose internal cause does not rise above inference (**Hypothesis**). More essentially, it is better read as: treating a NAS Bucket as S3-compatible object storage itself still has difficult areas (§5.4). On the fix side, the point that matters is that fixing only the HeadObject 404 leaves ETag, user metadata and cleanup outstanding (§6).

**Q4. If a vendor is on Snowflake's list, does that mean it connects?**

A listing is not a connectivity guarantee. The KB body states the list is for convenience and that Snowflake does not validate compatibility. At actual registration you run the test suite against your own endpoint and submit the results to Support.

---

## References

**Snowflake (Public)**
- [Work with Amazon S3-compatible storage](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage) — requirements, enablement flow, vendor-list note
- [snowflake-s3compat-api-test-suite (GitHub)](https://github.com/snowflakedb/snowflake-s3compat-api-test-suite) — API list and Troubleshooting

**This repository**
- [Read files on FSx for ONTAP from Snowflake and write Iceberg tables](./snowflake-iceberg-setup.md) — E2E steps for path (A), Storage Integration
- [S3 Access Point networking](./fsx-ontap-s3ap-networking.md) — endpoint reachability design
- [Vendor comparison](./vendor-comparison.md) — Snowflake / Databricks integration paths
- [Databricks FILE type (Beta) evaluation](./databricks-file-type-evaluation.md) — S3 Access Points behaviour on another engine (sibling to this document)
