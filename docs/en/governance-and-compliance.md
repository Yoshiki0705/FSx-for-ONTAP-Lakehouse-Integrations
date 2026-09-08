# Governance and Compliance

## Overview

This document defines the governance, security, and compliance framework for FSx for ONTAP Lakehouse integrations. It is designed for regulated industries (healthcare, financial services, public sector) where data classification, access control, audit, and responsibility boundaries must be clearly documented before deployment.

## Data Classification

| Classification | Description | Example Data | Access Control |
|---------------|-------------|--------------|----------------|
| **Public** | Non-sensitive, publishable | Aggregated reports, public datasets | Open read via internet-origin AP |
| **Internal** | Business-sensitive, not regulated | Internal analytics, operational metrics | VPC-origin AP, team-scoped IAM roles |
| **Confidential** | Business-critical, contractual obligations | Financial transactions, customer records | VPC-origin AP, per-user IAM, restricted file system user |
| **Regulated** | Subject to legal/regulatory requirements | PHI (HIPAA), PII (GDPR), PCI DSS data | VPC-origin AP, minimum-privilege IAM, read-only AP user, audit logging mandatory |

## Access Control Architecture

FSx for ONTAP S3 Access Points use a **dual-layer authorization model** ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)):

```
┌─────────────────────────────────────────────────────────────────┐
│                    Request Flow                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Caller (IAM Principal)                                          │
│       │                                                           │
│       ▼                                                           │
│  ┌─────────────────────────────────────────┐                     │
│  │  Layer 1: AWS IAM Authorization          │                     │
│  │  ─────────────────────────────────────── │                     │
│  │  • IAM identity policy                   │                     │
│  │  • S3 Access Point resource policy       │                     │
│  │  • VPC Endpoint policy (if applicable)   │                     │
│  │  • Service Control Policy (SCP)          │                     │
│  │  • Network origin check (VPC/Internet)   │                     │
│  └─────────────────┬───────────────────────┘                     │
│                    │ ALLOW                                         │
│                    ▼                                               │
│  ┌─────────────────────────────────────────┐                     │
│  │  Layer 2: File System Authorization      │                     │
│  │  ─────────────────────────────────────── │                     │
│  │  • File system user (UNIX or Windows)    │                     │
│  │  • UNIX: mode-bits or NFSv4 ACLs        │                     │
│  │  • NTFS: Windows ACLs                    │                     │
│  │  • Directory/file level permissions      │                     │
│  └─────────────────┬───────────────────────┘                     │
│                    │ ALLOW                                         │
│                    ▼                                               │
│              Access Granted                                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Both layers must permit the request.** An explicit Deny in any layer overrides Allow statements in other layers.

### Layer 1: IAM Authorization Details

| Policy Type | Scope | Example Use |
|-------------|-------|-------------|
| IAM Identity Policy | Per-principal (user/role) | Grant analyst role read-only access to AP |
| Access Point Policy | Per-access point | Restrict AP to specific IAM roles or VPC |
| VPC Endpoint Policy | Per-VPC endpoint | Limit which APs are accessible from VPC |
| Service Control Policy | Per-OU/account | Enforce organization-wide restrictions |
| Network Origin | Per-access point (immutable after creation) | VPC-origin: deny all requests not from bound VPC |

### Layer 2: File System Authorization Details

| Security Style | Permission Model | Use Case |
|---------------|-----------------|----------|
| UNIX | mode-bits (rwx) or NFSv4 ACLs | Linux/NFS workloads |
| NTFS | Windows ACLs (full/modify/read) | Windows/SMB workloads |
| Mixed | UNIX effective, NTFS for Windows clients | Hybrid environments |

**Important**: The file system user associated with the access point determines the permission level for ALL requests through that AP. Use the principle of least privilege:
- Read-only analytics → read-only file system user
- ETL write-back → read-write user scoped to specific directories
- Never use root (UID 0) for production access points

## Network Security

### Block Public Access

Amazon S3 enforces Block Public Access by default for all access points attached to FSx for ONTAP volumes. **This setting cannot be modified or disabled.** ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html))

### Network Origin Options

| Origin | Security Level | Use Case | Limitation |
|--------|---------------|----------|------------|
| **VPC** | Highest | Regulated data, internal analytics | Cannot be changed after creation; Athena/managed services cannot access |
| **Internet** | Standard (IAM-controlled) | AWS managed services (Athena, Bedrock, Glue) | Requires strong IAM policies for access control |

**Note**: "Internet origin" does NOT mean public access. All requests still require valid IAM credentials. Block Public Access prevents anonymous access. ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html))

### Recommended Network Architecture for Regulated Data

```
┌─────────────────────────────────────────────────┐
│  VPC (Private Subnets Only)                      │
│                                                   │
│  ┌───────────┐    ┌──────────────────────┐       │
│  │ Analytics │───▶│ S3 Gateway Endpoint  │       │
│  │ Platform  │    │ (in-VPC traffic)     │       │
│  └───────────┘    └──────────┬───────────┘       │
│                              │                    │
│  ┌───────────┐    ┌──────────▼───────────┐       │
│  │On-premises│───▶│ S3 Interface Endpoint│       │
│  │via DX/VPN │    │ (external traffic)   │       │
│  └───────────┘    └──────────┬───────────┘       │
│                              │                    │
│                    ┌─────────▼────────────┐       │
│                    │ S3 Access Point      │       │
│                    │ (VPC origin)         │       │
│                    └─────────┬────────────┘       │
│                              │                    │
│                    ┌─────────▼────────────┐       │
│                    │ FSx for ONTAP Volume │       │
│                    └─────────────────────-┘       │
└─────────────────────────────────────────────────┘
```

## Audit and Logging

| Log Source | What is Captured | Retention | Use |
|-----------|-----------------|-----------|-----|
| **AWS CloudTrail** | FSx for ONTAP API calls (CreateAccessPoint, etc.), S3 data events (GetObject, PutObject via AP) | Configurable (recommend 1+ year for compliance) | Who accessed what, when, from where |
| **FSx for ONTAP audit logs** | NFS/SMB file access events (via ONTAP fpolicy/audit) | Configurable on ONTAP | Direct file system access not through S3 AP |
| **Lakehouse audit logs** | Query history, table modifications (platform-specific) | Platform-dependent | Analytics activity tracking |
| **VPC Flow Logs** | Network traffic to/from FSx for ONTAP ENIs | Configurable | Network-level access verification |
| **S3 Access Point access logs** | S3 data events via CloudTrail | Same as CloudTrail | S3 API-level access audit |

### Enabling S3 Data Events for Access Points

To audit individual object-level operations (GetObject, PutObject) through access points, enable **S3 data events** in CloudTrail:

```json
{
  "EventSelectors": [{
    "ReadWriteType": "All",
    "DataResources": [{
      "Type": "AWS::S3::AccessPoint",
      "Values": ["arn:aws:s3:REGION:ACCOUNT:accesspoint/ACCESS-POINT-NAME"]
    }]
  }]
}
```

## Encryption

| Layer | Mechanism | Key Management | Notes |
|-------|-----------|---------------|-------|
| **At rest** | SSE-FSX (automatic) | AWS KMS managed | All FSx for ONTAP file systems encrypted by default; transparent to applications |
| **In transit (S3 API)** | TLS 1.2+ | AWS managed | HTTPS enforced for S3 API calls |
| **In transit (NFS)** | Kerberos encryption (optional) | Customer managed | For NFS clients accessing same data |
| **In transit (SMB)** | SMB encryption (optional) | Customer managed | For SMB clients accessing same data |

**Note**: SSE-FSX is the only supported server-side encryption mode for S3 Access Points. SSE-S3, SSE-KMS, and SSE-C are not supported. ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html))

## Data Residency

| Aspect | Guarantee |
|--------|-----------|
| Data at rest | Remains in the AWS Region where FSx for ONTAP is deployed |
| S3 Access Point | Must be in same Region as FSx for ONTAP volume ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html)) |
| DR replication | SnapMirror to specified DR Region (customer-controlled) |
| Query results | Written to customer-specified S3 bucket (same or different Region) |
| Backup storage | Same Region as file system, redundant across multiple AZs |

## Responsibility Matrix (RACI)

| Responsibility | AWS | FSx for ONTAP Admin | Lakehouse Admin | Data Owner |
|---------------|-----|-----------|-----------------|------------|
| Physical infrastructure security | **R** | — | — | — |
| FSx for ONTAP file system encryption at rest | **R** | — | — | — |
| FSx for ONTAP file system provisioning | I | **R** | — | — |
| S3 Access Point creation & policy | I | **R** | C | — |
| IAM role/policy for analytics | I | C | **R** | — |
| File system user permissions | I | **R** | C | A |
| Data classification | — | — | C | **R** |
| Lakehouse table access control | — | — | **R** | A |
| Audit log review | — | C | C | **R** |
| Compliance validation | — | C | C | **R** |
| Incident response | C | **R** | **R** | A |

R = Responsible, A = Accountable, C = Consulted, I = Informed

## Industry-Specific Considerations

### Healthcare (HIPAA)

| Requirement | Implementation |
|-------------|---------------|
| PHI access control | VPC-origin AP + minimum-privilege IAM + read-only file system user |
| Audit trail | CloudTrail S3 data events enabled on AP |
| Encryption | SSE-FSX (at rest) + TLS (in transit) — both automatic |
| Data residency | Single-region deployment, no cross-region replication of PHI without BAA |
| De-identification | Glue ETL pipeline for de-identification before analytics access |
| Sample data | Use synthetic data only for development/testing |

### Financial Services (PCI DSS / SOX)

| Requirement | Implementation |
|-------------|---------------|
| Segregation of duties | Separate IAM roles for admin vs. analyst; separate APs per domain |
| Data mesh domain ownership | Per-domain SVMs with per-consumer access points |
| Audit retention | CloudTrail logs retained 7+ years (SOX) |
| Change management | Infrastructure as Code (CloudFormation), PR-based changes |
| DR/BCP | SnapMirror cross-region, documented RTO/RPO |

### Manufacturing (OT/IT Boundary)

| Requirement | Implementation |
|-------------|---------------|
| OT/IT separation | Separate VPCs for OT data collection and IT analytics |
| Edge ingestion | NFS/SMB write from edge → S3 AP read for analytics |
| Long-term retention | FabricPool tiering for cold data |
| Data freshness | Near-real-time (NFS write immediately visible via S3 AP) |

## Secure Reference Deployment: Healthcare Read-Only Analytics

```yaml
# Minimal secure deployment for healthcare analytics
Components:
  FSx for ONTAP:
    deployment_type: MULTI_AZ
    throughput_capacity: 512  # MB/s
    storage_capacity: 1024   # GB
    ontap_version: "9.17.1+"
    
  S3 Access Point:
    network_origin: VPC      # Private access only
    file_system_user: 
      type: UNIX
      username: analytics_reader  # Read-only user
    block_public_access: true     # Enforced (cannot disable)
    
  IAM:
    role: healthcare-analytics-role
    policy:
      - Effect: Allow
        Action: [s3:GetObject, s3:ListBucket]
        Resource: 
          - "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap"
          - "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap/object/*"
      # No PutObject, DeleteObject — read-only
      
  VPC:
    endpoint_type: Gateway  # For in-VPC analytics
    endpoint_policy: Scoped to healthcare-ap only
    
  Audit:
    cloudtrail: 
      data_events: enabled
      resource: "arn:aws:s3:REGION:ACCOUNT:accesspoint/healthcare-ap"
      retention: 7_years
      
  Data:
    type: Synthetic only (no real PHI in dev/test)
    format: Parquet (de-identified)
