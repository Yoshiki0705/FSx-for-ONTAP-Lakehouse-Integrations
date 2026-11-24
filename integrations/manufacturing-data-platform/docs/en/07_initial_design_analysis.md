# 07: Initial Architecture Design Analysis

🌐 **English** | [日本語](../ja/07_initial_design_analysis.md)

> This document analyses the manufacturing data platform PoC concept against five design concerns as defined in [00_project_overview](00_project_overview.md) and [01_requirements](01_requirements.md).

> Each numbered section below covers one design concern, using a checklist derived from AWS Well-Architected and industry practice. This is a structured self-review of our own design — not an interview, survey, or review by external experts.

---

## Analysis Summary

### Scope

- **Analysis date**: 2026-06-07
- **Documents analysed**: OVR-000 (Project Overview), REQ-F001–F007, REQ-N001–N007, references.md, glossary
- **Scope**: Full architecture concept — edge ingestion, streaming, real-time analytics, payload storage, governed lakehouse, public repository readiness
- **Evidence Classification**: Each finding is tagged as `[Confirmed]`, `[Assumption]`, `[Hypothesis]`, or `[Open Question]`

---

## 1. Architecture Soundness

### Strengths

1. **Clear component separation** `[Confirmed]` — Kafka (event backbone), ClickHouse (real-time analytics), FSx for ONTAP (payload storage), Databricks (governed lakehouse) each have distinct, non-overlapping responsibilities.
2. **Avoids S3 Access Points dependency** `[Confirmed]` — DEC-005 explicitly decouples the architecture from S3 AP limitations documented in this project's prior work (Part 2 blog, SHARED-KNOWLEDGE.md).
3. **Native S3 for Delta tables** `[Confirmed]` — DEC-001 correctly addresses the Unity Catalog limitation that only native cloud storage is supported for external locations (REF-020, REF-021, REF-022).
4. **Metadata/payload separation** `[Confirmed]` — REQ-F002 bounds Kafka message size (≤1 MB) and references payloads by URI. This is a proven pattern for manufacturing data platforms (REF-033).
5. **Exactly-once streaming semantics** `[Confirmed]` — Structured Streaming + Delta Lake provides exactly-once guarantees (REF-002, REF-004).

### Concerns

1. **ClickHouse deployment model undefined** `[Assumption]` — The architecture assumes ClickHouse is available in the same VPC but does not specify Cloud, BYOC, or self-managed. Each has different operational, cost, and integration implications.
2. **Kafka → ClickHouse ingestion pattern unspecified** `[Open Question]` — Is ingestion via Kafka Engine (built-in), ClickPipes (managed), or Kafka Connect? Each has latency and reliability trade-offs.
3. **No data reconciliation between ClickHouse and Databricks** `[Hypothesis]` — If both consume from Kafka independently, divergence is possible during failures. Whether reconciliation is needed depends on use case.
4. **Observability architecture not designed** `[Assumption]` — REQ-N003 lists metrics but does not define the observability platform (CloudWatch, Grafana, Databricks SQL Analytics, etc.).

### Required Validations

| # | Validation | Status |
|---|-----------|--------|
| 1 | Kafka → Databricks Structured Streaming write to UC-managed Delta table | Confirmed feasible (REF-001, REF-003) |
| 2 | Kafka → ClickHouse sub-5s end-to-end latency | Needs PoC measurement |
| 3 | ClickHouse → Databricks batch export (Spark connector) | Confirmed feasible (REF-010, REF-011) |
| 4 | FSx for ONTAP multiprotocol payload access from downstream systems | Confirmed (existing project validation) |
| 5 | End-to-end failure recovery with checkpointing | Needs PoC validation |

### Required Design Changes

- Specify ClickHouse deployment model (Cloud / BYOC / self-managed on EC2)
- Define Kafka → ClickHouse connector choice
- Add data reconciliation strategy or explicitly document why it is unnecessary

### Open Questions

- What is the expected event volume (events/sec) for PoC vs production?
- What is the maximum acceptable end-to-end latency from edge to ClickHouse dashboard?
- Will the PoC use Amazon MSK or MSK Serverless?
- Is Confluent Tableflow (REF-005, REF-061) a candidate to replace custom Structured Streaming?

### Production-Readiness Assessment

**PoC-Ready with gaps** — Core data flow is technically validated via references. Deployment model and operational design require specification before PoC execution.

---

## 2. Edge and Factory Fit

### Strengths

