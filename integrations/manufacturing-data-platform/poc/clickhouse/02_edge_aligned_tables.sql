-- Manufacturing Data Platform PoC — ClickHouse DDL (Edge v3 Aligned)
-- Synced from: ONTAP-Edge-to-Cloud-AI/cloud/clickhouse/ddl/
-- Sync Date: 2026-06-15
-- Schema Version: 2.0.0 (Unified Event Envelope)
--
-- This DDL aligns the Lakehouse project's ClickHouse schema with the
-- Edge-to-Cloud project's confirmed design. The Edge project owns
-- the primary DDL; this file mirrors it for Lakehouse-side validation.
--
-- Kafka Topic Design (Edge confirmed):
--   factory.events.raw     — All events (partition key: site_id-equipment_id)
--   factory.events.quality — AI analysis results
--   factory.events.anomaly — Anomaly detection
--   factory.events.dlq     — Dead Letter Queue
--
-- Replace ${KAFKA_BOOTSTRAP_SERVERS} with actual MSK/Kafka bootstrap servers
-- Replace ${KAFKA_SASL_*} with authentication parameters

-- ============================================================
-- Database
-- ============================================================
CREATE DATABASE IF NOT EXISTS factory_v3;

-- ============================================================
-- 1. kafka_events_raw — Primary event store
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.kafka_events_raw (
    event_id UUID,
    event_type LowCardinality(String),
    domain LowCardinality(String) DEFAULT 'manufacturing',
    event_category LowCardinality(String),
    source_id LowCardinality(String),
    asset_type LowCardinality(String),
    asset_id LowCardinality(String),
    site_id LowCardinality(String),
    line_id LowCardinality(String),
    equipment_id LowCardinality(String),
    sensor_id LowCardinality(String),
    timestamp DateTime64(3),
    ingest_time DateTime64(3),
    schema_version LowCardinality(String) DEFAULT '2.0.0',
    payload_uri Nullable(String),
    payload_type Nullable(LowCardinality(String)),
    content_type Nullable(LowCardinality(String)),
    checksum Nullable(String),
    size_bytes Nullable(UInt64),
    lineage_id Nullable(String),
    processing_status LowCardinality(String) DEFAULT 'pending_analysis',
    metadata String DEFAULT '{}' COMMENT 'JSON — event-type specific metadata'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (site_id, equipment_id, timestamp, event_id)
TTL timestamp + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================
-- 2. quality_events — AI analysis results
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.quality_events (
    event_id UUID,
    event_type LowCardinality(String),
    event_category LowCardinality(String),
    source_id LowCardinality(String),
    asset_type LowCardinality(String),
    asset_id LowCardinality(String),
    site_id LowCardinality(String),
    line_id LowCardinality(String),
    equipment_id LowCardinality(String),
    sensor_id LowCardinality(String),
    timestamp DateTime64(3),
    ingest_time DateTime64(3),
    schema_version LowCardinality(String) DEFAULT '2.0.0',
    payload_uri Nullable(String),
    payload_type Nullable(LowCardinality(String)),
    content_type Nullable(LowCardinality(String)),
    checksum Nullable(String),
    size_bytes Nullable(UInt64),
    lineage_id Nullable(String),
    processing_status LowCardinality(String),
    -- Quality-specific fields (extracted from metadata JSON)
    classification_result Nullable(String),
    confidence_score Nullable(Float64),
    defect_type Nullable(String),
    -- anomalies is an object array in metadata; extract type only (Edge round 2 fix)
    anomaly_types Array(LowCardinality(String)),
    model_id Nullable(String),
    model_version Nullable(String),
    metadata String DEFAULT '{}'
)
ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (site_id, equipment_id, timestamp, event_id)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================
-- 3. payload_manifest — ONTAP ↔ Event bridge
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.payload_manifest (
    payload_uri String,
    event_id UUID,
    site_id LowCardinality(String),
    equipment_id LowCardinality(String),
    asset_id LowCardinality(String),
    payload_type LowCardinality(String),
    content_type LowCardinality(String),
    checksum String,
    size_bytes UInt64,
    storage_protocol LowCardinality(String) DEFAULT 'nfs' COMMENT 'nfs | smb | s3',
    svm_name Nullable(LowCardinality(String)),
    volume_name Nullable(LowCardinality(String)),
    ontap_snapshot Nullable(String),
    registered_at DateTime64(3) DEFAULT now64(3),
    verified Boolean DEFAULT false,
    verified_at Nullable(DateTime64(3)),
    lineage_id Nullable(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(registered_at)
ORDER BY (site_id, equipment_id, registered_at, event_id)
TTL registered_at + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================
-- 4. sensor_events_rollup_1m — Pre-aggregated sensor metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.sensor_events_rollup_1m (
    site_id LowCardinality(String),
    equipment_id LowCardinality(String),
    sensor_id LowCardinality(String),
    minute DateTime,
    count_state AggregateFunction(count, UInt64),
    avg_state AggregateFunction(avg, Float64),
    min_state AggregateFunction(min, Float64),
    max_state AggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMMDD(minute)
ORDER BY (site_id, equipment_id, sensor_id, minute)
TTL minute + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================
-- 5. anomaly_events — Anomaly detection results
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.anomaly_events (
    event_id UUID,
    event_type LowCardinality(String) DEFAULT 'anomaly_event',
    source_id LowCardinality(String),
    asset_type LowCardinality(String),
    asset_id LowCardinality(String),
    site_id LowCardinality(String),
    line_id LowCardinality(String),
    equipment_id LowCardinality(String),
    sensor_id LowCardinality(String),
    timestamp DateTime64(3),
    ingest_time DateTime64(3),
    -- Anomaly-specific
    anomaly_type LowCardinality(String),
    severity LowCardinality(String) COMMENT 'low | medium | high | critical',
    anomaly_score Float64,
    expected_value Nullable(Float64),
    actual_value Nullable(Float64),
    detection_model Nullable(String),
    recommended_action Nullable(String),
    metadata String DEFAULT '{}'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (site_id, equipment_id, timestamp, event_id)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- ============================================================
-- 6. dead_letter_events — Failed event processing
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.dead_letter_events (
    received_at DateTime64(3) DEFAULT now64(3),
    source_topic LowCardinality(String),
    partition_id UInt32,
    offset UInt64,
    raw_message String,
    error_reason String,
    error_category LowCardinality(String) COMMENT 'parse_error | validation_error | routing_error',
    retry_count UInt8 DEFAULT 0,
    resolved Boolean DEFAULT false
)
ENGINE = MergeTree()
ORDER BY (received_at, source_topic)
TTL received_at + INTERVAL 30 DAY DELETE;

-- ============================================================
-- 7. training_features_export — Databricks export table
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.training_features_export (
    export_id UUID DEFAULT generateUUIDv4(),
    site_id LowCardinality(String),
    equipment_id LowCardinality(String),
    sensor_id LowCardinality(String),
    feature_window_start DateTime64(3),
    feature_window_end DateTime64(3),
    -- Aggregated features
    avg_value Float64,
    min_value Float64,
    max_value Float64,
    stddev_value Float64,
    count_readings UInt64,
    p50_value Float64,
    p95_value Float64,
    p99_value Float64,
    -- Labels (from quality events)
    quality_label Nullable(String) COMMENT 'good | defect | unknown',
    defect_type Nullable(String),
    -- Human ground-truth labels (from feedback loop, Edge round 2)
    human_label Nullable(String) COMMENT 'Operator-confirmed label',
    label_confidence Nullable(Float64) COMMENT 'Labeler confidence (0.0-1.0)',
    labeled_by Nullable(String) COMMENT 'Operator/role identifier',
    labeled_at Nullable(DateTime64(3)) COMMENT 'Label timestamp',
    -- Metadata
    export_timestamp DateTime64(3) DEFAULT now64(3),
    feature_version LowCardinality(String) DEFAULT '1.0.0',
    window_duration_seconds UInt32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(feature_window_start)
ORDER BY (site_id, equipment_id, feature_window_start, export_id)
COMMENT 'Pre-computed training features for Databricks ML pipeline. No TTL — retained for model reproducibility.';

-- ============================================================
-- 8. Kafka Table Engine — Raw event consumer
-- ============================================================
-- Error handling (Edge aligned, round 2): kafka_handle_error_mode = 'stream'
-- exposes _error / _raw_message virtual columns so parse failures can be
-- routed to dead_letter_events instead of silently dropped.
CREATE TABLE IF NOT EXISTS factory_v3.kafka_events_queue (
    raw String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = '${KAFKA_BOOTSTRAP_SERVERS}',
    kafka_topic_list = 'factory.events.raw',
    kafka_group_name = 'clickhouse-lakehouse-consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 3,
    kafka_max_block_size = 65536,
    kafka_skip_broken_messages = 10,
    kafka_poll_timeout_ms = 1000,
    kafka_handle_error_mode = 'stream';

CREATE TABLE IF NOT EXISTS factory_v3.kafka_quality_queue (
    raw String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = '${KAFKA_BOOTSTRAP_SERVERS}',
    kafka_topic_list = 'factory.events.quality',
    kafka_group_name = 'clickhouse-lakehouse-quality-consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 2,
    kafka_handle_error_mode = 'stream';

CREATE TABLE IF NOT EXISTS factory_v3.kafka_anomaly_queue (
    raw String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = '${KAFKA_BOOTSTRAP_SERVERS}',
    kafka_topic_list = 'factory.events.anomaly',
    kafka_group_name = 'clickhouse-lakehouse-anomaly-consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 1,
    kafka_handle_error_mode = 'stream';

CREATE TABLE IF NOT EXISTS factory_v3.kafka_dlq_queue (
    raw String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = '${KAFKA_BOOTSTRAP_SERVERS}',
    kafka_topic_list = 'factory.events.dlq',
    kafka_group_name = 'clickhouse-lakehouse-dlq-consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 1;

-- ============================================================
-- 9. Materialized Views (Kafka → MergeTree routing)
-- ============================================================

-- MV 1: Raw events → kafka_events_raw (only successfully parsed messages)
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_raw_events
TO factory_v3.kafka_events_raw AS
SELECT
    toUUID(JSONExtractString(raw, 'event_id')) AS event_id,
    JSONExtractString(raw, 'event_type') AS event_type,
    JSONExtractString(raw, 'domain') AS domain,
    JSONExtractString(raw, 'event_category') AS event_category,
    JSONExtractString(raw, 'source_id') AS source_id,
    JSONExtractString(raw, 'asset_type') AS asset_type,
    JSONExtractString(raw, 'asset_id') AS asset_id,
    JSONExtractString(raw, 'site_id') AS site_id,
    JSONExtractString(raw, 'line_id') AS line_id,
    JSONExtractString(raw, 'equipment_id') AS equipment_id,
    JSONExtractString(raw, 'sensor_id') AS sensor_id,
    parseDateTime64BestEffort(JSONExtractString(raw, 'timestamp')) AS timestamp,
    parseDateTime64BestEffort(JSONExtractString(raw, 'ingest_time')) AS ingest_time,
    JSONExtractString(raw, 'schema_version') AS schema_version,
    nullIf(JSONExtractString(raw, 'payload_uri'), '') AS payload_uri,
    nullIf(JSONExtractString(raw, 'payload_type'), '') AS payload_type,
    nullIf(JSONExtractString(raw, 'content_type'), '') AS content_type,
    nullIf(JSONExtractString(raw, 'checksum'), '') AS checksum,
    JSONExtractUInt(raw, 'size_bytes') AS size_bytes,
    nullIf(JSONExtractString(raw, 'lineage_id'), '') AS lineage_id,
    JSONExtractString(raw, 'processing_status') AS processing_status,
    JSONExtractRaw(raw, 'metadata') AS metadata
FROM factory_v3.kafka_events_queue
WHERE length(_error) = 0;

-- MV 1b: Parse failures → dead_letter_events (Edge aligned, round 2)
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_kafka_errors
TO factory_v3.dead_letter_events AS
SELECT
    now64(3) AS received_at,
    'factory.events.raw' AS source_topic,
    toUInt32(0) AS partition_id,
    toUInt64(0) AS offset,
    _raw_message AS raw_message,
    _error AS error_reason,
    'parse_error' AS error_category,
    toUInt8(0) AS retry_count,
    false AS resolved
FROM factory_v3.kafka_events_queue
WHERE length(_error) > 0;

-- MV 2: Payload arrival events → payload_manifest
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_payload_manifest
TO factory_v3.payload_manifest AS
SELECT
    JSONExtractString(raw, 'payload_uri') AS payload_uri,
    toUUID(JSONExtractString(raw, 'event_id')) AS event_id,
    JSONExtractString(raw, 'site_id') AS site_id,
    JSONExtractString(raw, 'equipment_id') AS equipment_id,
    JSONExtractString(raw, 'asset_id') AS asset_id,
    JSONExtractString(raw, 'payload_type') AS payload_type,
    JSONExtractString(raw, 'content_type') AS content_type,
    JSONExtractString(raw, 'checksum') AS checksum,
    JSONExtractUInt(raw, 'size_bytes') AS size_bytes,
    'nfs' AS storage_protocol,
    nullIf(JSONExtractString(raw, 'lineage_id'), '') AS lineage_id
FROM factory_v3.kafka_events_queue
WHERE JSONExtractString(raw, 'event_type') = 'payload_arrival'
  AND JSONExtractString(raw, 'payload_uri') != '';

-- MV 3: Quality events from dedicated topic
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_quality_events
TO factory_v3.quality_events AS
SELECT
    toUUID(JSONExtractString(raw, 'event_id')) AS event_id,
    JSONExtractString(raw, 'event_type') AS event_type,
    JSONExtractString(raw, 'event_category') AS event_category,
    JSONExtractString(raw, 'source_id') AS source_id,
    JSONExtractString(raw, 'asset_type') AS asset_type,
    JSONExtractString(raw, 'asset_id') AS asset_id,
    JSONExtractString(raw, 'site_id') AS site_id,
    JSONExtractString(raw, 'line_id') AS line_id,
    JSONExtractString(raw, 'equipment_id') AS equipment_id,
    JSONExtractString(raw, 'sensor_id') AS sensor_id,
    parseDateTime64BestEffort(JSONExtractString(raw, 'timestamp')) AS timestamp,
    parseDateTime64BestEffort(JSONExtractString(raw, 'ingest_time')) AS ingest_time,
    JSONExtractString(raw, 'schema_version') AS schema_version,
    nullIf(JSONExtractString(raw, 'payload_uri'), '') AS payload_uri,
    nullIf(JSONExtractString(raw, 'payload_type'), '') AS payload_type,
    nullIf(JSONExtractString(raw, 'content_type'), '') AS content_type,
    nullIf(JSONExtractString(raw, 'checksum'), '') AS checksum,
    JSONExtractUInt(raw, 'size_bytes') AS size_bytes,
    nullIf(JSONExtractString(raw, 'lineage_id'), '') AS lineage_id,
    JSONExtractString(raw, 'processing_status') AS processing_status,
    nullIf(JSONExtractString(raw, 'metadata.classification_result'), '') AS classification_result,
    JSONExtractFloat(raw, 'metadata.confidence_score') AS confidence_score,
    nullIf(JSONExtractString(raw, 'metadata.defect_type'), '') AS defect_type,
    -- anomalies is an object array: [{ "type": "...", "score": ... }, ...]
    -- Extract the 'type' field of each element. Direct assignment of the raw
    -- object array to Array(LowCardinality(String)) fails with a type mismatch,
    -- so arrayMap over JSONExtractArrayRaw is required (Edge round 2 fix).
    arrayMap(
        x -> JSONExtractString(x, 'type'),
        JSONExtractArrayRaw(JSONExtractRaw(raw, 'metadata'), 'anomalies')
    ) AS anomaly_types,
    nullIf(JSONExtractString(raw, 'metadata.model_id'), '') AS model_id,
    nullIf(JSONExtractString(raw, 'metadata.model_version'), '') AS model_version,
    JSONExtractRaw(raw, 'metadata') AS metadata
FROM factory_v3.kafka_quality_queue
WHERE length(_error) = 0;

-- MV 4: Anomaly events from dedicated topic
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_anomaly_events
TO factory_v3.anomaly_events AS
SELECT
    toUUID(JSONExtractString(raw, 'event_id')) AS event_id,
    JSONExtractString(raw, 'event_type') AS event_type,
    JSONExtractString(raw, 'source_id') AS source_id,
    JSONExtractString(raw, 'asset_type') AS asset_type,
    JSONExtractString(raw, 'asset_id') AS asset_id,
    JSONExtractString(raw, 'site_id') AS site_id,
    JSONExtractString(raw, 'line_id') AS line_id,
    JSONExtractString(raw, 'equipment_id') AS equipment_id,
    JSONExtractString(raw, 'sensor_id') AS sensor_id,
    parseDateTime64BestEffort(JSONExtractString(raw, 'timestamp')) AS timestamp,
    parseDateTime64BestEffort(JSONExtractString(raw, 'ingest_time')) AS ingest_time,
    JSONExtractString(raw, 'metadata.anomaly_type') AS anomaly_type,
    JSONExtractString(raw, 'metadata.severity') AS severity,
    JSONExtractFloat(raw, 'metadata.anomaly_score') AS anomaly_score,
    JSONExtractFloat(raw, 'metadata.expected_value') AS expected_value,
    JSONExtractFloat(raw, 'metadata.actual_value') AS actual_value,
    nullIf(JSONExtractString(raw, 'metadata.detection_model'), '') AS detection_model,
    nullIf(JSONExtractString(raw, 'metadata.recommended_action'), '') AS recommended_action,
    JSONExtractRaw(raw, 'metadata') AS metadata
FROM factory_v3.kafka_anomaly_queue;

-- MV 5: Dead letter events
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_dead_letter
TO factory_v3.dead_letter_events AS
SELECT
    now64(3) AS received_at,
    JSONExtractString(raw, '_source_topic') AS source_topic,
    JSONExtractUInt(raw, '_partition_id') AS partition_id,
    JSONExtractUInt(raw, '_offset') AS offset,
    raw AS raw_message,
    JSONExtractString(raw, '_error_reason') AS error_reason,
    JSONExtractString(raw, '_error_category') AS error_category,
    toUInt8(JSONExtractUInt(raw, '_retry_count')) AS retry_count,
    false AS resolved
FROM factory_v3.kafka_dlq_queue;

-- ============================================================
-- 10. Sensor rollup materialized view (from raw events)
-- ============================================================
-- Note: This MV aggregates sensor_event types from kafka_events_raw into 1-minute buckets
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_sensor_rollup_1m
TO factory_v3.sensor_events_rollup_1m AS
SELECT
    site_id,
    equipment_id,
    sensor_id,
    toStartOfMinute(timestamp) AS minute,
    countState() AS count_state,
    avgState(JSONExtractFloat(metadata, 'value')) AS avg_state,
    minState(JSONExtractFloat(metadata, 'value')) AS min_state,
    maxState(JSONExtractFloat(metadata, 'value')) AS max_state
FROM factory_v3.kafka_events_raw
WHERE event_type = 'sensor_event'
GROUP BY site_id, equipment_id, sensor_id, minute;

-- ============================================================
-- 11. feedback_events — Human ground-truth labels (Edge round 2)
-- Mirror of Edge cloud/clickhouse/ddl/010_feedback_events.sql
-- Path: operator → feedback_recorder Lambda → Kafka (feedback_event)
--       → ClickHouse (feedback_events) → training_features
-- ============================================================
CREATE TABLE IF NOT EXISTS factory_v3.feedback_events (
    event_id UUID,
    event_type LowCardinality(String) DEFAULT 'feedback_event',
    target_event_id UUID COMMENT 'The quality/anomaly event this feedback corrects',
    site_id LowCardinality(String),
    equipment_id LowCardinality(String),
    asset_id LowCardinality(String),
    timestamp DateTime64(3),
    ingest_time DateTime64(3),
    -- Feedback content
    human_label String COMMENT 'Operator-confirmed ground truth (good | defect | ...)',
    label_confidence Nullable(Float64) COMMENT 'Labeler confidence (0.0-1.0)',
    defect_type Nullable(String),
    labeled_by String COMMENT 'Operator/role identifier',
    labeled_at DateTime64(3),
    correction_reason Nullable(String) COMMENT 'Why the AI result was corrected',
    original_ai_label Nullable(String) COMMENT 'AI prediction being corrected',
    is_synthetic Boolean DEFAULT false COMMENT 'Governance: synthetic data flag',
    metadata String DEFAULT '{}'
)
ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (target_event_id)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- MV: raw events → feedback_events (event_type = 'feedback_event')
CREATE MATERIALIZED VIEW IF NOT EXISTS factory_v3.mv_raw_to_feedback
TO factory_v3.feedback_events AS
SELECT
    toUUID(JSONExtractString(raw, 'event_id')) AS event_id,
    'feedback_event' AS event_type,
    toUUID(JSONExtractString(raw, 'metadata.target_event_id')) AS target_event_id,
    JSONExtractString(raw, 'site_id') AS site_id,
    JSONExtractString(raw, 'equipment_id') AS equipment_id,
    JSONExtractString(raw, 'asset_id') AS asset_id,
    parseDateTime64BestEffort(JSONExtractString(raw, 'timestamp')) AS timestamp,
    parseDateTime64BestEffort(JSONExtractString(raw, 'ingest_time')) AS ingest_time,
    JSONExtractString(raw, 'metadata.human_label') AS human_label,
    JSONExtractFloat(raw, 'metadata.label_confidence') AS label_confidence,
    nullIf(JSONExtractString(raw, 'metadata.defect_type'), '') AS defect_type,
    JSONExtractString(raw, 'metadata.labeled_by') AS labeled_by,
    parseDateTime64BestEffort(JSONExtractString(raw, 'metadata.labeled_at')) AS labeled_at,
    nullIf(JSONExtractString(raw, 'metadata.correction_reason'), '') AS correction_reason,
    nullIf(JSONExtractString(raw, 'metadata.original_ai_label'), '') AS original_ai_label,
    JSONExtractBool(raw, '_synthetic') AS is_synthetic,
    JSONExtractRaw(raw, 'metadata') AS metadata
FROM factory_v3.kafka_events_queue
WHERE length(_error) = 0
  AND JSONExtractString(raw, 'event_type') = 'feedback_event';
