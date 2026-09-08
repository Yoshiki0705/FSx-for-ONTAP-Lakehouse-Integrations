🌐 **English** | [日本語](../ja/cross-repo-integration-strategy.md)

# Cross-Repository Integration Strategy: FSx for ONTAP Ecosystem

> **Status**: Initial version (2026-06-18). Post-DAIS 2026 + AWS Summit NYC 2026 landscape overview.
> **Purpose**: Clarify integration strategy across Yoshiki0705 public repositories and map remaining action items.

---

## Repository Landscape

```
Yoshiki0705 GitHub (public repositories)
│
├── fsxn-lakehouse-integrations (this repository)
│   ├── Lakehouse / Databricks integration patterns
│   ├── Manufacturing data platform PoC
│   ├── Iceberg metadata catalog
│   └── DAIS 2026 / Summit NYC analysis
│
├── FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
│   ├── 17 industry use cases
│   ├── FPolicy event-driven pipeline
│   ├── Capacity guardrails
│   └── Property-based testing
│
├── FSx-for-ONTAP-Agentic-Access-Aware-RAG
│   ├── Permission-aware RAG (CDK)
│   ├── Bedrock KB + S3 AP
│   ├── AD-integrated ACL
│   └── Agentic access control
│
├── ontap-edge-to-cloud-ai
│   ├── Edge device data aggregation
│   ├── ONTAP → AWS AI/Analytics
│   └── Cross-organizational utilization via S3 AP
│
└── fsxn-observability-integrations
    ├── EC2-free audit log shipping
    ├── Datadog / Splunk / Grafana etc.
    └── S3 AP + Lambda patterns
```

---

## Integration Matrix: Remaining P1/P2 Actions × Repositories

| Action | Primary Repository | Linked Repository | Detail |
|--------|-------------------|-------------------|--------|
| **P1: S3 Vectors × Permission-aware RAG** | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | This repo (reference) | ✅ **Already implemented**. `docs/s3-vectors-sid-architecture-guide.md` + CDK stack (`bin/demo-app.ts`) with S3 Vectors path already built. This repo references as comparison material |
| **P2: Bedrock Managed KB × Omnigent Polly** | This repository | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | Managed KB's Agentic Retriever coordinates with Omnigent Polly for multi-step retrieval + multi-agent quality pipeline |
| **P2: FSx for ONTAP official RAG tutorial** | `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | This repo (link) | Add link to official AWS documentation `docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html` |
| **P2: LTAP (Kafka → Lakebase) path integration** | `ontap-edge-to-cloud-ai` + this repo | Bidirectional | 🆕 **Under design review** (added 2026-06-18). Path D added on edge repo side. Connector spec publication + Lakehouse//RT GA are adoption gates |

---

## Integration Pattern Details

### 1. S3 Vectors × Permission-aware RAG (Already Implemented)

**Status**: ✅ Implemented in `FSx-for-ONTAP-Agentic-Access-Aware-RAG` repository

**Artifacts**:
- `docs/s3-vectors-sid-architecture-guide.md` (JA/EN, architecture guide)
- `bin/demo-app.ts` (CDK stack, includes S3 Vectors path)
- `stack-architecture-comparison.md` (OpenSearch Serverless vs S3 Vectors comparison)

**Background**: Amazon S3 Vectors reached GA (re:Invent 2025-12). 90% cost reduction vs dedicated vector DBs, 2 billion vectors/index, ap-northeast-1 available.

**Integration design**:

```
FSx for ONTAP (documents)
       │
       ▼ S3 Access Point
Bedrock Embedding Model
       │
       ▼
Amazon S3 Vectors
(vectors stored with ACL metadata)
       │
       ├── metadata: {owner, group, acl_hash, svm, volume, source_path}
       │
       ▼ Metadata-filtered search
Permission-aware Retrieval
       │
       ▼