1. **MQTT + Kafka producer pattern** `[Confirmed]` — Standard IIoT pattern validated by industry references (REF-032, REF-033).
2. **Metadata/payload separation** `[Confirmed]` — REQ-F002 correctly constrains Kafka to lightweight metadata. Large payloads (images, video, quality documents) bypass Kafka and go directly to FSx for ONTAP (REQ-F003).
3. **Event schema includes payload_reference** `[Confirmed]` — REQ-F001 acceptance criteria include `payload_reference` field linking events to stored payloads.

### Concerns

1. **Edge buffering and retry not designed** `[Open Question]` — What happens when Kafka is unreachable from the factory floor? Is there a local buffer (e.g., MQTT broker with persistence, local filesystem queue)?
2. **Payload upload mechanism undefined** `[Assumption]` — REQ-F003 says payloads go to FSx for ONTAP via S3/SMB/NFS but does not specify the upload flow. Is it a direct write from edge, a gateway, or a store-and-forward pattern?
3. **Deduplication strategy absent** `[Open Question]` — At-least-once delivery (REQ-F001) means duplicates are possible. How are duplicates detected and handled in ClickHouse and Databricks?
4. **Time synchronization not addressed** `[Hypothesis]` — Manufacturing environments often have NTP drift. If event_timestamp is generated at edge, clock skew could cause ordering issues.
5. **Payload integrity verification absent** `[Open Question]` — REQ-F002 mentions checksum but does not specify when/how verification occurs after upload.

### Edge Pipeline Assumptions

| # | Assumption | Risk if Wrong |
|---|-----------|---------------|
| 1 | Edge devices can reach Kafka/MSK endpoint | Pipeline stops; no local buffering specified |
| 2 | Large files can be uploaded to FSx for ONTAP without interruption | Partial uploads corrupt payload store |
| 3 | MQTT broker handles backpressure gracefully | Message loss during Kafka outages |
| 4 | Event ordering is preserved per device | Out-of-order events in ClickHouse |

### Required Metadata Schema

The following fields are confirmed (REQ-F001, REQ-F002):

```json
{
  "event_id": "uuid",
  "timestamp": "ISO8601",
  "device_id": "string",
  "event_type": "string",
  "payload_reference": "s3://or nfs:// URI (nullable)",
  "content_type": "string",
  "payload_size_bytes": "integer",
  "checksum_sha256": "string"
}
```

**Missing fields** `[Open Question]`:
- `factory_id` / `line_id` — needed for multi-factory deployments
- `sequence_number` — needed for ordering within device
- `retry_count` — needed for deduplication

### Failure Scenarios

| Scenario | Current Design | Gap |
|----------|---------------|-----|
| Kafka unavailable | Not addressed | Need edge buffer |
| FSx for ONTAP write failure | Not addressed | Need retry + partial upload cleanup |
| Duplicate event delivery | At-least-once acknowledged | No dedup strategy |
| Network partition (edge ↔ cloud) | Not addressed | Need store-and-forward |
| Large file upload interruption | Not addressed | Need multipart with resume |

### PoC Validation Tasks

1. Simulate Kafka producer with synthetic edge events
2. Simulate large file upload to FSx for ONTAP (via S3 multipart)
3. Validate event-to-payload linkage (query Delta table, retrieve payload via URI)
4. Simulate network interruption and measure data loss
5. Measure end-to-end latency: edge event → ClickHouse query result

---

## 3. Catalog Governance

### Strengths

1. **Native S3 for Delta tables** `[Confirmed]` — DEC-001 avoids the known Unity Catalog limitation. Delta tables on native S3 are fully governed.
2. **Kafka → Structured Streaming → Delta** `[Confirmed]` — Well-supported, production-proven pattern (REF-001, REF-003, REF-007).
3. **Metadata-to-payload reference pattern** `[Confirmed]` — REQ-F006 stores payload_uri in Delta columns without requiring Databricks to access FSx for ONTAP directly.
4. **No UC external location for FSx for ONTAP** `[Confirmed]` — Correctly avoids the unsupported pattern documented in REF-020, REF-022.

### Concerns

1. **ClickHouse → Databricks integration not fully specified** `[Assumption]` — REF-010 confirms the Spark ClickHouse Connector exists, but the use case (batch export? real-time sync? aggregated summaries?) is not defined.
2. **Schema evolution strategy undefined** `[Open Question]` — REQ-F005 mentions schema evolution support but does not specify how edge schema changes propagate through Kafka → Delta.
3. **Unity Catalog permissions model not designed** `[Assumption]` — Who can read/write which tables? How are factory-specific datasets isolated within UC?
4. **Streaming table vs managed table choice not made** `[Open Question]` — Databricks supports both streaming tables and standard managed tables for streaming ingestion. Each has different checkpoint and DLT implications.

