🌐 **English** | [日本語](../ja/kafka-clickhouse-unity-catalog-connectivity.md)

> 📖 **Comprehensive guide**: For a full overview of all FSx for ONTAP → Databricks UC connection paths, see the [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md). This document focuses on streaming/catalog connectivity technical details.

# Connecting Kafka / ClickHouse to Databricks Unity Catalog: a connectivity, path, and port perspective

> **Status**: Initial version (2026-06-18). Based on public documentation.
> **Evidence tier**: claims are **Public** (confirmed in official docs) unless marked **Hypothesis** (unverified).
> **Framing**: a perspective **distinct from storage protocols (SMB/NFS/S3 API)** — connectivity (streaming / catalog / wire protocols). Right-tool-for-the-job, no vendor-versus wording.
> **Note**: no individual or company names (external reviewers) are recorded (role descriptions only).

---

## 0. Why a different perspective: data-at-rest vs data-in-motion

Prior evaluations were **storage-centric** (FSx for ONTAP SMB/NFS/S3 AP) = file/object access to **data-at-rest**. Architectures including Kafka / ClickHouse must be understood through a **connectivity perspective** = **data-in-motion + metadata/query protocols**.

| Aspect | Storage perspective (existing) | Connectivity perspective (this doc) |
|--------|-------------------------------|-------------------------------------|
| Target | Data-at-rest (files/objects) | Data-in-motion + metadata/query |
| Protocols | SMB / NFS / S3 API | Kafka (streaming) / Iceberg REST·Unity REST (catalog) / native TCP·JDBC (query) |
| Ports | 445(SMB) / 2049(NFS) / 443(S3) | 9094–9098(Kafka) / 443(REST) / 9000·9440(ClickHouse native) |
| Touchpoint with UC | External Location (S3 AP unsupported, see other doc) | **Streaming ingest** (Kafka→UC Delta) / **catalog exposure** (UC Iceberg REST→external engines) |
| Enforcement point | ONTAP ACL + IAM (FPolicy covers only the NFS / SMB path and does not block operations through an S3 access point) | UC (table / service credential) + credential vending |

> Related: for the storage perspective see [S3 Annotations evaluation](./s3-annotations-governance-evaluation.md) and [zero-copy media governance](./zero-copy-media-governance.md).

---

## 1. Kafka → Databricks Unity Catalog (ingestion)

### Connection method (Public)

