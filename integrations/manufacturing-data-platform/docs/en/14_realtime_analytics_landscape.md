# Real-Time Analytics in a Hybrid Manufacturing Architecture: Positioning Guide

🌐 English | [日本語](../ja/14_realtime_analytics_landscape.md)

> Last updated: 2026-06-18
> Context: Databricks Data + AI Summit 2026 — LTAP Architecture / Lakehouse//RT / Lakebase announcements

---

## Background

At the Databricks Data + AI Summit (June 2026), Databricks made two interrelated major announcements:

1. **LTAP (Lake Transactional/Analytical Processing)** — A new architecture concept that unifies OLTP and OLAP on a single lake storage layer, declaring CDC pipelines "unnecessary."
2. **Lakehouse//RT** — A real-time query layer powered by the "Reyden" engine, enabling millisecond-level queries directly on Delta Lake / Iceberg tables.

LTAP is the **architectural philosophy**; Lakehouse//RT is the **query engine implementation**. Their relationship:

```
LTAP (concept: transactions + analytics = 1 copy)
 ├── Lakebase (transaction layer — Postgres-compatible)
 ├── Lakehouse//RT (real-time analytics layer — Reyden engine)
 └── Databricks SQL / Spark (batch/BI analytics layer)
```

This document evaluates how these announcements affect a hybrid manufacturing data platform that includes both on-premises real-time analytics (ClickHouse) and cloud-based governed analytics (Databricks).

---

## Architecture Context: Three-Layer Hybrid Platform

```
Layer 1: Edge/Factory (on-premises)
  Kafka → ClickHouse → Local dashboards, anomaly detection

Layer 2: Real-time cloud analytics
  Kafka (replicated) → ClickHouse Cloud or Lakehouse//RT → Operational dashboards

Layer 3: Governed AI and analytics
  Databricks → Unity Catalog → Delta/Iceberg → AI, BI, compliance
```

The question Lakehouse//RT raises: **Does Layer 2 still need a dedicated real-time database, or can Databricks now serve both Layer 2 and Layer 3?**

---

## LTAP: The End of Pipelines? — Architecture Impact Analysis

### What Is LTAP

LTAP (Lake Transactional/Analytical Processing) is a new architecture concept announced by Ali Ghodsi in the DAIS 2026 keynote (evidence tier: **Public**). It claims to resolve the 40-year-old OLTP/OLAP divide by unifying both on "a single copy of data in the lake."

| Characteristic | Traditional Architecture | LTAP |
|----------------|--------------------------|------|
| Data copies | Operational DB → CDC → Analytics DB (2+ copies) | 1 copy on the lake |
| Pipelines | ETL / CDC required | Unnecessary (Databricks claims) |
| Transactions | Dedicated OLTP DB (PostgreSQL, MySQL, etc.) | Lakebase (Postgres-compatible, on the lake) |
| Analytics queries | Dedicated OLAP DB / DWH | Lakehouse//RT (Reyden), Databricks SQL |
| Data freshness | CDC latency (seconds to minutes) | Real-time (same storage) |
| Governance | Distributed (per-DB) | Unified (Unity Catalog) |

**Databricks' claim**: CDC is "Continuous Data Corruption" — schema drift, ordering guarantee failures, and transaction boundary loss cause production incidents. LTAP eliminates these structurally.

### LTAP Components

| Component | Role | Status |
|-----------|------|--------|
| **Lakebase** | Postgres-compatible operational DB. Data stored as Delta/Iceberg on the lake | GA (AWS, Azure) |
| **Lakehouse//RT** | Millisecond queries via Reyden engine. Reads Delta/Iceberg directly | Preview |
| **Lakebase Search** | Hybrid vector + full-text search. `lakebase_vector` / `lakebase_text` Postgres extensions | Beta |
| **Lakebase branching / PITR** | DB branching. Agents can safely test destructive operations | GA |
| **Unity Catalog** | Cross-layer governance, lineage, and ACL | GA |

### Impact on the Manufacturing Data Platform