### Unity Catalog Compatibility Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| External location on native S3 | ✅ Compatible | DEC-001 |
| Managed tables for curated data | ✅ Compatible | Standard pattern |
| Storage credentials (IAM role) | ✅ Compatible | Standard pattern |
| Lineage tracking | ✅ Compatible | Automatic for managed tables |
| S3-compatible endpoint (FSx for ONTAP) | ❌ Not Used | Correctly avoided |
| Payload access from notebooks | ⚠️ Indirect | Via boto3/requests using payload_uri, not UC-governed |

### Ingestion Pattern Recommendation

**Primary path**: Kafka → Databricks Structured Streaming → Delta Lake managed tables on native S3 → Unity Catalog governance

**Secondary path** (for aggregated data): ClickHouse → Spark ClickHouse Connector → Delta Lake (batch, scheduled)

**Payload access** (when needed in notebooks): boto3 + FSx for ONTAP S3 or NFS mount via cluster init script (outside UC governance)

### Unsupported Assumption List

| # | Assumption to Avoid | Why |
|---|-------------------|-----|
| 1 | Register FSx for ONTAP as UC external location | S3-compatible endpoints not supported (REF-020) |
| 2 | Write Delta tables to FSx for ONTAP | No atomic rename, no conditional writes |
| 3 | Direct Unity Catalog governance over payload files | UC governs tables, not arbitrary file stores |
| 4 | Use S3 Access Points in UC storage credential | Session policy limitation (SHARED-KNOWLEDGE.md) |

### Governance Risk Assessment

**Low risk** — The architecture correctly separates governed data (Delta tables on S3) from unstructured payloads (FSx for ONTAP). UC governs the structured metadata layer. Payload governance requires a separate mechanism (IAM, export policies, application-level controls).

---

## 4. Storage Fit

### Strengths

1. **Clear technical positioning** `[Confirmed]` — FSx for ONTAP is positioned specifically for large unstructured payloads where multiprotocol access, Snapshot, and enterprise data protection are needed.
2. **Not over-extended** `[Confirmed]` — The architecture does NOT attempt to use FSx for ONTAP as Delta Lake storage (which would fail due to atomic rename limitations).
3. **Multiprotocol access valuable for manufacturing** `[Confirmed]` — Factory systems may write via NFS/SMB while analytics consumers read via S3 protocol. This is a property the architecture depends on.
4. **Metadata/payload pattern preserves FSx for ONTAP value** `[Confirmed]` — Payloads remain on FSx for ONTAP with full ONTAP data services (Snapshot, SnapMirror, dedup, compression) while metadata flows through Kafka/Delta.

### Concerns

1. **ONTAP S3 protocol vs S3 Access Points distinction unclear** `[Assumption]` — DEC-005 says "no S3 Access Points dependency" but does not clarify whether payloads are accessed via ONTAP native S3 protocol, NFS, or SMB by downstream consumers.
2. **Data protection strategy not detailed** `[Open Question]` — Snapshot policy, SnapMirror target, retention period, and recovery procedures are not defined.
3. **Storage sizing absent** `[Open Question]` — No estimate of payload volume (GB/TB), growth rate, or tier distribution (SSD vs capacity pool).
4. **FlexClone for PoC data isolation not mentioned** `[Hypothesis]` — FlexClone could provide instant copies of production-like payload data for PoC testing without duplicating storage.

### FSx for ONTAP Value Assessment