Bedrock FM (response generation)
```

**Primary owner**: `FSx-for-ONTAP-Agentic-Access-Aware-RAG` — add S3 Vectors alternative path alongside existing OpenSearch Serverless

**This repo's role**: Add S3 Vectors as vector store candidate in manufacturing data platform "vector store selection" section with cost comparison

**OpenSearch Serverless vs S3 Vectors selection criteria**:

| Dimension | OpenSearch Serverless | S3 Vectors |
|-----------|----------------------|------------|
| Filtering | Complex metadata filters + boolean operations | Basic metadata filtering |
| Cost | OCU-based (minimum 2 OCU ≈ $700/month) | Storage + query (pay-per-use) |
| Scale | Large (billions of vectors) | 2B/index (GA) |
| Latency | 10-100ms | Sub-100ms |
| Bedrock KB integration | Native support | Managed KB support (to confirm) |
| Best for | Advanced filters, hybrid search, k-NN + BM25 | Cost-sensitive, simple ACL filters, large vector volumes |

### 2. Bedrock Managed KB × Omnigent Polly

**Background**: Bedrock Managed Knowledge Base (GA 2026-06-17) includes Agentic Retriever, integrated with AgentCore Gateway via MCP.

**Integration design**:

```
Omnigent (multi-agent orchestration)
       │
       ├── Polly (multi-agent coding)
       │
       ├── Quality Supervisor Agent
       │        │
       │        ▼
       │   Bedrock Managed KB (Agentic Retriever)
       │        │
       │        ├── S3 connector → FSx for ONTAP S3 AP
       │        ├── Smart Parsing (PDF/Office/tables)
       │        └── Multi-step retrieval
       │
       └── AgentCore Gateway (MCP)
                │
                ├── Unity AI Gateway (Databricks governance)
                └── AWS Context (discovery)
```

**Primary owner**: This repository (within Omnigent evaluation document)
**Linked**: Upgrade Bedrock KB pattern in `FSx-for-ONTAP-Agentic-Access-Aware-RAG` to Managed KB

### 3. FSx for ONTAP Official RAG Tutorial

**AWS official tutorial**: [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)

**repost.aws guide**: [Using FSx for ONTAP S3 Access Points as an Amazon Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w)

**Add to**:
- `FSx-for-ONTAP-Agentic-Access-Aware-RAG` README — add official links
- This repository's related documents — add reference links

---

## Edge → Cloud Integration: ontap-edge-to-cloud-ai Touchpoints

The `ontap-edge-to-cloud-ai` repository provides patterns for aggregating edge device data into ONTAP and connecting to AWS AI/Analytics via S3 AP. Integration with this repository's manufacturing data platform:

| This Repo Feature | ontap-edge-to-cloud-ai Counterpart |
|-------------------|-------------------------------------|
| Layer 1 edge data ingestion | Edge device → ONTAP aggregation patterns |
| Kafka → local ClickHouse | Edge-side streaming design |
| S3 AP → Bedrock/Athena | Aggregated data analytics path |
| AWS Context auto-catalog | Edge data automatic discovery |

### Databricks Integration Paths (edge-to-cloud-ai side)

> Sync source: `ontap-edge-to-cloud-ai/docs/en/databricks-integration.md` (updated 2026-06-18)

| Path | Route | Latency | Status |
|------|-------|---------|--------|
| A | Kafka → Structured Streaming → Delta | Seconds–minutes | ✅ Validated |
| B | S3 AP → Auto Loader → Delta | Minutes | ✅ Validated |
| C | ONTAP S3 → External Location → Unity Catalog | — | Designed |
| **D** | **Kafka → Lakebase (LTAP)** | **Milliseconds–seconds (estimated)** | **🆕 Under design review (added 2026-06-18)** |

> **Path A improvement (added 2026-06-18, updated 2026-06-20)**: Lakeflow Real-Time Mode (Spark Declarative Pipelines) is **GA (2025-12)**. Can reduce Path A's Structured Streaming latency (seconds–minutes) to ~5ms. This is an improvement to the existing Path A via a trigger-mode change, not a new path. Immediately applicable. See [Lakeflow Evaluation](#lakeflow-evaluation-zerobus-ingest--real-time-mode-dais-2026--synced-2026-06-18) below.

### Path D: Kafka → Lakebase (LTAP) — Details

**Sync status**: Under design review (added 2026-06-18). Added to `ontap-edge-to-cloud-ai` in `docs/en/databricks-integration.md` Section 2.5 and `.kiro/specs/edge-to-cloud-poc/design.md` Section 4.5.

**Data flow**:

```
Edge ONTAP
    │ Kafka Producer (v3 event schema)
    ▼