If LTAP fully matures, the **boundary between Layer 2 and Layer 3 disappears** in this PoC's three-layer architecture:

```
Traditional 3-layer model:
  Layer 1: Edge (Kafka + local ClickHouse)
  Layer 2: Cloud RT analytics (separate system) ←── LTAP absorbs this
  Layer 3: Governed AI/analytics (Databricks) ←── LTAP includes this

LTAP model (Databricks' vision):
  Layer 1: Edge (Kafka + local analytics) — unchanged
  Layer 2+3: Databricks LTAP
    ├── Lakebase: Transactional writes for quality inspection results
    ├── Lakehouse//RT: Operational dashboards (millisecond response)
    ├── Databricks SQL: BI / compliance reporting
    └── Unity Catalog: Governance for all data
```

### Three-Layer Model vs LTAP Model: Manufacturing Use Case Comparison

| Dimension | 3-Layer Model (CH + Databricks) | LTAP Model (Databricks unified) |
|-----------|--------------------------------|----------------------------------|
| Systems to manage | 3+ (Kafka, ClickHouse, Databricks) | 2 (Kafka, Databricks) |
| Pipeline complexity | CDC / Kafka Connector / sync logic required | Direct Lakebase write → immediate analytics |
| Governance | Self-built for CH side | Unified via Unity Catalog |
| Edge support | ✅ CH on-premises | ❌ Databricks is cloud-only |
| Sub-10ms latency | ✅ CH MergeTree | ❌ Reyden delivers 10-100ms |
| Network resilience | ✅ Local operation | ❌ Cloud connectivity required |
| AI agent integration | Built separately | Native (Agent Bricks, Genie One) |
| Operational write + immediate analytics | CH is analytics DB (writes handled elsewhere) | Lakebase write → Lakehouse//RT immediate query |
| Cost transparency | Fixed infrastructure cost | DBU billing (pay per use, but harder to predict) |
| Maturity | CH: 10+ years, extensive production track record | LTAP: announced 2026-06, Preview |

### What LTAP Changes / Does Not Change

#### Changes (cloud-side design decisions)

1. **ClickHouse Cloud positioning reconsidered**: The decision to adopt ClickHouse Cloud as a "real-time serving layer" in the cloud requires re-evaluation after Lakehouse//RT GA + pricing clarity
2. **CDC pipeline simplification**: The two-stage Kafka → ClickHouse → Databricks ingestion could become single-stage Kafka → Lakebase
3. **Easier agent integration**: Genie One / Agent Bricks access Lakebase data directly. Quality inspection agents can reason across both operational and analytical data

> **⚠️ Validation Required**:
> - **Ingestion mechanism unconfirmed**: The specific Kafka → Lakebase path is not yet validated. Candidates: Kafka Connect JDBC Sink / Lakeflow Streaming / Structured Streaming DLT. Recommended path requires Databricks documentation confirmation.
> - **Propagation latency unmeasured**: Lakebase write → Lakehouse//RT queryable delay is not benchmarked. Delta Lake's write-audit-publish protocol may introduce hundreds of milliseconds to seconds of delay, meaning "immediate query" may not be truly instantaneous.
> - **Edge → cloud failure mode**: If Kafka replication targets Lakebase direct writes, cloud outage data loss/replay design is needed. Define RPO using Kafka retention + replay controls.
> - **Ordering guarantees**: Whether Kafka partition ordering is maintained in Lakebase without CDC depends on the ingestion mechanism. Structured Streaming provides watermark-based ordering; JDBC sink may not guarantee order.

#### Does Not Change (edge/on-premises design)

1. **Edge real-time analytics**: LTAP has no on-premises option. Local analytics engines (ClickHouse, etc.) remain essential for immediate factory-floor decisions
2. **Network resilience**: Design for continued operation during cloud connectivity loss is outside LTAP's scope
3. **Sub-10ms alerting**: Equipment control feedback and immediate stop decisions may not fit Reyden's 10-100ms range
4. **FSx for ONTAP payload storage**: Storage of unstructured data (images, video, CAD) with multi-protocol access is orthogonal to LTAP. FSx for ONTAP continues in this role

