# ISV Validation Matrix

> For ISVs building S3 API-compatible applications that may connect to FSx for ONTAP S3 Access Points.

## Key Lesson

S3 API compatibility at the SDK level does not guarantee compatibility with every platform's governance, runtime, or distributed execution layer. ISVs should validate each dimension independently.

## Validation Dimensions

| Dimension | What to test | Why it matters |
|---|---|---|
| Direct SDK access | boto3 / AWS SDK against S3 AP alias | Confirms basic S3 API compatibility |
| Platform connector access | Platform-native storage connector (e.g., Unity Catalog External Location) | Platform may add session policies or ARN restrictions |
| Distributed executor behavior | Multi-node / multi-worker credential and network propagation | Driver success ≠ executor success |
| Write-path behavior | PutObject, multipart upload, conditional writes | FSx for ONTAP S3 AP may not support all S3 write semantics |
| Governance integration | Platform lineage, audit, access control | Bypassing platform governance creates compliance gaps |
| Audit evidence | CloudTrail, platform audit logs, ONTAP audit | Required for regulated workloads |
| Performance and retry behavior | Latency, throughput, error rate under load | FSx throughput is bounded by provisioned capacity |
| Customer-managed VPC / private networking | VPC endpoint, private subnet, no internet egress | Many enterprise deployments require private connectivity |

## Validation Checklist

- [ ] S3 AP alias resolves correctly from application
- [ ] ListObjectsV2 returns expected results
- [ ] GetObject retrieves file content
- [ ] HeadObject returns correct metadata
- [ ] PutObject behavior documented (success or expected failure)
- [ ] DeleteObject behavior documented
- [ ] Multipart upload behavior documented
- [ ] Conditional write (If-None-Match) behavior documented
- [ ] Large file handling (>5 GB) documented
- [ ] Concurrent access behavior documented
- [ ] Error codes match standard S3 error responses
- [ ] Platform governance layer tested (if applicable)
- [ ] Distributed execution tested (if applicable)
- [ ] Private networking tested (if applicable)

## ARN Format Awareness

FSx S3 Access Points use a different ARN format than standard S3 buckets:

```
Standard S3:  arn:aws:s3:::bucket-name
FSx for ONTAP S3 AP:    arn:aws:s3:<region>:<account>:accesspoint/<name>
```

Applications or platforms that validate or restrict S3 ARN patterns may not recognize the FSx for ONTAP S3 AP format. This was the root cause of the session policy failures documented in this repository for both Databricks Unity Catalog and Snowflake.

The two platforms then diverged:

- **Snowflake — resolved.** Setting `AWS_ACCESS_POINT_ARN` on `CREATE STAGE` makes the session policy include the access point ARN. Verified 2026-05-24 ([evidence](../snowflake/evidence/2026-05-24/evidence-record.yaml)).
- **Databricks Unity Catalog — not resolved.** An equivalent `access_point` field exists but is not in current documentation, and the read through it is denied — registration succeeds ([details](../../integrations/databricks/README.md#where-the-denial-originates)).

The lesson for ISVs is that exposing a way to declare the access point ARN explicitly is what makes the difference — the SDK-level compatibility is identical in both cases.

## References

- [FSx for ONTAP S3 Access Points documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Managing access point access (dual-layer authorization)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [S3 Access Points overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points.html)
