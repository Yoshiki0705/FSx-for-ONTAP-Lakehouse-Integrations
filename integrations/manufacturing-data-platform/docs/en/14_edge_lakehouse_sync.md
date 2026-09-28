# 14. Edge-to-Cloud ↔ Lakehouse Project Synchronization

**Sync Date**: 2026-06-15
**Edge Repository**: [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI)
**Lakehouse Repository**: [FSx-for-ONTAP-Lakehouse-Integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations)

---

## 1. Synchronized Design Decisions

The following design decisions confirmed in the Edge-to-Cloud project have been reflected in the Lakehouse project.

### 1.1 Unified Event Schema v2.0.0

Common envelope published from edge devices to Kafka. Both projects treat this schema as the source of truth.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_id | UUID v4 | ✅ | Unique event identifier |
| event_type | string | ✅ | payload_arrival, sensor_event, quality_event, anomaly_event, telemetry_event |
| domain | string | - | Fixed: manufacturing |
| event_category | string | - | quality_inspection, environmental_monitoring, equipment_telemetry, storage_health |
| source_id | string | ✅ | Edge device ID (e.g., rpi5-001) |
| asset_type | string | - | 3d_printer, storage_system, sensor_array |
| asset_id | string | - | Individual asset ID |
| site_id | string | ✅ | Site ID (e.g., lab-tokyo) |
| line_id | string | - | Production line ID |
| equipment_id | string | - | Equipment ID |
| sensor_id | string | - | Sensor ID |
| timestamp | ISO 8601 | ✅ | Event occurrence time |
| ingest_time | ISO 8601 | - | Kafka publish time |
| schema_version | string | - | Fixed: 2.0.0 |
| payload_uri | string | - | nfs://svm/vol/path (or null) |
| payload_type | string | - | image, csv, json, null |
| content_type | string | - | MIME type |
| checksum | string | - | sha256:\<hex\> |
| size_bytes | int | - | Payload size |
| lineage_id | string | - | Session/batch tracking ID |
| processing_status | string | - | pending_analysis, completed, failed |
| metadata | object | - | Event-type specific metadata |

### 1.2 Kafka Topic Design

| Topic | Partition Key | Purpose |
|-------|--------------|---------|
| factory.events.raw | site_id-equipment_id | All events (primary) |
| factory.events.quality | site_id-equipment_id | AI analysis results |
| factory.events.anomaly | site_id-equipment_id | Anomaly detection |
| factory.events.dlq | - | Dead Letter Queue |

### 1.3 ClickHouse Table Design (Edge DDL is authoritative)

| Table | Engine | TTL | Role |
|-------|--------|-----|------|
| kafka_events_raw | MergeTree | 30d | All events raw storage |
| quality_events | ReplacingMergeTree | 365d | AI analysis results |
| payload_manifest | MergeTree | 365d | ONTAP ↔ event bridge |
| sensor_events_rollup_1m | AggregatingMergeTree | 90d | 1-minute aggregated metrics |
| anomaly_events | MergeTree | 365d | Anomaly detection results |
| dead_letter_events | MergeTree | 30d | Failed event processing |
| training_features_export | MergeTree | None | Databricks export target |

### 1.4 Databricks Integration Paths

| Path | Data Type | Method | Lakehouse Implementation |
|------|-----------|--------|--------------------------|
| A | Kafka events → Bronze | Spark Structured Streaming (DLT) | `04_kafka_to_bronze_dlt.py` |
| B | ClickHouse aggregated features → Silver/Gold | Parquet Export → ONTAP S3 → DataSync → S3 → UC | `05_training_features_import.py` |
| C | ONTAP NFS raw images/CSV → Bronze | DataSync → S3 → Auto Loader | (planned) |

### 1.5 Unity Catalog Design

```
manufacturing_poc (catalog)
├── bronze
│   ├── kafka_events           ← Path A: Kafka Structured Streaming
│   ├── sensor_events          ← Extracted from kafka_events
│   ├── quality_events         ← Extracted from kafka_events
│   ├── payload_manifest       ← Generated from payload_arrival events
│   └── raw_images             ← Path C: Auto Loader
├── silver
│   ├── training_features      ← Path B: ClickHouse export import
│   ├── quality_trends         ← Aggregated from bronze.quality_events
│   └── equipment_health       ← Derived from bronze.sensor_events + anomaly
├── gold
│   ├── training_dataset       ← ML training dataset
│   ├── quality_summary        ← Dashboard aggregates
│   └── predictive_maintenance ← Predictive maintenance results
└── ml
    └── print_features         ← Feature Store registered table
```