### Lakebase × FSx for ONTAP Touchpoints

LTAP/Lakebase unifies structured/operational data, but touchpoints with FSx for ONTAP include:

| Pattern | Description |
|---------|-------------|
| **Metadata = Lakebase, Payload = FSx for ONTAP** | Quality inspection metadata (pass/fail, measurements, timestamps) written to Lakebase; corresponding images and log files stored on FSx for ONTAP. Lakebase records hold S3 AP URIs as links |
| **Document Intelligence + FSx for ONTAP** | Design documents and specifications on FSx for ONTAP parsed by Document Intelligence; results stored in Lakebase / Delta tables. Agents search via Lakebase Search |
| **Lakebase branching ≈ FlexClone (scope differs)** | Lakebase DB branching (agent sandbox) is conceptually analogous to FSx for ONTAP FlexClone (zero-copy fork). However, **scope differs significantly**: Lakebase branching operates on DB tables (structured data, GB–TB scale); FlexClone operates on entire volumes (including unstructured, TB–PB scale). Structured data uses Lakebase branching; unstructured data uses FlexClone for safe test environments |
| **SnapMirror read replicas** | Isolate agent read workloads from production FSx for ONTAP by creating SnapMirror read-only replicas. Agents read payloads via S3 AP on DP volumes without impacting production NFS/SMB workloads |
| **FabricPool capacity pool tiering** | Manufacturing payloads (images, video) accumulate significantly. Since agents primarily access recent data, older payloads auto-tier to capacity pool (S3 Standard-IA) via FabricPool, optimizing storage cost |

> **⚠️ Governance Gap**:
> - Unity Catalog governs Delta/Iceberg tables but **does NOT directly govern data at S3 AP URI destinations**. When an agent retrieves an S3 AP URI from a Lakebase record and reads the payload, Unity Catalog ACL does not control that payload read.
> - **Mitigation**: Application-layer authorization check required on S3 AP URI follow-through. Control via IAM policies + S3 AP access point policies + agent IAM role separation.
> - **Lakebase Search vector ACL**: Whether row-level security applies to vector search results when Document Intelligence extractions are stored in Lakebase Search is unconfirmed. A Permission-aware RAG chain design is needed (FSx for ONTAP ACL → extraction-time ACL metadata preservation → Lakebase table row filter → agent query-time filter).

> **⚠️ S3 AP Latency Consideration**:
> - Even with Lakehouse//RT providing millisecond queries, if agents follow-fetch payloads via S3 AP, ONTAP S3 protocol overhead adds latency. P99 latency measurement is needed.
> - Throughput limits for concurrent multi-agent payload reads via S3 AP also require validation.

### Decision Framework: When to Adopt LTAP

```
                          ┌──────────────────────┐
                          │ On-premises required? │
                          └────────┬─────────────┘
                                   │
                    Yes ┌──────────┴──────────┐ No
                        ▼                      ▼
              ┌─────────────────┐    ┌─────────────────────────┐
              │ Edge: dedicated  │    │ Cloud-only?              │
              │ RT engine        │    │ Databricks already in    │
              │ (ClickHouse etc) │    │ use?                     │
              └─────────┬───────┘    └──────────┬──────────────┘
                        │                       │
                        │              Yes ┌────┴────┐ No
                        │                  ▼         ▼
                        │    ┌──────────────────┐ ┌─────────────────┐
                        │    │ Consider LTAP     │ │ Choose based on  │
                        │    │ (Layer 2+3 merge) │ │ requirements     │
                        │    └──────────────────┘ └─────────────────┘
                        │
                        ▼
              ┌─────────────────────────────────┐
              │ Hybrid:                          │
              │ Edge = dedicated RT              │
              │ Cloud = LTAP (Lakehouse//RT +    │
              │         Lakebase) migration path │
              └─────────────────────────────────┘
```

### Maturity Considerations (as of 2026-06)