Kafka (MSK / Confluent)
    │
    ├── Path A: Structured Streaming → Delta (existing)
    │
    └── Path D: Kafka → Lakebase (LTAP) [future candidate]
              │
              ├── Operational DB + analytics unification
              ├── Real-time quality decision API
              └── Lakebase Search (vector + full-text)
```

**LTAP components** (evidence tier: **Public**, DAIS 2026-06-16):

| Component | Role | Status |
|---|---|---|
| Lakebase | Postgres-compatible operational DB | GA |
| Lakehouse//RT | Millisecond queries (Reyden engine) | Preview |
| Lakebase Search | Hybrid vector + full-text | Beta |

**Relationship with existing paths**: Path D is a **parallel option (alternative candidate), not a replacement** for Path A. Edge-side design (local ONTAP + Kafka topic design) is unchanged.

**Adoption gate conditions**:
1. Kafka → Lakebase connector documentation published
2. Lakehouse//RT reaches GA
3. Latency / Operational AI requirements materialize that existing Path A cannot satisfy

**Related documentation**: Detailed LTAP analysis in this repository is at [14_realtime_analytics_landscape.md](../../integrations/manufacturing-data-platform/docs/en/14_realtime_analytics_landscape.md), section "LTAP (Lake Transactional/Analytical Processing)".

### Lakeflow Evaluation: Zerobus Ingest / Real-Time Mode (DAIS 2026 — synced 2026-06-18)

> Sync source: `ontap-edge-to-cloud-ai/docs/en/databricks-integration.md` Section 2.6 (added 2026-06-18). Records the evaluation of the DAIS 2026 (2026-06-16) Lakeflow announcements in the context of the edge → cloud streaming design.

The Lakeflow-related features announced at DAIS 2026 were evaluated in the context of this ecosystem's streaming design (Paths A–D). All are positioned as **additional options to choose based on use case**, not replacements for the existing Kafka event bus design.

| Feature | Status | Position in this ecosystem |
|---------|--------|----------------------------|
| Zerobus Ingest | GA | **Additional option** for Databricks-only ingestion. Writes directly to Delta bypassing Kafka, but is not a Kafka replacement (see "Key Design Decisions" below) |
| Real-Time Mode (Spark Declarative Pipelines) | ✅ GA (2025-12) | **Path A latency improvement path**. May reduce Structured Streaming's seconds–minutes to ~5ms |
| Lakeflow Connect (100+ connectors) | GA (connector-dependent) | Managed connector suite. ONTAP/NFS direct connector availability to be confirmed |
| Agentic Data Engineering | Preview | Touchpoint of data quality × agents. Awaiting API availability |

#### Key Design Decisions

- **Kafka continues as a general-purpose event bus**: This ecosystem's Kafka fans out to multiple consumers (ClickHouse, Lambda, Databricks). Zerobus Ingest is an ingestion interface to a single Databricks sink and is not a replacement for the Kafka fan-out role. Zerobus is treated as "an additional route when a Databricks-only ingestion need materializes."
- **Real-Time Mode is a Path A improvement**: Real-Time Mode is not a new path but a latency improvement to the existing Path A (Kafka → Structured Streaming → Delta) via a trigger-mode change. **GA reached (2025-12)**. Immediately applicable when a Path A latency requirement materializes. It may cover some Path D (Lakebase/LTAP) use cases (millisecond latency).
- **No edge-side changes**: The Kafka Producer design (v3 event schema, topic design) is unchanged. The impact is limited to cloud-side reception/ingestion.
- **No on-premises support**: Lakeflow is a Databricks-managed feature with no on-premises/edge deployment option. Edge-layer real-time analytics (ClickHouse, etc.) remains necessary.

#### Path Relationship

```
Kafka (general event bus, multiple consumers)
 ├── Path A current (Structured Streaming, sec–min) ✅ Validated
 │     └── Path A improved (Real-Time Mode, ~5ms) ✅ GA (immediately applicable)
 ├── Path D future (Lakebase/LTAP, ms–sec) 🔄 Under design review
 └── (other consumers: ClickHouse, Lambda)