---

## 2. v1 → v2 Difference Summary

| Item | v1 (Old Lakehouse) | v2 (Edge aligned) |
|------|-------------------|-------------------|
| Kafka topics | Individual (sensor-data, quality-events, system-alerts) | Unified (events.raw) + category topics |
| ClickHouse DB | factory | factory_v3 |
| UC schemas | factory_alpha / factory_beta (per-site) | bronze / silver / gold / ml (medallion) |
| Event schema | Flat, per-type | Unified envelope v2.0.0 |
| Payload linkage | payload_reference (String) | payload_manifest table |
| Feature export | None | training_features_export + import pipeline |
| DLT | None | 04_kafka_to_bronze_dlt.py |

---

## 3. Sync Confirmation Items and Status

### ✅ Item 1: ClickHouse Table Design Differences

**Result**: Created `02_edge_aligned_tables.sql` on Lakehouse side using Edge DDL as authoritative source. v1 `01_setup_tables.sql` retained as reference but deprecated for new deployments.

### ✅ Item 2: Kafka → Databricks Structured Streaming

**Result**: Created `04_kafka_to_bronze_dlt.py` as DLT pipeline template.

### ✅ Item 3: training_features_export Automation

**Result**: Created `05_training_features_import.py` for Path B import.

### ✅ Item 4: Unity Catalog Shared Assumption

**Conclusion**: `manufacturing_poc` catalog is shared between both projects.

### 🔲 Item 5: Shared Test Data

**Status**: Edge side ready (21 sample events), Lakehouse import pending

**Edge**: `tests/sample_events/` — 21 sample event JSON files created
**Lakehouse**: `poc/shared-test-data/samples/` — import pending

**Import procedure**:
```bash
EDGE_REPO="../ONTAP-Edge-to-Cloud-AI"
cp ${EDGE_REPO}/tests/sample_events/*.json \
   integrations/manufacturing-data-platform/poc/shared-test-data/samples/
```

---

## 4. File Mapping

| Edge Path | Lakehouse Path | Sync Method |
|-----------|---------------|-------------|
| `cloud/clickhouse/ddl/` | `poc/clickhouse/02_edge_aligned_tables.sql` | Manual (Edge authoritative) |
| `docs/*/databricks-integration.md` | `docs/ja/14_edge_lakehouse_sync.md` | This document |
| `docs/*/data-schema-design.md` | `poc/databricks/03_unity_catalog_v2.sql` | Reflected as UC DDL |
| `synthetic_events.py` | `poc/shared-test-data/` | TBD |