| Component | Status | Production Readiness Guidance |
|-----------|--------|------------------------------|
| Lakebase | GA | Testable. Verify Postgres compatibility scope |
| Lakehouse//RT (Reyden) | Preview | Recommend GA + 6 months stabilization |
| Lakebase Search | Beta | Re-evaluate after Preview |
| LTAP overall | Architectural declaration | Wait for individual component GAs |

**Recommendation**: Understand LTAP as an architecture vision and reflect its direction in design. However, for the current PoC phase, wait for Lakehouse//RT GA and pricing clarity before making concrete migration decisions. Edge-side design continues regardless of LTAP.

---

## Comparison: Dedicated Real-Time DB vs Lakehouse//RT

| Dimension | Dedicated RT DB (e.g., ClickHouse) | Lakehouse//RT (Databricks) |
|-----------|-----------------------------------|---------------------------|
| Deployment options | On-premises, cloud, hybrid | Cloud only (current) |
| Query latency | 1-50ms (tuned MergeTree) | 10-100ms (Reyden engine, preview) |
| Data format | Proprietary columnar | Open formats (Delta, Iceberg) |
| Governance integration | External (no built-in catalog) | Native (Unity Catalog, lineage, tags) |
| Ingestion latency | Sub-second (Kafka Engine) | Seconds to minutes (Structured Streaming) |
| Network resilience | Operates locally during outages | Requires cloud connectivity |
| Concurrency | Hundreds to thousands of concurrent queries | High (improved with Reyden) |
| Cost model | Infrastructure-based (no per-query markup) | DBU-based (compute time billing) |
| AI/ML integration | Separate pipeline needed | Native (MLflow, Feature Store, AI/BI) |

---

## When Lakehouse//RT Can Replace a Dedicated RT Engine

1. **All data is already in Databricks** — No separate ingestion path needed
2. **Cloud-only architecture** — No on-premises or edge requirements
3. **Governance is the primary concern** — Unity Catalog lineage and access control are non-negotiable
4. **10-100ms latency is acceptable** — Dashboard and BI use cases (not sub-10ms alerting)
5. **Unified platform preference** — Organization wants to minimize systems to manage

## When a Dedicated RT Engine Remains Necessary

1. **On-premises / edge deployment** — Factory floor, manufacturing line, disconnected environments
2. **Sub-10ms latency requirement** — Real-time alerting, anomaly detection, control system feedback
3. **Ultra-high-frequency ingestion** — Millions of events/second with sub-second visibility
4. **Network-resilient operation** — Must continue during cloud connectivity loss
5. **Cost-sensitive high-volume queries** — No per-query compute billing; fixed infrastructure cost
6. **Lightweight deployment** — No need for full Databricks platform for a single analytics use case

---

## Hybrid Architecture: Both Can Coexist

For manufacturing and industrial IoT use cases, the optimal architecture often uses **both**:

```
On-premises                              Cloud (AWS)
┌──────────────────────┐          ┌──────────────────────────┐
│ Sensors/PLCs/Cameras │          │                          │
│        │             │          │   Kafka (replicated)     │
│        ▼             │          │        │                 │
│ Kafka (local)        │─────────▶│        ▼                 │
│        │             │          │ Databricks Lakehouse//RT │
│        ▼             │          │ (governed, AI-ready,     │
│ ClickHouse (local)   │          │  millisecond queries)    │
│ - Anomaly detection  │          │                          │
│ - Quality dashboard  │          │ Unity Catalog governance │
│ - Sub-5ms alerting   │          │ AI/ML model training     │
│                      │          │ Cross-plant comparison   │
│ Payload Storage      │          │                          │
│ (ONTAP on-prem)      │─ ─ ─ ─ ─ │ FSx for ONTAP (cache)    │
└──────────────────────┘          └──────────────────────────┘
```

**Division of responsibility:**
- **Local ClickHouse**: Immediate operational analytics (line-stop decisions, quality alerts, OEE)
- **Lakehouse//RT / Databricks**: Cross-plant analysis, AI model serving, governed BI, compliance reporting

---

## Impact on This PoC