```

## Pre-Deployment Checklist

> **Important**: This document provides a generic governance framework. For any real deployment, all sections must be customized with the customer's legal, security, data protection, and business stakeholders. Do not use these templates as-is without customer-specific review.

### Healthcare PoC Governance Intake Questions

Before starting any Healthcare PoC, answer these questions with the customer:

| # | Question | Answer Options | Impact on Design |
|---|----------|---------------|-----------------|
| 1 | Does the data contain PHI or PII? | Yes / No / Partially | If Yes: de-identification pipeline required before S3 AP exposure |
| 2 | Is the data de-identified, pseudonymized, or raw? | De-identified / Pseudonymized / Raw | Raw/Pseudo: cannot expose via S3 AP without processing |
| 3 | What is the intended use? | Administrative / Research / Clinical Documentation / CDS / Patient-facing | Determines risk level and required approvals (see RAG Use Risk Classification) |
| 4 | Who will review AI-generated responses? | Named role/person | Must be qualified for the use classification |
| 5 | Who is the data owner? | Named role/person | Required for access approval and risk acceptance |
| 6 | Who can accept residual risk? | Named role/person | See Risk Acceptance Authority Matrix |
| 7 | What is the required audit log retention? | Years | Minimum 6 years (HIPAA) or 7 years (SOX) |
| 8 | Is IRB/ethics board approval required? | Yes / No | Required for research secondary use |

### Healthcare PoC Recommended Initial Scope

For the first Healthcare PoC, limit to the lowest-risk configuration:

- ✅ De-identified documents only (no raw PHI)
- ✅ Research support or Administrative use only
- ✅ Read-only S3 Access Point
- ✅ Human review mandatory for all RAG responses
- ❌ Patient-facing responses: NOT in initial scope
- ❌ Clinical decision support: NOT in initial scope
- ❌ Raw PHI: NOT in initial scope

### Healthcare
- [ ] De-identification pipeline validated
- [ ] No PHI in sample/test data
- [ ] VPC-origin access point (if not using Athena/managed services)
- [ ] Read-only file system user
- [ ] CloudTrail S3 data events enabled
- [ ] Audit log retention configured (7+ years)
- [ ] BAA in place with AWS
- [ ] Data residency confirmed (single region)

### Financial Services
- [ ] Segregation of duties validated (admin ≠ analyst roles)
- [ ] Per-domain access points with scoped policies
- [ ] CloudTrail enabled with long-term retention
- [ ] SnapMirror DR configured and tested
- [ ] Change management process documented
- [ ] Encryption verified (at rest + in transit)

### Manufacturing
- [ ] OT/IT network separation confirmed
- [ ] Edge data ingestion path validated
- [ ] Data freshness SLA documented
- [ ] Long-term retention policy configured (FabricPool)

---

## Safety vs. Assurance

Technical safety and organizational assurance are distinct concerns. Regulated industries require both.

| Aspect | Safety (技術的安全性) | Assurance (説明可能な安心) |
|--------|---------------------|--------------------------|
| **What it answers** | "Is the system technically secure?" | "Can we explain WHY it is secure to stakeholders?" |
| **Audience** | Security engineers, auditors | CxO, compliance officers, patients, regulators |
| **Evidence** | Configuration, test results, penetration tests | Documentation, diagrams, responsibility matrices, audit reports |
| **FSx for ONTAP S3 AP controls** | IAM policy, AP policy, VPC endpoint, file system ACL, SSE-FSX, Block Public Access | Architecture diagrams, RACI matrix, audit log samples, incident response procedures |

### Building Assurance from Safety Controls

| Safety Control | Assurance Artifact |
|---------------|-------------------|
| Block Public Access (enforced, cannot disable) | "No anonymous access is possible — this is enforced by AWS at the infrastructure level and cannot be overridden by any administrator" |
| Dual-layer authorization | Architecture diagram showing both IAM and file system checks must pass |
| VPC-origin access point | "Data can only be accessed from within our private network — requests from the internet are rejected before any policy evaluation" |
| CloudTrail S3 data events | Monthly audit report showing who accessed what data, when, from where |
| SSE-FSX encryption | "All data is encrypted at rest using AWS KMS — encryption is automatic and cannot be disabled" |
| Read-only file system user | "The analytics system can only read data — it is physically impossible for it to modify or delete files" |

### Assurance Documentation Checklist

- [ ] Non-technical architecture overview (1-page diagram with plain language)
- [ ] Data flow diagram showing where data resides and who can access it
- [ ] RACI matrix signed by all responsible parties
- [ ] Audit log sample report (redacted) demonstrating monitoring capability
- [ ] Incident response procedure document
- [ ] Annual access review process document
- [ ] Third-party explanation materials (for regulators, patients, partners)

---

## Generative AI / RAG Governance

When using FSx for ONTAP S3 AP as a data source for generative AI (e.g., Amazon Bedrock Knowledge Bases, Snowflake Cortex Search), additional governance considerations apply.

### Platform-Specific RAG Governance

| Platform | RAG Path | Data Movement | Governance Model | Best For |
|----------|----------|---------------|-----------------|----------|
| **Amazon Bedrock KB** | FSx for ONTAP S3 AP → Bedrock KB → OpenSearch (embeddings) | Embeddings created in customer account | IAM + Bedrock guardrails + human review | AWS-native, permission-aware retrieval |
| **Snowflake Cortex Search** | FSx for ONTAP S3 AP → External Table → COPY INTO → Cortex Search Service | Data copied to Snowflake storage | Snowflake RBAC + Tags + Row Access Policy | Snowflake-native, governed analytics + RAG |

### Snowflake Governance on FSx for ONTAP Data

Snowflake provides a complementary governance layer for FSx for ONTAP data accessed via S3 Access Points:

| Capability | How It Works | Governance Value |
|---|---|---|
| **Object Tagging** | `ALTER TABLE ext_table SET TAG sensitivity = 'confidential'` | Data classification at table/column level |
| **Row Access Policy** | Policy function filters rows based on user role/context | Row-level security without data duplication |
| **Dynamic Data Masking** | Column masking policy hides sensitive values for unauthorized roles | Column-level protection on External Table |
| **Access History** | `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` tracks all queries | Query-level audit trail (who queried what, when) |
| **Data Sharing Governance** | Share External Tables with Row Access Policy applied | Governed distribution to partners/suppliers |
| **Cortex AI Guardrails** | Cross-Region Inference controls, model access policies | AI processing boundary control |

**Snowflake governance applies to External Tables on FSx for ONTAP S3 AP** — no COPY INTO required for governance features (Tags, Row Policy, Masking, Sharing, Access History). Cortex AI functions (COMPLETE, SUMMARIZE, EXTRACT_ANSWER) and Cortex Search also work directly on Managed Iceberg Tables without requiring data in internal tables (confirmed May 2026). Only Vision AI with TO_FILE on FSx for ONTAP S3 AP stages requires the COPY FILES workaround.

### Snowflake Audit for External Engine Access (Confirmed May 2026)

External engine access via Horizon Iceberg REST Catalog is tracked through `SNOWFLAKE.ACCOUNT_USAGE.STORAGE_REQUEST_HISTORY`, which records HTTP operations (Class 1: PUT/COPY/POST/LIST, Class 2: GET/SELECT) with counts per time window. Note: these accesses do NOT appear in QUERY_HISTORY since external engines bypass the Snowflake query engine.

### Snowflake Open Catalog (Polaris) vs Horizon REST Catalog

| Path | Use Case | Metadata Owner | Governance Enforcement |
|------|----------|---------------|----------------------|
| **Horizon REST Catalog** (recommended) | Snowflake is primary writer | Snowflake | ✅ Row Access Policy + Masking enforced |
| **Open Catalog (Polaris)** | Dedicated catalog layer needed | Open Catalog | Sync from Snowflake (read-only in Open Catalog) |
| **Externally managed Iceberg** | External engine is primary writer | Glue/external | Snowflake reads as External Iceberg Table (read-only) |

Reference: [Snowflake Open Catalog Sync](https://docs.snowflake.com/en/user-guide/tables-iceberg-open-catalog-sync)

### Snowflake Horizon Iceberg REST Catalog — Governance on External Engines (Confirmed May 2026)

> **Verified here (May 2026)**: Snowflake Horizon Catalog enforces governance policies on external engine access (Row Access Policies and Dynamic Data Masking evaluated at the catalog layer).

| Aspect | Snowflake Horizon Catalog | Databricks Unity Catalog |
|--------|--------------------------|--------------------------|
| **Row Access Policies on external engines** | ✅ **Enforced** — policies evaluated before vended credentials are issued | ❌ NOT enforced on external engines |
| **Dynamic Data Masking on external engines** | ✅ **Enforced** — masking applied at catalog layer | ❌ NOT enforced on external engines |
| **RBAC on external engines** | ✅ **Enforced** — role-based access control evaluated | ✅ Metadata access controlled |
| **Data access model** | Vended credentials scoped by policy evaluation | Vended credentials without policy enforcement |
| **Edition requirement** | All editions (Standard, Enterprise, Business Critical) | All editions |
| **Billing** | 0.5 credits per million API calls (billing starts H2 2026) | Included in platform cost |
| **Supported external engines** | Apache Spark, Trino (Databricks UC integration: "Not announced") | Athena, EMR, Trino, Spark |

**How Horizon Catalog governance works for external engines:**

```
External Engine (Spark/Trino)
  │
  │ 1. Authenticate to Horizon Iceberg REST Catalog API
  │    (using Snowflake user credentials)
  ▼