> **Bidirectional navigation (resolved on both repos' `main`)**: The Edge `docs/{ja,en}/databricks-integration.md` now back-links to this document, and this repo links to the Edge project from both the root README and the manufacturing-data-platform README. The `databricks-integration.md` ↔ `14_edge_lakehouse_sync.md` mapping above therefore resolves in both directions on GitHub.

---

## 5. Responsibility Matrix

**Confirmed**: 2026-06-16 (Edge project confirmed)

| Responsibility | Edge Project | Lakehouse Project |
|---------------|-------------|-------------------|
| Event generation (Pi → Kafka) | ✅ `simple_capture.py` + `event_schema.py` | — |
| Kafka Topic design | ✅ Finalized (factory.events.raw etc.) | ✅ Synced |
| ClickHouse DDL | ✅ `cloud/clickhouse/ddl/` (authoritative) | ✅ Mirror (`02_edge_aligned_tables.sql`) |
| ClickHouse → Parquet Export | ✅ `export_training_features.sh` | ✅ Import (`05_training_features_import.py`) |
| Databricks DLT | ✅ Design document | ✅ Implementation (`04_kafka_to_bronze_dlt.py`) |
| Unity Catalog design | ✅ Design document | ✅ DDL (`03_unity_catalog_v2.sql`) |
| Synthetic test data | ✅ `synthetic_events.py` | ✅ Shared (`poc/shared-test-data/`) |

---

## 6. Remaining Tasks

**Software, design, schema alignment, and cross-project sync are all complete** (2026-06-16).
Only physical environment setup and post-data-arrival execution remain.

| # | Task | Owner | Trigger | Status |
|---|------|-------|---------|--------|
| 1 | Test data import | Lakehouse | Ready after clone | Ready |
| 2 | DataSync configuration | Lakehouse | After ONTAP S3 bucket creation | Waiting |
| 3 | M1-M6 measurement (run 06/07) | Lakehouse | After Bronze data arrival | Waiting |
| 4 | Instaclustr deployment | Edge (physical) | After PoC document approval | Waiting |
| 5 | Phase 1 (Pi → ONTAP) | Edge (physical) | After physical setup complete | Waiting |

---

## 7. Improvements Carried Over from the Edge Project

**Applied**: 2026-06-16

The Edge project revised its design against the
[design concern checklist](08_design_concern_checklist.md). The following revisions
are reflected on the Lakehouse side.

### 7.1 ClickHouse Mirror DDL (`02_edge_aligned_tables.sql`)

| Improvement | Change |
|-------------|--------|
| quality_events MV type fix | `anomalies` is an object array. Added `anomaly_types Array(LowCardinality(String))` extracted via `arrayMap(x -> JSONExtractString(x, 'type'), JSONExtractArrayRaw(...))`. Avoids the direct-assignment type mismatch bug |
| Kafka error handling | Set `kafka_handle_error_mode = 'stream'` on all Kafka Engines. Added `mv_kafka_errors` MV to route `length(_error) > 0` messages to `dead_letter_events`. Normal messages filtered with `WHERE length(_error) = 0` |
| feedback_events table | Added in section 11. `ReplacingMergeTree(ingest_time)`, `ORDER BY (target_event_id)`. `mv_raw_to_feedback` MV extracts `event_type='feedback_event'`. Preserves `is_synthetic` flag |
| training_features_export | Added `human_label` / `label_confidence` / `labeled_by` / `labeled_at` columns |

### 7.2 Databricks Integration

| File | Change |
|------|--------|
| `03_unity_catalog_v2.sql` | Added `bronze.feedback_events` table. Added 4 human_label columns to `silver.training_features` |
| `04_kafka_to_bronze_dlt.py` | Added `feedback_event → bronze.feedback_events` DLT route. Preserves `is_synthetic` flag |
| `05_training_features_import.py` | Added 4 human_label columns to import schema |
| `06_gold_training_dataset.py` | **New**. Joins human_label to build labeled Gold dataset. Label priority: human > AI > unknown. Deterministic train/validation/test split |
| `07_success_metrics_gold.sql` | **New**. M1-M6 Go/No-Go metric queries for Databricks Gold dashboard. M2 (accuracy/precision/recall) computed via feedback_events JOIN |

### 7.3 Feedback Loop (Complete Across Both Projects)

```
operator
  → feedback_recorder Lambda (publishes via KAFKA_REST_PROXY_URL)
  → Kafka (factory.events.raw, event_type=feedback_event)
  → ClickHouse feedback_events (mv_raw_to_feedback)
  → training_features_export (human_label)          [Path B → Lakehouse]
  → Databricks bronze.feedback_events (DLT)          [Path A → Lakehouse]
  → Databricks gold.training_dataset (human label JOIN)
```

**Note (Edge design)**: The Lambda cannot connect directly to on-premises Kafka, so it publishes via REST Proxy. When REST Proxy is unavailable, it stores to S3 only and ClickHouse batch-imports from S3.

### 7.4 Governance

- Synthetic test data carries the `_synthetic: true` flag (required by the [design concern checklist](08_design_concern_checklist.md))
- The `_synthetic` flag lives at the **top level** of the event envelope. ClickHouse reads it via `JSONExtractBool(raw, '_synthetic')`; the Databricks DLT carries it through `bronze.kafka_events.is_synthetic` (top-level field in the envelope schema, defaulting to `false` when absent) and into `bronze.feedback_events.is_synthetic`. Both paths are consistent.
- The `feedback_events.is_synthetic` column (ClickHouse / Bronze) allows excluding synthetic data from production accuracy metrics

---

## 8. Change Log

| Date | Change |
|------|--------|
| 2026-06-15 | Initial version. Edge v3 design reflected in Lakehouse project. |
| 2026-06-16 | Edge sync confirmation received. Added responsibility matrix. Reflected export_training_features.sh. |
| 2026-06-16 | Edge final sync complete. All items confirmed aligned. Added test data import procedure (21 files). |
| 2026-06-16 | Improvements carried over from the Edge project: feedback_events, human_label, Kafka error handling, quality_events type fix, Gold training_dataset generation, M1-M6 success metrics (see section 7). |
| 2026-06-16 | Follow-up: aligned `_synthetic` governance flag to the top-level envelope across ClickHouse and Databricks DLT (bronze.kafka_events.is_synthetic). |
| 2026-06-16 | Noted bidirectional Edge ↔ Lakehouse navigation now resolves on both repos' main (databricks-integration.md back-link). |
