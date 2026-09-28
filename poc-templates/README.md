# PoC Templates — FSx for ONTAP S3 Access Points × Lakehouse

🌐 **English** | [日本語](README-ja.md)

## 30-Minute Quick Start

Deploy base infrastructure and run your first query in 30 minutes:

```bash
# 1. Deploy (10 min)
./scripts/deploy.sh --region ap-northeast-1

# 2. Upload sample data (2 min)
./scripts/upload-sample-data.sh

# 3. Validate (1 min)
./scripts/validate.sh

# 4. Run first Athena query (2 min)
./02-athena-quickstart/run-first-query.sh
```

**Result**: Athena queries FSx for ONTAP data via S3 Access Point — zero data copy.

---

## Choose Your Engine

| Customer's platform | Module | Time to first query | PoC cost (1 day) |
|---|---|---|---|
| AWS-native (Athena) | [02-athena-quickstart](02-athena-quickstart/) | 15 min | ~$0.05 |
| Snowflake | [03-snowflake-integration](03-snowflake-integration/) | 30 min | ~$5 |
| Databricks | [04-databricks-integration](04-databricks-integration/) | 1 hour | ~$10 |
| EMR Spark (ETL) | [05-emr-spark-etl](05-emr-spark-etl/) | 20 min | ~$0.50 |
| DuckDB Lambda (cheapest) | [06-duckdb-lambda](06-duckdb-lambda/) | 10 min | ~$0.01 |
| Enterprise governance | [07-governance](07-governance/) | 30 min | $0 (Lake Formation) |

---

## Repository Structure

```
poc-templates/
├── README.md                         # This file
├── 02-athena-quickstart/             # Fastest validation path
│   ├── sample-queries.sql            # Validation queries
│   └── README.md                     # Athena quickstart guide
├── 03-snowflake-integration/         # Snowflake External Table + Cortex AI
│   ├── 01-storage-integration.sql    # Storage Integration setup
│   ├── 02-stage-and-table.sql        # Stage + External Table
│   ├── 03-cortex-ai-demo.sql         # Cortex AI functions demo
│   └── README.md                     # Snowflake setup guide
├── 04-databricks-integration/        # DataSync → S3 → UC
│   ├── datasync-task.yaml            # DataSync CFn template
│   └── README.md                     # Databricks setup guide (UC DDL inline)
├── 05-emr-spark-etl/                 # EMR Serverless write-back
│   ├── spark-job.py                  # PySpark ETL script
│   └── README.md                     # EMR setup guide
├── 06-duckdb-lambda/                 # Cheapest path
│   ├── handler.py                    # Lambda handler
│   ├── template.yaml                 # Lambda CFn
│   └── README.md                     # DuckDB Lambda guide
├── 07-governance/                    # Lake Formation fine-grained
│   ├── lakeformation-setup.sh        # LF admin + grants
│   └── README.md                     # Governance guide
├── templates/                        # Partner-facing templates
│   ├── poc-proposal.md               # PoC proposal for customer
│   ├── success-criteria.md           # Go/No-Go checklist
│   ├── cost-estimate.md              # Cost calculator
│   ├── discovery-questions.md        # First meeting questions
│   ├── regulated-workload-checklist.md # Healthcare/Finance checklist
│   ├── post-poc-report.md            # Results report template
│   └── ja/                           # Japanese versions
├── sample-data/                      # Sample datasets
│   └── generate-sensor-data.py       # 10K row sensor data generator
└── scripts/
    ├── deploy.sh                     # One-click deploy
    └── validate.sh                   # Connectivity validation
```

Each numbered directory has both `README.md` and `README-ja.md`.

**Not yet included.** Earlier revisions of this README listed the following as
present. They were never added, so they have been removed from the tree above
rather than left as broken references:

