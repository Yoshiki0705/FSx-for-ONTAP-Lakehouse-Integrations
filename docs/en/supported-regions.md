# Supported Regions

[日本語](../ja/supported-regions.md)

## Overview

Amazon FSx for NetApp ONTAP (FSx for ONTAP) and S3 Access Points are available in most AWS regions.
When planning your deployment, consider the availability of both FSx for ONTAP and your target
analytics platform in the same region.

---

## FSx for ONTAP Region Availability

FSx for ONTAP is available in the following AWS regions:

### Americas

| Region | Region Code | Availability |
|--------|-------------|--------------|
| US East (N. Virginia) | us-east-1 | ✅ |
| US East (Ohio) | us-east-2 | ✅ |
| US West (N. California) | us-west-1 | ✅ |
| US West (Oregon) | us-west-2 | ✅ |
| Canada (Central) | ca-central-1 | ✅ |
| Canada West (Calgary) | ca-west-1 | ✅ |
| South America (São Paulo) | sa-east-1 | ✅ |

### Europe

| Region | Region Code | Availability |
|--------|-------------|--------------|
| Europe (Ireland) | eu-west-1 | ✅ |
| Europe (London) | eu-west-2 | ✅ |
| Europe (Paris) | eu-west-3 | ✅ |
| Europe (Frankfurt) | eu-central-1 | ✅ |
| Europe (Stockholm) | eu-north-1 | ✅ |
| Europe (Milan) | eu-south-1 | ✅ |
| Europe (Zurich) | eu-central-2 | ✅ |

### Asia Pacific

| Region | Region Code | Availability |
|--------|-------------|--------------|
| Asia Pacific (Tokyo) | ap-northeast-1 | ✅ |
| Asia Pacific (Seoul) | ap-northeast-2 | ✅ |
| Asia Pacific (Osaka) | ap-northeast-3 | ✅ |
| Asia Pacific (Singapore) | ap-southeast-1 | ✅ |
| Asia Pacific (Sydney) | ap-southeast-2 | ✅ |
| Asia Pacific (Mumbai) | ap-south-1 | ✅ |
| Asia Pacific (Jakarta) | ap-southeast-3 | ✅ |

### Other

| Region | Region Code | Availability |
|--------|-------------|--------------|
| Middle East (Bahrain) | me-south-1 | ✅ |
| Africa (Cape Town) | af-south-1 | ✅ |
| Israel (Tel Aviv) | il-central-1 | ✅ |

> **Note:** Region availability is subject to change. Check the
> [AWS Regional Services List](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/)
> for the latest information.

---

## S3 Access Points Availability

S3 Access Points are available in **all AWS regions** where Amazon S3 is available.
Since S3 is available in every commercial AWS region, S3 Access Points do not impose
additional regional constraints.

### S3 Access Points on FSx for ONTAP

S3 Access Points for FSx for ONTAP are available wherever FSx for ONTAP is available.
The S3 Access Point must be created in the same region as the FSx for ONTAP file system.

---

## Vendor Platform Region Availability

### Databricks on AWS

Databricks is available in the following AWS regions:

| Region | Region Code | Unity Catalog | Notes |
|--------|-------------|---------------|-------|
| US East (N. Virginia) | us-east-1 | ✅ | Primary US region |
| US East (Ohio) | us-east-2 | ✅ | |
| US West (Oregon) | us-west-2 | ✅ | |
| Canada (Central) | ca-central-1 | ✅ | |
| Europe (Ireland) | eu-west-1 | ✅ | Primary EU region |
| Europe (London) | eu-west-2 | ✅ | |
| Europe (Frankfurt) | eu-central-1 | ✅ | |
| Asia Pacific (Tokyo) | ap-northeast-1 | ✅ | |
| Asia Pacific (Seoul) | ap-northeast-2 | ✅ | |
| Asia Pacific (Singapore) | ap-southeast-1 | ✅ | |
| Asia Pacific (Sydney) | ap-southeast-2 | ✅ | |
| Asia Pacific (Mumbai) | ap-south-1 | ✅ | |
| South America (São Paulo) | sa-east-1 | ✅ | |

> **Requirement:** FSx for ONTAP and Databricks workspace must be in the same region
> for VPC-scoped S3 Access Point connectivity.

### Snowflake on AWS

Snowflake is available in the following AWS regions:

| Region | Region Code | Iceberg Tables | Notes |
|--------|-------------|----------------|-------|
| US East (N. Virginia) | us-east-1 | ✅ | |
| US East (Ohio) | us-east-2 | ✅ | |
| US West (Oregon) | us-west-2 | ✅ | |
| Canada (Central) | ca-central-1 | ✅ | |
| Europe (Ireland) | eu-west-1 | ✅ | |
| Europe (London) | eu-west-2 | ✅ | |
| Europe (Frankfurt) | eu-central-1 | ✅ | |
| Asia Pacific (Tokyo) | ap-northeast-1 | ✅ | |
| Asia Pacific (Seoul) | ap-northeast-2 | ✅ | |
| Asia Pacific (Singapore) | ap-southeast-1 | ✅ | |
| Asia Pacific (Sydney) | ap-southeast-2 | ✅ | |
| Asia Pacific (Mumbai) | ap-south-1 | ✅ | |