| PoC Component | Lakehouse//RT Impact | LTAP Impact | Action |
|---------------|---------------------|-------------|--------|
| On-premises ClickHouse (Phase B) | **No impact** — cloud only | **No impact** — no on-prem option | Continue as designed |
| ClickHouse Cloud (Phase A) | **Potential replacement** — if Databricks is already in use | **Absorption target** — Layer 2 merges into LTAP | Re-evaluate after GA |
| Kafka → ClickHouse pipeline | **Complementary** — CH for local RT, Databricks for governed analytics | **Simplification candidate** — Kafka → Lakebase direct path may eliminate CH Cloud | Keep both paths; decide after LTAP GA |
| Databricks Structured Streaming | **Enhanced** — streaming table latency may improve | **Unified** — streaming + operational + analytical on same base | Monitor GA performance |
| FSx for ONTAP payload storage | **No impact** — unstructured data out of scope | **Complementary** — structured=Lakebase, unstructured=FSx for ONTAP | Begin metadata link design |
| Multi-agent pipeline (Omnigent) | **Indirect** — better access to analytics data | **Direct** — Agent Bricks + Lakebase provide native agent integration | Add Lakebase path to Omnigent design |

### Recommendation

- **Phase A (AWS)**: Continue ClickHouse Cloud for real-time validation. Re-evaluate after Lakehouse//RT GA + pricing. **Based on the LTAP vision, design a parallel PoC path for Kafka → Lakebase direct writes** (Lakebase is GA but not in ap-northeast-1 — validate in us-east-1 or ap-southeast-1).
- **Phase B (On-premises)**: ClickHouse on-prem is unaffected. LTAP / Lakehouse//RT have no on-premises option.
- **Long-term**: Assume LTAP will unify Layer 2+3 in the cloud; design cloud-side architecture simplification path accordingly. Edge-side evolves independently.
- **FSx for ONTAP integration**: Validate Lakebase record ↔ FSx for ONTAP payload linking design (S3 AP URI as metadata column) early in Phase A.

> **Cross-repository link**: The `ONTAP-Edge-to-Cloud-AI` repository has added Path D (Kafka → Lakebase) as a design candidate (2026-06-18). See [Cross-Repository Integration Strategy](../../../../docs/en/cross-repo-integration-strategy.md), Edge → Cloud Integration section, for details.