| Not present | Use instead |
|---|---|
| `01-base-infrastructure/` (CFn for FSx + S3 AP + IAM) | [`shared/cloudformation/`](../shared/cloudformation/) |
| `02-athena-quickstart/create-glue-table.sql`, `run-first-query.sh` | DDL and query steps are inline in that directory's README |
| `03-snowflake-integration/04-dynamic-table.sql` | [`integrations/snowflake/sql/`](../integrations/snowflake/sql/) |
| `04-databricks-integration/uc-setup.sql`, `auto-loader-notebook.py` | Both are inline in that directory's README |
| `05-emr-spark-etl/emr-app.yaml` | [`integrations/`](../integrations/) EMR templates |
| `07-governance/column-level-demo.sql`, `row-filter-demo.sql` | Steps are inline in `lakeformation-setup.sh` and the README |
| `sample-data/generate-documents.py` | Not implemented |
| `scripts/upload-sample-data.sh`, `cleanup.sh` | Upload steps are in each README; delete the CFn stacks to clean up |

---

## Prerequisites

- AWS Account with FSx for ONTAP (ONTAP 9.17.1+)
- AWS CLI v2 configured
- Python 3.12+ (for sample data generation)
- (Optional) Snowflake account for Module 03
- (Optional) Databricks workspace for Module 04

---

## PoC Success Criteria

### Minimum Success (30 minutes)
- [ ] S3 Access Point is `AVAILABLE`
- [ ] `ListObjectsV2` returns sample data files
- [ ] Athena query returns correct results
- [ ] NFS/SMB access to same files still works

### Operational Success (1 day)
- [ ] Chosen engine queries FSx data successfully
- [ ] IAM and S3 AP policy scoped to minimum privilege
- [ ] Query latency and cost measured
- [ ] FSx throughput impact measured during queries
- [ ] Go/No-Go decision documented

### AI/Governance Success (2 days)
- [ ] AI functions work on FSx data (Cortex AI or Bedrock KB)
- [ ] Governance controls applied (Lake Formation or Snowflake Tags)
- [ ] Data sharing demonstrated (if required)
- [ ] Regulated workload checklist completed (if applicable)

---

## Cost Estimate

| Component | 1-day PoC | 1-week PoC | Notes |
|-----------|-----------|-----------|-------|
| FSx for ONTAP (existing) | $0 | $0 | Use existing file system |
| S3 Access Point | $0 | $0 | No additional charge |
| Athena queries | ~$0.05 | ~$0.25 | $5/TB scanned |
| EMR Serverless | ~$0.50 | ~$2.50 | Per-job pricing |
| Snowflake (XS warehouse) | ~$5 | ~$25 | Credit-based |
| Databricks (DataSync + compute) | ~$10 | ~$50 | Sync + DBU |
| Lake Formation | $0 | $0 | No additional charge |
| **Total (AWS-native only)** | **~$0.55** | **~$2.75** | Athena + EMR |
| **Total (with Snowflake)** | **~$5.55** | **~$27.75** | Add Snowflake credits |

---

## For Partners

See [templates/](templates/) for customer-facing materials:
- **First meeting**: [discovery-questions.md](templates/discovery-questions.md)
- **Proposal**: [poc-proposal.md](templates/poc-proposal.md)
- **Cost justification**: [cost-estimate.md](templates/cost-estimate.md)
- **Success criteria**: [success-criteria.md](templates/success-criteria.md)
- **Regulated workloads**: [regulated-workload-checklist.md](templates/regulated-workload-checklist.md)
- **Final report**: [post-poc-report.md](templates/post-poc-report.md)

---

## Related

- [Main README](../README.md) — Project overview and compatibility matrix
- [PoC ↔ Documentation Mapping](MAPPING.md) — Module-to-guide-to-blog correspondence table
- [Zero-Copy Unstructured Data Governance](../docs/en/zero-copy-media-governance.md) — S3 cost reduction + multi-platform governance + FlexCache S3 AP roadmap
- [Compatibility Matrix](../docs/en/compatibility-matrix.md) — Which operations work on which engine
- [Blog Series](../README.md#get-started) — Detailed validation articles (Part 0-7)
- [Verification Pack](../verification-pack/) — Evidence records from validation
- [Observability Integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations) — Audit log shipping (Datadog, Splunk, Grafana, Elastic)