Zerobus Ingest → Delta direct (Kafka bypass, Databricks-only) 🆕 Under evaluation (GA)
```

#### Adoption Gate Conditions

| Feature | Gate condition |
|---------|----------------|
| Zerobus Ingest | A Databricks-only ingestion need materializes and a use case without Kafka fan-out is identified |
| Real-Time Mode | ~~Reaches GA~~ ✅ GA (2025-12). Immediately applicable when latency requirement materializes |
| Lakeflow Connect | ONTAP/NFS direct connector published |
| Agentic Data Engineering | API published + a data quality workflow use case identified |

> **How to choose (use-case-based)**: Use the Kafka event bus when general fan-out to multiple consumers is required; Zerobus Ingest for low-ops ingestion to a single Databricks sink; Real-Time Mode to reduce existing Path A latency — select per requirement. None are mutually exclusive; they can be combined.

> See also the DAIS 2026 note in [14_realtime_analytics_landscape.md](../../integrations/manufacturing-data-platform/docs/en/14_realtime_analytics_landscape.md). Note that Lakehouse//RT (query engine) and Real-Time Mode (Structured Streaming latency improvement) are distinct features.

### Cross-Repository Validation Items (LTAP Path)

| Validation Item | Description | Owner | Status |
|----------------|-------------|-------|--------|
| Kafka → Lakebase connector | Connector specification, configuration, Kafka topic → table mapping | edge repo + this repo | 🔲 Spec not published |
| Ordering guarantees | Whether Kafka **intra-partition** ordering is preserved in Lakebase writes (cross-partition ordering is not guaranteed by Kafka design — out of scope) | edge repo | 🔲 Not validated |
| Failure behavior | Kafka offset management on Lakebase write failure, retry, DLQ. Future design consideration: DLQ message replay procedure (timing, trigger, re-injection method) | edge repo | 🔲 Not validated |
| Schema compatibility | v3 event schema (JSON) → Lakebase table schema mapping | both repos | 🔲 Design pending |
| Write → query latency | Time from Lakebase write to query availability (including via Lakehouse//RT) | this repo | 🔲 After Lakehouse//RT Preview validation |
| ACL integration | Whether Lakebase tables can hold FSx for ONTAP-derived ACL metadata | this repo | 🔲 Design pending |
| Lakebase ap-northeast-1 availability | Confirm Lakebase GA is not region-limited; verify availability in ap-northeast-1 | this repo | ⚠️ **Not available confirmed** (2026-06-18) |
| Lakebase Private Link connectivity | Whether Private Link (port 5432) is available for Lakebase access from VPC (announced GA at DAIS 2026). Note: moot in ap-northeast-1 until Lakebase itself is available | this repo | ⚠️ Blocked by Lakebase region constraint |
| Zerobus Ingest alternative path | Whether Zerobus Ingest (Private Link supported) can write directly to Lakebase as Kafka alternative. Prerequisite: confirm whether external sources (MSK/Kafka Producer) can push to Zerobus Ingest endpoint | edge repo | 🔲 Spec confirmation pending |
| Real-Time Mode GA evaluation | Real-Time Mode (Spark Declarative Pipelines) **GA reached (2025-12)**. Path A latency improvement (sec–min → ~5ms) now evaluatable. Verify whether it applies to existing Path A via trigger-mode change alone, and whether it can cover some Path D (Lakebase/LTAP) use cases | edge repo + this repo | 🔄 GA confirmed, production validation pending |
| Zerobus Ingest SDK validation (gRPC/Python) | Validate Zerobus Ingest SDK (gRPC / Python) direct Delta writes. Confirm push method from external sources, throughput, Private Link route, and schema definition method | edge repo | 🔲 Awaiting SDK validation |

> ⚠️ **Validation Required**: The Kafka → Lakebase direct write path has no published connector specification. Do not make PoC adoption decisions until all validation items above are confirmed.

> ⚠️ **Region constraint confirmed (2026-06-18)**: Lakebase Autoscaling is **not available in ap-northeast-1 (Tokyo)** ([official docs](https://docs.databricks.com/en/resources/feature-region-support.html)). Available APAC regions: ap-south-1 (Mumbai), ap-southeast-1 (Singapore), ap-southeast-2 (Sydney). For Path D validation on an ap-northeast-1-based architecture, options are:
> 1. **Validate in a Lakebase-supported region** — PoC in us-east-1 or ap-southeast-1
> 2. **Wait for ap-northeast-1 support** — track Databricks region expansion
> 3. **Deprioritize Path D** — continue with existing Path A (Structured Streaming → Delta)
>
> Zerobus Ingest is available in ap-northeast-1. The Lakebase limitation affects the Zerobus → Lakebase path specifically. Zerobus → Delta (Structured Streaming) path works in ap-northeast-1.

**Future integration**: Validate LTAP (Kafka → Lakebase) path integrated with `ontap-edge-to-cloud-ai` edge → cloud flows. Re-evaluate at Lakehouse//RT GA.

---

## Observability Integration: fsxn-observability-integrations Touchpoints

`fsxn-observability-integrations` provides S3 AP + Lambda patterns for shipping audit logs to external SIEMs. Integration with this repository's agent security design:

| This Repo Requirement | fsxn-observability-integrations Counterpart |
|----------------------|---------------------------------------------|
| FPolicy audit log × agent access correlation | ⚠️ **Needs redesign**: [`docs/en/agent-fpolicy-correlation-pattern.md`](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/agent-fpolicy-correlation-pattern.md) (PR #22). When an agent reaches the data through an S3 access point, FPolicy receives no notification and the correlation does not hold (measured 2026-08-26). The input has to be replaced with the ONTAP native audit log |
| Omnigent tool call logging | OpenTelemetry → CloudWatch integration |
| Unity Catalog audit × ONTAP audit correlation | Time-axis join queries across both audit logs |

---

## Action Priority (Updated)

**Status legend**: ✅ Complete (implemented/designed) / 🔄 In progress (under design review) / 🔲 Not started (awaiting external dependency)

| Priority | Action | Owner | Status | Prerequisite |
|----------|--------|-------|--------|--------------|
| **P1** | S3 Vectors design pattern | Agentic-RAG repo | ✅ Implemented | `docs/s3-vectors-sid-architecture-guide.md` + CDK stack |
| **P2** | Managed KB × Omnigent integration design | This repository | ✅ Design complete | Added as Section 4 in `omnigent-multi-agent-evaluation.md` |
| **P2** | Official RAG tutorial links | Agentic-RAG repo + this repo | ✅ Both repos done | Agentic-RAG repo README "AWS Official Resources" section added |
| **P2** | LTAP integration design with ontap-edge-to-cloud-ai | This repo + edge repo | 🔄 Under design review | edge repo Path D added (2026-06-18). Awaiting Lakebase GA / connector spec |
| **P2** | Lakeflow Real-Time Mode / Zerobus Ingest evaluation | This repo + edge repo | 🔄 Real-Time Mode GA confirmed, validation pending | Real-Time Mode GA (2025-12). edge repo updated. Next gates: production latency validation / Zerobus Ingest SDK validation (gRPC/Python) |
| **P3** | AWS Context GA validation for FSx for ONTAP auto-catalog | This repository | 🔲 | Waiting for AWS Context GA |
| **P3** | Audit log integrated query patterns | observability repo | ✅ Design complete (PR #22) | Implementation after agent infrastructure build |

---

## References

- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
- [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG)
- [ontap-edge-to-cloud-ai](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai)
- [fsxn-observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations)
- [AWS: Build a RAG application with Bedrock KB + FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- [repost.aws: FSx for ONTAP S3 AP as Bedrock Data Source](https://repost.aws/articles/AReKa8-o8XRGeVW2Nicbg1_w)
- [Amazon S3 Vectors GA](https://aws.amazon.com/blogs/aws/amazon-s3-vectors-now-generally-available-with-increased-scale-and-performance/)
- [Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/)
- Related analysis in this repo: [S3 Annotations governance evaluation](./s3-annotations-governance-evaluation.md) (applying S3 Annotations/Metadata to the Databricks UC × FSx for ONTAP S3 AP challenge, 2026-06-18)
