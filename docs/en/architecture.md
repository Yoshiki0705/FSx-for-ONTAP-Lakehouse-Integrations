# Architecture Overview

## Amazon FSx for NetApp ONTAP (FSx for ONTAP) × S3 Access Points × Lakehouse Integration Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Account                                 │
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐  │
│  │  Lakehouse   │     │  S3 Access Point │     │  FSx for ONTAP  │  │
│  │  Platform    │────▶│  (VPC-scoped)    │────▶│  Volume (S3)    │  │
│  │              │◀────│                  │◀────│                 │  │
│  └──────────────┘     └──────────────────┘     └─────────────────┘  │
│        │                       │                        │           │
│        │                       │                        │           │
│  ┌─────▼──────┐         ┌──────▼─────┐          ┌───────▼────┐      │
│  │ Unity Cat. │         │ S3 AP      │          │ ONTAP      │      │
│  │ Ext Stage  │         │ Policy     │          │ Features   │      │
│  │ Ext Table  │         │ (IAM+VPC)  │          │ Dedup/Snap │      │
│  └────────────┘         └────────────┘          └────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Description

#### 1. FSx for ONTAP

Functions as the enterprise storage layer.

| Feature | Lakehouse Benefit |
|---------|-------------------|
| S3 Protocol | Direct access from lakehouse platforms |
| Deduplication | Storage reduction for similar datasets (dev/staging/prod) |
| Compression | Cost optimization via inline compression |
| Snapshot | Point-in-time table recovery |
| FlexClone | Instant dataset cloning for dev environments |
| FabricPool | Automatic S3 tiering for cold partitions |
| SnapMirror | Cross-region DR |

#### 2. S3 Access Points

Connection layer between FSx for ONTAP and lakehouse platforms.

**Key Roles:**
- Network-level access control via VPC restrictions
- Fine-grained permission management via IAM policies
- Per-platform access point isolation
- Data isolation via path (prefix) restrictions

**S3 API Compatibility:**

| API | Supported | Notes |
|-----|-----------|-------|
| GetObject | ✅ | Read queries |
| PutObject | ✅ | Table writes |
| DeleteObject | ✅ | Table maintenance |
| ListObjectsV2 | ✅ | Table discovery |
| HeadObject | ✅ | Metadata checks |
| CreateMultipartUpload | ✅ | Large file writes |
| GetBucketLocation | ⚠️ | Required by some platforms |

#### 3. Lakehouse Platforms

Each platform accesses FSx for ONTAP via S3 API.

---

## Architecture Patterns

### Pattern A: Read-Only Analytics

```
┌────────────┐    S3 GetObject     ┌─────────┐    NFS/S3   ┌──────────────┐
│ Databricks │──────────────────▶  │  S3 AP  │────────────▶│FSx for ONTAP │
│ Athena     │    ListObjectsV2    │ (read)  │             │   Volume     │
│ Snowflake  │◀──────────────────  │         │◀────────────│              │
└────────────┘                     └─────────┘             └──────────────┘
```

**Use Cases:**
- Analytics queries on existing NFS/SMB data on FSx for ONTAP
- ETL-free data exploration
- Ad-hoc analysis

**ONTAP Value:**
- Query existing data without copying
- Freeze analysis-time data with Snapshots

### Pattern B: Read-Write Managed Tables

```
┌────────────┐  Get/Put/Delete   ┌─────────┐             ┌──────────────┐
│ Databricks │◀────────────────▶ │  S3 AP  │◀──────────▶ │FSx for ONTAP │
│ (Delta)    │  Multipart Upload │ (r/w)   │             │   Volume     │
│ Snowflake  │                   │         │             │              │
│ (Iceberg)  │                   └─────────┘             └──────────────┘
└────────────┘
```

**Use Cases:**
- Delta Lake / Iceberg table storage on FSx for ONTAP
- ACID transaction-capable tables
- Time Travel + ONTAP Snapshot combination

**ONTAP Value:**
- Deduplication for Delta/Iceberg version files
- Snapshot for full table recovery
- FlexClone for dev table copies

### Pattern C: ETL Pipeline (Medallion Architecture)