Snowflake Horizon Catalog
  │
  │ 2. Evaluate RBAC + Row Access Policies + Masking Policies
  │    against authenticated user's context
  ▼
  │ 3. Return Iceberg metadata + scoped temporary credentials
  │    (credentials are limited to policy-permitted data)
  ▼
External Engine reads S3 data files directly
  (Snowflake is NOT in the data path for file reads)
```

**Architecture implication for regulated workloads:**
- **Snowflake Horizon path**: Single governance layer covers both internal Snowflake queries AND external engine access. No additional Lake Formation setup needed.
- **Databricks UC path**: Requires Lake Formation as a separate governance layer for external engine access (UC governance only applies within Databricks compute).

**Reference**: [Snowflake Horizon Iceberg REST Catalog — External Engine Access](https://docs.snowflake.com/en/user-guide/tables-iceberg-access-using-external-query-engine-snowflake-horizon) (Step 5: Configure data protection policies)

### Comparison: AWS-Native vs Snowflake vs Databricks Governance for FSx for ONTAP S3 AP Data

| Aspect | AWS-Native (Lake Formation) | Snowflake (External Table) | Databricks (Unity Catalog via DataSync → S3) |
|--------|---|---|---|
| Table/column permissions | ✅ Lake Formation grants | ✅ Object Tags + Column Masking | ✅ UC Grants + Column Masks |
| Row-level filtering | ✅ Data Cells Filter | ✅ Row Access Policy | ✅ Row Filters |
| Tag-based access control | ✅ LF-Tags | ✅ Object Tags + Tag-based masking | ✅ UC Tags + Tag-based policies |
| Audit trail | ✅ CloudTrail + LF audit | ✅ Access History + query logs | ✅ System Tables (audit logs) |
| Cross-account/org sharing | ✅ LF cross-account grants | ✅ Snowflake Data Sharing (simpler) | ✅ Delta Sharing (open protocol) |
| AI governance | ✅ Bedrock guardrails | ✅ Cortex AI controls + Cross-Region settings | ✅ Mosaic AI guardrails + Model Registry |
| Data lineage | ❌ Not built-in | ❌ Not built-in | ✅ Automatic (UC lineage graph) |
| Setup complexity | Medium (LF admin + grants) | Low (built-in to Snowflake platform) | Medium (DataSync + UC setup) |
| Engines covered | Athena, Redshift, EMR, Glue | Snowflake only | Databricks (Spark, SQL, ML) |
| Data movement required | None (governance on same data) | None for governance; COPY INTO for Cortex Search | **Yes — DataSync → S3 required** (UC cannot access FSx for ONTAP S3 AP directly) |
| FSx for ONTAP S3 AP direct access | ✅ | ✅ (with `AWS_ACCESS_POINT_ARN`) | ❌ (UC table creation blocked; DataSync path required) |
| Governance enforced on external engines | ✅ (Athena, Redshift, EMR all governed) | ✅ **Horizon Catalog enforces Row Access Policies + Masking on external engines** (confirmed May 2026) | ❌ **UC Row Filters/Column Masks NOT enforced on external engines** (Athena/EMR via Iceberg REST Catalog bypass UC governance) |

### Databricks Unity Catalog Governance (via DataSync → S3)

Databricks Unity Catalog provides enterprise governance for FSx for ONTAP data **after syncing to S3 via DataSync**. While UC cannot directly access FSx for ONTAP S3 AP (session policy limitation confirmed May 2026), the DataSync → S3 → UC path provides full governance capabilities:

| Capability | How It Works | Governance Value |
|---|---|---|
| **Table/Column Grants** | `GRANT SELECT ON TABLE ... TO group` | Fine-grained access control per principal |
| **Row Filters** | `ALTER TABLE ... SET ROW FILTER function` | Row-level security based on user context |
| **Column Masks** | `ALTER TABLE ... ALTER COLUMN ... SET MASK function` | Dynamic column masking per role |
| **UC Tags** | `ALTER TABLE ... SET TAGS ('sensitivity' = 'pii')` | Data classification and discovery |
| **Automatic Lineage** | Built-in lineage graph (table → table, column → column) | Impact analysis, compliance tracing |
| **Audit Logs** | `system.access.audit` system table | Who accessed what, when, from where |
| **Delta Sharing** | Open protocol — share with any Delta Sharing-compatible client | Cross-org sharing without data copy (Snowflake, Pandas, Spark can read) |
| **Mosaic AI Governance** | Model Registry, Feature Store, AI guardrails | ML model lifecycle governance |
| **Lakehouse Monitoring** | Data quality metrics, drift detection | Proactive data quality governance |

**Key constraint**: All Databricks UC governance requires data to be in S3 (not FSx for ONTAP S3 AP directly). The recommended architecture:

```
FSx for ONTAP (source of truth)
  ↓ DataSync (incremental sync, 5-min schedule)