| Feature | Applicable to This Architecture | Justification |
|---------|:------------------------------:|---------------|
| Multiprotocol (NFS/SMB/S3) | ✅ High | Factory writes via NFS/SMB, analytics reads via S3 |
| Snapshot | ✅ High | Point-in-time payload recovery, testing |
| SnapMirror | ✅ Medium | DR for critical payload data |
| FlexClone | ✅ Medium | PoC data provisioning, dev/test isolation |
| Deduplication | ⚠️ Depends | Useful if similar payload versions exist |
| Compression | ✅ Medium | Cost reduction for large document/image payloads |
| FabricPool | ✅ Medium | Capacity pool tiering moves old payloads to a lower-cost tier automatically (the tier is managed by Amazon FSx; S3 Glacier Flexible Retrieval and S3 Glacier Deep Archive are not valid targets). To place payloads in the S3 Glacier classes, copy them to a general purpose bucket with an S3 Access Points server-side copy (sources, checked 2026-11-24: [Hub measurement note](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/s3-access-points-server-side-copy-use-cases.md) (Japanese), [NetApp](https://docs.netapp.com/us-en/ontap/fabricpool/requirements-concept.html)) |
| SnapLock | ⚠️ Depends | Only if regulatory retention is required |

### Native Amazon S3 Comparison

| Consideration | FSx for ONTAP | Native S3 |
|--------------|:-------------:|:---------:|
| Multiprotocol (NFS/SMB/S3) | ✅ | ❌ S3 only |
| Existing factory NFS/SMB integration | ✅ No change | ❌ Requires migration |
| Space-efficient snapshots | ✅ Volume-level | ⚠️ S3 Versioning (per-object, costly) |
| Instant cloning (FlexClone) | ✅ | ❌ Full copy required |
| Cross-region replication | ✅ SnapMirror | ✅ S3 Replication |
| Cost (large payload store) | ⚠️ Higher per-GB | ✅ Lower per-GB |
| Operational complexity | ⚠️ ONTAP management | ✅ Fully managed |
| Integration with analytics platforms | ⚠️ Requires S3 AP or NFS mount | ✅ Native |

### Required Storage Tests (PoC)

1. Upload 100 mixed payloads (images 5–50 MB, documents 1–10 MB) via NFS
2. Read same payloads via ONTAP S3 protocol from a Lambda function
3. Create Snapshot before and after payload batch upload
4. Restore specific file from Snapshot
5. Measure deduplication ratio on similar image sets
6. Validate payload_uri resolution from Delta table metadata

### NetApp Positioning Notes

- FSx for ONTAP adds clear value in this architecture as the payload store for large unstructured data that needs multiprotocol access
- The architecture correctly avoids over-positioning FSx for ONTAP as a Delta Lake storage layer (known limitation)
- The metadata/payload separation pattern allows FSx for ONTAP to operate in its strength zone: enterprise file services with data protection
- The architecture should explicitly document that native S3 is more cost-effective for payloads that only need S3 access — FSx for ONTAP is justified only when multiprotocol or ONTAP data services are needed

---

## 5. Confidentiality Check

### Result

### Review Checklist

| Check | Result | Notes |
|-------|--------|-------|
| Real customer names | ✅ None found | All examples use generic manufacturing terms |
| Real partner names | ✅ None found | Technology vendors (Databricks, Snowflake, ClickHouse, Confluent) are public and required for technical accuracy |
| Individual names | ✅ None found | — |
| Internal meeting names | ✅ None found | — |
| Private opportunity names | ✅ None found | — |
| Non-public business context | ✅ None found | — |
| Real factory/device names | ✅ None found | Generic terms: "edge device", "factory floor", "sensor" |
| Real data schemas | ✅ None found | All schemas are synthetic |
| Confidential diagrams | ✅ None found | — |
| Private URLs | ✅ None found | All references are public documentation |
| AWS account IDs | ✅ None found | — |
| Support case references | ✅ None found | — |

### Sensitive Terms Found

None.

### Required Redactions

None.

### Public Repository Readiness Assessment

**Ready** — All content is generic, uses public technology names only where required for accuracy, and contains no confidential information.

---

## Conclusions

### Feasibility Assessment

**Feasible, with open items** — The architecture concept is sound, technically
validated by references, and correctly avoids known limitations. The core data flow
(Kafka → ClickHouse / Databricks / FSx for ONTAP) is feasible for a PoC. The items
below need to be resolved before PoC execution.

### Required Next Actions

| Priority | Action | Owner |
|----------|--------|-------|
| Must Fix | Define ClickHouse deployment model | Architecture |
| Must Fix | Design edge buffering and failure recovery | Architecture |
| Must Fix | Specify Kafka → ClickHouse connector | Architecture |
| Should Fix | Define deduplication strategy | Architecture |
| Should Fix | Design Unity Catalog permissions model | Architecture |
| Should Fix | Define FSx for ONTAP sizing and Snapshot policy | Architecture |
| Nice to Have | Evaluate Confluent Tableflow as alternative | Research |
| Nice to Have | Design FlexClone-based PoC data provisioning | Architecture |

### Public Repository Readiness

✅ Ready — No confidentiality issues identified.

---

## Evidence Classification Summary

| Category | Count | Examples |
|----------|-------|---------|
| Confirmed | 14 | UC supports only native S3, Kafka→SS works, metadata/payload separation |
| Assumption | 6 | ClickHouse deployment model, observability platform, UC permissions |
| Hypothesis | 3 | ClickHouse/Databricks divergence, FlexClone for PoC, NTP drift |
| Open Question | 11 | Event volume, dedup strategy, edge buffering, schema evolution |
| Vendor Confirmation Required | 0 | None (all referenced capabilities are publicly documented) |