```
┌──────────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐
│    Source    │─▶│  S3 AP  │─▶│  Glue/   │─▶│  S3 AP  │─▶│ FSx for ONTAP│
│    (Raw)     │  │  (read) │  │  EMR/    │  │  (write)│  │    (Gold)    │
│FSx for ONTAP │  │         │  │  Lambda  │  │         │  │    Volume    │
└──────────────┘  └─────────┘  └──────────┘  └─────────┘  └──────────────┘
     Raw             Bronze         Transform      Silver/Gold      Curated
```

**Use Cases:**
- Medallion architecture (Raw → Bronze → Silver → Gold)
- Data quality checks + transformation pipelines
- Scheduled ETL execution

**ONTAP Value:**
- Manage each layer as separate volumes
- Snapshot consistency across layers
- FabricPool auto-tiering for Bronze layer

### Pattern D: Data Sharing

```
┌──────────────┐  ┌─────────────┐   ┌────────────┐
│FSx for ONTAP │─▶│  S3 AP (A)  │──▶│ Consumer A │ (Databricks)
│    Volume    │  │  prefix=/a/ │   └────────────┘
│  (Producer)  │  └─────────────┘
│              │  ┌─────────────┐   ┌────────────┐
│              │─▶│  S3 AP (B)  │──▶│ Consumer B │ (Snowflake)
│              │  │  prefix=/b/ │   └────────────┘
└──────────────┘  └─────────────┘
```

**Use Cases:**
- Data mesh data product publishing
- Multi-tenant data sharing
- Partner data provisioning

**ONTAP Value:**
- FlexClone for per-consumer logical copies
- S3 AP policy for access control
- SnapMirror for cross-region sharing

---

## Network Architecture

### VPC-Internal Access (Recommended)

```
┌──────────────────────────────────────────────────────┐
│                       VPC                            │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌────────┐      │
│  │ Platform │──▶ │ VPC Endpoint │──▶ │ S3 AP  │      │
│  │ (Private │    │ (Interface)  │    │        │      │
│  │  Subnet) │    │ com.aws.s3   │    │        │      │
│  └──────────┘    └──────────────┘    └───┬────┘      │
│                                          │           │
│                                  ┌───────▼────────┐  │
│                                  │ FSx for ONTAP  │  │
│                                  │ (Private       │  │
│                                  │  Subnet)       │  │
│                                  └────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Security Layers

Defense in depth is built from five layers.

| Layer | Role |
|---|---|
| VPC Endpoint Policy | Allow access only from within the VPC |
| S3 Access Points Policy | IAM Principal + VPC conditions |
| IAM Role Policy | Principle of least privilege |
| ONTAP Export Policy | Volume-level access control |
| Security Group | Network-level filtering |

---

## Data Format Support

> **Important**: The table below shows S3 API-level format support. For FSx for ONTAP S3 Access Points, write operations for transactional formats (Delta Lake, Apache Hudi) are **Not Supported** due to the lack of atomic rename and conditional writes. See [Compatibility Matrix](compatibility-matrix.md) for verified platform × format × mode combinations.

| Format | Read | Write | Primary Use | FSx for ONTAP S3 AP Write |
|--------|------|-------|-------------|:---------------:|
| Parquet | ✅ | ✅ | Analytics queries (columnar) | ✅ Append |
| Apache Iceberg | ✅ | ⚠️ | ACID tables (vendor-neutral) | Experimental (external catalog) |
| Delta Lake | ✅ | Not supported | ACID tables (Databricks) | Not Supported (no atomic rename) |
| Apache Hudi | ✅ | Not supported | CDC + Upsert | Not Supported (no atomic rename) |
| CSV | ✅ | ✅ | Legacy data ingestion | ✅ Append |
| JSON / NDJSON | ✅ | ✅ | Semi-structured data | ✅ Append |
| ORC | ✅ | ✅ | Hive compatible | ✅ Append |
| Avro | ✅ | ✅ | Schema evolution | ✅ Append |

---

## Next Steps

- [Getting Started](getting-started.md) — First deployment
- S3 AP fundamentals — S3 Access Points × FSx for ONTAP details
- [Vendor Comparison](vendor-comparison.md) — Platform selection guide
- data formats — Per-format recommended configurations
