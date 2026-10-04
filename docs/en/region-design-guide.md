# Region Design Guide

[日本語](../ja/region-design-guide.md)

## Overview

When integrating Amazon FSx for NetApp ONTAP (FSx for ONTAP) with Lakehouse platforms,
**region selection and alignment** is one of the most critical design decisions.

This guide documents the configuration adopted in this project and provides
design guidelines for users deploying in other regions.

---

## This Project's Configuration

### Verification Environment

| Component | Region | Details |
|-----------|--------|---------|
| FSx for ONTAP | `ap-northeast-1` (Tokyo) | File System ID: `<YOUR_FSX_FILESYSTEM_ID>` |
| S3 Access Point | `ap-northeast-1` (Tokyo) | Same region as FSx for ONTAP (required) |
| Databricks Workspace | `ap-northeast-1` (Tokyo) | Same region for VPC-scoped AP |
| AWS Account | `<YOUR_AWS_ACCOUNT_ID>` | Verification account |

### Design Decision: Co-located in Same Region

```
┌─────────────────────────────────────────────────────────────┐
│                  ap-northeast-1 (Tokyo)                       │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │ Databricks  │──▶│ S3 Access    │──▶│ FSx for ONTAP   │  │
│  │ Workspace   │   │ Point (VPC)  │   │ Volume          │  │
│  │             │   │              │   │                 │  │
│  │ (in VPC)    │   │ (VPC-scoped) │   │ (Private Subnet)│  │
│  └─────────────┘   └──────────────┘   └─────────────────┘  │
│                                                               │
│  ✅ Low latency (< 1ms)                                      │
│  ✅ No data transfer cost (same AZ)                           │
│  ✅ VPC-scoped AP for network isolation                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Region Selection Principles

### Principle 1: Co-locate FSx for ONTAP and Analytics Platform in Same Region

```text
Recommended: Same region
┌──────────────────────────────────┐
│  Region X                         │
│  FSx for ONTAP + S3 AP + Platform │
└──────────────────────────────────┘