Amazon S3 bucket (synced copy)
  ↓ Auto Loader (incremental ingestion)
Unity Catalog Managed Table (full governance)
  ↓
  ├── Row Filters + Column Masks (fine-grained access)
  ├── Automatic Lineage (impact analysis)
  ├── Mosaic AI (ML training, Feature Store)
  └── Delta Sharing (cross-org distribution)
```

#### UC Iceberg REST Catalog — External Engine Access Constraints

> **Verified here (May 2026)**: When external engines (Athena, EMR Spark, Trino) access UC-managed tables via the Iceberg REST Catalog:

| Aspect | Behavior | Implication |
|--------|----------|-------------|
| **Data access** | External engine reads S3 data files **directly** — UC does not proxy data | External engine's IAM role must have S3 read permissions on underlying data files |
| **Row Filters** | ❌ **NOT enforced** for external engines | Row-level security only applies within Databricks compute (Spark/Photon) |
| **Column Masks** | ❌ **NOT enforced** for external engines | Column masking only applies within Databricks compute |
| **UC Grants** | Metadata access controlled by UC | External engine can discover tables but governance is not enforced at data layer |

**Architecture implication**: If you need governance enforced on external engines (Athena, EMR) accessing UC-managed data, you must **additionally configure Lake Formation** on the same S3 data. UC governance and Lake Formation governance operate independently — UC governs Databricks access, Lake Formation governs AWS-native engine access.

```
UC-managed Delta/Iceberg table on S3
  ├── Databricks access → UC Row Filters + Column Masks (enforced)
  └── Athena/EMR access (via Iceberg REST Catalog) → UC governance NOT enforced
       └── Must use Lake Formation for governance on external engine access