> **DAIS 2026 additional information (2026-06-18)**:
> - **Lakeflow Zerobus Ingest**: New high-throughput event ingestion interface (GA). Private Link supported. Not a Kafka replacement — positioned as an **additional option** for Databricks-only ingestion. Evaluated in `ONTAP-Edge-to-Cloud-AI` (see [Lakeflow Evaluation in the Cross-Repository Integration Strategy](../../../../docs/en/cross-repo-integration-strategy.md#lakeflow-evaluation-zerobus-ingest--real-time-mode-dais-2026--synced-2026-06-18)). ([Lakeflow blog](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering))
> - **Lakeflow Real-Time Mode (Spark Declarative Pipelines)**: An execution mode that reduces Structured Streaming latency from seconds–minutes to ~5ms (**GA, 2025-12**). It improves the ingestion latency (seconds–minutes, Structured Streaming) shown in the "Dedicated RT DB vs Lakehouse//RT" comparison above. **Distinct from Lakehouse//RT (query engine)**; immediately applicable as a Path A improvement in `ONTAP-Edge-to-Cloud-AI`. ([Lakeflow blog](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering))
> - **Lakebase Private Link (GA)**: Private Link connectivity to Lakebase from VPC (port 5432) now available. Enables agent → Lakebase access without traversing public internet. ([Security blog](https://www.databricks.com/blog/whats-new-databricks-platform-security-and-compliance-data-ai-summit-2026))
> - **AIM (Automatic Identity Management) for Entra ID — GA on AWS**: Automates user/group identity sync to Databricks workspaces. May simplify ACL-based access control design by automatically reflecting group memberships that agents belong to.

> ⚠️ **Region constraint confirmed (2026-06-18)**: Per [official docs](https://docs.databricks.com/en/resources/feature-region-support.html), **Lakebase Autoscaling is not available in ap-northeast-1 (Tokyo)**. If this project targets ap-northeast-1, LTAP Path D (Kafka → Lakebase) validation requires one of:
> - Validate in a Lakebase-supported region (us-east-1 / ap-southeast-1 / ap-southeast-2) for tech validation only
> - Wait for ap-northeast-1 support (Databricks region expansion timeline unknown)
> - Continue with Path A (Kafka → Structured Streaming → Delta) and keep Path D as a long-term candidate
>
> Zerobus Ingest is available in ap-northeast-1, so the Zerobus → Delta (Structured Streaming) path is usable.

---

## Key Takeaways

1. **LTAP declares "the end of pipelines"** — an architecture vision to structurally eliminate OLTP/OLAP separation, CDC, and data copies
2. Lakehouse//RT is LTAP's query-layer implementation. A significant advancement for cloud real-time analytics within Databricks
3. It directly targets the "separate serving layer" pattern (ClickHouse, Druid, Pinot in cloud)
4. **Lakebase is LTAP's transaction layer**. Postgres-compatible, enabling operational writes + immediate analytics
5. Does NOT address on-premises, edge, or network-disconnected real-time analytics — edge layer remains necessary in hybrid manufacturing architectures
6. **FSx for ONTAP coexists orthogonally with LTAP as unstructured payload storage** — structured data = Lakebase, unstructured data = FSx for ONTAP
7. Agent integration (Agent Bricks / Genie One) natively accessing LTAP data affects Omnigent multi-agent design

---

## References

### AWS Official: FSx for ONTAP × Bedrock RAG

- [AWS Official Tutorial: Build a RAG application using Amazon Bedrock Knowledge Bases with FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) — Step-by-step guide for configuring FSx for ONTAP S3 AP as a Bedrock KB data source
- [repost.aws: Using FSx for ONTAP S3 Access Points as an Amazon Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w) — Community guide

### Databricks / DAIS 2026

- [Databricks: LTAP Press Release](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-ltap-first-lake-transactionalanalytical) (2026-06-16)
- [Databricks: Introducing Lakehouse//RT](https://www.databricks.com/blog/introducing-lakehousert-real-time-performance-unified-lakehouse) (2026-06-16)
- [Databricks: Lakehouse//RT Press Release](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-lakehousert-bring-real-time-analytics-directly) (2026-06-16)
- [Databricks: Lakebase Search (Beta)](https://www.databricks.com/blog/announcing-lakebase-search-agent-native-retrieval-built-lakebase-postgres) (2026-06-16)
- [Databricks: Agent Bricks DAIS 2026](https://www.databricks.com/blog/agent-bricks-dais-2026) (2026-06-16)
- [Databricks: What's new with Unity Catalog](https://www.databricks.com/blog/whats-new-unity-catalog-data-ai-summit-2026) (2026-06-16)
- [diginomica: Why Databricks calls CDC 'continuous data corruption'](https://diginomica.com/why-databricks-calls-cdc-continuous-data-corruption-and-what-it-built-instead) (2026-06-16)
- [Databricks: Lakeflow — A new era of agentic data engineering](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering) (2026-06-16)
- [Databricks: What's new in Platform Security and Compliance](https://www.databricks.com/blog/whats-new-databricks-platform-security-and-compliance-data-ai-summit-2026) (2026-06-17)
- [Databricks: AWS and Databricks at DAIS 2026](https://www.databricks.com/blog/aws-and-databricks-data-ai-summit-2026-accelerating-real-world-ai-innovation) (2026-06-09)
- [ClickHouse vs Databricks: Join Performance](https://clickhouse.com/blog/join-me-if-you-can-clickhouse-vs-databricks-snowflake-join-performance) (2025)
- [ClickHouse: Real-Time Analytics Platforms Comparison](https://clickhouse.com/resources/engineering/real-time-analytics-platforms-a-practical-comparison) (2025)
- This repo: [Kafka/ClickHouse → Unity Catalog connectivity (paths/ports — a perspective distinct from storage)](../../../../docs/en/kafka-clickhouse-unity-catalog-connectivity.md)