Not recommended: Cross-region
┌──────────────┐         ┌──────────────┐
│  Region A    │ ──────▶ │  Region B    │
│  FSx for ONTAP│  High latency │  Platform    │
└──────────────┘  Transfer cost └──────────────┘
```

**Reasons:**
- S3 Access Points are regional resources (created in same region as FSx for ONTAP)
- VPC-scoped APs are only accessible from VPCs within the same region
- Cross-region access adds 100-200ms latency
- Cross-region data transfer costs $0.02/GB

### Principle 2: Prefer VPC-Scoped AP (When Possible)

| Platform | VPC-scoped AP | Internet-origin AP |
|----------|--------------|-------------------|
| Databricks | ✅ Recommended | Possible (not recommended) |
| EMR / Spark | ✅ Recommended | Possible |
| Lambda | ✅ Recommended | Possible |
| Snowflake | Not possible | ✅ Required |
| Athena | Not possible | ✅ Required |
| Glue | Not possible | ✅ Required |
| Redshift Spectrum | Not possible | ✅ Required |

### Principle 3: Data Residency Requirements Take Priority

When regulatory requirements exist, compliance drives region selection:

| Regulation | Target Regions | Notes |
|-----------|---------------|-------|
| GDPR | eu-west-1, eu-central-1 | Data must stay within EU |
| FISC | ap-northeast-1 | Japanese financial regulation |
| HIPAA | us-east-1, us-west-2 | BAA-eligible regions |
| PDPA | ap-southeast-1 | Singapore data protection |
| PIPL | cn-north-1, cn-northwest-1 | China data regulation |

---

## Recommended Configurations by Region

### Asia Pacific (APAC)

| Use Case | Recommended Region | Reason |
|----------|-------------------|--------|
| Japanese enterprise (FISC) | `ap-northeast-1` | Regulatory + full service availability |
| Korean enterprise | `ap-northeast-2` | Low latency + Databricks support |
| Southeast Asia | `ap-southeast-1` | Singapore hub + PDPA compliance |
| Australia | `ap-southeast-2` | Data sovereignty + full service support |
| India | `ap-south-1` | Low latency + cost efficiency |

### Europe, Middle East & Africa (EMEA)

| Use Case | Recommended Region | Reason |
|----------|-------------------|--------|
| EU enterprise (GDPR) | `eu-west-1` | Ireland, broadest service availability |
| German enterprise | `eu-central-1` | Frankfurt, GDPR + BaFin |
| UK enterprise | `eu-west-2` | London, UK GDPR |
| Nordic enterprise | `eu-north-1` | Stockholm |
| Middle East | `me-south-1` | Bahrain |

### Americas

| Use Case | Recommended Region | Reason |
|----------|-------------------|--------|
| US enterprise (general) | `us-east-1` | Broadest service availability, lowest cost |
| US West Coast | `us-west-2` | Low latency for west coast users |
| Canadian enterprise | `ca-central-1` | Canadian data sovereignty |
| Brazilian enterprise | `sa-east-1` | LGPD compliance |

---

## Databricks Region Availability

### Regions Where Databricks Workspace Can Be Created

| Region | Unity Catalog | Delta Sharing | Notes |
|--------|--------------|---------------|-------|
| us-east-1 | ✅ | ✅ | US primary |
| us-east-2 | ✅ | ✅ | |
| us-west-2 | ✅ | ✅ | |
| ca-central-1 | ✅ | ✅ | |
| eu-west-1 | ✅ | ✅ | EU primary |
| eu-west-2 | ✅ | ✅ | |
| eu-central-1 | ✅ | ✅ | |
| ap-northeast-1 | ✅ | ✅ | **Used in this project** |
| ap-northeast-2 | ✅ | ✅ | |
| ap-southeast-1 | ✅ | ✅ | |
| ap-southeast-2 | ✅ | ✅ | |
| ap-south-1 | ✅ | ✅ | |
| sa-east-1 | ✅ | ✅ | |

### Creating a Databricks Workspace

1. Log in to [Databricks Account Console](https://accounts.cloud.databricks.com/)
2. Navigate to **Workspaces** → **Create Workspace**
3. Select **Cloud**: AWS
4. Select **Region**: Same region as your FSx for ONTAP
5. Select **Pricing Tier**: Premium or above (required for Unity Catalog)
6. VPC configuration: Customer-managed VPC recommended (same VPC as FSx for ONTAP or peered)

---

## Multi-Region Design Patterns

### Pattern: SnapMirror + Regional Workspaces

For global enterprises with data and analytics across multiple regions:

```
┌─────────────────────┐    SnapMirror     ┌─────────────────────┐
│  ap-northeast-1     │ ───────────────▶ │  eu-central-1       │
│                     │                   │                     │
│  FSx for ONTAP      │                   │  FSx for ONTAP      │
│  + S3 AP            │                   │  + S3 AP            │
│  + Databricks WS    │                   │  + Databricks WS    │
│  (APAC team)        │                   │  (EMEA team)        │
└─────────────────────┘                   └─────────────────────┘
         │                                          │
         │              SnapMirror                   │
         └──────────────────┬───────────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  us-east-1          │
                 │                     │
                 │  FSx for ONTAP      │
                 │  + S3 AP            │
                 │  + Databricks WS    │
                 │  (AMERICAS team)    │
                 └─────────────────────┘
```

**Design Points:**
- Independent FSx for ONTAP + S3 AP + Databricks Workspace per region
- SnapMirror replicates required data between regions
- Each team accesses local region with low latency
- Global aggregation achieved via Delta Sharing

---

## Design Checklist

When deploying in a new region:

- [ ] Verify FSx for ONTAP is available in target region
- [ ] Verify analytics platform (Databricks/Snowflake/etc.) is available in same region
- [ ] Check data residency/compliance requirements
- [ ] VPC design: FSx for ONTAP and platform in same VPC or peerable
- [ ] Confirm S3 AP network origin requirement (VPC vs Internet)
- [ ] Set CloudFormation `--region` parameter to target region
- [ ] Set Terraform `aws_region` variable to target region
- [ ] If SnapMirror needed, select DR region

---

## Next Steps

- [Supported Regions](supported-regions.md) — Full region availability details
- [Architecture Overview](architecture.md) — Overall architecture
- [Getting Started](getting-started.md) — First deployment