```

> **For regulated workloads**: Do not assume that UC governance automatically protects data when accessed from non-Databricks engines. If compliance requires row/column-level access control on Athena or EMR queries, configure Lake Formation permissions on the same underlying S3 data independently of UC.

> **Trade-off**: Databricks provides the richest governance feature set (especially automatic lineage and ML governance), but requires data duplication via DataSync. Snowflake and Lake Formation can govern FSx for ONTAP S3 AP data without copying. Choose based on whether lineage/ML governance or zero-copy access is the higher priority.

> **Recommendation for regulated workloads**: Use **Lake Formation** when governance must apply across multiple AWS-native engines (Athena + Redshift + EMR). Use **Snowflake governance** when the primary platform is Snowflake and you need integrated AI + governance + data sharing without data movement. Use **Databricks UC** when automatic lineage, ML governance (Mosaic AI, Feature Store), or Delta Sharing (open protocol) are required — accepting the DataSync sync latency and storage duplication as trade-offs. All three can coexist on the same FSx for ONTAP source data.

### Data Handling for AI/RAG

| Concern | Governance Control |
|---------|-------------------|
| **PHI/PII in source documents** | De-identification pipeline BEFORE indexing; never index raw PHI/PII |
| **Embedding storage location** | Bedrock Knowledge Bases stores embeddings in a customer-managed vector store (OpenSearch Serverless); ensure same-region, same-account |
| **Vector store encryption** | OpenSearch Serverless encrypts at rest by default (AWS KMS) |
| **Embedding deletion** | When source document is deleted, re-sync Knowledge Base to remove corresponding embeddings |
| **Prompt/response logging** | Enable CloudWatch Logs for Bedrock model invocations; retain per compliance requirements |
| **Human review requirement** | RAG responses in healthcare/financial MUST include human review before action |
| **Hallucination mitigation** | Configure Bedrock guardrails; include source citation in responses; validate against source documents |
| **Synthetic data for testing** | Use synthetic documents for development/testing; never use real PHI/PII in non-production |
| **Model access policy** | Restrict which Bedrock models can be invoked; use IAM policies on `bedrock:InvokeModel` |

### RAG Architecture for Regulated Industries

```
┌─────────────────────────────────────────────────────────────┐
│  Regulated RAG Architecture                                  │
│                                                              │
│  ┌──────────────┐     ┌─────────────────┐                  │
│  │ Source Docs   │     │ De-identification│                  │
│  │ (FSx for ONTAP Volume)  │────▶│ Pipeline (Glue)  │                  │
│  │ NFS/SMB write │     │ Remove PHI/PII   │                  │
│  └──────────────┘     └────────┬────────┘                  │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Clean Documents  │                   │
│                       │ (FSx for ONTAP Volume)     │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ S3 Access Point  │                   │
│                       │ (read-only user) │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Bedrock KB       │                   │
│                       │ (ingestion)      │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Vector Store     │                   │
│                       │ (OpenSearch)     │                   │
│                       └────────┬────────┘                   │
│                                │                             │
│  ┌──────────────┐     ┌───────▼─────────┐                  │
│  │ User Query    │────▶│ Bedrock Agent    │                  │
│  │ (with guardrails)   │ + Guardrails     │                  │
│  └──────────────┘     └───────┬─────────┘                  │
│                                │                             │
│                       ┌────────▼────────┐                   │
│                       │ Human Review     │                   │
│                       │ (required)       │                   │
│                       └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Lifecycle Management

### Retention Policy Framework