> **Note:** Snowflake uses internet network origin for S3 Access Points.
> Cross-region access is technically possible but not recommended due to latency and data transfer costs.

### AWS Native Services (Athena, Glue, Redshift Spectrum)

AWS native analytics services are available in all regions where FSx for ONTAP is available.
No additional region constraints apply.

| Service | Network Origin | Same-Region Required |
|---------|---------------|---------------------|
| Athena | Internet | Yes (for performance) |
| Glue | Internet | Yes |
| Redshift Spectrum | Internet | Yes |
| EMR | VPC | Yes |
| Lambda | VPC | Yes |

---

## Region Selection Considerations

### Primary Factors

1. **Data Residency / Compliance**
   - Regulatory requirements (GDPR, HIPAA, FISC, etc.)
   - Data sovereignty laws
   - Industry-specific compliance

2. **Latency**
   - Proximity to end users and data producers
   - Cross-service communication latency
   - FSx for ONTAP and analytics platform should be co-located

3. **Service Availability**
   - Ensure FSx for ONTAP + target platform are both available
   - Check for feature parity across regions

4. **Cost**
   - Regional pricing differences for FSx for ONTAP
   - Data transfer costs (cross-region is expensive)
   - Analytics platform pricing by region

### Vendor-Specific Considerations

| Vendor | Key Consideration |
|--------|-------------------|
| **Databricks** | Workspace and FSx for ONTAP must be in same region (VPC-scoped AP) |
| **Snowflake** | Account region should match FSx for ONTAP region for optimal latency |
| **Athena** | Same region required; internet network origin AP needed |
| **Glue** | Same region required; internet network origin AP needed |
| **EMR** | Same VPC or peered VPC; VPC-scoped AP supported |

---

## Multi-Region Architecture Patterns

### Pattern 1: SnapMirror for Cross-Region DR

```
┌─────────────────────┐         SnapMirror          ┌─────────────────────┐
│  Primary Region     │ ──────────────────────────▶ │  DR Region          │
│  (ap-northeast-1)   │                             │  (us-west-2)        │
│                     │                             │                     │
│  FSx for ONTAP      │         Async/Sync          │  FSx for ONTAP      │
│  + S3 AP            │         Replication         │  + S3 AP            │
│  + Databricks       │                             │  + Databricks       │
└─────────────────────┘                             └─────────────────────┘
```

**Use Cases:**
- Disaster recovery with RPO < 15 minutes (async) or RPO = 0 (sync)
- Read replicas for analytics in secondary region
- Regulatory compliance requiring data copies in specific regions

### Pattern 2: SnapMirror for Data Distribution

```
                    ┌─────────────────────┐
                    │  Source Region      │
                    │  FSx for ONTAP      │
                    │  (Data Producer)    │
                    └──────────┬──────────┘
                               │ SnapMirror
                    ┌──────────┼──────────┐
                    │          │          │
                    ▼          ▼          ▼
          ┌─────────────┐ ┌─────────┐ ┌─────────────┐
          │ Region A    │ │Region B │ │ Region C    │
          │ Databricks  │ │Snowflake│ │ Athena      │
          │ (Analytics) │ │(Sharing)│ │ (Ad-hoc)    │
          └─────────────┘ └─────────┘ └─────────────┘
```

**Use Cases:**
- Global data mesh with regional consumers
- Multi-region analytics with local data copies
- Compliance-driven data distribution

### Pattern 3: Active-Active Multi-Region

```
┌─────────────────────┐                             ┌─────────────────────┐
│  Region A           │ ◀── SnapMirror (bidirectional) ──▶ │  Region B    │
│                     │                             │                     │
│  FSx for ONTAP      │                             │  FSx for ONTAP      │
│  Volume: /sales-a/  │                             │  Volume: /sales-b/  │
│  + S3 AP            │                             │  + S3 AP            │
│  + Lakehouse        │                             │  + Lakehouse        │
└─────────────────────┘                             └─────────────────────┘
```

**Use Cases:**
- Regional data partitioning (each region owns its data)
- Global aggregation queries across regions
- Low-latency local writes with global reads

### SnapMirror Configuration Considerations

| Factor | Async SnapMirror | Sync SnapMirror |
|--------|-----------------|-----------------|
| RPO | Minutes (schedule-based) | Zero (synchronous) |
| Distance | Any (cross-region) | Limited (same region or nearby) |
| Performance impact | Minimal | Moderate (write latency) |
| Use case | DR, distribution | Zero data loss requirement |
| Cost | Data transfer charges | Higher throughput needed |

---

## Recommendations

### For New Deployments

1. Choose a region where both FSx for ONTAP and your primary analytics platform are available
2. Prefer regions with the broadest service availability (us-east-1, eu-west-1, ap-northeast-1)
3. Consider data residency requirements first, then optimize for latency and cost

### For Multi-Region Deployments

1. Use SnapMirror for cross-region data replication
2. Deploy S3 Access Points in each region (they cannot span regions)
3. Consider FlexClone for read-only replicas within the same region
4. Plan for data transfer costs between regions

---

## Next Steps

- [Architecture Overview](architecture.md)
- [Getting Started](getting-started.md)
- [Vendor Comparison](vendor-comparison.md)
