🌐 **English** | [日本語](./poc-execution-guide-ja.md)

# PoC Execution Guide: FSx for ONTAP AI Metadata Catalog

> Step-by-step checklist for deploying and validating the AI metadata catalog pipeline.

---

## Prerequisites

| Requirement | Detail |
|-------------|--------|
| AWS Account | With permissions for FSx for ONTAP, Lambda, Bedrock, S3 Tables, OpenSearch |
| FSx for ONTAP | Existing environment or new provisioning |
| Bedrock model access | Enabled in target region (Claude + Titan Embeddings) |
| Network connectivity | VPC peering/endpoints validated |
| Sample files | 100–1,000 representative files identified |

---

## Implementation Timeline

### Phase 1: Infrastructure (1–2 days)

- Deploy FSx for ONTAP (or validate existing environment)
- Configure S3 Access Point
- Create S3 Tables (Iceberg) namespace
- Deploy Lambda functions and IAM roles
- Validate network connectivity (VPC, security groups)

### Phase 2: AI Pipeline (2–3 days)

- Configure FPolicy on FSx for ONTAP
- Deploy Bedrock-powered classification pipeline
- Configure classification templates for target file types
- Set up OpenSearch Serverless collection
- Run initial batch processing on existing files
- Validate AI classification accuracy

### Phase 3: Search & Analytics Interface (1–2 days)

- Configure Athena workgroup and saved queries
- Deploy OpenSearch Dashboards (search UI)
- Set up Lake Formation governance policies
- Create dashboards for target use cases
- Conduct acceptance testing

**Total: 5–7 business days** from kickoff to operational system.

---

## Execution Checklist

### Pre-deployment (Day 0)

- [ ] PoC scope and success criteria defined
- [ ] AWS Account ID and region confirmed
- [ ] FSx for ONTAP environment available (or provisioned)
- [ ] Sample files identified (100–1,000 representative files)
- [ ] Network connectivity validated (VPC peering/endpoints)
- [ ] Bedrock model access enabled in target region

### Phase 1: Deploy (Day 1–2)

- [ ] CloudFormation stack deployed successfully
- [ ] S3 Access Point validated (can read files from FSx for ONTAP)
- [ ] Lambda functions tested with sample file
- [ ] S3 Tables namespace created and accessible from Athena

### Phase 2: Pipeline (Day 3–5)

- [ ] FPolicy configured and events flowing — **only if the PoC writes over NFS or SMB.** Writes that arrive through an S3 access point raise no FPolicy notification (measured 2026-08-26, ONTAP 9.18.1P3D1), so this criterion is unreachable for an S3-write PoC and the polling or audit-log path should be used instead
- [ ] AI classification running on sample files
- [ ] Classification accuracy reviewed (target: >85%)
- [ ] OpenSearch index populated
- [ ] Vector embeddings generated

### Phase 3: Validation (Day 6–7)

- [ ] File search via Athena SQL confirmed
- [ ] File search via OpenSearch UI confirmed
- [ ] PII detection validated (if applicable)
- [ ] Pipeline performance measured (target: 42s single file)
- [ ] Cost projection validated against [Cost Estimation](../adoption-guide/cost-estimation.md)

### Post-PoC

- [ ] Results documented with measured metrics
- [ ] Accuracy assessment per file type
- [ ] Identified gaps and tuning requirements
- [ ] Production scaling considerations documented

---

## Success Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Pipeline latency | <60s (single file) | CloudWatch Lambda duration |
| Classification accuracy | >85% confidence average | Manual review of sample set |
| Search availability | Files searchable within 2 minutes of creation | End-to-end timing test |
| FPolicy impact | <5ms added latency | NAS client I/O measurement |
| Cost per file | Within 2x of estimate | CloudWatch + Cost Explorer |

---

## Common Issues & Troubleshooting

| Issue | Likely Cause | Resolution |
|-------|-------------|------------|
| S3 AP returns AccessDenied | IAM policy or S3 AP policy misconfigured | Verify Lambda role has `s3:GetObject` on AP ARN |
| FPolicy events not flowing | **First check how the data is being written.** Writes through an S3 access point produce no FPolicy notification at all, and that is expected — not a misconfiguration. Otherwise: engine not connected, or scope too narrow | Confirm the write path first, then `vserver fpolicy show` and the event scope |
| Bedrock timeout | File too large or prompt too complex | Reduce file size limit or simplify prompt |
| OpenSearch index empty | Embedding pipeline failed silently | Check Lambda CloudWatch logs for errors |
| Athena query returns 0 rows | S3 Tables namespace or table not registered | Verify `SHOW TABLES` in Athena workgroup |
| High FPolicy latency | Synchronous mode or network bottleneck | Switch to asynchronous FPolicy if acceptable |

---

## CloudFormation Quick Deploy

```bash
# Deploy the full stack (single command)
aws cloudformation deploy \
  --template-file integrations/iceberg-metadata-catalog/cloudformation/template.yaml \
  --stack-name fsxontap-metadata-catalog \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    FsxFileSystemId=fs-0123456789abcdef0 \
    SvmId=svm-0123456789abcdef0 \
    S3AccessPointAlias=your-ap-alias-s3alias \
    BedrockModelId=anthropic.claude-3-5-sonnet-20241022-v2:0
```

---

## Related Documents

| Document | Content |
|----------|---------|
| [Technical Overview](../adoption-guide/technical-overview.md) | Architecture and verified metrics |
| [Technical FAQ](../adoption-guide/technical-faq.md) | Detailed Q&A on limitations and integrations |
| [Cost Estimation](../adoption-guide/cost-estimation.md) | Component-level cost breakdown |
| [Architecture Comparison](../adoption-guide/architecture-comparison.md) | Decision framework for approach selection |

---

*Last updated: 2026-06*