| Data Type | Retention Period | Storage Tier | Deletion Method |
|-----------|----------------|-------------|-----------------|
| Active analytics data | Indefinite (while in use) | FSx for ONTAP SSD | Manual review + approval |
| Historical analytics data | Per business requirement | FSx for ONTAP Capacity Pool (FabricPool) | Automated tiering, manual deletion |
| Audit logs (CloudTrail) | 7 years (SOX) / 6 years (HIPAA) | S3 (CloudTrail destination) | S3 Lifecycle policy |
| ONTAP Snapshots | Per snapshot policy (e.g., 7 daily, 4 weekly) | FSx for ONTAP SSD (copy-on-write) | Automatic per policy |
| RAG embeddings | Same as source document retention | OpenSearch Serverless | Re-sync Knowledge Base after source deletion |
| Query results (Athena) | 90 days (default) or per policy | S3 (Athena results bucket) | S3 Lifecycle policy |

### Data Deletion Procedure

1. **Identify**: Determine which files/records must be deleted (data owner approval required)
2. **Verify dependencies**: Check if data is referenced by Glue Catalog, Bedrock KB, or other services
3. **Delete from source**: Remove via NFS/SMB or S3 AP (DeleteObject)
4. **Update catalog**: Re-run Glue Crawler or manually drop table/partition
5. **Re-sync AI**: If used by Bedrock KB, trigger re-sync to remove embeddings
6. **Verify deletion**: Confirm via ListObjectsV2 and catalog query
7. **Audit**: CloudTrail records the deletion event automatically

---

## Incident Response

### Incident Response Flow

```
Detection → Triage → Containment → Investigation → Recovery → Post-mortem
    │          │          │              │             │           │
    ▼          ▼          ▼              ▼             ▼           ▼
CloudTrail  Severity   Revoke AP     CloudTrail    Snapshot    Document
Alert       Assessment policy/IAM    log analysis  restore     & improve
```

### Incident Scenarios and Response

| Scenario | Detection | Containment | Recovery |
|----------|-----------|-------------|----------|
| Unauthorized data access | CloudTrail alert on unexpected principal | Update AP policy to deny; revoke IAM credentials | Review access logs; assess data exposure |
| AP policy misconfiguration | CloudTrail `PutAccessPointPolicy` event | Revert to known-good policy (IaC) | Verify access restored for authorized users |
| Data corruption (accidental) | Application error reports; data validation failure | Isolate affected volume (if needed) | Restore from ONTAP Snapshot |
| Ransomware | Unusual write patterns; file extension changes | Disconnect NFS/SMB clients; AP remains read-only if configured | Restore from immutable Snapshot |
| Region failure | AWS Health Dashboard; connectivity loss | Activate DR runbook | SnapMirror failover; create new AP in DR region |

### Snapshot Restore Approval Flow

For regulated environments, snapshot restore should follow an approval process:

1. **Request**: Operator identifies need for restore (with justification)
2. **Approve**: Data owner or compliance officer approves (documented)
3. **Notify**: Inform all stakeholders (analytics teams, application owners)
4. **Execute**: Perform snapshot restore
5. **Reconcile**: Re-run Glue Crawler; verify catalog consistency
6. **Validate**: Confirm data integrity via sample queries
7. **Document**: Record restore event, reason, approver, outcome

### DR Failover Governance Checklist

- [ ] SnapMirror relationship confirmed healthy (lag within RPO)
- [ ] DR region AP creation procedure documented and tested
- [ ] IAM roles/policies replicated to DR region
- [ ] Glue Catalog recreation procedure documented
- [ ] Application configuration update procedure documented
- [ ] Communication plan for stakeholders activated
- [ ] Post-failover validation queries defined
- [ ] Failback procedure documented

---

## Stakeholder Explanation Guide

Different stakeholders have different concerns. Tailor the explanation to their role.

| Stakeholder | Primary Concern | Key Explanation | Evidence Artifact | Decision Criteria |
|-------------|----------------|-----------------|-------------------|-------------------|
| **Hospital CIO** | Business value, cost, timeline | "Analyze existing file data without migration; reduce analytics setup from weeks to hours" | Cost comparison, timeline, architecture overview | ROI, implementation risk, vendor lock-in |
| **CISO / Security Team** | Data protection, access control, attack surface | "Dual-layer auth, Block Public Access enforced, VPC isolation option, all access audited" | Security architecture diagram, penetration test results, CloudTrail samples | Threat model coverage, compliance alignment |
| **Data Protection Officer** | Privacy, data residency, deletion rights | "Data stays in-region, single source (no copies), deletion procedure documented, audit trail" | Data flow diagram, retention policy, deletion procedure | GDPR/HIPAA alignment, data subject rights |
| **Clinical Research Lead** | Data access speed, research enablement | "Query research data with SQL in minutes, not days; AI search on documents" | Demo, query latency benchmarks | Time-to-insight, data freshness |
| **Legal / Compliance** | Regulatory adherence, liability, contracts | "BAA with AWS, encryption at rest/transit, audit retention 7+ years, responsibility matrix" | RACI, BAA confirmation, compliance mapping | Regulatory gap analysis |
| **Audit Team** | Evidence, traceability, completeness | "Every data access logged in CloudTrail with principal, timestamp, action, resource" | Audit log samples, report generation procedure | Audit trail completeness, retention |
| **Public Sector Procurement** | Certification, sovereignty, vendor assessment | "AWS Region data residency, FedRAMP/ISO certifications, no data leaves region" | AWS compliance certifications, data residency guarantee | Procurement checklist compliance |
| **Patient Communication** | Trust, transparency, control | "Your data is protected by multiple security layers; only authorized researchers can access de-identified data" | Plain-language privacy notice | Patient trust, opt-out mechanism |

---

## Assurance Artifact Pack

Complete set of deliverables for regulated industry deployment approval.

