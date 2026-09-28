🌐 **English** | [日本語](ja/poc-proposal.md)

# PoC Proposal: FSx for ONTAP S3 Access Points × Analytics

## For: [Customer Name]
## By: [Partner Name]
## Date: [YYYY-MM-DD]

---

## Executive Summary

[Customer] stores [X TB] of enterprise file data on [FSx for ONTAP / on-premises ONTAP]. Today, analytics requires copying this data to S3 — creating duplicate storage, stale data, and pipeline maintenance overhead.

**Proposed solution**: Enable S3 Access Points on FSx for ONTAP to provide direct S3 API access to existing file data. Analytics platforms (Athena, Snowflake, Databricks, EMR) query the data in place — no copy, no sync pipeline, no duplicate storage.

**Expected outcome**: Eliminate data freshness lag (24h → near-zero), remove [N] copy pipelines, save ~$[X]/month in duplicate storage.

---

## Business Challenge

| Current pain | Impact | Root cause |
|---|---|---|
| Data freshness lag | Decisions based on stale data | Nightly batch copy to S3 |
| Duplicate storage cost | $___/month for S3 copies | Analytics requires S3 |
| Pipeline maintenance | ___h/month ops overhead | Sync pipelines break |
| Governance fragmentation | Separate controls for NAS vs S3 | Two access paths |

---

## Proposed Solution

```
Before: NFS/SMB → [Copy Pipeline] → S3 → Analytics Platform
After:  NFS/SMB ←→ FSx for ONTAP ←→ S3 Access Point → Analytics Platform
                    (same data, same volume, zero copy)
```

**Key technical facts:**
- S3 Access Points provide S3 API access to FSx for ONTAP file data
- Dual-layer authorization (IAM + file system permissions)
- Supported by: Athena, Glue, EMR, Redshift Spectrum, Snowflake, DuckDB
- ONTAP features preserved: Snapshot, Dedup, FlexClone, multi-protocol

---

## PoC Scope

| Dimension | Scope |
|-----------|-------|
| Duration | [1 day / 1 week / 2 weeks] |
| Data | [Sample / subset of production] |
| Engine | [Athena / Snowflake / Databricks / EMR] |
| Governance | [IAM only / Lake Formation / Snowflake Tags] |
| AI/ML | [None / Cortex AI / Bedrock KB] |
| Success criteria | [See attached success-criteria.md] |

---

## Deliverables

| # | Deliverable | Timeline |
|---|-------------|----------|
| 1 | S3 Access Point configured and validated | Day 1 |
| 2 | First successful query from chosen engine | Day 1 |
| 3 | Governance controls applied and tested | Day 2 |
| 4 | Performance benchmark (latency, throughput) | Day 2-3 |
| 5 | AI/ML demonstration (if in scope) | Day 3-4 |
| 6 | Go/No-Go recommendation with evidence | Final day |
| 7 | Post-PoC report with architecture recommendation | +2 days |

---

## Cost

| Component | Estimated cost |
|-----------|---------------|
| AWS infrastructure (PoC duration) | ~$[X] |
| Partner professional services | [X] days × $[rate] |
| **Total PoC investment** | **$[X]** |

See [cost-estimate.md](cost-estimate.md) for detailed breakdown.

---

## Expected ROI (Post-PoC Production)

| Metric | Current | After | Annual savings |
|--------|---------|-------|---------------|
| Duplicate S3 storage | $___/month | $0 | $___/year |
| Pipeline maintenance | ___h/month | 0h | ___h/year |
| Data freshness | ___hours | Near-zero | — |
| Time-to-insight | ___days | ___hours | — |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| FSx throughput impact on NFS/SMB workloads | Measure during PoC; rollback = revoke AP policy |
| Platform doesn't support S3 AP | Validated in [blog series](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations#blog-series--ブログシリーズ); fallback = DataSync |
| Governance requirements not met | Lake Formation (AWS) or Snowflake Tags provide fine-grained control |
| PoC data contains sensitive information | Use synthetic data; real data only after approval |

---

## Next Steps

1. [ ] Customer confirms PoC scope and timeline
2. [ ] Partner deploys base infrastructure (Day 1 morning)
3. [ ] First query success (Day 1 afternoon)
4. [ ] Governance and AI validation (Day 2-3)
5. [ ] Go/No-Go decision meeting (Final day)

---

## References

- [GitHub: fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations)
- [AWS: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Blog Series: 7-part validation](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations#blog-series--ブログシリーズ)