Databricks **Structured Streaming / Lakeflow Declarative Pipelines** read Kafka as a source and write to **UC-managed Delta tables**. The Databricks Kafka connector is built on the Apache Spark Kafka connector; `kafka.*` options pass through ([Connect to Apache Kafka](https://docs.databricks.com/aws/en/connect/streaming/kafka)).

- **Two touchpoints with UC**:
  1. **Destination table**: the target Delta table is governed by UC (tags/permissions/lineage).
  2. **Connection auth**: **since DBR 16.1, MSK authentication can use UC service credentials** (recommended, especially on shared/serverless compute) ([Kafka authentication](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)).

> **Streaming semantics**: store the checkpoint (offset management) on durable storage (cloud storage / a UC volume). Default is **at-least-once**; absorb duplicates with **idempotent writes** on the destination (Delta MERGE / event-ID dedup). Ordering is guaranteed only **within a Kafka partition** (important for connected-vehicle telemetry).

### Communication path (network)

```
[Databricks compute]                                [Amazon MSK / Kafka]
  classic (customer VPC) ── VPC Peering / Transit Gateway ──▶ brokers
  serverless ──────────── PrivateLink / NCC (Network Connectivity Config) ─▶ brokers
        │                                                       │
        └─ read (Structured Streaming) ───────────────────────┘
        ▼
[UC-managed Delta table]  ← governed by UC
```

### Ports / auth (MSK)

| Access type | TLS | SASL/SCRAM | IAM |
|-------------|-----|-----------|-----|
| Within AWS (private) | **9094** | **9096** | **9098** (IPv6: 20098) |
| Public access | **9194** | **9196** | **9198** |

([MSK Port information](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html). Plaintext 9092 is VPC-internal only and discouraged.)

- **Auth methods**: UC service credentials (DBR 16.1+, recommended) / IAM (SigV4) / SASL-SCRAM / mTLS.
- **Recommendation**: private path (PrivateLink/NCC or VPC peering) + TLS/IAM. Minimize opening public ports.

---

## 2. ClickHouse ↔ Databricks Unity Catalog (catalog integration / query)

### Connection method (ClickHouse → UC, supported & recommended) (Public)

ClickHouse's **`DataLakeCatalog` database engine** (`type: unity` (Delta) / `rest` (Iceberg), **Beta**) connects **directly to Databricks Unity Catalog** and reads UC tables as Delta / Iceberg ([ClickHouse: Unity Catalog](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog), [DataLakeCatalog](https://clickhouse.com/docs/engines/database-engines/datalakecatalog)). The whole catalog appears as one ClickHouse database, queryable with ClickHouse SQL.

On the UC side, open APIs + credential vending are provided for external engines:
- **Iceberg REST catalog**: endpoint `/api/2.1/unity-catalog/iceberg-rest` ([Iceberg clients](https://docs.databricks.com/aws/en/external-access/iceberg.html))
- **Unity REST API** (Delta clients) ([Delta clients](https://docs.databricks.com/external-access/unity-rest.html))
- **Credential vending**: issues temporary credentials that inherit UC privileges to external engines (used by Trino / DuckDB / StarRocks / Dremio / Spark, etc.) ([Secure External Access via Open APIs](https://www.databricks.com/blog/secure-external-access-unity-catalog-assets-open-apis))

> **ClickHouse Cloud vs self-managed**: `DataLakeCatalog` is a ClickHouse Cloud-centric feature. ClickHouse Cloud → UC/S3 is SaaS egress (verify PrivateLink options). For self-managed (EC2/on-prem), design outbound 443 from your own VPC + S3 endpoints.

#### Access patterns by UC object type (Public)

| UC object | Format | External access |
|---|---|---|
| Managed table | Delta / Iceberg | Unity REST / Iceberg REST / Delta Sharing |
| External table | Delta | above + cloud URIs |
| Foreign table (federation) | Delta / Iceberg | Iceberg REST (**Preview**) / Delta Sharing |

> External engines fetch a **point-in-time metadata** snapshot. Fresh reads on foreign tables require **periodic metadata refresh (Lakeflow jobs)** ([Access Databricks data using external systems](https://docs.gcp.databricks.com/external-access/index.html)).

### Communication path (network)

```
[ClickHouse (connects outbound as a client)]
   │ ① fetch metadata + credential vending
   │    HTTPS 443 → Databricks workspace (/api/2.1/unity-catalog/iceberg-rest)
   │ ② read data
   │    HTTPS 443 → Amazon S3 (inherits UC privileges via vended credentials)
   ▼
[Query UC tables with ClickHouse SQL]

(Ports to connect TO ClickHouse: see §4. The connection to UC is ClickHouse's outbound 443.)
```

### An important directional distinction (easy to conflate)

| Direction | Description | Status |
|-----------|-------------|--------|
| **UC = Iceberg REST server → ClickHouse/Trino/Spark read** | UC exposes the catalog and external engines consume it (credential vending) | ✅ **Supported** (consistent with [S3 Annotations doc](./s3-annotations-governance-evaluation.md)) |
| **UC consumes AWS S3 Tables via an `iceberg_rest` connection** | UC ingests external Iceberg (reverse direction) | ❌ **Blocked** (this repo's iceberg-metadata-catalog Phase 4) |

→ "ClickHouse reads UC" is **supported**. "UC reads S3 Tables" is blocked, and **the two are opposite directions / different things**.

### Databricks → ClickHouse (reverse)

- UC **Lakehouse Federation** has **no official ClickHouse connector at the time of research** (supported: MySQL/PostgreSQL/SQL Server/Snowflake/Redshift/BigQuery, etc.).
- Because ClickHouse exposes **MySQL-compatible (9004) / PostgreSQL-compatible (9005)** wire interfaces, referencing it via UC's MySQL/PG federation connector is theoretically possible but **unverified (Hypothesis)**. Mind SQL dialect / type-conversion differences.

---

## 3. Kafka as a "shared bus" (no direct connection)

In the manufacturing data-platform 3-layer design, ClickHouse and Databricks consume **independently via Kafka** and do not connect to each other directly.

```
                ┌──▶ ClickHouse (on-prem/cloud, real-time OLAP)
Kafka (shared bus)─┤
                └──▶ Databricks (Structured Streaming → UC-managed Delta) ── UC governance
```

- Both are independent Kafka consumer groups. **No direct ClickHouse↔Databricks connection is needed.**
- UC governs the Delta tables on the Databricks side; the ClickHouse side is controlled on the ONTAP/ClickHouse side.
- Only when needed, use the §2 "ClickHouse → UC" integration to read Databricks-side data from ClickHouse.

---

## 4. Consolidated ports / protocols

| Component | Protocol | Port | Purpose | Encryption |
|-----------|----------|------|---------|-----------|
| Kafka (MSK, private) | TLS / SASL_SSL / IAM | 9094 / 9096 / 9098 | Databricks ingest | TLS |
| Kafka (MSK, public) | TLS / SASL_SSL / IAM | 9194 / 9196 / 9198 | Public path (minimize) | TLS |
| Databricks UC REST | HTTPS (Iceberg REST / Unity REST) | 443 | External-engine catalog/credentials | TLS |
| Amazon S3 (data) | HTTPS | 443 | Data read via vended credentials | TLS |
| ClickHouse native | TCP | 9000 / **9440 (TLS)** | ClickHouse client/distributed | TLS on 9440 |
| ClickHouse HTTP | HTTP / HTTPS | 8123 / **8443 (TLS)** | REST-style access | TLS on 8443 |
| ClickHouse MySQL-compat | MySQL wire | 9004 | Compatible clients (UC reverse unverified) | config-dependent |
| ClickHouse PostgreSQL-compat | PG wire | 9005 | Compatible clients (UC reverse unverified) | config-dependent |

(Sources: [MSK port-info](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html), [ClickHouse network ports](https://clickhouse.com/docs/guides/sre/network-ports))

---

## 5. Security considerations

- **Prefer private connectivity**: Kafka on private ports (9094/9096/9098) + PrivateLink/NCC/VPC peering. Minimize opening public ports (919x).
- **Consolidate auth**: govern Kafka auth via **UC service credentials** (DBR 16.1+). External-engine (ClickHouse) access via **credential vending** inherits UC privileges (avoids distributing static credentials).
- **TLS required**: ClickHouse uses 9440 / 8443 (plaintext 9000 / 8123 internal-only).
- **Least privilege**: minimize UC table/catalog grants; scope credential-vending grants tightly.
- **Auditing**: correlate Kafka ingest (UC lineage) with external-engine access (UC audit logs).
- **Storage-layer compensating controls (the other perspective)**: the ONTAP file-level ACL remains effective. **FPolicy, however, does not see operations through an S3 access point and does not block them even under a `mandatory` policy** (measured 2026-08-26, ONTAP 9.18.1P3D1). A compensating control on the access point path has to sit on the S3 side (access point policy, IAM); for detection only, the ONTAP audit log or ARP (see [S3 Annotations doc §2](./s3-annotations-governance-evaluation.md), [the measured FPolicy / S3 access point coverage](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/s3ap-monitoring-coverage-implications.md)).
- **Concrete network controls**: Databricks serverless fixes egress via **NCC (Network Connectivity Config)** (stable IPs / PrivateLink), allowed on the MSK broker security group. ClickHouse → S3 should use an **S3 gateway/interface VPC endpoint** where possible. SG direction: **the MSK broker SG allows inbound from Databricks (9094, etc.)**, **ClickHouse allows outbound 443 (Databricks workspace / S3)**.
- **Credential-vending operations**: vended credentials are **TTL- and scope-bound** temporary credentials; external-engine reads are recorded in UC audit. **Distinguish the two UC mechanisms**: (a) **UC service credentials** = auth for Databricks itself connecting outward (e.g., Kafka); (b) **credential vending** = external engines (e.g., ClickHouse) inheriting UC privileges to read data.
- **Prerequisite: enable external data access**: credential vending / external-engine UC access requires **enabling "external data access"** at the metastore/workspace level ([External data access for pipelines](https://docs.databricks.com/aws/en/external-access/external-for-pipelines)); otherwise connections from ClickHouse, etc., are rejected.

---

## 6. Selection guide (use-case-based / right-tool-for-the-job)

| Goal | Connection method | Note |
|------|-------------------|------|
| Land Kafka events under UC governance | Kafka → Structured Streaming/Lakeflow → UC Delta | UC service credentials recommended |
| Read Databricks/UC data from ClickHouse | ClickHouse `DataLakeCatalog` (unity/rest) → UC Iceberg REST + credential vending | Beta; reads are version/config-dependent |
| Loosely couple ClickHouse and Databricks | Kafka shared bus (independent consumption) | No direct connection; 3-layer pattern |
| Reference ClickHouse from Databricks | (no official connector) via MySQL/PG-compat is unverified | Hypothesis; needs validation |

---

## References

- [Databricks: Connect to Apache Kafka](https://docs.databricks.com/aws/en/connect/streaming/kafka)
- [Databricks: Kafka authentication (UC service credentials, MSK)](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)
- [Databricks: Access Databricks tables from Apache Iceberg clients (Iceberg REST)](https://docs.databricks.com/aws/en/external-access/iceberg.html)
- [Databricks: Read Databricks tables from Delta clients (Unity REST)](https://docs.databricks.com/external-access/unity-rest.html)
- [Databricks: Secure External Access to Unity Catalog via Open APIs (credential vending)](https://www.databricks.com/blog/secure-external-access-unity-catalog-assets-open-apis)
- [ClickHouse: DataLakeCatalog engine](https://clickhouse.com/docs/engines/database-engines/datalakecatalog)
- [ClickHouse: Unity Catalog integration](https://clickhouse.com/docs/use-cases/data-lake/unity-catalog)
- [ClickHouse: network ports](https://clickhouse.com/docs/guides/sre/network-ports)
- [Amazon MSK: Port information](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)
- This repo: [S3 Annotations evaluation](./s3-annotations-governance-evaluation.md) / [Real-time analytics landscape](../../integrations/manufacturing-data-platform/docs/en/14_realtime_analytics_landscape.md)
- Live verification plan: [Verification phase plan (ClickHouse→UC Beta / NCC·SG·endpoints)](./verification-plan-clickhouse-uc-connectivity.md)

> Source descriptions are paraphrased/summarized for licensing compliance.