| # | Artifact | Purpose | Audience | Format |
|---|----------|---------|----------|--------|
| 1 | Non-technical architecture overview | Explain system in plain language | CxO, board, patients | 1-page PDF with diagram |
| 2 | Data flow diagram | Show where data resides and moves | DPO, security, audit | Visio/draw.io diagram |
| 3 | Access control explanation | Explain who can access what and why | CISO, compliance | 2-page document |
| 4 | RACI matrix (signed) | Assign responsibilities | All stakeholders | Signed document |
| 5 | Audit log sample report | Demonstrate monitoring capability | Audit, compliance | Redacted CloudTrail report |
| 6 | Incident response procedure | Define response to security events | Security, operations | Runbook document |
| 7 | Data lifecycle policy | Define retention, deletion, archival | DPO, legal | Policy document |
| 8 | RAG governance checklist | AI-specific controls | CISO, research lead | Checklist |
| 9 | Residual risk register | Document accepted risks | CxO, CISO | Risk register |
| 10 | Compliance mapping | Map controls to regulations | Compliance, audit | Matrix (HIPAA/PCI/SOX) |

### Artifact Production Timeline

| Week | Artifacts Produced | Input Required From |
|------|-------------------|-------------------|
| 1 | #1 Architecture, #2 Data flow | Technical team |
| 2 | #3 Access control, #4 RACI draft | Security + data owners |
| 3 | #5 Audit sample, #6 Incident response | Operations + security |
| 4 | #7 Lifecycle, #8 RAG governance | DPO + research lead |
| 5 | #9 Risk register, #10 Compliance mapping | CISO + legal |
| 6 | Review and sign-off | All stakeholders |

---

## Secondary Use of Healthcare Data

When healthcare data is used beyond its primary clinical purpose (e.g., for research, AI training, population health analytics), additional governance applies.

### Primary vs. Secondary Use

| Aspect | Primary Use | Secondary Use |
|--------|------------|---------------|
| Purpose | Direct patient care | Research, analytics, AI, quality improvement |
| Data form | Identified (PHI) | De-identified or anonymized |
| Consent | Treatment consent | Research consent or waiver (IRB/ethics board) |
| Access | Clinical staff | Researchers, data scientists, AI systems |
| Storage | Clinical systems (EHR) | Research data platform (FSx for ONTAP + analytics) |
| Governance | Clinical data governance | Research data governance + ethics |

### Secondary Use Governance Framework

| Control | Implementation |
|---------|---------------|
| **Consent / Approval** | IRB/ethics board approval for research use; document consent basis |
| **De-identification** | Apply HIPAA Safe Harbor or Expert Determination method before analytics access |
| **Re-identification risk** | Assess k-anonymity; restrict linkage variables; monitor for re-identification attempts |
| **Dataset access approval** | Per-project approval by data governance committee; time-limited access |
| **Research workspace isolation** | Separate VPC/account for research; no data export without approval |
| **Export control** | Results only (aggregated); no individual-level data export without review |
| **Publication review** | All publications using the data must be reviewed for re-identification risk |
| **Audit trail** | All research data access logged; periodic access review |

### De-identification Pipeline for FSx for ONTAP S3 AP

```
Clinical Volume (PHI)          Research Volume (De-identified)
      │                                    │
      ▼                                    ▼
┌──────────────┐              ┌─────────────────────┐
│ NFS/SMB      │              │ S3 Access Point     │
│ (clinical    │              │ (read-only,         │
│  staff only) │              │  research team)     │
└──────┬───────┘              └──────────┬──────────┘
       │                                  │
       ▼                                  ▼
┌──────────────────────────────────────────────────┐
│         FSx for ONTAP (separate volumes)          │
│  Vol1: /clinical (PHI)  │  Vol2: /research (safe) │
└─────────────┬────────────┴───────────────────────┘
              │
     ┌────────▼────────┐
     │ Glue ETL        │
     │ De-identification│
     │ Pipeline         │
     │ (scheduled)      │
     └─────────────────┘
```

**Key principle**: PHI volume has NO S3 Access Point. Only the de-identified research volume is exposed via S3 AP.

---

## Human Review Workflow for RAG

When RAG is used in regulated industries, AI-generated responses require human review before action.

### Workflow Steps

```
┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐
│ 1. User │───▶│ 2. RAG   │───▶│ 3. Response  │───▶│ 4. Human │
│ submits │    │ retrieves│    │ generated    │    │ reviewer │
│ query   │    │ + answers│    │ with citations│    │ evaluates│
└─────────┘    └──────────┘    └──────────────┘    └────┬─────┘
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                    ┌──────────┐ ┌──────────┐ ┌──────────┐
                                    │ APPROVE  │ │ EDIT     │ │ REJECT   │
                                    │ (as-is)  │ │ (modify) │ │ (discard)│
                                    └────┬─────┘ └────┬─────┘ └────┬─────┘
                                         │            │             │
                                         ▼            ▼             ▼
                                    ┌──────────────────────────────────┐
                                    │ 5. Decision logged               │
                                    │    (who, when, action, reason)   │
                                    └──────────────┬───────────────────┘
                                                   │
                                         ┌─────────▼─────────┐
                                         │ 6. Response        │
                                         │    delivered to user│
                                         └─────────┬─────────┘
                                                   │
                                         ┌─────────▼─────────┐
                                         │ 7. Feedback loop   │
                                         │    (accuracy       │
                                         │     tracking)      │
                                         └───────────────────┘
```

### Review Criteria

| Criterion | Check | Action if Failed |
|-----------|-------|-----------------|
| Source accuracy | Do citations match the answer? | REJECT or EDIT |
| Completeness | Does the answer address the full question? | EDIT to add missing info |
| Hallucination | Does the answer contain claims not in sources? | REJECT |
| PHI leakage | Does the answer reveal patient-identifiable information? | REJECT + escalate |
| Clinical safety | Could the answer cause patient harm if acted upon? | REJECT + escalate |
| Regulatory compliance | Does the answer comply with applicable regulations? | REJECT + legal review |

### Review SLA

| Priority | Review Time | Escalation |
|----------|-------------|-----------|
| Routine research query | < 4 hours | Auto-escalate after 8 hours |
| Clinical decision support | < 1 hour | Immediate escalation if unreviewed |
| Compliance/audit query | < 2 hours | Escalate to compliance officer |

---

## Governance Approval Workflow

Sequential approval process for regulated industry deployments.

