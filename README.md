🌐 **English** | [日本語](./README-ja.md)

# FSx for ONTAP Lakehouse Integrations

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/fsxn-lakehouse-integrations/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/fsxn-lakehouse-integrations)
[![gitleaks](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/actions/workflows/gitleaks.yml)

> Validation framework for querying enterprise file data (NFS/SMB) from analytics and lakehouse engines via **FSx for ONTAP S3 Access Points** — without data movement. For data engineers, solutions architects, and implementation partners evaluating zero-copy analytics on existing file storage.

**Scope**: this repository covers the analytics and lakehouse slice — which engines work against an access point, and what each result was measured on. It is **not** a general FSx for ONTAP guide. For adoption, design, migration and operations, start with the [Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook); for ransomware and immutability, audit log shipping, edge ingestion or access-aware RAG, see **[which repository answers your question](docs/en/repository-map.md)**.

---

## Get Started

| What you want to do | Guide | Time |
|---|---|:---:|
| Find out whether this is even the right repository | [Which repository answers your question](docs/en/repository-map.md) | 3 min |
| Understand what this is for, without jargon | [Business Guide](docs/en/quickstart-business-guide.md) | 5 min |
| Choose the right engine for your use case | [Engine Selection Guide](docs/en/engine-selection-guide.md) | 10 min |
| Compare architecture options & trade-offs | [Architecture Comparison](docs/adoption-guide/architecture-comparison.md) | 15 min |
| Understand S3 AP directory design & performance | [S3 AP Design Considerations](docs/en/s3ap-design-considerations.md) | 15 min |
| See every known constraint, grouped by originating layer | [Known Challenges by Layer](docs/en/known-challenges.md) | 15 min |
| Run a PoC end-to-end | [PoC Execution Guide](docs/implementation-guide/poc-execution-guide.md) | 15 min |
| Deploy base infrastructure | [Deployment Guide](docs/en/deployment-guide.md) | 30 min |
| Operate it: rollback, Day 2 tasks, getting ONTAP audit logs to a SIEM | [Deployment Guide — Day 2 Operations](docs/en/deployment-guide.md#day-2-operations) | 15 min |
| Distribute data with FlexCache / SnapMirror | [FlexCache/SnapMirror Considerations](docs/en/s3ap-flexcache-snapmirror-considerations.md) | 15 min |
| Connect FSx for ONTAP → Databricks Unity Catalog | [UC Connection Guide](docs/en/fsx-ontap-to-databricks-unity-catalog-guide.md) | 30 min |
| Govern unstructured data (images/video/docs) in a lakehouse | [Databricks FILE type Evaluation](docs/en/databricks-file-type-evaluation.md) | 20 min |
| Estimate what a Databricks verification costs before running one | [Databricks Verification Environment and Cost](docs/en/databricks-verification-environment-cost.md) | 10 min |
| Reproduce the Unity Catalog x S3 Access Point result in your own account | [Databricks Verification Runbook](docs/en/databricks-verification-runbook.md) | 45 min hands-on |

<details>
<summary>📂 All integrations & verification status</summary>

| Platform | Status | Pattern | Key Finding |
|----------|:---:|---------|-------------|
| [Athena](integrations/athena/) | ✅ Verified | Glue Catalog + Serverless | 54.8 MB/s, 5M rows in 2s |
| [Glue ETL](integrations/glue/) | ✅ Verified | Crawler + Medallion | Read + write-back (Parquet) |
| [EMR Spark](integrations/emr-spark/) | ✅ Verified | Spark SQL + Iceberg | Read + write-back, 10K rows in 16s |
| [Redshift Spectrum](integrations/redshift-spectrum/) | ✅ Verified | External Schema + Lake Formation | 5M rows in 4.3s |
| [DuckDB Lambda](integrations/duckdb/) | ✅ Verified | Serverless lightweight | 5M rows in 779ms, ~$0.00001/query |
| [Snowflake](integrations/snowflake/) | ✅ Verified | External Stage (`AWS_ACCESS_POINT_ARN`) | SELECT + External Table |
| [Delta Lake OSS](integrations/delta-lake-oss/) | ⚠️ Read only | delta-rs + Spark | Write returns 501 (conditional writes unsupported) |
| [Databricks](integrations/databricks/) | ⚠️ Blocked | Unity Catalog + Delta Lake | Session policy does not recognize S3 AP ARN format |
| [Iceberg Metadata Catalog](integrations/iceberg-metadata-catalog/) | ✅ AWS Native | S3 Tables + PyIceberg + Bedrock | AI-powered catalog; cross-platform in progress |
| [Manufacturing Platform](integrations/manufacturing-data-platform/) | 🔧 PoC | Kafka + ClickHouse + Databricks | Edge-to-cloud streaming |
| Dremio / Trino / BigQuery / Fabric | 🔲 Planned | — | — |

**Key insight**: AWS-native services work out of the box. Third-party platforms need explicit S3 AP ARN configuration. See [Compatibility Matrix](docs/en/compatibility-matrix.md).

</details>

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Analytics Engines (Athena / EMR / DuckDB / Snowflake / ...)    │
└────────────────────────────┬────────────────────────────────────┘
                             │ S3 API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              S3 Access Point  (IAM + AP policy)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ NFS/SMB  │ │ Snapshot │ │FlexClone │ │ Dedup/Compression  │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

Existing NFS/SMB applications continue unchanged. S3 Access Points add a read (and limited write) path for analytics — no data copies, no sync pipelines.

Full architecture details: [docs/en/architecture.md](docs/en/architecture.md)

<details>
<summary>⚠️ Constraints & known limitations</summary>

| Constraint | Impact | Workaround |
|---|---|---|
| No conditional writes (If-None-Match) | Delta/Iceberg/Hudi cannot write directly | Read from FSx for ONTAP, write to S3 |
| Databricks session policy rejects S3 AP ARN | Unity Catalog external location blocked | DataSync → S3, or OpenSharing (under analysis) |
| Same-region requirement | Analytics engine must co-locate with FSx for ONTAP | [Region Design Guide](docs/en/region-design-guide.md) |
| ONTAP S3 object-store-server conflicts with S3 AP | Cannot coexist on same SVM | Use separate SVMs |
| S3 AP on AD-joined SVM requires DC connectivity | Data ops fail if AD unreachable | [AD Integration notes](docs/en/fsx-ontap-s3ap-networking.md) |
| An access point authorizes every request as **one identity** | The original per-file ACLs do not carry into an analytics or RAG pipeline reading through it | Scope retrieval in the index, not in the storage layer — [Adoption Playbook: Data Utilization hub](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) |

</details>

<details>
<summary>📚 Articles & related repositories</summary>

**Blog series** (dev.to — 7-part validation deep dive):

[Part 0: Overview](https://dev.to/aws-builders/fsx-for-ontap-s3-access-points-x-lakehouse-what-works-what-doesnt-and-why-1jo3) ·
[Part 1: Athena](https://dev.to/aws-builders/query-nas-data-in-place-with-athena-and-fsx-for-ontap-s3-access-points-3lhh) ·
[Part 2: Databricks](https://dev.to/aws-builders/databricks-and-fsx-for-ontap-s3-access-points-a-layer-by-layer-validation-of-observed-boundaries-p4d) ·
[Part 3: Snowflake](https://dev.to/aws-builders/snowflake-and-fsx-for-ontap-s3-access-points-from-access-denied-to-working-external-tables-9k8) ·
[Part 4: DuckDB](https://dev.to/aws-builders/serverless-analytics-on-nas-data-for-000001query-duckdb-lambda-x-fsx-for-ontap-2o5o) ·
[Part 5: EMR Spark](https://dev.to/aws-builders/read-write-etl-on-nas-data-with-emr-serverless-spark-no-cluster-no-copy-hgm) ·
[Part 6: Redshift + Lake Formation](https://dev.to/aws-builders/redshift-spectrum-lake-formation-enterprise-governance-on-nas-data-2pik) ·
[Part 7: Table Format Boundaries](https://dev.to/aws-builders/why-delta-iceberg-and-hudi-cant-write-to-fsx-s3-access-points-and-what-works-instead-5be3)

**Related repositories**:

| Repository | Description |
|---|---|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | 17 serverless patterns for FSx for ONTAP S3 AP |
| [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai) | Edge (Raspberry Pi) → ONTAP → Kafka — feeds [Manufacturing Platform](integrations/manufacturing-data-platform/) |
| [FSx-for-ONTAP-Adoption-Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) | Adoption design notes organized by lifecycle and domain. Its Data Utilization hub covers the access-point constraints and dataset-versioning decisions that sit upstream of the integrations here |

**Documentation index**: [Reading Path Guide](docs/en/reading-path-guide.md) · [Industry Solution Catalog (26 industries)](docs/en/industry-solution-catalog.md)

**For AI agents and LLM tooling**: [llms.txt](llms.txt) — what this repository is, how to read its confidence markers, the entry points, and the eight assumptions that cost the most time when wrong.

</details>

<details>
<summary>🔧 For developers</summary>

```bash
npm install && npm test                    # Lint + unit tests
zizmor .github/workflows/                  # Actions security check
gitleaks detect --no-git --source .        # Secret scan
```

- **Stack**: CloudFormation (YAML), Python 3.12, Bash, pytest, cfn-lint
- **Security**: All Actions pinned to SHA. Renovate for dependency updates. [Supply-chain details](.github/workflows/)
- **Contributing**: Issues and PRs welcome. Run `npm test` and `gitleaks` before pushing.

</details>

<details>
<summary>🔀 S3 Access Points + SnapMirror / FlexCache — Multi-region data distribution</summary>

S3 Access Points で収集したデータを SnapMirror（DR）や FlexCache（読み取り加速）で別リージョン/別クラウドに配信し、宛先で NFS/SMB/S3 API アクセスを実現する構成を検証済み。

**S3 Access Points と FlexCache / SnapMirror の互換性（動作検証済み）:**

| 構成 | サポート | 条件 |
|------|:--------:|------|
| S3 AP ボリュームを SnapMirror Async ソースに | ✅ 検証済み | ONTAP 9.12.1+ |
| S3 AP ボリュームを FlexCache Origin に | ✅ 検証済み | ONTAP 9.12.1+ |
| FlexCache Cache Volume に S3 AP アタッチ | ✅ (version-gated) | ONTAP 9.18.1+ |
| SnapMirror Synchronous | ❌ | S3 NAS bucket では非サポート |
| SVM-DR | ❌ | S3 NAS bucket を含む SVM では非サポート |

> FSx for ONTAP S3 Access Points は ONTAP の S3 NAS bucket メカニズムに基づいている。上記は [NetApp 公式ドキュメント](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html) で S3 NAS bucket として記載されている仕様に対し、FSx for ONTAP S3 Access Points で動作検証を実施した結果である。

**詳細ドキュメント**: [SnapMirror + FlexCache 調査・検証](integrations/snapmirror-flexcache-multicloud/) (12 demo guides, validation scripts, 41 findings)

</details>

---

## License

MIT — see [LICENSE](LICENSE).

---

🌐 **English** | [日本語](./README-ja.md)