| Step | Approver | Required Artifact | Decision Criteria | Possible Outcomes |
|------|----------|-------------------|-------------------|-------------------|
| 1. Technical review | Platform architect | Architecture diagram, compatibility matrix | Technically sound, no unsupported patterns | Approve / Request changes |
| 2. Security review | CISO / security team | Security architecture, negative test results, AP policy | All Security Verified criteria met | Approve / Conditional (with mitigations) / Reject |
| 3. Data owner review | Data governance committee | Data classification, access scope, retention policy | Data used appropriately, access minimized | Approve / Restrict scope / Reject |
| 4. Legal / compliance | Legal counsel | Compliance mapping, BAA, data residency | Regulatory requirements met | Approve / Require additional controls / Reject |
| 5. Clinical / business owner | Department head | Business case, KPI targets, user impact | Business value justified, risk acceptable | Approve / Defer / Reject |
| 6. Executive approval | CIO / CISO | Residual risk register, cost approval, RACI | Organizational risk acceptable | Approve / Reject |
| 7. Go-live approval | Operations lead | Runbooks tested, monitoring configured, DR validated | Operationally ready | Approve / Delay |

### Approval Evidence Retention

All approval decisions must be documented and retained:
- Approver name and role
- Date of decision
- Decision (Approve / Conditional / Reject)
- Conditions (if conditional)
- Evidence reviewed
- Retention: Same as audit log retention (7+ years for regulated)

---

## Residual Risk Register Template

| Risk ID | Description | Impact (1-5) | Likelihood (1-5) | Risk Score | Existing Controls | Residual Level | Owner | Treatment | Acceptance Authority | Review Frequency |
|---------|-------------|:---:|:---:|:---:|-------------------|:---:|-------|-----------|---------------------|-----------------|
| R-001 | FSx for ONTAP S3 AP does not support atomic rename; Delta write may corrupt | 5 | 1 | 5 | Anti-pattern documented; read-only AP enforced | Low | Platform team | Avoid (do not use Delta write) | CISO | Quarterly |
| R-002 | Tens of ms latency may not meet real-time analytics SLA | 3 | 3 | 9 | Benchmark before production; document SLA | Medium | Platform team | Mitigate (provision higher throughput) | Business owner | Quarterly |
| R-003 | AP policy misconfiguration could block all access | 4 | 2 | 8 | IaC-managed policy; SCP restricts changes; runbook | Low | Security team | Mitigate (SCP + IaC + runbook) | CISO | Monthly |
| R-004 | Snapshot restore may cause Glue Catalog inconsistency | 3 | 2 | 6 | Runbook for catalog repair; crawler re-run | Low | Data platform | Mitigate (runbook + automation) | Platform lead | Quarterly |
| R-005 | RAG hallucination in clinical context | 5 | 3 | 15 | Human review required; Bedrock guardrails; citation check | Medium | AI team | Mitigate (human-in-loop mandatory) | Clinical lead | Monthly |

### Risk Scoring Guide

- **Impact**: 1=Negligible, 2=Minor, 3=Moderate, 4=Major, 5=Critical
- **Likelihood**: 1=Rare, 2=Unlikely, 3=Possible, 4=Likely, 5=Almost certain
- **Risk Score**: Impact × Likelihood
- **Residual Level**: Low (1-6), Medium (7-12), High (13-19), Critical (20-25)

---

## Plain-Language Explanation Examples

For non-technical stakeholders (patients, citizens, board members).

| Question | Plain-Language Answer |
|----------|---------------------|
| **Where is my data stored?** | "Your data stays on a secure file system in an AWS data center in [region]. It is never moved or copied to another location for analytics." |
| **Who can access my data?** | "Only authorized staff with specific job roles can access data. Every access requires two separate permission checks — one from AWS security, and one from the file system itself." |
| **Can anyone on the internet see my data?** | "No. Public access is blocked by default and cannot be turned on. Even authorized users must prove their identity before every access." |
| **What does the AI see?** | "The AI only sees documents that have been de-identified — all personal information is removed before the AI can access them." |
| **Does a human check the AI's answers?** | "Yes. Every AI-generated answer is reviewed by a qualified person before it is used for any decision." |
| **What if the AI gives a wrong answer?** | "Wrong answers are flagged, logged, and discarded. The system learns from these errors to improve over time." |
| **Can I ask for my data to be deleted?** | "Yes. We have a documented deletion process. When data is deleted, it is removed from the file system, the search index, and the AI's knowledge base." |
| **How do you know no one accessed my data improperly?** | "Every single data access is automatically logged with who, when, and what. These logs are kept for [7+] years and reviewed regularly." |

---

## RAG Use Risk Classification

Different RAG use cases carry different risk levels in healthcare/regulated contexts.

| Classification | Risk Level | Examples | Allowed Data | Required Review | Prohibited Use | Approval Level |
|---------------|:---:|---------|-------------|----------------|---------------|----------------|
| **Administrative** | Low | Meeting scheduling, facility info, HR policy lookup | Public + Internal | Optional (spot-check) | No clinical data | Team lead |
| **Research support** | Medium | Literature search, protocol lookup, methodology guidance | De-identified research data | Required (researcher) | No identified patient data | Research lead + IRB |
| **Clinical documentation** | Medium-High | Discharge summary drafting, coding assistance | De-identified clinical notes | Required (clinician) | No autonomous documentation | Clinical director |
| **Clinical decision support** | High | Differential diagnosis assistance, treatment option lookup | De-identified + evidence-based sources only | Mandatory (physician) | No autonomous decisions | Medical director + CISO |
| **Patient-facing** | Highest | Patient portal Q&A, appointment guidance | Public health info only | Mandatory (clinical + legal) | No clinical advice, no PHI | Executive + legal + clinical |

### Risk-Based Controls

| Risk Level | Logging | Human Review | Guardrails | Audit Frequency |
|:---:|---------|:---:|-----------|:---:|
| Low | Standard | Optional | Basic (topic filtering) | Quarterly |
| Medium | Enhanced | Required | Moderate (citation required) | Monthly |
| Medium-High | Full (prompt + response) | Mandatory | Strict (hallucination detection) | Bi-weekly |
| High | Full + clinical context | Mandatory (physician) | Maximum (Bedrock guardrails + custom) | Weekly |
| Highest | Full + legal hold | Mandatory (multi-party) | Maximum + legal review | Continuous |

---

## References

- [Managing access point access — Dual-layer authorization](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Configuring network access for Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)
- [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [Monitoring FSx for ONTAP API Calls with AWS CloudTrail](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/logging-using-cloudtrail-win.html)
- [Access points naming rules, restrictions, and limitations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html)
- [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
